#####################################################################
# make_release.py
#####################################################################
#  python script to make a .curaplugin file for drag/drop
#  installation into cura as well as making the necessary zip file for
#  uploading to contribute.ultimaker.com for release in the cura marketplace
#
# Written by Tim Schoenmackers and mirdoc
#
# This source is released under the terms of the LGPLv3 or higher.
# The full text of the LGPLv3 License can be found here:
# https://github.com/mirdoc/Cura-CubePrinterPlugin/blob/master/LICENSE
#
#
# Requirements:
#  This tool calls the wkhtmltopdf tool (64 bit) to make the pdf documentation
#    Download the tool from: https://wkhtmltopdf.org/downloads.html and set
#    the WKHTMLTOPDF_DIR appropriately below
#
#  Additionally this tool requires python 3 and the grip package
#    (pip install grip)
#####################################################################
import os
import shutil
import zipfile
import json

PLUGIN_NAME = 'CubePrinterPlugin'

with open(f'../plugins/{PLUGIN_NAME}/plugin.json') as json_file:
    plugin_json = json.load(json_file)
    json_file.close()

RELEASE_DIR = os.path.abspath('../RELEASE/' + PLUGIN_NAME)
RELEASE_PLUGINS_DIR = os.path.abspath(os.path.join(RELEASE_DIR, 'files/plugins'))
CURA_PACKAGE_FILE = os.path.abspath('../RELEASE/' + PLUGIN_NAME + '-' + str(plugin_json["version"]) + '.curapackage')
ULTIMAKER_ZIP = os.path.abspath('../RELEASE/' + PLUGIN_NAME + '.zip')
PLUGIN_DIR = os.path.join(RELEASE_DIR, 'files/plugins/' + PLUGIN_NAME)

WKHTMLTOPDF_DIR = "c:/Program Files/wkhtmltopdf/bin/wkhtmltopdf.exe"

ALL_PLUGINS = [PLUGIN_NAME, 'CubeWriter', 'Cube3Writer', 'CubexWriter', 'CubeproWriter']

################################
## Step 1
## cleanup & make directories
################################

if(os.path.exists(RELEASE_DIR)):
    shutil.rmtree(RELEASE_DIR)

# delete existing files
for item in ['../README.html', '../README.pdf', CURA_PACKAGE_FILE,
             os.path.join(RELEASE_DIR, 'files/plugins/' + PLUGIN_NAME + '/' + PLUGIN_NAME + '.zip')]:
    print('Checking '+ os.path.abspath(item))
    if os.path.exists(os.path.abspath(item)):
        ('Deleting ' + os.path.abspath(item))
        os.remove(os.path.abspath(item))

# make new dirs
if not os.path.exists(RELEASE_DIR):
    os.makedirs(RELEASE_DIR)

dirs = [
    RELEASE_DIR,
    os.path.join(RELEASE_DIR, 'files'),
    os.path.join(RELEASE_DIR, RELEASE_PLUGINS_DIR)]
    
for item in ALL_PLUGINS:
    dirs.append(os.path.join(RELEASE_PLUGINS_DIR, item))

for item in dirs:
    if not os.path.exists(item):
        os.makedirs(item)

################################
## Step 2
## copy the cubepro printer definitions,
## materials, the platform stl file,
## and the quality files
################################
zipList = {
    'CubePro.def.json':             '../resources/definitions/',
    'CubeProDuo.def.json':          '../resources/definitions/',
    'CubeProTrio.def.json':         '../resources/definitions/',
    'Cube.def.json':                '../resources/definitions/',
    'Cube2.def.json':               '../resources/definitions/',
    'Cube3.def.json':               '../resources/definitions/',
    'CubeX.def.json':               '../resources/definitions/',
    'CubeXDuo.def.json':            '../resources/definitions/',
    'CubeXTrio.def.json':           '../resources/definitions/',
    'CubePro_extruder_0.def.json':  '../resources/extruders/',
    'CubePro_extruder_1.def.json':  '../resources/extruders/',
    'CubePro_extruder_2.def.json':  '../resources/extruders/',
    'Cube_extruder_0.def.json':     '../resources/extruders/',
    'Cube2_extruder_0.def.json':     '../resources/extruders/',
    'Cube3_extruder_0.def.json':    '../resources/extruders/',
    'Cube3_extruder_1.def.json':    '../resources/extruders/',
    'CubeX_extruder_0.def.json':    '../resources/extruders/',
    'CubeX_extruder_1.def.json':    '../resources/extruders/',
    'CubeX_extruder_2.def.json':    '../resources/extruders/',
    'CubePro_platform.stl':         '../resources/meshes/',
    'CubePro/':                     '../resources/quality/',
    'CubeProDuo/':                  '../resources/quality/',
    'CubeProTrio/':                 '../resources/quality/',
    'CubeX/':                       '../resources/quality/',
    'CubeXDuo/':                    '../resources/quality/',
    'CubeXTrio/':                   '../resources/quality/',
    'Cube/':                        '../resources/quality/',
    'Cube2/':                       '../resources/quality/',
    'Cube3/':                       '../resources/quality/'
}

for file_name, file_path in zipList.items():
    if file_name.endswith('/'):
        shutil.copytree(os.path.abspath(file_path + file_name), os.path.join(PLUGIN_DIR, file_name))
    else:
        shutil.copy2(os.path.abspath(file_path + file_name), PLUGIN_DIR)

################################
## Step 3
## zip the files copied above
################################
internal_zip_file_name = os.path.join(PLUGIN_DIR, PLUGIN_NAME + '.zip')
z = zipfile.ZipFile(internal_zip_file_name, 'w', zipfile.ZIP_DEFLATED)
for file_name, file_path in zipList.items():
    if file_name.endswith('/'):
        for root, dirs, files in os.walk(os.path.join(PLUGIN_DIR, file_name)):
            for file in files:
                z.write(os.path.join(PLUGIN_DIR, file_name, file), os.path.join(file_name, file))
    else:
        z.write(os.path.join(PLUGIN_DIR, file_name), os.path.basename(file_name));

################################
## Step 4
## now delete the files that were copied in Step 2
################################
for file_name, file_path in zipList.items():
    if file_name.endswith('/'):
        shutil.rmtree(os.path.join(PLUGIN_DIR, file_name))
    else:   
        os.remove(os.path.join(PLUGIN_DIR, file_name))

################################
## Step 5
## Create the README.pdf file from
## the markdown
################################
currDir = os.getcwd()
os.chdir('..')
os.system('python -m grip README.md --export README.html')
os.system('"{0}" {1} {2} {3}'.format(WKHTMLTOPDF_DIR, '--enable-local-file-access', 'README.html', os.path.join(PLUGIN_DIR,'README.pdf')))
shutil.copy2(os.path.join(PLUGIN_DIR, 'README.pdf'), '.')
os.chdir(currDir)

################################
## Step 6
## Copy the remaining plugin files
################################
for item in ALL_PLUGINS:
    shutil.copytree(os.path.abspath('../plugins/' + item),  os.path.join(RELEASE_PLUGINS_DIR, item), dirs_exist_ok = True)

################################
## Step 7
## Copy required files to the release directory
################################
remaining_files = [os.path.abspath('../LICENSE'),
                   os.path.abspath('../docs/icon.png'),
                   os.path.abspath('../resources/package.json')]

for file in remaining_files:
    shutil.copy2(file, RELEASE_DIR)

################################
## Step 8
## Zip up the plugin for release
################################
z = zipfile.ZipFile(CURA_PACKAGE_FILE, 'w', zipfile.ZIP_DEFLATED)
for root, dirs, files in os.walk(RELEASE_DIR):
    for file in files:
        z.write(os.path.join(root, file), os.path.join(root, file).replace(RELEASE_DIR, ""))


################################
## Step 9
## Make the ultimaker zip file for upload to contribute.ultimaker.com
################################
shutil.copy2(os.path.abspath('../LICENSE'), PLUGIN_DIR)

z = zipfile.ZipFile(ULTIMAKER_ZIP, 'w', zipfile.ZIP_DEFLATED)
for root, dirs, files in os.walk(RELEASE_PLUGINS_DIR):
    for file in files:
        print(os.path.join(root, file))
        z.write(os.path.join(root, file), os.path.join(root, file).replace(RELEASE_PLUGINS_DIR, ''))


################################
## Step 10
## Cleanup the files and directories
################################
shutil.rmtree(RELEASE_DIR)
