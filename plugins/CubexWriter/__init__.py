# Copyright (c) 2023 UltiMaker
# Cura is released under the terms of the LGPLv3 or higher.

import sys

from UM.Logger import Logger
try: 
    from . import CubexWriter
except ImportError:
    Logger.log("w", "Could not import CubexWriter")

from UM.i18n import i18nCatalog
catalog = i18nCatalog("cura")


def getMetaData():
    file_extension = "cubex"
    return {
        "mesh_writer": {
            "output": [{
                "extension": file_extension,
                "description": catalog.i18nc("@item:inlistbox", "Cubex Print File"),
                "mime_type": "application/x-cubex",
                "mode": CubexWriter.CubexWriter.OutputMode.BinaryMode,
            }],
        }
    }


def register(app):
    if "CubexWriter.CubexWriter" not in sys.modules:
        return {}
    plugin = CubexWriter.CubexWriter()
    return {
        "mesh_writer": plugin
    }
