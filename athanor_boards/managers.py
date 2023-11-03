import re
import math
from django.db import IntegrityError, transaction
from django.db import models
from django.db.models.functions import Concat
from django.conf import settings
from evennia.typeclasses.managers import TypeclassManager, TypedObjectManager
from evennia.utils import class_from_module
from evennia.locks.lockhandler import LockException
from athanor.utils import (
    Operation,
    validate_name,
    online_accounts,
    online_characters,
    staff_alert,
    utcnow,
)

_RE_ABBREV = re.compile(r"^[a-zA-Z]{1,10}$")

_RE_BOARDID = re.compile(r"(?P<collection>[a-zA-Z]{1,10})?(?P<order>\d+)")


class BoardDBManager(TypedObjectManager):
    system_name = "BBS"

    def with_board_id(self):
        return self.annotate(
            board_id=Concat(
                models.F("db_collection__db_abbreviation"),
                models.F("db_order"),
                output_field=models.CharField(),
            )
        )

    def find_board(
        self, operation: Operation, field: str = "board_id"
    ) -> tuple["BoardDB", int]:
        if (input := operation.kwargs.get(field, None)) is None:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a Board ID.")

        if "." in input:
            board_id, page_number = input.split(".", 1)
            try:
                page_number = int(page_number)
            except ValueError as err:
                operation.status = operation.st.HTTP_400_BAD_REQUEST
                raise operation.ex("You must provide a valid page number.")
        else:
            board_id = input
            page_number = -1

        if not (
            found := self.with_board_id()
            .filter(board_id=board_id)
            .exclude(db_deleted=True)
            .exclude(db_collection__db_deleted=True)
            .first()
        ):
            operation.status = operation.st.HTTP_404_NOT_FOUND
            raise operation.ex(f"No board found with ID {input}.")
        return found, page_number

    def op_config_list(self, operation: Operation):
        board, page = self.find_board(operation)

        if not board.access(operation.actor, "admin"):
            operation.status = operation.st.HTTP_401_UNAUTHORIZED
            raise operation.ex("You do not have permission to configure this board.")

        config = board.options.all(return_objs=True)

        out = list()
        for op in config:
            out.append(
                {
                    "name": op.key,
                    "description": op.description,
                    "type": op.__class__.__name__,
                    "value": op.display(),
                }
            )

        operation.results = {"success": True, "board": board.serialize(), "config": out}

    def op_config_set(self, operation: Operation):
        board, page = self.find_board(operation)

        if not board.access(operation.actor, "admin"):
            operation.status = operation.st.HTTP_401_UNAUTHORIZED
            raise operation.ex("You do not have permission to configure this board.")

        try:
            result = board.options.set(
                operation.kwargs.get("key", None), operation.kwargs.get("value", None)
            )
        except ValueError as err:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex(str(err))

        message = f"Board '{board.board_label}: {board.db_key}' config '{result.key}' set to '{result.display()}'."
        operation.results = {
            "success": True,
            "board": board.serialize(),
            "message": message,
        }

    def _validate_name(self, operation: Operation):
        if not (
            name := validate_name(
                operation.kwargs.get("name", None), thing_type="Board"
            )
        ):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a name for the board.")
        return name

    def op_create(self, operation: Operation):
        col_class = class_from_module(settings.BASE_BOARD_COLLECTION_TYPECLASS)
        collection = col_class.objects.find_collection(operation)

        caller = operation.character or operation.user

        if not collection.access(caller, "admin"):
            operation.status = operation.st.HTTP_401_UNAUTHORIZED
            raise operation.ex(
                "You do not have permission to create a board in this collection."
            )

        if (order := operation.kwargs.get("order", None)) is None:
            result = collection.boards.aggregate(models.Max("db_order"))
            max_result = result["db_order__max"]
            order = max_result + 1 if max_result is not None else 1
        else:
            try:
                order = int(order)
            except ValueError:
                operation.status = operation.st.HTTP_400_BAD_REQUEST
                raise operation.ex("You must provide a valid order number.")
            if collection.boards.filter(db_order=order).first():
                operation.status = operation.st.HTTP_400_BAD_REQUEST
                raise operation.ex(f"A board with order {order} already exists.")

        name = self._validate_name(operation)

        if self.model.objects.filter(db_key__iexact=name).first():
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex(f"A board with the name '{name}' already exists.")

        board = self.create(db_collection=collection, db_order=order, db_key=name)
        operation.status = operation.st.HTTP_201_CREATED
        message = f"Board '{board.board_label}: {board.db_key}' created."
        operation.results = {
            "success": True,
            "created": board.serialize(),
            "message": message,
        }
        staff_alert(message, senders=operation.user)

    def op_rename(self, operation: Operation):
        board, page = self.find_board(operation)

        if not board.access(operation.actor, "admin"):
            operation.status = operation.st.HTTP_401_UNAUTHORIZED
            raise operation.ex("You do not have permission to rename this board.")

        name = self._validate_name(operation)

        if self.filter(db_key__iexact=name).exclude(id=board).first():
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex(f"A board with the name '{name}' already exists.")

        old_name = board.db_key
        board.key = name
        message = f"Board '{board.board_label}: {old_name}' renamed to '{board.board_label}: {board.db_key}'."
        operation.results = {"success": True, "renamed": name, "message": message}
        staff_alert(message, senders=operation.user)

    def op_list(self, operation: Operation):
        output = list()

        for board in self.all():
            if not (
                board.collection.access(operation.actor, "read")
                or board.access(operation.actor, "admin")
            ):
                continue
            if not (
                board.access(operation.actor, "read")
                or board.access(operation.actor, "admin")
            ):
                continue

            out = board.serialize()
            post_count = board.posts.count()
            out["post_count"] = post_count
            out["unread_count"] = (
                post_count - board.posts.filter(read__id=operation.user.id).count()
            )
            out["read_perm"] = board.access(operation.actor, "read")
            out["post_perm"] = board.access(operation.actor, "post")
            out["admin_perm"] = board.access(operation.actor, "admin")
            output.append(out)

        operation.status = operation.st.HTTP_200_OK
        operation.results = {"success": True, "boards": output}

    def op_order(self, operation: Operation):
        board, page = self.find_board(operation)

        if not board.access(operation.actor, "admin"):
            operation.status = operation.st.HTTP_401_UNAUTHORIZED
            raise operation.ex("You do not have permission to re-order this board.")

        if (order := operation.kwargs.get("order", None)) is None:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide an order number.")

        try:
            order = int(order)
        except ValueError:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a valid order number.")

        if board.db_order == order:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("Board is already in that order.")

        if board.collection.boards.filter(db_order=order).first():
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex(f"A board with order {order} already exists.")

        old_order = board.db_order
        board.db_order = order
        message = f"Board '{board.board_label}: {board.db_key}' re-ordered from {old_order} to {order}."
        operation.results = {"success": True, "reordered": order, "message": message}

    def op_lock(self, operation: Operation):
        board, page = self.find_board(operation)

        if not board.access(operation.actor, "admin"):
            operation.status = operation.st.HTTP_401_UNAUTHORIZED
            raise operation.ex("You do not have permission to lock this board.")

        if not (lock := operation.kwargs.get("lockstring", None)):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a lockstring.")

        try:
            ok = board.locks.add(lock)
        except LockException as err:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex(str(err))

        if not ok:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("Lockstring not added.")

        message = f"Board '{board.board_label}: {board.db_key}' locked with '{lock}'."
        operation.results = {"success": True, "locked": lock, "message": message}

    def op_delete(self, operation: Operation):
        board, page = self.find_board(operation)

        if not board.collection.access(operation.actor, "admin"):
            operation.status = operation.st.HTTP_401_UNAUTHORIZED
            raise operation.ex("You do not have permission to delete this board.")

        validate = operation.kwargs.get("validate", "")

        if board.posts.count():
            if validate.lower() != board.db_key.lower():
                operation.status = operation.st.HTTP_400_BAD_REQUEST
                raise operation.ex(
                    f"Board '{board.board_label}: {board.db_key}' still has posts.  You must provide the board name to confirm deletion."
                )

        board.deleted = True

        message = f"Board '{board.board_label}: {board.db_key}' deleted."
        operation.results = {
            "success": True,
            "board": board.serialize(),
            "message": message,
        }
        staff_alert(message, senders=operation.user)


class CollectionDBManager(TypedObjectManager):
    system_name = "BBS"

    def prepare_kwargs(self, operation: Operation):
        pass

    def _validate_abbreviation(self, operation: Operation):
        abbreviation = operation.kwargs.get("abbreviation", None)
        if abbreviation != "" and not (
            abbreviation := validate_name(
                operation.kwargs.get("abbreviation", None),
                thing_type="Board Collection",
                matcher=_RE_ABBREV,
            )
        ):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex(
                "You must provide an abbreviation for the board collection."
            )
        return abbreviation

    def _validate_name(self, operation: Operation):
        if not (
            name := validate_name(
                operation.kwargs.get("name", None), thing_type="Board Collection"
            )
        ):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a name for the board collection.")
        return name

    def op_create(self, operation: Operation):
        if not operation.actor.locks.check_lockstring(
            self, settings.BOARD_PERMISSIONS_ADMIN_OVERRIDE
        ):
            operation.status = operation.st.HTTP_401_UNAUTHORIZED
            raise operation.ex(
                "You do not have permission to create a board collection."
            )

        name = self._validate_name(operation)

        if self.model.objects.filter(db_key__iexact=name).first():
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex(
                f"A board collection with the name '{name}' already exists."
            )

        abbreviation = self._validate_abbreviation(operation)

        if self.model.objects.filter(db_abbreviation__iexact=abbreviation).first():
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex(
                f"A board collection with the abbreviation '{abbreviation}' already exists."
            )

        collection = self.create(db_key=name, db_abbreviation=abbreviation)
        operation.status = operation.st.HTTP_201_CREATED
        message = f"Board Collection '{collection.db_abbreviation}: {collection.db_key}' created."
        operation.results = {
            "success": True,
            "created": collection.serialize(),
            "message": message,
        }
        staff_alert(message, senders=operation.user)

    def op_delete(self, operation: Operation):
        if not operation.actor.locks.check_lockstring(
            self, settings.BOARD_PERMISSIONS_ADMIN_OVERRIDE
        ):
            operation.status = operation.st.HTTP_401_UNAUTHORIZED
            raise operation.ex(
                "You do not have permission to delete a board collection."
            )

        collection = self.find_collection(operation)

        validate = operation.kwargs.get("validate", "")

        if collection.boards.count():
            if validate.lower() != collection.db_key.lower():
                operation.status = operation.st.HTTP_400_BAD_REQUEST
                raise operation.ex(
                    f"Board Collection '{collection.db_abbreviation}: {collection.db_key}' still has boards.  You must provide the collection name to confirm deletion."
                )

        collection.deleted = True

        message = f"Board Collection '{collection.db_abbreviation}: {collection.db_key}' deleted."
        operation.results = {
            "success": True,
            "collection": collection.serialize(),
            "message": message,
        }
        staff_alert(message, senders=operation.user)

    def op_config_list(self, operation: Operation):
        collection = self.find_collection(operation)

        if not collection.access(operation.actor, "admin"):
            operation.status = operation.st.HTTP_401_UNAUTHORIZED
            raise operation.ex(
                "You do not have permission to configure this board collection."
            )

        config = collection.options.all(return_objs=True)

        out = list()
        for op in config:
            out.append(
                {
                    "name": op.key,
                    "description": op.description,
                    "type": op.__class__.__name__,
                    "value": op.display(),
                }
            )

        operation.results = {
            "success": True,
            "collection": collection.serialize(),
            "config": out,
        }

    def op_config_set(self, operation: Operation):
        collection = self.find_collection(operation)

        if not collection.access(operation.actor, "admin"):
            operation.status = operation.st.HTTP_401_UNAUTHORIZED
            raise operation.ex(
                "You do not have permission to configure this board collection."
            )

        try:
            result = collection.options.set(
                operation.kwargs.get("key", None), operation.kwargs.get("value", None)
            )
        except ValueError as err:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex(str(err))

        message = f"Board Collection '{collection.db_abbreviation}: {collection.db_key}' config '{result.key}' set to '{result.display()}'."
        operation.results = {
            "success": True,
            "collection": collection.serialize(),
            "message": message,
        }

    def find_collection(self, operation: Operation) -> "BoardCollectionDB":
        if (input := operation.kwargs.get("collection_id", None)) is None:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a Board Collection ID.")

        collection_id = input.strip()

        if isinstance(collection_id, str) and collection_id.isnumeric():
            collection_id = int(collection_id)

        start = self.exclude(db_deleted=True)

        if isinstance(collection_id, int):
            if not (found := start.filter(id=collection_id).first()):
                operation.status = operation.st.HTTP_404_NOT_FOUND
                raise operation.ex(
                    f"No board collection found with ID {collection_id}."
                )
            return found

        if found := start.filter(db_key__iexact=collection_id).first():
            return found
        elif found := start.filter(db_abbreviation__iexact=collection_id).first():
            return found

        operation.status = operation.st.HTTP_404_NOT_FOUND
        raise operation.ex(f"No board collection found with ID {collection_id}.")

    def op_rename(self, operation: Operation):
        if not operation.actor.locks.check_lockstring(
            self, settings.BOARD_PERMISSIONS_ADMIN_OVERRIDE
        ):
            operation.status = operation.st.HTTP_401_UNAUTHORIZED
            raise operation.ex(
                "You do not have permission to rename a board collection."
            )

        collection = self.find_collection(operation)

        name = self._validate_name(operation)

        if self.filter(db_key__iexact=name).exclude(id=collection).first():
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex(
                f"A board collection with the name '{name}' already exists."
            )

        old_name = collection.db_key
        collection.key = name
        message = f"Board Collection '{collection.db_abbreviation}: {old_name}' renamed to '{collection.db_abbreviation}: {collection.db_key}'."
        operation.results = {"success": True, "renamed": name, "message": message}
        staff_alert(message, senders=operation.user)

    def op_abbreviate(self, operation: Operation):
        if not operation.actor.locks.check_lockstring(
            self, settings.BOARD_PERMISSIONS_ADMIN_OVERRIDE
        ):
            operation.status = operation.st.HTTP_401_UNAUTHORIZED
            raise operation.ex(
                "You do not have permission to re-abbreviate a board collection."
            )

        collection = self.find_collection(operation)

        abbreviation = self._validate_abbreviation(operation)

        if (
            self.filter(db_abbreviation__iexact=abbreviation)
            .exclude(id=collection)
            .first()
        ):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex(
                f"A board collection with the abbreviation '{abbreviation}' already exists."
            )

        old_abbreviation = collection.db_abbreviation
        collection.abbreviation = abbreviation
        message = f"Board Collection '{old_abbreviation}: {collection.db_key}' re-abbreviated to '{collection.db_abbreviation}: {collection.db_key}'."
        operation.results = {
            "success": True,
            "abbreviated": abbreviation,
            "message": message,
        }
        staff_alert(message, senders=operation.user)

    def op_lock(self, operation: Operation):
        if not operation.actor.locks.check_lockstring(
            self, settings.BOARD_PERMISSIONS_ADMIN_OVERRIDE
        ):
            operation.status = operation.st.HTTP_401_UNAUTHORIZED
            raise operation.ex("You do not have permission to lock a board collection.")

        collection = self.find_collection(operation)

        if not (lock := operation.kwargs.get("lockstring", None)):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a lockstring.")

        try:
            ok = collection.locks.add(lock)
        except LockException as err:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex(str(err))

        if not ok:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("Lockstring not added.")

        message = f"Board Collection '{collection.db_abbreviation}: {collection.db_key}' locked with '{lock}'."
        operation.results = {"success": True, "locked": lock, "message": message}

    def op_list(self, operation: Operation):
        if not operation.actor.locks.check_lockstring(
            self, settings.BOARD_PERMISSIONS_ADMIN_OVERRIDE
        ):
            operation.status = operation.st.HTTP_401_UNAUTHORIZED
            raise operation.ex("You do not have permission to list board collections.")

        operation.results = {
            "success": True,
            "collections": [c.serialize() for c in self.all()],
        }


class BoardManager(BoardDBManager, TypeclassManager):
    pass


class CollectionManager(CollectionDBManager, TypeclassManager):
    system_name = "BBS"


class PostManager(models.Manager):
    system_name = "BBS"

    def prepare_kwargs(self, operation: Operation):
        pass

    def op_create(self, operation: Operation):
        c = class_from_module(settings.BASE_BOARD_TYPECLASS)

        board, page = c.objects.find_board(operation)
        if not (
            board.access(operation.actor, "post")
            or board.access(operation.actor, "admin")
        ):
            operation.status = operation.st.HTTP_401_UNAUTHORIZED
            raise operation.ex("You do not have permission to post to this board.")

        if not (subject := operation.kwargs.get("subject", "").strip()):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a subject for the post.")

        if not (body := operation.kwargs.get("body", "")):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a body for the post.")

        disguise = operation.kwargs.get("disguise", None)
        if disguise:
            disguise = disguise.strip()

        kwargs = {
            "board": board,
            "subject": subject,
            "body": body,
            "user": operation.user,
            "reply_number": 0,
        }

        if ic := board.options.get("ic"):
            if not operation.character:
                operation.status = operation.st.HTTP_400_BAD_REQUEST
                raise operation.ex("You must provide a character for the post.")
            kwargs["character"] = operation.character

        if board.options.get("disguise"):
            if not disguise:
                operation.status = operation.st.HTTP_400_BAD_REQUEST
                raise operation.ex("You must provide a disguise name for the post.")
            kwargs["disguise"] = disguise

        kwargs["number"] = board.next_post_number

        with transaction.atomic():
            post = self.create(**kwargs)
            post.read.add(operation.user)
            board.last_activity = post.date_created
            board.next_post_number += 1

        targets = online_characters() if ic else online_accounts()

        for target in targets:
            if not (board.access(target, "read") or board.access(target, "admin")):
                continue
            author = (
                post.render_author(target.account, character=target)
                if hasattr(target, "account")
                else post.render_author(target)
            )
            target.system_send(
                self.system_name,
                f"New BB Message ({board.board_label}/{post.post_number()}) posted to '{board.db_key}' by {author}: {subject}",
            )

        operation.status = operation.st.HTTP_201_CREATED
        operation.results = {
            "success": True,
            "post": post.serialize(operation.user, character=operation.character),
        }

    def with_post_id(self):
        return self.annotate(
            post_id=models.Case(
                models.When(reply_number=0, then="number"),
                default=Concat(
                    models.F("number"),
                    models.Value("."),
                    models.F("reply_number"),
                    output_field=models.CharField(),
                ),
                output_field=models.CharField(),
            )
        )

    def find_post(self, operation: Operation, board, field: str = "post_id"):
        if (input := operation.kwargs.get(field, None)) is None:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a Post ID.")

        post_number = None
        reply_number = 0

        try:
            if "." in input:
                post_number, reply_number = input.split(".", 1)
                post_number = int(post_number)
                reply_number = int(reply_number)
            else:
                post_number = int(input)
        except ValueError:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a valid Post ID.")

        if not (
            found := self.with_post_id()
            .filter(
                board=board,
                number=post_number,
                reply_number=reply_number,
                deleted=False,
            )
            .first()
        ):
            operation.status = operation.st.HTTP_404_NOT_FOUND
            raise operation.ex(f"No post found with ID {input}.")
        return found

    def op_reply(self, operation: Operation):
        c = class_from_module(settings.BASE_BOARD_TYPECLASS)

        board, page = c.objects.find_board(operation)
        if not (
            board.access(operation.actor, "post")
            or board.access(operation.actor, "admin")
        ):
            operation.status = operation.st.HTTP_401_UNAUTHORIZED
            raise operation.ex("You do not have permission to post to this board.")

        post = self.find_post(operation, board)

        if not (body := operation.kwargs.get("body", "")):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a body for the reply.")

        disguise = operation.kwargs.get("disguise", None)
        if disguise:
            disguise = disguise.strip()

        now = utcnow()
        kwargs = {
            "board": board,
            "subject": f"RE: {post.subject}",
            "body": body,
            "user": operation.user,
            "number": post.number,
            "date_created": now,
            "date_modified": now,
        }

        # get max reply_number + 1 from posts with the same board and number...
        result = self.filter(board=board, number=post.number).aggregate(
            models.Max("reply_number")
        )
        max_result = result["reply_number__max"]
        kwargs["reply_number"] = max_result + 1 if max_result is not None else 1

        if ic := board.options.get("ic"):
            if not operation.character:
                operation.status = operation.st.HTTP_400_BAD_REQUEST
                raise operation.ex("You must provide a character for the post.")
            kwargs["character"] = operation.character

        if board.options.get("disguise"):
            if not disguise:
                operation.status = operation.st.HTTP_400_BAD_REQUEST
                raise operation.ex("You must provide a disguise name for the post.")
            kwargs["disguise"] = disguise

        with transaction.atomic():
            reply = self.create(**kwargs)
            reply.read.add(operation.user)
            board.last_activity = now

        targets = online_characters() if ic else online_accounts()
        for target in targets:
            if not (board.access(target, "read") or board.access(target, "admin")):
                continue
            author = (
                reply.render_author(target.account, character=target)
                if hasattr(target, "account")
                else reply.render_author(target)
            )
            target.system_send(
                self.system_name,
                f"New BB Message ({board.board_label}/{reply.post_number()}) posted to '{board.db_key}' by {author}: {reply.subject}",
            )

        operation.status = operation.st.HTTP_201_CREATED
        operation.results = {
            "success": True,
            "post": reply.serialize(operation.user, character=operation.character),
        }

    def op_read(self, operation: Operation):
        c = class_from_module(settings.BASE_BOARD_TYPECLASS)

        board, page = c.objects.find_board(operation)
        if not (
            board.access(operation.actor, "read")
            or board.access(operation.actor, "admin")
        ):
            operation.status = operation.st.HTTP_401_UNAUTHORIZED
            raise operation.ex("You do not have permission to read from this board.")

        post = self.find_post(operation, board)
        post.read.add(operation.user)
        operation.results = {
            "success": True,
            "board": board.serialize(),
            "post": post.serialize(operation.user, character=operation.character),
        }

    def op_list(self, operation: Operation):
        c = class_from_module(settings.BASE_BOARD_TYPECLASS)

        board, page = c.objects.find_board(operation)
        if not (
            board.access(operation.actor, "read")
            or board.access(operation.actor, "admin")
        ):
            operation.status = operation.st.HTTP_401_UNAUTHORIZED
            raise operation.ex("You do not have permission to read from this board.")

        if page < 1:
            page = 1

        posts_per_page = operation.kwargs.get("posts_per_page", 50)

        count = board.posts.filter(deleted=False).count()

        pages = math.ceil(float(count) / float(posts_per_page))

        posts = reversed(
            board.posts.all().reverse()[
                posts_per_page * (page - 1) : (posts_per_page * page)
            ]
        )

        serialized = [
            post.serialize(operation.user, character=operation.character)
            for post in posts
        ]

        operation.results = {
            "success": True,
            "board": board.serialize(),
            "page": page,
            "pages": pages,
            "posts": serialized,
        }

    def op_remove(self, operation: Operation):
        c = class_from_module(settings.BASE_BOARD_TYPECLASS)

        board, page = c.objects.find_board(operation)
        if not (
            board.access(operation.actor, "post")
            or board.access(operation.actor, "admin")
        ):
            operation.status = operation.st.HTTP_401_UNAUTHORIZED
            raise operation.ex("You do not have permission to post to this board.")

        post = self.find_post(operation, board)

        if not (
            post.user == operation.user or post.character == operation.character
        ) or board.access(operation.actor, "admin"):
            operation.status = operation.st.HTTP_401_UNAUTHORIZED
            raise operation.ex("You do not have permission to remove this post.")

        post.deleted = True
        post.save()

        operation.results = {
            "success": True,
            "board": board.serialize(),
            "post": post.serialize(operation.user, character=operation.character),
        }
