from collections import defaultdict
from django.conf import settings
from evennia.utils import class_from_module
from evennia.utils.ansi import ANSIString

from athanor.utils import Request
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

        req = self.request(
            target=col.objects,
            operation="create",
            kwargs={"name": self.rhs, "abbreviation": self.lhs},
        )
        req.execute()
        message = req.results.get("message", "")
        if message:
            self.msg(message)


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

        req = self.request(
            target=col.objects,
            operation="delete",
            kwargs={"validate": self.rhs, "collection_id": self.lhs},
        )
        req.execute()
        message = req.results.get("message", "")
        if message:
            self.msg(message)


class CmdBcList(_CmdBcBase):
    """
    List all BBS Board Collections.

    Syntax:
        bclist
    """

    key = "bclist"

    def func(self):
        col = class_from_module(settings.BASE_BOARD_COLLECTION_TYPECLASS)

        req = self.request(
            target=col.objects,
            operation="list",
        )

        req.execute()

        data = req.results.get("collections", list())
        if not data:
            self.msg("No collections found.")
            return

        out = list()
        out.append(self.styled_header("BBS Board Collections"))
        t = self.styled_table("ID", "Abbr", "Name", "Locks")
        t.reformat_column(0, width=7)
        t.reformat_column(1, width=10)
        t.reformat_column(2, width=20)
        for collection in data:
            t.add_row(
                collection["id"],
                collection["db_abbreviation"],
                collection["db_key"],
                collection["locks"],
            )
        out.append(t)
        self.msg_lines(out)


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

        req = self.request(
            target=col.objects,
            operation="rename",
            kwargs={"name": self.rhs, "collection_id": self.lhs},
        )
        req.execute()
        self.request_message(req)


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

        req = self.request(
            target=col.objects,
            operation="rename",
            kwargs={"abbreviation": self.rhs, "collection_id": self.lhs},
        )
        req.execute()
        self.request_message(req)


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

        req = self.request(
            target=col.objects,
            operation="lock",
            kwargs={"lockstring": self.rhs, "collection_id": self.lhs},
        )
        req.execute()
        self.request_message(req)


class CmdBcDelete(_CmdBcBase):
    key = "bcdelete"


class _CmdBbBase(AthanorAccountCommand):
    help_category = "BBS"


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

        req = self.request(
            target=b.objects,
            operation="create",
            kwargs=kwargs,
        )
        req.execute()


class CmdBbRename(_CmdBbBase):
    key = "bbrename"

    def func(self):
        pass


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

        req = self.request(
            target=Post.objects,
            operation="create",
            kwargs={"board_id": board_id, "subject": subject, "body": self.rhs},
        )
        req.execute()


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

        req = self.request(
            target=Post.objects,
            operation="reply",
            kwargs={"board_id": board_id, "post_id": post_id, "body": self.rhs},
        )
        req.execute()


class CmdBbList(_CmdBbBase):
    """
    List all BBS Boards.

    Syntax:
        bblist
    """
    key = "bblist"

    def func(self):
        b = class_from_module(settings.BASE_BOARD_TYPECLASS)

        req = self.request(
            target=b.objects,
            operation="list",
        )
        req.execute()

        data = req.results.get("boards", list())
        if not data:
            self.msg("No boards found.")
            return

        out = list()

        board_collections = defaultdict(list)
        for board in data:
            board_collections[board["collection_name"]].append(board)

        for collection, boards in board_collections.items():
            t = self.rich_table("ID", "Name", "Locks", title=collection)
            for board in boards:
                t.add_row(board["board_id"], board["db_key"], board["locks"])
            out.append(t)

        self.msg_group(*out)


class CmdBbRead(_CmdBbBase):
    """
    Read a BBS Board.

    Syntax:
        bbread
        bbread <board id>
        bbread <board id>/<post id>

    If no board id is provided, a list of all boards will be displayed.
    If a board id is provided, a list of all posts on that board will be displayed.
    If a post id is provided, the post will be displayed.
    """
    key = "bbread"

    def list_all_boards(self):
        b = class_from_module(settings.BASE_BOARD_TYPECLASS)

        req = self.request(
            target=b.objects,
            operation="list",
        )
        req.execute()

        data = req.results.get("boards", list())
        if not data:
            self.msg("No boards found.")
            return

        out = list()

        board_collections = defaultdict(list)
        for board in data:
            board_collections[board["collection_name"]].append(board)

        for collection, boards in board_collections.items():
            t = self.rich_table("ID", "Name", "Last Post", "#Msg", "#Unr", "Perm", title=collection)
            for board in boards:
                perm = "R" if board["read_perm"] else " "
                perm += "P" if board["post_perm"] else " "
                perm += "A" if board["admin_perm"] else " "
                t.add_row(str(board["board_id"]), board["db_key"], self.account.datetime_format(board["db_last_activity"], template="%b %d %Y"),
                          str(board["post_count"]),
                          str(board["unread_count"]), perm)
            out.append(t)

        self.msg_group(*out)

    def list_board_posts(self):
        req = self.request(
            target=Post.objects,
            operation="list",
            kwargs={"board_id": self.args},
        )
        req.execute()

        data = req.results.get("posts", list())
        if not data:
            self.msg("No posts found.")
            return

        board = req.results.get("board")

        out = list()
        t = self.rich_table("ID", "Rd", "Subject", "Date", "Author", title=f"{board['collection_name']} Board {board['board_id']}: {board['db_key']}")
        for post in data:
            t.add_row(f"{post['board_id']}/{post['post_number']}", 'Y' if post["read"] else 'N',
                      post["subject"], self.account.datetime_format(post["date_created"], template="%b %d %Y"),
                      post["author"])
        out.append(t)
        self.msg_group(*out)

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

        req = self.request(
            target=Post.objects,
            operation="read",
            kwargs={"board_id": board_id, "post_id": post_id},
        )
        req.execute()

        data = req.results.get("post", None)
        if not data:
            self.msg("No post found.")
            return
