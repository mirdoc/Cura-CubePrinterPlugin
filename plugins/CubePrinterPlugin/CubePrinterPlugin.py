####################################################################
# Cura-CubePro-Printer-Plugin for Ultimaker Cura
# 
# A plugin that adds the 3D Systems CubePro, CubePro Duo, and 
# CubePro Trio printers to Cura and enables Cura to export to the 
# proprietary 3D Systems .cubepro file format.
#
# Written by mirdoc
# Borrows heavily on Cura-Dremel-Printer-Plugin by Tim Schoenmackers
# which is based on the GcodeWriter plugin written by Ultimaker
#
# The Cura-Dremel-Printer-Plugin source can be found here:
# https://github.com/metalman3797/Cura-Dremel-Printer-Plugin
#
# The GcodeWriter plugin source can be found here:
# https://github.com/Ultimaker/Cura/tree/master/plugins/GCodeWriter
#
# This plugin is released under the terms of the LGPLv3 or higher.
# The full text of the LGPLv3 License can be found here:
# https://github.com/mirdoc/Cura-CubePrinterPlugin/blob/master/LICENSE
####################################################################

import sys
import os       # for listdir
import os.path  # for isfile and join and path
import zipfile  # For unzipping the printer files
import stat     # For setting file permissions correctly
import json
import copy
import struct

from distutils.version import StrictVersion # for upgrade installations

from UM.i18n import i18nCatalog
from UM.Extension import Extension
from UM.Message import Message
from UM.Resources import Resources
from UM.Logger import Logger
from UM.Mesh.MeshWriter import MeshWriter
from UM.Settings.InstanceContainer import InstanceContainer
from UM.Qt.Duration import DurationFormat
from UM.PluginRegistry import PluginRegistry
from UM.Mesh.MeshWriter import MeshWriter
from UM.MimeTypeDatabase import MimeTypeDatabase, MimeType

from io import StringIO, BytesIO, BufferedIOBase
from typing import cast, List, Optional, Dict

from UM.Application import Application
from UM.Settings.InstanceContainer import InstanceContainer
from cura.CuraApplication import CuraApplication
from cura.CuraVersion import ConanInstalls
from cura.Utils.Threading import call_on_qt_thread
from cura.Snapshot import Snapshot

from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QObject, QUrl, pyqtSlot

catalog = i18nCatalog("cura")


class CubePrinterPlugin(QObject, Extension):
    ######################################################################
    ##  The version number of this plugin
    ##  Please ensure that the version number is the same match in all
    ##  three of the following Locations:
    ##    1) below (this file)
    ##    2) .\plugin.json
    ##    3) ..\..\resources\package.json
    ######################################################################
    version = "0.2.5"
    _website_url = "https://github.com/mirdoc/Cura-CubePrinterPlugin"

    def __init__(self) -> None:
        super().__init__()
        self._application = Application.getInstance()
        
        self._name = "CubePrinterPlugin"
        
        if self.getPreferenceValue("curr_version") is None:
            self.setPreferenceValue("curr_version", "0.0.0")

        Logger.log("i", self._name + " - Initialising...")

        self.this_plugin_path = os.path.join(Resources.getStoragePath(Resources.Resources), "plugins", self._name + "", self._name + "")

        self.local_meshes_path = os.path.join(Resources.getStoragePathForType(Resources.Resources), "meshes")
        self.local_printer_def_path = Resources.getStoragePath(Resources.DefinitionContainers)
        self.local_quality_path = os.path.join(Resources.getStoragePath(Resources.Resources), "quality")
        self.local_extruder_path = os.path.join(Resources.getStoragePath(Resources.Resources),"extruders")

        plugin_install_required = False

        if self.isInstalled():
            # if the version isn't the same, then force installation
            if not self.versionsMatch():
                Logger.log("i", self._name + " - Detected that plugin needs to be upgraded")
                plugin_install_required = True

        else:
            Logger.log("i", self._name + " - Some files are NOT installed")
            plugin_install_required = True

        # if we need to install the files, then do so
        if plugin_install_required:
            self.installPluginFiles()

        self.addMenuItem(catalog.i18nc("@item:inmenu", "Help "), self.showHelp)
        self.addMenuItem(catalog.i18nc("@item:inmenu", self._name + " Version " + CubePrinterPlugin.version), self.openPluginWebsite)
        
        # finally save the cura.cfg file
        Logger.log("i", self._name + " - Writing to " + str(Resources.getStoragePath(Resources.Preferences, self._application.getApplicationName() + ".cfg")))
        self._application.getPreferences().writeToFile(Resources.getStoragePath(Resources.Preferences, self._application.getApplicationName() + ".cfg"))

    ######################################################################
    ##  function so that the preferences menu can open website
    ######################################################################
    @pyqtSlot()
    def openPluginWebsite(self):
        url = QUrl(self._website_url, QUrl.ParsingMode.TolerantMode)
        if not QDesktopServices.openUrl(url):
            message = Message(catalog.i18nc("@info:warning", self._name + " - Could not navigate to " + self._website_url))
            message.show()
        return

    ######################################################################
    ##  Show the help
    ######################################################################
    @pyqtSlot()
    def showHelp(self):
        url = os.path.join(PluginRegistry.getInstance().getPluginPath(self.getPluginId()), "README.pdf")
        Logger.log("i", self._name + " - Opening help document: " + url)
        try:
            if not QDesktopServices.openUrl(QUrl("file:///"+url, QUrl.ParsingMode.TolerantMode)):
                message = Message(catalog.i18nc("@info:warning", self._name + " could not open help document.\n Please download it from here: " + self._website_url + "/raw/stable/README.pdf"))
                message.show()
        except:
            message = Message(catalog.i18nc("@info:warning", self._name + " could not open help document.\n Please download it from here: " + self._website_url + "/raw/stable/README.pdf"))
            message.show()
        return

    ######################################################################
    ## returns true if the versions match and false if they don't
    ######################################################################
    def versionsMatch(self):
        # get the currently installed plugin version number
        if self.getPreferenceValue("curr_version") is None:
            self.setPreferenceValue("curr_version", "0.0.0")

        installedVersion = self._application.getPreferences().getValue(self._name + "/curr_version")

        if StrictVersion(installedVersion) == StrictVersion(CubePrinterPlugin.version):
            # if the version numbers match, then return true
            Logger.log("i", self._name + " - Versions match: " + installedVersion + " matches " + CubePrinterPlugin.version)
            return True
        else:
            Logger.log("i", self._name + " - The currently installed version: " + installedVersion + " doesn't match this version: " + CubePrinterPlugin.version)
            return False

    ######################################################################
    ## Check to see if the plugin files are all installed
    ## Return True if all files are installed, false if they are not
    ######################################################################
    def isInstalled(self):
        install_file_locations = {
            "CubePro definition file":          os.path.join(self.local_printer_def_path, "CubePro.def.json"),
            "CubePro Duo definition file":      os.path.join(self.local_printer_def_path, "CubeProDuo.def.json"),
            "CubePro Trio definition file":     os.path.join(self.local_printer_def_path, "CubeProTrio.def.json"),
            "CubeX definition file":            os.path.join(self.local_printer_def_path, "CubeX.def.json"),
            "CubeX Duo definition file":        os.path.join(self.local_printer_def_path, "CubeXDuo.def.json"),
            "CubeX Trio definition file":       os.path.join(self.local_printer_def_path, "CubeXTrio.def.json"),
            "Cube definition file":             os.path.join(self.local_printer_def_path, "Cube.def.json"),
            "Cube 2nd Gen definition file":     os.path.join(self.local_printer_def_path, "Cube2.def.json"),
            "Cube 3rd Gen definition file":     os.path.join(self.local_printer_def_path, "Cube3.def.json"),
            "CubePro extruder 1 file":          os.path.join(self.local_extruder_path, "CubePro_extruder_0.def.json"),
            "CubePro extruder 2 file":          os.path.join(self.local_extruder_path, "CubePro_extruder_1.def.json"),
            "CubePro extruder 3 file":          os.path.join(self.local_extruder_path, "CubePro_extruder_2.def.json"),
            "CubeX extruder 1 file":            os.path.join(self.local_extruder_path, "CubeX_extruder_0.def.json"),
            "CubeX extruder 2 file":            os.path.join(self.local_extruder_path, "CubeX_extruder_1.def.json"),
            "CubeX extruder 3 file":            os.path.join(self.local_extruder_path, "CubeX_extruder_2.def.json"),
            "Cube extruder 1 file":             os.path.join(self.local_extruder_path, "Cube_extruder_0.def.json"),
            "Cube2 extruder 1 file":            os.path.join(self.local_extruder_path, "Cube2_extruder_0.def.json"),
            "Cube3 extruder 1 file":            os.path.join(self.local_extruder_path, "Cube3_extruder_0.def.json"),
            "Cube3 extruder 2 file":            os.path.join(self.local_extruder_path, "Cube3_extruder_1.def.json")
        }
        
        install_dir_locations = {
            "CubePro quality files":            os.path.join(self.local_quality_path, "CubePro"),
            "CubePro Duo quality files":        os.path.join(self.local_quality_path, "CubeProDuo"),
            "CubePro Trio quality files":       os.path.join(self.local_quality_path, "CubeProTrio"),
            "CubeX quality files":              os.path.join(self.local_quality_path, "CubeX"),
            "CubeX Duo quality files":          os.path.join(self.local_quality_path, "CubeXDuo"),
            "CubeX Trio quality files":         os.path.join(self.local_quality_path, "CubeXTrio"),
            "Cube quality files":               os.path.join(self.local_quality_path, "Cube"),
            "Cube 2nd Gen quality files":       os.path.join(self.local_quality_path, "Cube2"),
            "Cube 3rd Gen quality files":       os.path.join(self.local_quality_path, "Cube3")
        }

        # if some files are missing then return that this plugin as not installed
        
        for name, location in install_file_locations.items():
            if not os.path.isfile(location):
                Logger.log("i", self._name + " - " + name + " is NOT installed")
                return False

        for name, location in install_dir_locations.items():
            if not os.path.isdir(location):
                Logger.log("i", self._name + " - " + name + " are NOT installed")
                return False

        # if everything is there, return True
        Logger.log("i", self._name + " - All files ARE installed")
        return True

    ######################################################################
    ##  Gets a value from Cura's preferences
    ######################################################################
    def getPreferenceValue(self, preferenceName):
        return self._application.getPreferences().getValue(self._name + "/" + str(preferenceName))

    ######################################################################
    ## Sets a value to be stored in Cura's preferences file
    ######################################################################
    def setPreferenceValue(self, preferenceName, preferenceValue):
        if preferenceValue is None:
            return False
        name = self._name + "/" + str(preferenceName)
        Logger.log("i", self._name + " - Setting preference " + name + " to " + str(preferenceValue))
        if self.getPreferenceValue(preferenceName) is None:
            Logger.log("i", self._name + " - Adding preference " + name);
            self._application.getPreferences().addPreference(name, preferenceValue)

        self._application.getPreferences().setValue(name, preferenceValue)
        return self.getPreferenceValue(preferenceName) == preferenceValue

    ######################################################################
    ## Install the plugin files from the included zip file.
    ######################################################################
    def installPluginFiles(self):
        Logger.log("i", self._name + " - Installing printer files")

        try:
            zipdata = os.path.join(self.this_plugin_path, self._name + ".zip")
            Logger.log("i", self._name + " - Found zipfile: " + zipdata)
            with zipfile.ZipFile(zipdata, "r") as zip_ref:
                for info in zip_ref.infolist():
                    Logger.log("i", self._name + " - Found in zipfile: " + info.filename )
                    folder = None
                    if info.filename.endswith(".def.json"):
                        if "_extruder_" in str(info.filename):
                            folder = self.local_extruder_path
                        else:
                            folder = self.local_printer_def_path
                    elif info.filename.endswith(".cfg"):
                        folder = self.local_quality_path
                    elif info.filename.endswith(".stl"):
                        folder = self.local_meshes_path
                        # Cura doesn't always create the meshes folder by itself.
                        # We may have to manually create it if it doesn't exist
                        if not os.path.exists(folder):
                            os.mkdir(folder)

                    # now that we know where this file goes, extract it to the proper directory
                    if folder is not None:
                        extracted_path = zip_ref.extract(info.filename, path = folder)
                        permissions = os.stat(extracted_path).st_mode
                        os.chmod(extracted_path, permissions | stat.S_IEXEC) #Make these files executable.
                        Logger.log("i", self._name + " - Installing " + info.filename + " to " + extracted_path)

            # now that we've unzipped everything, check again to see if everything exists
            if self.isInstalled():
                # The files are now installed, so set the curr_version prefrences value
                if not self.setPreferenceValue("curr_version", CubePrinterPlugin.version):
                    Logger.log("e", self._name + " - Could not set curr_version preference")

        except: # Installing a new plugin should never crash the application so catch any random errors and show a message.
            Logger.logException("w", "An exception occurred in " + self._name + " while installing the files")
            message = Message(catalog.i18nc("@warning:status", self._name + " experienced an error installing the necessary files"))
            message.show()
    
