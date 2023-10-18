from django.db import models
from django.conf import settings
from evennia.typeclasses.models import TypedObject
from athanor.utils import utcnow
from .managers import BoardDBManager, CollectionDBManager, PostManager


class BoardCollectionDB(TypedObject):
    objects = CollectionDBManager()

    __settingsclasspath__ = settings.BASE_BOARD_COLLECTION_TYPECLASS
    __defaultclasspath__ = "athanor_boards.boards.DefaultBoardCollection"
    __applabel__ = "athanor_boards"

    db_key = models.CharField("key", max_length=255, unique=True)
    db_abbreviation = models.CharField(
        max_length=30, unique=True, null=False, blank=True
    )
    db_config = models.JSONField(null=False, default=dict)


class BoardDB(TypedObject):
    objects = BoardDBManager()

    # defaults
    __settingsclasspath__ = settings.BASE_BOARD_TYPECLASS
    __defaultclasspath__ = "athanor_boards.boards.DefaultBoard"
    __applabel__ = "athanor_boards"

    db_collection = models.ForeignKey(
        BoardCollectionDB, on_delete=models.PROTECT, related_name="boards"
    )
    db_order = models.IntegerField(default=1, null=False)

    db_config = models.JSONField(null=False, default=dict)
    db_next_post_number = models.IntegerField(default=1, null=False)
    db_last_activity = models.DateTimeField(null=False, default=utcnow)

    class Meta:
        unique_together = (("db_collection", "db_key"), ("db_collection", "db_order"))
        ordering = ["-db_collection", "db_order"]


class Post(models.Model):
    objects = PostManager()

    board = models.ForeignKey(BoardDB, on_delete=models.CASCADE, related_name="posts")
    user = models.ForeignKey("accounts.AccountDB", on_delete=models.PROTECT)
    character = models.ForeignKey(
        "objects.ObjectDB", null=True, on_delete=models.PROTECT
    )
    disguise = models.CharField(max_length=255, null=True, blank=True)
    number = models.IntegerField(null=False)
    reply_number = models.IntegerField(null=False, default=0)

    subject = models.CharField(max_length=255, null=False)

    date_created = models.DateTimeField(null=False, default=utcnow)
    date_modified = models.DateTimeField(null=False, default=utcnow)

    body = models.TextField(null=False)

    read = models.ManyToManyField("accounts.AccountDB", related_name="read_posts")

    class Meta:
        unique_together = (("board", "number", "reply_number"),)
        ordering = ["board", "number", "reply_number"]

    def post_number(self):
        if self.reply_number == 0:
            return str(self.number)
        return f"{self.number}.{self.reply_number}"

    def render_author(self, user, character=None, known_admin: bool = None):
        if known_admin is None:
            admin = (self.user == user) or (character and (self.character == character)) or self.board.access(user,
                                                                                                              "admin")
        else:
            admin = known_admin
        poster = self.character or self.user
        if self.board.options.get("disguise"):
            return f"{self.disguise} ({poster.key})" if admin else self.disguise
        elif self.board.options.get("character"):
            return f"{self.character.key}"
        else:
            return self.user.key

    def serialize(self, user, character=None):
        data = {
            "id": self.id,
            "post_number": self.post_number(),
            "board_id": self.board.board_label,
            "board_name": self.board.db_key,
            "number": self.number,
            "reply_number": self.reply_number,
            "subject": self.subject,
            "date_created": self.date_created,
            "date_modified": self.date_modified,
            "body": self.body,
            "read": self.read.filter(id=user.id).exists(),
        }

        enactor = character or user

        admin = (self.user == user) or (character and (self.character == character)) or self.board.access(enactor,
                                                                                                          "admin")
        if admin:
            data["character_id"] = self.character.id if self.character else None
            data["character_name"] = self.character.key if self.character else None
            data["user_id"] = self.user.id
            data["user_name"] = self.user.key
            data["disguise"] = self.disguise

        data["author"] = self.render_author(user, character=character, known_admin=admin)

        return data
