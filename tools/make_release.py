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
# https://github.com/mirdoc/Cura-CubeProPrinterPlugin/blob/master/LICENSE
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

with open('../plugins/CubeProPrinterPlugin/plugin.json') as json_file:
    plugin_json = json.load(json_file)
    json_file.close()

RELEASE_DIR = os.path.abspath('../RELEASE/CubeProPrinterPlugin')
CURA_PACKAGE_FILE = os.path.abspath('../RELEASE/CubeProPrinterPlugin-'+str(plugin_json["version"])+'.curapackage')
ULTIMAKER_ZIP = os.path.abspath('../RELEASE/CubeProPrinterPlugin.zip')
PLUGIN_DIR = os.path.join(RELEASE_DIR,'files/plugins/CubeProPrinterPlugin')

WKHTMLTOPDF_DIR = "c:/Program Files/wkhtmltopdf/bin/wkhtmltopdf.exe"

################################
## Step 1
## cleanup & make directories
################################

if(os.path.exists(RELEASE_DIR)):
    shutil.rmtree(RELEASE_DIR)

# delete existing files
for item in ['../README.html',
            '../README.pdf',
            os.path.join(RELEASE_DIR,'files/plugins/CubeProPrinterPlugin/CubeProPrinterPlugin.zip'),
            CURA_PACKAGE_FILE]:
    print('Checking '+ os.path.abspath(item))
    if os.path.exists(os.path.abspath(item)):
        #print('Deleting ' + os.path.abspath(item))
        os.remove(os.path.abspath(item))

# make new dirs
if not os.path.exists(RELEASE_DIR):
    os.makedirs(RELEASE_DIR)

dirs = [RELEASE_DIR,
        os.path.join(RELEASE_DIR,'files'),
        os.path.join(RELEASE_DIR,'files/plugins'),
        os.path.join(RELEASE_DIR,'files/plugins/CubeProPrinterPlugin')
        ]
for item in dirs:
    if not os.path.exists(item):
        os.makedirs(item)

################################
## Step 2
## copy the cubepro printer definitions,
## materials, the platform stl file,
## and the quality files
################################
copyList = ['../resources/definitions/CubePro.def.json',
           '../resources/definitions/CubeProDuo.def.json',
           '../resources/definitions/CubeProTrio.def.json',
           '../resources/extruders/CubePro_extruder_0.def.json',
           '../resources/extruders/CubePro_extruder_1.def.json',
           '../resources/extruders/CubePro_extruder_2.def.json',
           '../resources/meshes/CubePro_platform.stl']
for item in copyList:
    shutil.copy2(os.path.abspath(item),PLUGIN_DIR)

shutil.copytree(os.path.abspath('../resources/quality/CubePro'),
                os.path.join(PLUGIN_DIR,'CubePro'))

shutil.copytree(os.path.abspath('../resources/quality/CubeProDuo'),
                os.path.join(PLUGIN_DIR,'CubeProDuo'))

shutil.copytree(os.path.abspath('../resources/quality/CubeProTrio'),
                os.path.join(PLUGIN_DIR,'CubeProTrio'))

################################
## Step 3
## zip the files copied above
################################
internal_zip_file_name = os.path.join(PLUGIN_DIR,'CubeProPrinterPlugin.zip')
z = zipfile.ZipFile(internal_zip_file_name,'w', zipfile.ZIP_DEFLATED)
zipList = [os.path.join(PLUGIN_DIR,'CubePro.def.json'),
           os.path.join(PLUGIN_DIR,'CubeProDuo.def.json'),
           os.path.join(PLUGIN_DIR,'CubeProTrio.def.json'),
           os.path.join(PLUGIN_DIR,'CubePro_extruder_0.def.json'),
           os.path.join(PLUGIN_DIR,'CubePro_extruder_1.def.json'),
           os.path.join(PLUGIN_DIR,'CubePro_extruder_2.def.json'),
           os.path.join(PLUGIN_DIR,'CubePro_platform.stl')]
for item in zipList:
    z.write(item,os.path.basename(item));
path = os.path.join(PLUGIN_DIR,'CubePro')
for root, dirs, files in os.walk(path):
    for file in files:
        z.write(os.path.join(PLUGIN_DIR,'CubePro', file),os.path.join('CubePro',file))
path = os.path.join(PLUGIN_DIR,'CubeProDuo')
for root, dirs, files in os.walk(path):
    for file in files:
        z.write(os.path.join(PLUGIN_DIR,'CubeProDuo', file),os.path.join('CubeProDuo',file))
path = os.path.join(PLUGIN_DIR,'CubeProTrio')
for root, dirs, files in os.walk(path):
    for file in files:
        z.write(os.path.join(PLUGIN_DIR,'CubeProTrio', file),os.path.join('CubeProTrio',file))
################################
## Step 4
## now delete the files that were copied in Step 2
################################
for item in zipList:
    if os.path.exists(os.path.abspath(item)):
        #print('Deleting ' + os.path.abspath(item))
        os.remove(os.path.abspath(item))

shutil.rmtree(os.path.join(PLUGIN_DIR,'CubePro'))
shutil.rmtree(os.path.join(PLUGIN_DIR,'CubeProDuo'))
shutil.rmtree(os.path.join(PLUGIN_DIR,'CubeProTrio'))
################################
## Step 5
## Create the README.pdf file from
## the markdown
################################
currDir = os.getcwd()
os.chdir('..')
os.system('python -m grip README.md --export README.html')
os.system('"{0}" {1} {2} {3}'.format(WKHTMLTOPDF_DIR,'--enable-local-file-access','README.html', os.path.join(PLUGIN_DIR,'README.pdf')))
shutil.copy2(os.path.join(PLUGIN_DIR,'README.pdf'), '.')
os.chdir(currDir)

################################
## Step 6
## Copy the remaining plugin files
################################
src_dir=os.path.abspath('../plugins/CubeProPrinterPlugin')
src_files = os.listdir(src_dir)
for file_name in src_files:
    full_file_name = os.path.join(src_dir, file_name)
    if os.path.isfile(full_file_name):
        shutil.copy2(full_file_name, PLUGIN_DIR)

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
z = zipfile.ZipFile(CURA_PACKAGE_FILE,'w', zipfile.ZIP_DEFLATED)
for root, dirs, files in os.walk(RELEASE_DIR):
    for file in files:
        z.write(os.path.join(root,file),os.path.join(root,file).replace(RELEASE_DIR, ""))


################################
## Step 9
## Make the ultimaker zip file for upload to contribute.ultimaker.com
################################
shutil.copy2(os.path.abspath('../LICENSE'), PLUGIN_DIR)

z = zipfile.ZipFile(ULTIMAKER_ZIP,'w', zipfile.ZIP_DEFLATED)
for root, dirs, files in os.walk(PLUGIN_DIR):
    for file in files:
        print(os.path.join(root,file))
        z.write(os.path.join(root,file),os.path.join(root,file).replace(PLUGIN_DIR, "CubeProPrinterPlugin"))


################################
## Step 10
## Cleanup the files and directories
################################
shutil.rmtree(RELEASE_DIR)
