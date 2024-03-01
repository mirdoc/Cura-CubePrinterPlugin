# Copyright (c) 2023 UltiMaker
# Cura is released under the terms of the LGPLv3 or higher.

import sys

from UM.Logger import Logger
try: 
    from . import CubeproWriter
except ImportError:
    Logger.log("w", "Could not import CubeproWriter")

from UM.i18n import i18nCatalog
catalog = i18nCatalog("cura")


def getMetaData():
    file_extension = "cubepro"
    return {
        "mesh_writer": {
            "output": [{
                "extension": file_extension,
                "description": catalog.i18nc("@item:inlistbox", "Cubepro Print File"),
                "mime_type": "application/x-cubepro",
                "mode": CubeproWriter.CubeproWriter.OutputMode.BinaryMode,
            }],
        }
    }


def register(app):
    if "CubeproWriter.CubeproWriter" not in sys.modules:
        return {}
    plugin = CubeproWriter.CubeproWriter()
    return {
        "mesh_writer": plugin
    }
