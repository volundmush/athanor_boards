def init(settings, plugins: dict):
    settings.CMD_MODULES_ACCOUNT.append("athanor_boards.commands")
    settings.BASE_BOARD_COLLECTION_TYPECLASS = (
        "athanor.boards.boards.DefaultBoardCollection"
    )
    settings.BASE_BOARD_TYPECLASS = "athanor.boards.boards.DefaultBoard"
    settings.INSTALLED_APPS.append("athanor_boards")
