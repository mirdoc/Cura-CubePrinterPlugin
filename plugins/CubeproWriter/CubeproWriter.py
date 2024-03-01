####################################################################
#  CubeproWriter plugin for Ultimaker Cura
# 
#  This plugin enables Cura to export to the proprietary 3D Systems 
#  .cubepro print file format.
#
#  This plugin is usually bundled with Cura-CubePrinterPlugin
#  https://github.com/mirdoc/Cura-CubePrinterPlugin/
#
#  Written by mirdoc
#
#  This plugin is released under the terms of the LGPLv3 or higher.
#  The full text of the LGPLv3 License can be found here:
#  https://github.com/mirdoc/Cura-CubePrinterPlugin/blob/master/LICENSE
####################################################################

import sys

from io import StringIO, BytesIO, BufferedIOBase
from typing import cast, List, Optional, Dict

from UM.i18n import i18nCatalog
from UM.Message import Message
from UM.Logger import Logger
from UM.Mesh.MeshWriter import MeshWriter

from UM.Qt.Duration import DurationFormat
from UM.PluginRegistry import PluginRegistry

from cura.CuraApplication import CuraApplication
from cura.Utils.Threading import call_on_qt_thread
from PyQt6.QtCore import QObject

from .blowfish import Blowfish

catalog = i18nCatalog("cura")


class CubeproWriter(QObject, MeshWriter):
    def __init__(self) -> None:
        super().__init__(add_to_recent_files = False)
        self._plugin_name = "CubeproWriter"
        self._file_extension = "cubepro"
        self._version = "0.2.0"

        self._encryption_key = b"221BBakerMycroft"
            
        # Used to map specific values which depend on material type
        self._material_map = {
            "PLA": {
                "material_code": "209",     # PLA Black
                "gcode_M240_param": 2000
            },
            "ABS": {
                "material_code": "259",     # ABS Black
                "gcode_M240_param": 1400
            },
            "Nylon": {
                "material_code": "403",     # Nylon natural
                "gcode_M240_param": 1200
            },
            "PETG": {
                "material_code": "259",     # PETG - use ABS Black **EXPERIMENTAL**
                "gcode_M240_param": 1400
            }
        }

        # This array is used when parsing the g-code to skip lines
        self._skip_prefixes = [";", "G90", "G92", "M82", "M227 S128 P128"]

  
    ######################################################################
    ##  Used to set/change parameters when called by another plugin
    ######################################################################
    def setParams(self, params):
        param = params.get("plugin_name")
        if param is not None:
            self._plugin_name = param
        param = params.get("material_map")
        if param is not None:
            self._material_map = param
        param = params.get("encryption_key")
        if param is not None:
            self._encryption_key = param
        param = params.get("skip_prefixes")
        if param is not None:
            self._skip_prefixes = param


    ######################################################################
    ##  Called to output the file
    ######################################################################
    @call_on_qt_thread
    def write(self, stream: BufferedIOBase, nodes, mode=MeshWriter.OutputMode.BinaryMode) -> bool:
        try:
            return self.processOutput(stream, nodes, mode)
            
        except Exception as e:
            Logger.logException("w", "An exception occured in " + self._plugin_name + " while trying to create ." + self._file_extension + " file.")
            Logger.log("d", sys.exc_info()[:2])
            message = Message(catalog.i18nc("@warning:status", self._plugin_name + " experienced an error trying to create ." + self._file_extension + " file"))
            message.show()
            
            return False
            
    ######################################################################
    ##  Performs post-processing and encryption of print file stream
    ######################################################################
    def processOutput(self, stream: BufferedIOBase, nodes, mode) -> bool:
        if mode != MeshWriter.OutputMode.BinaryMode:
            error_message = self._plugin_name + " - Non-binary output mode is not supported."
            Logger.log("e", error_message)
            cubeMeshWriter.setInformation(catalog.i18nc("@error:not supported", error_message))
            return False

        if stream is None:
            error_message = self._plugin_name + " - Error while writing: no output stream."              
            Logger.log("e", error_message)
            return False

        # Setup constants
        _print_time_correction_factor = 2.0
        _newline = "\r\n"
        
        # The GCodeWriter plugin is always available since it is in the "required" list of plugins.
        gcode_writer = PluginRegistry.getInstance().getPluginObject("GCodeWriter")

        if gcode_writer is None:
            error_message = self._plugin_name + " - Could not load GCodeWriter plugin. Try to re-enable the plugin."
            Logger.log("e", error_message)
            cubeMeshWriter.setInformation(catalog.i18nc("@error:load", error_message))
            return False
        
        Logger.log("i", self._plugin_name + " - Writing started.")
        Logger.log("i", self._plugin_name + " - Fetching Cura's g-code...")
        gcode_writer = cast(MeshWriter, gcode_writer)

        gcode_in = StringIO()
        success = gcode_writer.write(gcode_in, None)
        
        # Getting the g-code failed so return with error
        if not success:
            cubeMeshWriter.setInformation(gcode_writer.getInformation())
            return False

        gcode_in.seek(0)
        gcode_out = BytesIO()
       
        Logger.log("i", self._plugin_name + " - Processing g-code...")
        
        initial_extruder = 1
        active_extruder = 1
        previous_extruder = -1
        
        application = CuraApplication.getInstance()
        global_stack = application.getMachineManager().activeMachine
        extruders = application.getExtruderManager().getUsedExtruderStacks()
        
        print_time_mins = round(float(application.getPrintInformation().currentPrintTime.getDisplayString(DurationFormat.Format.Seconds)) / 60 * _print_time_correction_factor)
        
        header_found = False
        command_buffer = ""

        for line in gcode_in:
            line = line.strip()
        
            # Skip unwanted lines
            line_skipped = False
            for prefix in self._skip_prefixes:
                if line.startswith(prefix):
                    line_skipped = True
                    continue
                    
            # Skip blank lines too
            if line_skipped or (not line):
                continue
            
            # Check for g-code header information and substitute in known values
            if line[0] == "^":
                # This is usually the first line from machine_gcode_start begins
                if line.startswith("^Firmware"):
                    header_found = True
                    
                # This is usually the last line from machine_gcode_start indicating end of the gcode header
                # Once this is found any pre-header commands that may have been stored away can be output
                elif line == "^InitComplete":
                    line = command_buffer + line
                
                elif line.startswith("^MaterialCode"):
                    extruder_num = int(line[14])
                    if extruder_num <= len(extruders) and extruders[extruder_num - 1].isEnabled:
                        material_mapped = self._material_map.get(extruders[extruder_num - 1].material.getMetaDataEntry("material"))
                        if material_mapped is None:
                            error_message = self._plugin_name + " - Unsupported filament type selected."
                            Logger.log("e", error_message)
                            cubeMeshWriter.setInformation(catalog.i18nc("@error", error_message))
                            return False
                        
                        line = f"^MaterialCodeE{extruder_num}:{material_mapped['material_code']}"

                elif line.startswith("^MaterialLength"):
                    extruder_num = int(line[16])
                    if extruder_num <= len(extruders) and extruders[extruder_num - 1].isEnabled:
                        line = f"^MaterialLengthE{extruder_num}:1" # The printer doesn't actually need to know how much

                elif line.startswith("^Time"):
                    line = f"^Time:{print_time_mins}"
            
            # T<int> sets active extruder.  CubePro does not use this as there are separate g-code commands for each extruder.
            # However we need to store it away so that subsequent extruder specific commands can specify the active extruder.
            elif line[0] == "T" and len(line) == 2:
                if previous_extruder == -1:
                    initial_extruder = int(line[1:]) + 1
                    
                previous_extruder = active_extruder
                active_extruder = int(line[1:]) + 1
                continue # skip this line
            
            # M240 command is used in the init g-code but it is not properly defined. It seems to be used on CubePro and Cube3
            # but the parameters are different. Cube3 params are X<int> Y<int> S<int>. CubePro params are S<int> however the
            # values are much higher on CubePro than on Cube3.
            # Different materials seem to use different values so we'll try to match it based on material in Extruder 1
            elif line.startswith("M240 S"):
                gcode_M240_param = self._material_map[extruders[0].material.getMetaDataEntry("material")].get("gcode_M240_param")
                if gcode_M240_param is not None:
                    line = "M240 S" + str()
                
            # M104 and M109 sets extruder temperature, with M109 triggering a pause until desired temperature is reached.
            # An optional paramater T<int> specifies an extruder number, and if omitted the active extruder will be used.
            # CubePro sets extruder temperature using M104, M204, and M304 for each extruder respectively and each command has 
            # an optional P1 parameter which if omitted will trigger a pause until desired temperature is reached.
            elif line.startswith("M104") or line.startswith("M109"):
                # if P parameter is present then this line is probably from start/end gcode so strip out P0 and leave P1 alone
                if "P0" in line:
                    line = line[:-3]
                elif "P1" not in line:
                    extruder_temp = 0
                    extruder_num = active_extruder
                    gcode_args = line.split(" ")
                    for gcode_arg in gcode_args:
                        if gcode_arg[0] == "S":                                   
                            extruder_temp = int(gcode_arg[1:])
                        elif gcode_arg[0] == "T":
                            extruder_num = int(gcode_arg[1]) + 1
                    add_P1 = (line[3] == "4") # if this is M104 then add P1
                    line = f"M{extruder_num}04 S{extruder_temp}"
                    if add_P1: 
                        line += " P1"
            
            # M106 sets fan speed with S<int> parameter which has a range of 0-255. CubePro uses a P<int> parameter with a range 
            # of 0-100. This converts to CubePro format M106 or change to M107 command (turn fan off) instead if fan speed is 0.
            elif line.startswith("M106 S"):
                fan_speed = round(float(line[6:]) / 2.55)
                if fan_speed == 0:
                    line = "M107"
                else:
                    line = f"M106 P{(fan_speed)}{_newline}G4 P2"
            
            # M141 and M191 sets chamber temperature, with M191 triggering a pause until desired temperature is reached.
            # CubePro uses M404 with optional P1 paramater which if omitted will trigger a pause until desired temperature
            # is reached.
            elif line.startswith("M141") or line.startswith("191"):
                # if P parameter is present then this line is probably from start/end gcode so strip out P0 and leave P1 alone
                if "P0" in line:
                    line = line[:-3]
                elif "P1" not in line:
                    build_volume_temperature = int(line[6:])
                    add_P1 = (line[2] == "4") # if this is M141 then add P1
                    line = f"M404 S{build_volume_temperature}"
                    if add_P1: 
                        line += " P1"
            
            # Cura sometimes throws extruder heat and fan commands in before the g-code start block and this will cause the
            # "Invalid Format" error when read by the printer, so we'll just store them away until after the header has
            # been written to the output stream
            if header_found:
                gcode_out.write((line + _newline).encode("utf-8"))
            else:
                command_buffer += line + _newline
        
        # If no header found throw an error
        if not header_found:
            error_message = self._plugin_name + " - No g-code header found. Has the machine start gcode been edited?"
            Logger.log("e", error_message)
            cubeMeshWriter.setInformation(catalog.i18nc("@error", error_message))
            return False
        
        # Encrypt gcode with blowfish and write to stream
        Logger.log("i", self._plugin_name + " - Encrypting with BlowFish cipher...")
        cipher = Blowfish(self._encryption_key)

        gcode_out.seek(0)
        padding = 0
        do_loop = True

        while do_loop:
            chunk = gcode_out.read(8)
            chunk_len = len(chunk)
            if chunk_len < 8:
                padding = 8 - chunk_len
                chunk = chunk.ljust(8, bytes([padding]))
                do_loop = False
                # Exit loop after write
                
            stream.write(cipher.encrypt(chunk, True))

        Logger.log("i", self._plugin_name + " - Writing completed successfully.")
        
        return True            
    
    