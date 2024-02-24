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
# The GcodeWriter plugin source can be found here:
# https://github.com/Ultimaker/Cura/tree/master/plugins/GCodeWriter
#
# This plugin is released under the terms of the LGPLv3 or higher.
# The full text of the LGPLv3 License can be found here:
# https://github.com/mirdoc/Cura-CubePro-Printer-Plugin/blob/master/LICENSE
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



from .blowfish import Blowfish

catalog = i18nCatalog("cura")


class CubeProPrinterPlugin(QObject, MeshWriter, Extension):
    ######################################################################
    ##  The version number of this plugin
    ##  Please ensure that the version number is the same match in all
    ##  three of the following Locations:
    ##    1) below (this file)
    ##    2) .\plugin.json
    ##    3) ..\..\resources\package.json
    ######################################################################
    version = "0.1.0"
    _website_url = "https://github.com/mirdoc/Cura-Cube-Printer-Plugin"

    ######################################################################
    ##  Dictionary that defines maps Cura material GUIDs to a CubePro
    ##  style material code.
    ##
    ##  CubePro material codes specify a material type and a material
    ##  color, but so long as the material type matches the catridge
    ##  that is in the printer it will print regardless of the color.
    ##
    ##  Therefore we have mapped some of Cura's Generic material types
    ##  to the equivalent material type in black.
    ##
    ##  There is much more to do here and probably a much better way
    ##  of mapping materials but this will do for now.
    ##
    ##  Note I have not tried printing with PETG yet but I assume that
    ##  if you have a catridge chip for ABS and run PETG filament it
    ##  should work.  For now consider this experimental!
    ######################################################################
    _MATERIAL_MAP = {"2780b345-577b-4a24-a2c5-12e6aad3e690": "259", # abs black         cube3: 137?
                     "0ff92885-617b-4144-a03c-9989872454bc": "209", # pla black         cube3: 87?
                     "283d439a-3490-4481-920c-c51d8cdecf9c": "403", # nylon natural
                     "69386c85-5b6c-421a-bec5-aeb1fb33f060": "259"} # petg - use abs black

    ######################################################################
    ##  These arrays are used when parsing the g-code to skip lines
    ##  with incompatible or unwanted/unneeded commands.  
    ######################################################################
    _SKIP_PREFIXES_ALL = [";", "M228", "M227", "T0", "T1", "T2", "M109", "G90", "G92", "M82"]
    _SKIP_PREFIXES_ONCE = ["M141", "M104", "M107"]
    

    ######################################################################
    ##  Cura seems to massively underestimate print times for these
    ##  printers so this is a correction factor.  This makes it more
    ##  accurate but it's still wrong a lot of the time.
    ######################################################################
    _PRINT_TIME_CORRECTION_FACTOR = 2.0

    ######################################################################
    ##  CubePro g-code is encoded with Windows style new lines
    ######################################################################
    _NEWLINE = "\r\n"
    
    ######################################################################
    ##  This is the encryption key used for the Blowfish cipher
    ######################################################################
    _ENCRYPTION_KEY = b"221BBakerMycroft"

    def __init__(self) -> None:
        super().__init__(add_to_recent_files = False)
        self._application = Application.getInstance()
        
        self._name = "CubeProPrinterPlugin"
        
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
            Logger.log("i", self._name + " - Some CubeProPrinterPlugin files are NOT installed")
            plugin_install_required = True

        # if we need to install the files, then do so
        if plugin_install_required:
            self.installPluginFiles()

        self.addMenuItem(catalog.i18nc("@item:inmenu", "Help "), self.showHelp)
        self.addMenuItem(catalog.i18nc("@item:inmenu", self._name + " Version " + CubeProPrinterPlugin.version), self.openPluginWebsite)
        
        MimeTypeDatabase.addMimeType(
            MimeType(
                name="application/x-cubepro",
                comment="CubePro Print File",
                suffixes=["cubepro"]
            )
        )
        
        # finally save the cura.cfg file
        Logger.log("i", self._name + " - Writing to " + str(Resources.getStoragePath(Resources.Preferences, self._application.getApplicationName() + ".cfg")))
        self._application.getPreferences().writeToFile(Resources.getStoragePath(Resources.Preferences, self._application.getApplicationName() + ".cfg"))

    ######################################################################
    ##  Performs the writing of the proprietary .cubepro print file
    ######################################################################
    @call_on_qt_thread
    def write(self, stream: BufferedIOBase, nodes, mode=MeshWriter.OutputMode.BinaryMode) -> bool:
        try:
            if mode != MeshWriter.OutputMode.BinaryMode:
                error_message = self._name + " - Non-binary output mode is not supported."
                Logger.log("e", error_message)
                self.setInformation(catalog.i18nc("@error:not supported", error_message))
                return False

            if stream is None:
                error_message = self._name + " - Error while writing: no output stream."              
                Logger.log("e", error_message)
                return False

            # The GCodeWriter plugin is always available since it is in the "required" list of plugins.
            gcode_writer = PluginRegistry.getInstance().getPluginObject("GCodeWriter")

            if gcode_writer is None:
                error_message = self._name + " - Could not load GCodeWriter plugin. Try to re-enable the plugin."
                Logger.log("e", error_message)
                self.setInformation(catalog.i18nc("@error:load", error_message))
                return False
            
            Logger.log("i", self._name + " - Writing started.")
            Logger.log("i", self._name + " - Fetching Cura's g-code...")
            gcode_writer = cast(MeshWriter, gcode_writer)

            gcode_in = StringIO()
            success = gcode_writer.write(gcode_in, None)
            
            # Writing the g-code failed so return with error
            if not success:
                self.setInformation(gcode_writer.getInformation())
                return False

            flow_rate = -1
            flow_rate_set = False
            
            Logger.log("i", self._name + " - Generating CubePro header and init g-code...")
        
            gcode_in.seek(0)
            gcode_out = BytesIO()
            gcode_out.write(self._generateCubeProHeader().encode("utf-8"))
           
            Logger.log("i", self._name + " - Processing g-code...")

            for line in gcode_in:
                line = line.strip()
            
                # Skip unwanted lines
                line_skipped = False
                for prefix in self._SKIP_PREFIXES_ALL:
                    if line.startswith(prefix):
                        line_skipped = True
                        continue
                for prefix in self._SKIP_PREFIXES_ONCE:     # At the start of g-code Cura inserts commands to set build volume temp, 
                    if line.startswith(prefix):             # extruder temp, and turn fans off but these are already set in the init
                        line_skipped = True                 # g-code that follows the header so we'll just strip them out 
                        self._SKIP_PREFIXES_ONCE.remove(prefix)
                        continue
                if line_skipped or (not line):
                    continue

                # Check if something resembling a CubePro header is present if so return with error
                elif line.startswith("^Firmware"):
                    error_message = self._name + " - Something that looks like a CubePro header found. Has this g-code already been processed?"
                    Logger.log("e", error_message)
                    self.setInformation(catalog.i18nc("@error", error_message))
                    return False

                # Convert fan speed from 0-255 to 0-100 range, or issue M107 command instead if fan speed is 0
                elif line.startswith("M106"):
                    fan_speed = round(float(line[6:]) / 2.55)
                    if fan_speed == 0:
                        line = "M107"
                    else:
                        line = f"M106 P{int(fan_speed)}{self._NEWLINE}G4 P2"

                # Change M141 to M404 for setting heating chamber temperature
                elif line.startswith("M141 "):
                    build_volume_temperature = int(line[6:])
                    line = f"M404 S{build_volume_temperature} P1"

                # If this is M108 then acknowledge flow rate has been set and store it away
                elif line.startswith("M108 "):
                    flow_rate = float(line[6:])
                    flow_rate_set = True

                # If this is an extruder-off command then we want to check to if flow rate has been set before next extruder-on command
                elif line.startswith("M103"):
                    flow_rate_set = False

                # If this is an extruder-on command and flow rate has not been set we need to issue a M108 command to set flow rate
                elif line.startswith("M101"):
                    if not flow_rate_set and flow_rate > -1:
                        line = f"M108 S{flow_rate:.1f}{self._NEWLINE}{line}"

                gcode_out.write((line + self._NEWLINE).encode("utf-8"))
            
            # Add end gcode stuff
            gcode_out.write(self._generateCubeProFooter().encode("utf-8"))
            
            # Encrypt gcode with blowfish and write to stream
            Logger.log("i", self._name + " - Encrypting with BlowFish cipher...")
            cipher = Blowfish(self._ENCRYPTION_KEY)

            gcode_out.seek(0)
            padding = 0
            do_loop = True

            while do_loop:
                chunk = gcode_out.read(8)
                chunk_len = len(chunk)
                if chunk_len < 8:
                    padding = 8 - chunk_len
                    chunk = chunk.ljust(8, bytes([padding]))
                    do_loop = False  # Exit loop 
                    
                stream.write(cipher.encrypt(chunk, True))

            # stream.write(gcode_out.getvalue()) -- write unencrypted g-code to stream for debugging purposes
            
            Logger.log("i", self._name + " - Writing completed successfully.")
            
            return True
        except Exception as e:
            Logger.logException("w", "An exception occured in " + self._name + " while trying to create .cubepro file.")
            Logger.log("d",sys.exc_info()[:2])
            message = Message(catalog.i18nc("@warning:status", self._name + " experienced an error trying to create .cubepro file"))
            message.show()
            
            return False

    ######################################################################
    ##  function to generate a string containing the proprietary CubePro 
    ##  g-code header and init g-code 
    ######################################################################
    def _generateCubeProHeader(self):
        application = CuraApplication.getInstance()
        machine_manager = application.getMachineManager()
        global_stack = machine_manager.activeMachine
        extruders = global_stack.extruderList
        print_information = application.getPrintInformation()
        
        material_codes = ["-1", "-1", "-1"]
        material_lengths = ["0", "0", "0"]
        
        num_extruders = len(extruders)
        if num_extruders > 3: 
            Logger.log("i", f"There are apparently {num_extruders} extruders... that's weird...")
            num_extruders = 3
            
        for i in range(num_extruders - 1):
            if extruders[i].isEnabled:
                material_codes[i] = self._MATERIAL_MAP.get(extruders[i].material.getMetaData().get("GUID"), "-1")
                material_lengths[i] = "1"
                
        layer_height = global_stack.getProperty("layer_height", "value")
        layer_count = 1 # TODO: figure out how to retrieve this

        # Cura seems to grossly underestimate print times for this printer so we'll adjust it
        print_time_mins = round(float(print_information.currentPrintTime.getDisplayString(DurationFormat.Format.Seconds)) / 60 * self._PRINT_TIME_CORRECTION_FACTOR)

        header = f"^Firmware:V1.03A{self._NEWLINE}^Minfirmware:V1.00{self._NEWLINE}^DRM:000000000000{self._NEWLINE}^PrinterModel:CUBEPRO{self._NEWLINE}"
        header += f"^MaterialCodeE1:{material_codes[0]}{self._NEWLINE}^MaterialCodeE2:{material_codes[1]}{self._NEWLINE}^MaterialCodeE3:{material_codes[2]}{self._NEWLINE}"
        header += f"^MaterialLengthE1: {material_lengths[0]}{self._NEWLINE}^MaterialLengthE2: {material_lengths[1]}{self._NEWLINE}^MaterialLengthE3: {material_lengths[2]}{self._NEWLINE}"
        header += f"^LayerCount: {layer_count}{self._NEWLINE}^LayerHeight:{layer_height}{self._NEWLINE}^Version:1494{self._NEWLINE}^Time:{print_time_mins}{self._NEWLINE}"
        
        # Add CubePro init Gcode to header here
        build_volume_temperature = global_stack.getProperty("build_volume_temperature", "value")

        # At this stage I'm assuming the first extruder in the extruder list will usually be the first to be initialised...
        if material_codes[0] == "209":   # PLA
            if layer_height >= 0.1 and layer_height < 0.2:
                gcode_destring_init = f"M227 P100 S100 G200 F700{self._NEWLINE}M228 P0 S100{self._NEWLINE}"
                gcode_M232_value = "P2000 S2000"
                gcode_destring_startprint = f"M228 P0 S100{self._NEWLINE}M227 P100 S100 G200 F700{self._NEWLINE}"
            else:                        # default to values for 0.2 layer height
                gcode_destring_init = f"M227 P150 S150 G200 F200{self._NEWLINE}M228 P0 S150{self._NEWLINE}"
                gcode_M232_value = "P2500 S2500"
                gcode_destring_startprint = f"M228 P0 S250{self._NEWLINE}M227 P250 S250 G200 F700{self._NEWLINE}"
            gcode_M240_value = "2000"
        elif material_codes[0] == "259": # ABS
            gcode_destring_init = f"M227 P150 S150 G200 F200{self._NEWLINE}M228 P0 S150{self._NEWLINE}"   
            gcode_M240_value = "1400"
            gcode_destring_startprint = f"M228 P0 S250{self._NEWLINE}M227 P250 S250 G300 F700{self._NEWLINE}"
        elif material_codes[0] == "403": # Nylon
            gcode_destring_init = f"M227 P250 S250 G200 F700{self._NEWLINE}M228 P0 S250{self._NEWLINE}"
            gcode_M240_value = "1200"
            gcode_destring_startprint = f"M228 P0 S150{self._NEWLINE}M227 P150 S150 G200 F200{self._NEWLINE}"
        else:                            # Default to PLA values here for now but probably needs error handling lol
            gcode_destring_init = f"M227 P150 S150 G200 F200{self._NEWLINE}M228 P0 S150{self._NEWLINE}" 
            gcode_M240_value = "2000"
            gcode_destring_startprint = f"M228 P0 S250{self._NEWLINE}M227 P250 S250 G200 F700{self._NEWLINE}"

        extruder_temp = extruders[0].getProperty("default_material_print_temperature", "value")

        header += f"M404 S{build_volume_temperature}{self._NEWLINE}"
        header += gcode_destring_init
        header += f"M231 P0 S0{self._NEWLINE}M232 {gcode_M232_value}{self._NEWLINE}M233 P1850{self._NEWLINE}M106 P100{self._NEWLINE}G4 P2{self._NEWLINE}M601 P2 S30 F5{self._NEWLINE}M228 P0 S1{self._NEWLINE}M227 P1 S1 G1000 F1000{self._NEWLINE}"
        header += f"M240 S{gcode_M240_value}{self._NEWLINE}"
        header += f"M104 S{round(extruder_temp * 0.8)} P1{self._NEWLINE}M104 S{extruder_temp} P1{self._NEWLINE}"
        header += f"G1 X108.000 Y136.000 Z5.2000 F9000.0{self._NEWLINE}G1 X108.000 Y161.000 Z5.2000 F9000.0{self._NEWLINE}G1 X108.000 Y157.000 Z5.2000 F9000.0{self._NEWLINE}"
        header += f"M104 S{extruder_temp}{self._NEWLINE}"
        header += f"M551 P1500 S50{self._NEWLINE}G1 X108.000 Y136.000 Z5.2000 F9000.0{self._NEWLINE}M601 P2 S30 F5{self._NEWLINE}"
        header += f"M107{self._NEWLINE}M404 S{build_volume_temperature} P1{self._NEWLINE}M107{self._NEWLINE}^InitComplete{self._NEWLINE}#Vector T22{self._NEWLINE}"
        header += gcode_destring_startprint

        return header
        
    ######################################################################
    ##  function to generate a string containing the end g-code
    ######################################################################
    def _generateCubeProFooter(self):
        footer = f"M103{self._NEWLINE}M561 P400 S500{self._NEWLINE}G4 P1{self._NEWLINE}M104 S0{self._NEWLINE}M204 S0{self._NEWLINE}M304 S0"
        
        return footer

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

        if StrictVersion(installedVersion) == StrictVersion(CubeProPrinterPlugin.version):
            # if the version numbers match, then return true
            Logger.log("i", self._name + " - Versions match: " + installedVersion + " matches " + CubeProPrinterPlugin.version)
            return True
        else:
            Logger.log("i", self._name + " - The currently installed version: " + installedVersion + " doesn't match this version: " + CubeProPrinterPlugin.version)
            return False

    ######################################################################
    ## Check to see if the plugin files are all installed
    ## Return True if all files are installed, false if they are not
    ######################################################################
    def isInstalled(self):
        CubeProDefFile = os.path.join(self.local_printer_def_path,"CubePro.def.json")
        CubeProDuoDefFile = os.path.join(self.local_printer_def_path,"CubeProDuo.def.json")
        CubeProTrioDefFile = os.path.join(self.local_printer_def_path,"CubeProTrio.def.json")
        CubeProExtruder1DefFile = os.path.join(self.local_extruder_path,"CubePro_extruder_0.def.json")
        CubeProExtruder2DefFile = os.path.join(self.local_extruder_path,"CubePro_extruder_1.def.json")
        CubeProExtruder3DefFile = os.path.join(self.local_extruder_path,"CubePro_extruder_2.def.json")
        CubeProQualityDir = os.path.join(self.local_quality_path,"CubePro")
        CubeProDuoQualityDir = os.path.join(self.local_quality_path,"CubeProDuo")
        CubeProTrioQualityDir = os.path.join(self.local_quality_path,"CubeProTrio")

        # if some files are missing then return that this plugin as not installed
        if not os.path.isfile(CubeProDefFile):
            Logger.log("i", self._name + " - CubePro definition file is NOT installed")
            return False
        if not os.path.isfile(CubeProDuoDefFile):
            Logger.log("i", self._name + " - CubePro Duo definition file is NOT installed")
            return False
        if not os.path.isfile(CubeProTrioDefFile):
            Logger.log("i", self._name + " - CubePro Trio definition file is NOT installed")
            return False
        if not os.path.isfile(CubeProExtruder1DefFile):
            Logger.log("i", self._name + " - CubePro extruder 1 file is NOT installed")
            return False
        if not os.path.isfile(CubeProExtruder2DefFile):
            Logger.log("i", self._name + " - CubePro extruder 2 file is NOT installed")
            return False
        if not os.path.isfile(CubeProExtruder3DefFile):
            Logger.log("i", self._name + " - CubePro extruder 3 file is NOT installed")
            return False
        if not os.path.isdir(CubeProQualityDir):
            Logger.log("i", self._name + " - CubePro quality files are NOT installed")
            return False
        if not os.path.isdir(CubeProDuoQualityDir):
            Logger.log("i", self._name + " - CubePro Duo quality files are NOT installed")
            return False
        if not os.path.isdir(CubeProTrioQualityDir):
            Logger.log("i", self._name + " - CubePro Trio quality files are NOT installed")
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
            zipdata = os.path.join(self.this_plugin_path, "CubeProPrinterPlugin.zip")
            Logger.log("i", self._name + " - Found zipfile: " + zipdata)
            with zipfile.ZipFile(zipdata, "r") as zip_ref:
                for info in zip_ref.infolist():
                    Logger.log("i", self._name + " - Found in zipfile: " + info.filename )
                    folder = None
                    if (info.filename == "CubePro.def.json" or
                       info.filename == "CubeProDuo.def.json" or
                       info.filename == "CubeProTrio.def.json"):
                        folder = self.local_printer_def_path
                    elif (info.filename == "CubePro_extruder_0.def.json" or
                          info.filename == "CubePro_extruder_1.def.json" or
                          info.filename == "CubePro_extruder_2.def.json"):
                        folder = self.local_extruder_path
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
                if not self.setPreferenceValue("curr_version", CubeProPrinterPlugin.version):
                    Logger.log("e", self._name + " - Could not set curr_version preference")

        except: # Installing a new plugin should never crash the application so catch any random errors and show a message.
            Logger.logException("w", "An exception occurred in " + self._name + " while installing the files")
            message = Message(catalog.i18nc("@warning:status", self._name + " experienced an error installing the necessary files"))
            message.show()
    
