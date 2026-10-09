from glob import glob
import os
import shutil
import sys

# pre-flight must run before PyInstaller is imported, so a missing pyinstaller
# gets install instructions instead of a bare ModuleNotFoundError
import _preflight
_preflight.run_preflight()

import PyInstaller.__main__

if 'linux' not in sys.platform:
	print("this script is for Linux only!")
	exit()

def clean(additional=None):
	removethese = ['__pycache__','build','dist','*.spec']
	if additional:
		removethese.append(additional)
	for _object in removethese:
		target=glob(os.path.join('.', _object))
		for _target in target:
			try:
				if os.path.isdir(_target):
					shutil.rmtree(_target)
				else:
					os.remove(_target)
			except:
				print(f'Error deleting {_target}.')

THIS_VERSION = None
try:
	mainfile = open('duckypad_autoprofile.py')
	for line in mainfile:
		if "THIS_VERSION_NUMBER =" in line:
			THIS_VERSION = line.replace('\n', '').replace('\r', '').split("'")[-2]
	mainfile.close()
except Exception as e:
	print('build_linux exception:', e)
	exit()

if THIS_VERSION is None:
	print('could not find version number!')
	exit()

exe_file_name = "duckypad_autoprofile_" + THIS_VERSION + "_linux_x64"

clean(additional='duckypad_*.zip')

PyInstaller.__main__.run([
	'duckypad_autoprofile.py',
	'--noconsole',
	'--add-data=_icon.ico:.',
	'--hidden-import=PIL._tkinter_finder',
	'--collect-all',
	'pystray',
	'--name=' + exe_file_name,
])

def prune(parent, keep):
	if not os.path.isdir(parent):
		return
	for entry in os.listdir(parent):
		if entry == keep:
			continue
		target = os.path.join(parent, entry)
		if os.path.isdir(target):
			shutil.rmtree(target)
		else:
			os.remove(target)

# The GTK hook bundles every icon/cursor theme installed on the build machine
# (2.5+ GB); the app only needs the hicolor icon fallback and Adwaita.
share_dir = os.path.join('dist', exe_file_name, '_internal', 'share')
prune(os.path.join(share_dir, 'icons'), 'hicolor')
prune(os.path.join(share_dir, 'themes'), 'Adwaita')

readme_content = """\
Running this app on Linux:

1. Install the udev rules for the duckyPad first, or the app cannot open
   the device (see the README of the repo this came from).
2. Run the app:
   ./%s/duckypad_autoprofile

Full User Manuals:

duckyPad.com

""" % exe_file_name

with open(os.path.join('dist', exe_file_name, "README.txt"), "w") as f:
	f.write(readme_content)

shutil.make_archive(exe_file_name, 'zip', os.path.join('dist', exe_file_name))

clean()
