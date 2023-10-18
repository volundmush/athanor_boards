import re
from django.db import IntegrityError, transaction
from django.db import models
from django.db.models.functions import Concat
from django.conf import settings
from evennia.typeclasses.managers import TypeclassManager, TypedObjectManager
from evennia.utils import class_from_module


from athanor.utils import Request, validate_name, online_accounts, online_characters, staff_alert, utcnow

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

    def find_board(self, request: Request, field: str = "board_id") -> "BoardDB":
        if (input := request.kwargs.get(field, None)) is None:
            request.status = request.st.HTTP_400_BAD_REQUEST
            raise request.ex("You must provide a Board ID.")
        if not (found := self.with_board_id().filter(board_id=input).first()):
            request.status = request.st.HTTP_404_NOT_FOUND
            raise request.ex(f"No board found with ID {input}.")
        return found

    def prepare_kwargs(self, request: Request):
        pass

    def _validate_name(self, request: Request):
        if not (
                name := validate_name(request.kwargs.get("name", None), thing_type="Board")
        ):
            request.status = request.st.HTTP_400_BAD_REQUEST
            raise request.ex("You must provide a name for the board.")
        return name

    def op_create(self, request: Request):
        col_class = class_from_module(settings.BASE_BOARD_COLLECTION_TYPECLASS)
        collection = col_class.objects.find_collection(request)

        caller = request.character or request.user

        if not collection.access(caller, "admin"):
            request.status = request.st.HTTP_401_UNAUTHORIZED
            raise request.ex(
                "You do not have permission to create a board in this collection."
            )

        if (order := request.kwargs.get("order", None)) is None:
            result = collection.boards.aggregate(models.Max("db_order"))
            max_result = result["db_order__max"]
            order = max_result + 1 if max_result is not None else 1
        else:
            try:
                order = int(order)
            except ValueError:
                request.status = request.st.HTTP_400_BAD_REQUEST
                raise request.ex("You must provide a valid order number.")
            if collection.boards.filter(db_order=order).first():
                request.status = request.st.HTTP_400_BAD_REQUEST
                raise request.ex(f"A board with order {order} already exists.")

        name = self._validate_name(request)

        if self.model.objects.filter(db_key__iexact=name).first():
            request.status = request.st.HTTP_400_BAD_REQUEST
            raise request.ex(f"A board with the name '{name}' already exists.")

        board = self.create(db_collection=collection, db_order=order, db_key=name)
        request.status = request.st.HTTP_201_CREATED
        message = f"Board '{board.board_label}: {board.db_key}' created."
        request.results = {"success": True, "created": board.serialize(), "message": message}
        staff_alert(message, senders=request.user)

    def op_list(self, request: Request):
        output = list()
        enactor = request.character or request.user
        for board in self.all():
            if not (board.collection.access(enactor, "read") or board.access(enactor, "admin")):
                continue
            if not (board.access(enactor, "read") or board.access(enactor, "admin")):
                continue

            out = board.serialize()
            post_count = board.posts.count()
            out["post_count"] = post_count
            out["unread_count"] = post_count - board.posts.filter(read__id=request.user.id).count()
            out["read_perm"] = board.access(enactor, "read")
            out["post_perm"] = board.access(enactor, "post")
            out["admin_perm"] = board.access(enactor, "admin")
            output.append(out)

        request.status = request.st.HTTP_200_OK
        request.results = {"success": True, "boards": output}


class CollectionDBManager(TypedObjectManager):
    system_name = "BBS"

    def prepare_kwargs(self, request: Request):
        pass

    def _validate_abbreviation(self, request: Request):
        abbreviation = request.kwargs.get("abbreviation", None)
        if abbreviation != "" and not (
                abbreviation := validate_name(
                    request.kwargs.get("abbreviation", None),
                    thing_type="Board Collection",
                    matcher=_RE_ABBREV,
                )
        ):
            request.status = request.st.HTTP_400_BAD_REQUEST
            raise request.ex(
                "You must provide an abbreviation for the board collection."
            )
        return abbreviation

    def _validate_name(self, request: Request):
        if not (
                name := validate_name(
                    request.kwargs.get("name", None), thing_type="Board Collection"
                )
        ):
            request.status = request.st.HTTP_400_BAD_REQUEST
            raise request.ex("You must provide a name for the board collection.")
        return name

    def op_create(self, request: Request):
        if not request.user.is_admin():
            request.status = request.st.HTTP_401_UNAUTHORIZED
            raise request.ex("You do not have permission to create a board collection.")

        name = self._validate_name(request)

        if self.model.objects.filter(db_key__iexact=name).first():
            request.status = request.st.HTTP_400_BAD_REQUEST
            raise request.ex(
                f"A board collection with the name '{name}' already exists."
            )

        abbreviation = self._validate_abbreviation(request)

        if self.model.objects.filter(db_abbreviation__iexact=abbreviation).first():
            request.status = request.st.HTTP_400_BAD_REQUEST
            raise request.ex(
                f"A board collection with the abbreviation '{abbreviation}' already exists."
            )

        collection = self.create(db_key=name, db_abbreviation=abbreviation)
        request.status = request.st.HTTP_201_CREATED
        message = f"Board Collection '{collection.db_abbreviation}: {collection.db_key}' created."
        request.results = {"success": True, "created": collection.serialize(), "message": message}
        staff_alert(message, senders=request.user)

    def op_delete(self, request: Request):
        if not request.user.is_admin():
            request.status = request.st.HTTP_401_UNAUTHORIZED
            raise request.ex("You do not have permission to delete a board collection.")

        collection = self.find_collection(request)

        validate = request.kwargs.get("validate", '')

        if collection.boards.count():
            if validate.lower() != collection.db_key.lower():
                request.status = request.st.HTTP_400_BAD_REQUEST
                raise request.ex(f"Board Collection '{collection.db_abbreviation}: {collection.db_key}' still has boards.  You must provide the collection name to confirm deletion.")

        message = f"Board Collection '{collection.db_abbreviation}: {collection.db_key}' deleted."
        request.results = {"success": True, "collection": collection.serialize(), "message": message}
        staff_alert(message, senders=request.user)

    def find_collection(self, request: Request) -> "BoardCollectionDB":
        if (input := request.kwargs.get("collection_id", None)) is None:
            request.status = request.st.HTTP_400_BAD_REQUEST
            raise request.ex("You must provide a Board Collection ID.")

        collection_id = input.strip()

        if isinstance(collection_id, str) and collection_id.isnumeric():
            collection_id = int(collection_id)

        if isinstance(collection_id, int):
            if not (found := self.filter(id=collection_id).first()):
                request.status = request.st.HTTP_404_NOT_FOUND
                raise request.ex(f"No board collection found with ID {collection_id}.")
            return found

        if found := self.filter(db_key__iexact=collection_id).first():
            return found
        elif found := self.filter(db_abbreviation__iexact=collection_id).first():
            return found

        request.status = request.st.HTTP_404_NOT_FOUND
        raise request.ex(f"No board collection found with ID {collection_id}.")

    def op_rename(self, request: Request):
        if not request.user.is_admin():
            request.status = request.st.HTTP_401_UNAUTHORIZED
            raise request.ex("You do not have permission to rename a board collection.")

        collection = self.find_collection(request)

        name = self._validate_name(request)

        if self.filter(db_key__iexact=name).exclude(id=collection).first():
            request.status = request.st.HTTP_400_BAD_REQUEST
            raise request.ex(
                f"A board collection with the name '{name}' already exists."
            )

        old_name = collection.db_key
        collection.key = name
        message = f"Board Collection '{collection.db_abbreviation}: {old_name}' renamed to '{collection.db_abbreviation}: {collection.db_key}'."
        request.results = {"success": True, "renamed": name, "message": message}
        staff_alert(message, senders=request.user)

    def op_abbreviate(self, request: Request):
        if not request.user.is_admin():
            request.status = request.st.HTTP_401_UNAUTHORIZED
            raise request.ex(
                "You do not have permission to re-abbreviate a board collection."
            )

        collection = self.find_collection(request)

        abbreviation = self._validate_abbreviation(request)

        if (
                self.filter(db_abbreviation__iexact=abbreviation)
                        .exclude(id=collection)
                        .first()
        ):
            request.status = request.st.HTTP_400_BAD_REQUEST
            raise request.ex(
                f"A board collection with the abbreviation '{abbreviation}' already exists."
            )

        old_abbreviation = collection.db_abbreviation
        collection.abbreviation = abbreviation
        message = f"Board Collection '{old_abbreviation}: {collection.db_key}' re-abbreviated to '{collection.db_abbreviation}: {collection.db_key}'."
        request.results = {"success": True, "abbreviated": abbreviation, "message": message}
        staff_alert(message, senders=request.user)

    def op_lock(self, request: Request):
        if not request.user.is_admin():
            request.status = request.st.HTTP_401_UNAUTHORIZED
            raise request.ex("You do not have permission to lock a board collection.")

        collection = self.find_collection(request)

    def op_config(self, request: Request):
        if not request.user.is_admin():
            request.status = request.st.HTTP_401_UNAUTHORIZED
            raise request.ex("You do not have permission to config a board collection.")

        collection = self.find_collection(request)

    def op_list(self, request: Request):
        if not request.user.is_admin():
            request.status = request.st.HTTP_401_UNAUTHORIZED
            raise request.ex("You do not have permission to list board collections.")

        request.results = {
            "success": True,
            "collections": [c.serialize() for c in self.all()],
        }


class BoardManager(BoardDBManager, TypeclassManager):
    pass


class CollectionManager(CollectionDBManager, TypeclassManager):
    system_name = "BBS"


class PostManager(models.Manager):
    system_name = "BBS"

    def prepare_kwargs(self, request: Request):
        pass

    def op_create(self, request: Request):
        enactor = request.character or request.user

        c = class_from_module(settings.BASE_BOARD_TYPECLASS)

        board = c.objects.find_board(request)
        if not (board.access(enactor, "post") or board.access(enactor, "admin")):
            request.status = request.st.HTTP_401_UNAUTHORIZED
            raise request.ex("You do not have permission to post to this board.")

        if not (subject := request.kwargs.get("subject", '').strip()):
            request.status = request.st.HTTP_400_BAD_REQUEST
            raise request.ex("You must provide a subject for the post.")

        if not (body := request.kwargs.get("body", '')):
            request.status = request.st.HTTP_400_BAD_REQUEST
            raise request.ex("You must provide a body for the post.")

        disguise = request.kwargs.get("disguise", None)
        if disguise:
            disguise = disguise.strip()

        kwargs = {"board": board, "subject": subject, "body": body, "user": request.user,
                  "reply_number": 0}

        if (ic := board.options.get("ic")):
            if not request.character:
                request.status = request.st.HTTP_400_BAD_REQUEST
                raise request.ex("You must provide a character for the post.")
            kwargs["character"] = request.character

        if board.options.get("disguise"):
            if not disguise:
                request.status = request.st.HTTP_400_BAD_REQUEST
                raise request.ex("You must provide a disguise name for the post.")
            kwargs["disguise"] = disguise

        kwargs["number"] = board.next_post_number

        with transaction.atomic():
            post = self.create(**kwargs)
            post.read.add(request.user)
            board.last_activity = post.date_created
            board.next_post_number += 1

        targets = online_characters() if ic else online_accounts()

        for target in targets:
            if not (board.access(target, "read") or board.access(target, "admin")):
                continue
            author = post.render_author(target.account, character=target) if hasattr(target,
                                                                                     "account") else post.render_author(
                target)
            target.system_send(self.system_name,
                               f"New BB Message ({board.board_label}/{post.post_number()}) posted to '{board.db_key}' by {author}: {subject}")

        request.status = request.st.HTTP_201_CREATED
        request.results = {"success": True, "post": post.serialize(request.user, character=request.character)}

    def with_post_id(self):
        return self.annotate(
            post_id=models.Case(
                models.When(reply_number=0, then='number'),
                default=Concat(
                    models.F("number"),
                    models.Value("."),
                    models.F("reply_number"),
                    output_field=models.CharField(),
                ),
                output_field=models.CharField(),
            )
        )

    def find_post(self, request: Request, board, field: str = "post_id"):
        if (input := request.kwargs.get(field, None)) is None:
            request.status = request.st.HTTP_400_BAD_REQUEST
            raise request.ex("You must provide a Post ID.")

        post_number = None
        reply_number = 0

        try:
            if '.' in input:
                post_number, reply_number = input.split('.', 1)
                post_number = int(post_number)
                reply_number = int(reply_number)
            else:
                post_number = int(input)
        except ValueError:
            request.status = request.st.HTTP_400_BAD_REQUEST
            raise request.ex("You must provide a valid Post ID.")

        if not (found := self.with_post_id().filter(board=board, number=post_number,
                                                    reply_number=reply_number).first()):
            request.status = request.st.HTTP_404_NOT_FOUND
            raise request.ex(f"No post found with ID {input}.")
        return found

    def op_reply(self, request: Request):
        enactor = request.character or request.user

        c = class_from_module(settings.BASE_BOARD_TYPECLASS)

        board = c.objects.find_board(request)
        if not (board.access(enactor, "post") or board.access(enactor, "admin")):
            request.status = request.st.HTTP_401_UNAUTHORIZED
            raise request.ex("You do not have permission to post to this board.")

        post = self.find_post(request, board)

        if not (body := request.kwargs.get("body", '')):
            request.status = request.st.HTTP_400_BAD_REQUEST
            raise request.ex("You must provide a body for the reply.")

        disguise = request.kwargs.get("disguise", None)
        if disguise:
            disguise = disguise.strip()

        now = utcnow()
        kwargs = {"board": board, "subject": f"RE: {post.subject}", "body": body, "user": request.user,
                  "number": post.number, "date_created": now, "date_modified": now}

        # get max reply_number + 1 from posts with the same board and number...
        result = self.filter(board=board, number=post.number).aggregate(models.Max("reply_number"))
        max_result = result["reply_number__max"]
        kwargs["reply_number"] = max_result + 1 if max_result is not None else 1

        if (ic := board.options.get("ic")):
            if not request.character:
                request.status = request.st.HTTP_400_BAD_REQUEST
                raise request.ex("You must provide a character for the post.")
            kwargs["character"] = request.character

        if board.options.get("disguise"):
            if not disguise:
                request.status = request.st.HTTP_400_BAD_REQUEST
                raise request.ex("You must provide a disguise name for the post.")
            kwargs["disguise"] = disguise

        with transaction.atomic():
            reply = self.create(**kwargs)
            reply.read.add(request.user)
            board.last_activity = now

        targets = online_characters() if ic else online_accounts()
        for target in targets:
            if not (board.access(target, "read") or board.access(target, "admin")):
                continue
            author = reply.render_author(target.account, character=target) if hasattr(target,
                                                                                     "account") else reply.render_author(
                target)
            target.system_send(self.system_name,
                               f"New BB Message ({board.board_label}/{reply.post_number()}) posted to '{board.db_key}' by {author}: {reply.subject}")

        request.status = request.st.HTTP_201_CREATED
        request.results = {"success": True, "post": reply.serialize(request.user, character=request.character)}

    def op_read(self, request: Request):
        enactor = request.character or request.user

        c = class_from_module(settings.BASE_BOARD_TYPECLASS)

        board = c.objects.find_board(request)
        if not (board.access(enactor, "read") or board.access(enactor, "admin")):
            request.status = request.st.HTTP_401_UNAUTHORIZED
            raise request.ex("You do not have permission to read from this board.")

        post = self.find_post(request, board)
        post.read.add(request.user)
        request.results = {"success": True, "board": board.serialize(),
                           "post": post.serialize(request.user, character=request.character)}

    def op_list(self, request: Request):
        enactor = request.character or request.user

        c = class_from_module(settings.BASE_BOARD_TYPECLASS)

        board = c.objects.find_board(request)
        if not (board.access(enactor, "read") or board.access(enactor, "admin")):
            request.status = request.st.HTTP_401_UNAUTHORIZED
            raise request.ex("You do not have permission to read from this board.")

        posts = [post.serialize(request.user, character=request.character) for post in board.posts.all()]

        request.results = {"success": True, "board": board.serialize(),
                           "posts": posts}
