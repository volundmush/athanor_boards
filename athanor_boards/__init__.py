def init(settings, plugins: dict):
    settings.CMD_MODULES_ACCOUNT.append("athanor_boards.commands")
    settings.BASE_BOARD_COLLECTION_TYPECLASS = (
        "athanor_boards.boards.DefaultBoardCollection"
    )
    settings.BASE_BOARD_TYPECLASS = "athanor_boards.boards.DefaultBoard"
    settings.INSTALLED_APPS.append("athanor_boards")

    settings.OPTIONS_BOARD_COLLECTION_DEFAULT = {}

    settings.OPTIONS_BOARD_DEFAULT = {
        "ic": ("Board uses character names.", "Boolean", False),
        "disguise": ("Board uses disguises.", "Boolean", False),
        "anonymous": ("Anonymous poster names. Value is the anon-name.", "String", ''),
    }