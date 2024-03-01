# Copyright (c) 2023 UltiMaker
# Cura is released under the terms of the LGPLv3 or higher.

import sys

from UM.Logger import Logger
try: 
    from . import Cube3Writer
except ImportError:
    Logger.log("w", "Could not import Cube3Writer")

from UM.i18n import i18nCatalog
catalog = i18nCatalog("cura")


def getMetaData():
    file_extension = "cube3"
    return {
        "mesh_writer": {
            "output": [{
                "extension": file_extension,
                "description": catalog.i18nc("@item:inlistbox", "Cube3 Print File"),
                "mime_type": "application/x-cube3",
                "mode": Cube3Writer.Cube3Writer.OutputMode.BinaryMode,
            }],
        }
    }


def register(app):
    if "Cube3Writer.Cube3Writer" not in sys.modules:
        return {}
    plugin = Cube3Writer.Cube3Writer()
    return {
        "mesh_writer": plugin
    }
