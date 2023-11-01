from collections import defaultdict
from django.conf import settings
from evennia.utils import class_from_module

from athanor.commands import AthanorAccountCommand

from .models import Post


class _CmdBcBase(AthanorAccountCommand):
    locks = "cmd:perm(bbadmin) or perm(Admin)"
    help_category = "BBS"


class CmdBcCreate(_CmdBcBase):
    """
    Create a BBS Board Collection.

    Syntax:
        bccreate <abbreviation>=<name>

    Abbreviations must be 1-10 characters long and contain only letters.
    Use the string 'None' to create a board collection without an abbreviation.
    Abbreviations and names must be unique (case insensitive).
    """

    key = "bccreate"

    def func(self):
        if not (self.lhs and self.rhs):
            self.msg("Usage: bccreate <abbreviation>=<name>")
            return

        if self.lhs.lower() == "none":
            self.lhs = ""

        col = class_from_module(settings.BASE_BOARD_COLLECTION_TYPECLASS)

        op = self.operation(
            target=col.objects,
            operation="create",
            kwargs={"name": self.rhs, "abbreviation": self.lhs},
        )
        op.execute()
        self.op_message(op)


class CmdBcDelete(_CmdBcBase):
    """
    Deletes a BBS Board Collection.

    Syntax:
        bcdelete <abbreviation>[=<name>]

    The name must be provided if the Collection has boards, for extra verification.

    WARNING: This will delete all boards and posts in the collection. There is no undo.
    """
    key = "bcdelete"

    def func(self):
        if not self.lhs:
            self.msg("Usage: bcdelete <abbreviation>[=<name>]")
            return

        col = class_from_module(settings.BASE_BOARD_COLLECTION_TYPECLASS)

        op = self.operation(
            target=col.objects,
            operation="delete",
            kwargs={"validate": self.rhs, "collection_id": self.lhs},
        )
        op.execute()
        self.op_message(op)


class CmdBcList(_CmdBcBase):
    """
    List all BBS Board Collections.

    Syntax:
        bclist
    """

    key = "bclist"

    def func(self):
        col = class_from_module(settings.BASE_BOARD_COLLECTION_TYPECLASS)

        op = self.operation(
            target=col.objects,
            operation="list",
        )
        op.execute()
        if not op.results.get("success", False):
            self.op_message(op)
            return

        if not (data := op.results.get("collections", list())):
            self.msg("No collections found.")
            return

        t = self.rich_table("ID", "Abbr", "Name", "Locks", title="BBS Board Collections")
        for collection in data:
            t.add_row(
                str(collection["id"]),
                collection["db_abbreviation"],
                collection["db_key"],
                collection["locks"],
            )
        self.buffer.append(t)


class CmdBcRename(_CmdBcBase):
    """
    Rename a BBS Board Collection.

    Syntax:
        bcrename <abbreviation>=<name>
    """

    key = "bcrename"

    def func(self):
        if not (self.lhs and self.rhs):
            self.msg("Usage: bcrename <abbreviation>=<name>")
            return

        if self.lhs.lower() == "none":
            self.lhs = ""

        col = class_from_module(settings.BASE_BOARD_COLLECTION_TYPECLASS)

        op = self.operation(
            target=col.objects,
            operation="rename",
            kwargs={"name": self.rhs, "collection_id": self.lhs},
        )
        op.execute()
        self.op_message(op)


class CmdBcConfig(_CmdBcBase):
    """
    Configure a BBS Board Collection.

    Syntax:
        bcconfig <abbreviation>
        bcconfig <abbreviation>/<key>=<value>

    If no key is provided, the current configuration will be displayed.
    If a key is provided, the configuration will be updated.
    """
    key = "bcconfig"

    def func(self):
        if not self.lhs:
            self.msg("Usage: bcconfig <abbreviation>[/<key>=<value>]")
            return

        abbr = None
        key = None
        value = self.rhs
        if "/" in self.lhs:
            abbr, key = self.lhs.split("/", 1)
        else:
            abbr = self.lhs

        if abbr.lower() == "none":
            abbr = ""

        if key is not None:
            self.update_config(abbr, key, value)
        else:
            self.display_config(abbr)

    def update_config(self, abbr: str, key: str, value: str):
        col = class_from_module(settings.BASE_BOARD_COLLECTION_TYPECLASS)

        op = self.operation(
            target=col.objects,
            operation="config_set",
            kwargs={"collection_id": abbr, "key": key, "value": value},
        )
        op.execute()
        self.op_message(op)

    def display_config(self, abbr: str):
        col = class_from_module(settings.BASE_BOARD_COLLECTION_TYPECLASS)

        op = self.operation(
            target=col.objects,
            operation="config_list",
            kwargs={"collection_id": abbr},
        )
        op.execute()

        if not op.results.get("success", False):
            self.op_message(op)
            return

        if not (data := op.results.get("config", list())):
            self.msg("No configuration found.")
            return

        c = op.results.get("collection")

        t = self.rich_table("Name", "Description", "Type", "Value",
                            title=f"'{c['db_abbreviation']}: {c['db_key']}' Config Options")
        for config in data:
            t.add_row(config["name"], config["description"], config["type"], config["value"])
        self.buffer.append(t)


class CmdBcAbbreviate(_CmdBcBase):
    """
    Rename a BBS Board Collection.

    Syntax:
        bcabbrev <abbreviation>=<new abbreviation>
    """

    key = "bcabbrev"

    def func(self):
        if not (self.lhs and self.rhs):
            self.msg("Usage: bcabbrev <abbreviation>=<new abbreviation>")
            return

        if self.lhs.lower() == "none":
            self.lhs = ""

        col = class_from_module(settings.BASE_BOARD_COLLECTION_TYPECLASS)

        op = self.operation(
            target=col.objects,
            operation="rename",
            kwargs={"abbreviation": self.rhs, "collection_id": self.lhs},
        )
        op.execute()
        self.op_message(op)


class CmdBcLock(_CmdBcBase):
    """
    Alters locks on a BBS Board Collection.

    Syntax:
        bclock <abbreviation>=<lockstring>

    Lockstrings must be valid Evennia lockstrings.
    See help lock for more information.

    Locks:
        read - Who can see the collection and its boards.
        admin - Who can modify the collection.
            (Add/Delete/Rename boards, etc.)
    """
    key = "bclock"

    def func(self):
        if not (self.lhs and self.rhs):
            self.msg("Usage: bclock <abbreviation>=<lockstring>")
            return

        if self.lhs.lower() == "none":
            self.lhs = ""

        col = class_from_module(settings.BASE_BOARD_COLLECTION_TYPECLASS)

        op = self.operation(
            target=col.objects,
            operation="lock",
            kwargs={"lockstring": self.rhs, "collection_id": self.lhs},
        )
        op.execute()
        self.op_message(op)


class _CmdBbBase(AthanorAccountCommand):
    help_category = "BBS"


class CmdBbDelete(_CmdBbBase):
    """
    Delete a BBS Board.

    Syntax:
        bbdelete <board id>=<name>
    """
    key = "bbdelete"

    def func(self):
        if not (self.lhs and self.rhs):
            self.msg("Usage: bbdelete <board id>=<name>")
            return

        b = class_from_module(settings.BASE_BOARD_TYPECLASS)

        op = self.operation(
            target=b.objects,
            operation="delete",
            kwargs={"validate": self.rhs, "board_id": self.lhs},
        )
        op.execute()
        self.op_message(op)


class CmdBbCreate(_CmdBbBase):
    """
    Create a BBS Board.

    Syntax:
        bbcreate <collection abbreviation>[/<order>]=<name>
    """
    key = "bbcreate"

    def func(self):
        if not (self.lhs and self.rhs):
            self.msg("Usage: bcabbrev <abbreviation>[/<order>]=<name>")
            return

        b = class_from_module(settings.BASE_BOARD_TYPECLASS)

        if "/" in self.lhs:
            collection_id, order = self.lhs.split("/", 1)
        else:
            collection_id, order = self.lhs, None

        if collection_id.lower() == "none":
            collection_id = ""

        kwargs = {"name": self.rhs, "collection_id": collection_id}
        if order is not None:
            kwargs["order"] = order

        op = self.operation(
            target=b.objects,
            operation="create",
            kwargs=kwargs,
        )
        op.execute()

        self.op_message(op)


class CmdBbRename(_CmdBbBase):
    """
    Renames a BBS Board.

    Syntax:
        bbrename <board id>=<new name>
    """
    key = "bbrename"

    def func(self):
        if not (self.lhs and self.rhs):
            self.msg("Usage: bbrename <board id>=<new name>")
            return

        b = class_from_module(settings.BASE_BOARD_TYPECLASS)

        op = self.operation(
            target=b.objects,
            operation="rename",
            kwargs={"name": self.rhs, "board_id": self.lhs},
        )
        op.execute()
        self.op_message(op)


class CmdBbOrder(_CmdBbBase):
    """
    Changes a board's order ID in its collection.

    Syntax:
        bborder <board id>=<new order>
    """
    key = "bborder"

    def func(self):
        if not (self.lhs and self.rhs):
            self.msg("Usage: bborder <board id>=<new order>")
            return

        b = class_from_module(settings.BASE_BOARD_TYPECLASS)

        op = self.operation(
            target=b.objects,
            operation="order",
            kwargs={"order": self.rhs, "board_id": self.lhs},
        )
        op.execute()
        self.op_message(op)


class CmdBbPost(_CmdBbBase):
    """
    Post a message to a BBS Board.

    Syntax:
        bbpost <board id>/<subject>=<message>
    """

    key = "bbpost"

    def func(self):
        if not (self.lhs and self.rhs):
            self.msg("Usage: bbpost <board id>/<subject>=<message>")
            return

        if "/" not in self.lhs:
            self.msg("Usage: bbpost <board id>/<subject>=<message>")
            return

        board_id, subject = self.lhs.split("/", 1)
        board_id = board_id.strip()

        op = self.operation(
            target=Post.objects,
            operation="create",
            kwargs={"board_id": board_id, "subject": subject, "body": self.rhs},
        )
        op.execute()

        self.op_message(op)


class CmdBbReply(_CmdBbBase):
    """
    Reply to a message on a BBS Board.

    Syntax:
        bbreply <board id>/<post id>=<message>
    """
    key = "bbreply"

    def func(self):
        if not (self.lhs and self.rhs):
            self.msg("Usage: bbreply <board id>/<post id>=<message>")
            return

        if "/" not in self.lhs:
            self.msg("Usage: bbreply <board id>/<post id>=<message>")
            return

        board_id, post_id = self.lhs.split("/", 1)
        board_id = board_id.strip()
        post_id = post_id.strip()

        op = self.operation(
            target=Post.objects,
            operation="reply",
            kwargs={"board_id": board_id, "post_id": post_id, "body": self.rhs},
        )
        op.execute()

        self.op_message(op)


class CmdBbList(_CmdBbBase):
    """
    List all BBS Boards.

    Syntax:
        bblist
    """
    key = "bblist"

    def func(self):
        b = class_from_module(settings.BASE_BOARD_TYPECLASS)

        op = self.operation(
            target=b.objects,
            operation="list",
        )
        op.execute()

        if not op.results.get("success", False):
            self.op_message(op)
            return

        if not (data := op.results.get("boards", list())):
            self.msg("No boards found.")
            return

        board_collections = defaultdict(list)
        for board in data:
            board_collections[board["collection_name"]].append(board)

        for collection, boards in board_collections.items():
            t = self.rich_table("ID", "Name", "Locks", title=collection)
            for board in boards:
                t.add_row(board["board_id"], board["db_key"], board["locks"])
            self.buffer.append(t)


class CmdBbRead(_CmdBbBase):
    """
    Read a BBS Board.

    Syntax:
        bbread
        bbread <board id>[.<page>]
        bbread <board id>/<post id>

    If no board id is provided, a list of all boards will be displayed.
    If a board id is provided, a list of all posts on that board will be displayed.
    If a post id is provided, the post will be displayed.
    """
    key = "bbread"

    def list_all_boards(self):
        b = class_from_module(settings.BASE_BOARD_TYPECLASS)

        op = self.operation(
            target=b.objects,
            operation="list",
        )
        op.execute()

        if not op.results.get("success", False):
            self.op_message(op)
            return

        if not (data := op.results.get("boards", list())):
            self.msg("No boards found.")
            return

        board_collections = defaultdict(list)
        for board in data:
            board_collections[board["collection_name"]].append(board)

        for collection, boards in board_collections.items():
            t = self.rich_table("ID", "Name", "Last Post", "#Msg", "#Unr", "Perm", title=collection)
            for board in boards:
                perm = "R" if board["read_perm"] else " "
                perm += "P" if board["post_perm"] else " "
                perm += "A" if board["admin_perm"] else " "
                t.add_row(str(board["board_id"]), board["db_key"],
                          self.account.datetime_format(board["db_last_activity"], template="%b %d %Y"),
                          str(board["post_count"]),
                          str(board["unread_count"]), perm)
            self.buffer.append(t)

    def list_board_posts(self):
        op = self.operation(
            target=Post.objects,
            operation="list",
            kwargs={"board_id": self.args, "posts_per_page": 50},
        )
        op.execute()

        if not op.results.get("success", False):
            self.op_message(op)
            return

        if not (data := op.results.get("posts", list())):
            self.msg("No posts found.")
            return

        board = op.results.get("board")
        page = op.results.get("page")
        pages = op.results.get("pages")

        page_display = f"(Page {page} of {pages})"
        t = self.rich_table("ID", "Rd", "Subject", "Date", "Author",
                            title=f"{board['collection_name']} Board {board['board_id']}: {board['db_key']} {page_display}", )
        for post in data:
            t.add_row(f"{post['board_id']}/{post['post_number']}", 'Y' if post["read"] else 'N',
                      post["subject"], self.account.datetime_format(post["date_created"], template="%b %d %Y"),
                      post["author"])
        self.buffer.append(t)

    def func(self):

        if not self.args:
            self.list_all_boards()
            return

        if "/" not in self.args:
            self.list_board_posts()
            return

        board_id, post_id = self.args.split("/", 1)
        board_id = board_id.strip()
        post_id = post_id.strip()

        op = self.operation(
            target=Post.objects,
            operation="read",
            kwargs={"board_id": board_id, "post_id": post_id},
        )
        op.execute()

        if not op.results.get("success", False):
            self.op_message(op)
            return

        if not (post := op.results.get("post", None)):
            self.msg("No post found.")
            return

        t = self.rich_table(
            title=f"{post['board_name']} Board Post {post['board_id']}/{post['post_number']}: {post['subject']}",
            show_lines=True,
            show_header=False)
        t.add_column()

        header = list()
        # we want the header to be lines of relevant information...
        header.append(f"{'Author:':>7} {post['author']:<20}")
        header.append(f"{'Date:':>7} {self.account.datetime_format(post['date_created'], template='%c'):<20}")

        t.add_row("\n".join(header))
        t.add_row(post["body"])

        self.buffer.append(t)



class CmdBbConfig(_CmdBbBase):
    """
    Configure a BBS Board.

    Syntax:
        bbconfig <board>
        bbconfig <board>/<key>=<value>

    If no key is provided, the current configuration will be displayed.
    If a key is provided, the configuration will be updated.
    """
    key = "bbconfig"

    def func(self):
        if not self.lhs:
            self.msg("Usage: bbconfig <board>[/<key>=<value>]")
            return

        board = None
        key = None
        value = self.rhs
        if "/" in self.lhs:
            board, key = self.lhs.split("/", 1)
        else:
            board = self.lhs

        if key is not None:
            self.update_config(board, key, value)
        else:
            self.display_config(board)

    def update_config(self, board: str, key: str, value: str):
        b = class_from_module(settings.BASE_BOARD_TYPECLASS)

        op = self.operation(
            target=b.objects,
            operation="config_set",
            kwargs={"board_id": board, "key": key, "value": value},
        )
        op.execute()
        self.op_message(op)

    def display_config(self, abbr: str):
        b = class_from_module(settings.BASE_BOARD_TYPECLASS)

        op = self.operation(
            target=b.objects,
            operation="config_list",
            kwargs={"board_id": abbr},
        )
        op.execute()

        if not op.results.get("success", False):
            self.op_message(op)
            return

        if not (data := op.results.get("config", list())):
            self.msg("No configuration found.")
            return

        c = op.results.get("board")

        t = self.rich_table("Name", "Description", "Type", "Value",
                            title=f"'{c['board_id']}: {c['db_key']}' Config Options")
        for config in data:
            t.add_row(config["name"], config["description"], config["type"], config["value"])
        self.buffer.append(t)


class CmdBbLock(_CmdBbBase):
    """
    Alters locks on a BBS Board.

    Syntax:
        bblock <board id>=<lockstring>

    Lockstrings must be valid Evennia lockstrings.
    See help lock for more information.

    Locks:
        read - Who can see the board and its posts.
        post - Who can post to the board.
        admin - Who can modify the board.
            (Moderate, etc.)
    """
    key = "bblock"

    def func(self):
        if not (self.lhs and self.rhs):
            self.msg("Usage: bblock <board id>=<lockstring>")
            return

        b = class_from_module(settings.BASE_BOARD_TYPECLASS)

        board_id = self.lhs.strip()

        op = self.operation(
            target=b.objects,
            operation="lock",
            kwargs={"lockstring": self.rhs, "board_id": board_id},
        )
        op.execute()
        self.op_message(op)

class CmdBbRemove(_CmdBbBase):
    """
    Remove a post from a BBS Board.

    Syntax:
        bbremove <board id>/<post id>
    """
    key = "bbremove"

    def func(self):
        if not self.args:
            self.msg("Usage: bbremove <board id>/<post id>")
            return

        if "/" not in self.args:
            self.msg("Usage: bbremove <board id>/<post id>")
            return

        board_id, post_id = self.args.split("/", 1)
        board_id = board_id.strip()
        post_id = post_id.strip()

        op = self.operation(
            target=Post.objects,
            operation="remove",
            kwargs={"board_id": board_id, "post_id": post_id},
        )
        op.execute()

        self.op_message(op)