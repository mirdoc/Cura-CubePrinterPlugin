# Copyright (c) 2023 UltiMaker
# Cura is released under the terms of the LGPLv3 or higher.

import sys

from UM.Logger import Logger
try: 
    from . import CubeWriter
except ImportError:
    Logger.log("w", "Could not import CubeWriter")

from UM.i18n import i18nCatalog
catalog = i18nCatalog("cura")


def getMetaData():
    file_extension = "cube"
    return {
        "mesh_writer": {
            "output": [{
                "extension": file_extension,
                "description": catalog.i18nc("@item:inlistbox", "Cube Print File"),
                "mime_type": "application/x-cube",
                "mode": CubeWriter.CubeWriter.OutputMode.BinaryMode,
            }],
        }
    }


def register(app):
    if "CubeWriter.CubeWriter" not in sys.modules:
        return {}
    plugin = CubeWriter.CubeWriter()
    return {
        "mesh_writer": plugin
    }
