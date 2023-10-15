import re
from django.conf import settings
from evennia.typeclasses.models import TypeclassBase
from evennia.utils.utils import lazy_property
from evennia.utils.optionhandler import OptionHandler
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

    @lazy_property
    def options(self):
        return OptionHandler(
            self,
            options_dict=settings.OPTIONS_BOARD_COLLECTION_DEFAULT,
            savefunc=self.attributes.add,
            loadfunc=self.attributes.get,
            save_kwargs={"category": "option"},
            load_kwargs={"category": "option"},
        )


class DefaultBoard(BoardDB, metaclass=TypeclassBase):
    system_name = "BBS"
    objects = BoardManager()
    init_locks = "read:all();post:all();admin:perm(Admin)"

    def at_first_save(self):
        self.locks.add(self.init_locks)

    @property
    def board_label(self):
        return f"{self.db_collection.db_abbreviation}{self.db_order}"

    def serialize(self):
        return {
            "id": self.id,
            "db_key": self.db_key,
            "board_id": self.board_label,
            "collection_id": self.db_collection.id,
            "collection_name": self.db_collection.db_key,
            "db_config": self.db_config,
            "db_next_post_number": self.db_next_post_number,
            "db_last_activity": self.db_last_activity,
            "locks": self.db_lock_storage,
        }

    @lazy_property
    def options(self):
        return OptionHandler(
            self,
            options_dict=settings.OPTIONS_BOARD_DEFAULT,
            savefunc=self.attributes.add,
            loadfunc=self.attributes.get,
            save_kwargs={"category": "option"},
            load_kwargs={"category": "option"},
        )