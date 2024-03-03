#####################################################################
#  set_version.py
#####################################################################
#  python script to update plugin version number in all source files
#
#  Written by mirdoc
#
#  This source is released under the terms of the LGPLv3 or higher.
#  The full text of the LGPLv3 License can be found here:
#  https://github.com/mirdoc/Cura-CubePrinterPlugin/blob/master/LICENSE
#####################################################################

import sys, re, os

PLUGIN_VERSION = '2.0.1'

if len(sys.argv) > 1:
    PLUGIN_VERSION = sys.argv[1]

source_files = [
    '../resources/package.json',
    '../plugins/CubePrinterPlugin/plugin.json',
    '../plugins/CubePrinterPlugin/CubePrinterPlugin.py',
    '../plugins/CubeWriter/plugin.json',
    '../plugins/CubeWriter/CubeWriter.py',
    '../plugins/CubeproWriter/plugin.json',
    '../plugins/CubeproWriter/CubeproWriter.py',
    '../plugins/CubexWriter/plugin.json',
    '../plugins/CubexWriter/CubexWriter.py',
    '../plugins/Cube3Writer/plugin.json',
    '../plugins/Cube3Writer/Cube3Writer.py'
]

for file_path in source_files:
        with open(os.path.abspath(file_path), 'r') as file:
            content = file.read()
            if file_path.endswith('.py'):
                new_content = re.sub(r'version\s*=\s*"\d+\.\d+\.\d+"', f'version = "{PLUGIN_VERSION}"', content)
            elif file_path.endswith('package.json'):
                new_content = re.sub(r'"package_version"\s*:\s*"\d+\.\d+\.\d+"', f'"package_version": "{PLUGIN_VERSION}"', content)
            elif file_path.endswith('.json'):
                new_content = re.sub(r'"version"\s*:\s*"\d+\.\d+\.\d+"', f'"version": "{PLUGIN_VERSION}"', content)
            with open(file_path, 'w') as file:
                file.write(new_content)