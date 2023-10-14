import re
from evennia.typeclasses.models import TypeclassBase

from .managers import BoardManager, CollectionManager
from .models import BoardDB, BoardCollectionDB, Post


class DefaultBoardCollection(BoardCollectionDB, metaclass=TypeclassBase):
    system_name = "BBS"
    objects = CollectionManager()
    init_locks = "read:all();admin:perm(Admin)"

    def at_first_save(self):
        self.locks.add(self.init_locks)

    def serialize(self):
        return {
            "id": self.id,
            "db_key": self.db_key,
            "db_abbreviation": self.db_abbreviation,
            "db_config": self.db_config,
            "locks": self.db_lock_storage,
        }


class DefaultBoard(BoardDB, metaclass=TypeclassBase):
    system_name = "BBS"
    objects = BoardManager()
    init_locks = "read:all();post:all();admin:perm(Admin)"

    def at_first_save(self):
        self.locks.add(self.init_locks)

    def board_id(self):
        return f"{self.db_collection.db_abbreviation}{self.db_order}"

    def serialize(self):
        return {
            "id": self.id,
            "db_key": self.db_key,
            "board_id": self.board_id,
            "collection_id": self.db_collection.id,
            "db_config": self.db_config,
            "db_next_post_number": self.db_next_post_number,
            "db_last_activity": self.db_last_activity,
            "locks": self.db_lock_storage,
        }
