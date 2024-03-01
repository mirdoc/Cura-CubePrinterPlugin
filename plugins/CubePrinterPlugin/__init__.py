# Copyright (c) 2023 UltiMaker
# Cura is released under the terms of the LGPLv3 or higher.

import sys

from UM.Logger import Logger
try: 
    from . import CubePrinterPlugin
except ImportError:
    Logger.log("w", "Could not import CubePrinterPlugin")

from UM.i18n import i18nCatalog
catalog = i18nCatalog("cura")

def getMetaData():
    return {}

def register(app):
    if "CubePrinterPlugin.CubePrinterPlugin" not in sys.modules:
        return {}
    return {"extension": CubePrinterPlugin.CubePrinterPlugin()}
