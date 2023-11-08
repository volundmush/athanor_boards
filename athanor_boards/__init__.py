import athanor
from collections import defaultdict


def init(settings, plugins: dict):
    settings.CMD_MODULES_ACCOUNT.append("athanor_boards.commands")
    settings.BASE_BOARD_COLLECTION_TYPECLASS = (
        "athanor_boards.boards.DefaultBoardCollection"
    )

    settings.BASE_BOARD_TYPECLASS = "athanor_boards.boards.DefaultBoard"
    settings.INSTALLED_APPS.append("athanor_boards")

    settings.OPTIONS_BOARD_COLLECTION_DEFAULT = {
        "default_locks": [
            "Default locks set for new Boards in this Collection.",
            "Lock",
            "read:all();post:all();admin:perm(Admin)",
        ],
    }

    settings.OPTIONS_BOARD_DEFAULT = {
        "ic": ["Board uses character names.", "Boolean", False],
        "disguise": ["Board uses disguises.", "Boolean", False],
        "anonymous": ["Anonymous poster names. Value is the anon-name.", "Text", ""],
    }

    settings.BOARD_ACCESS_FUNCTIONS = defaultdict(list)

    # those who pass this lockstring always pass permission checks on boards.
    # This is required to manage Board Collections.
    settings.BOARD_PERMISSIONS_ADMIN_OVERRIDE = "perm(Developer)"

    athanor.BOARD_ACCESS_FUNCTIONS = defaultdict(list)

    settings.ACCESS_FUNCTIONS_LIST.append("BOARD")
