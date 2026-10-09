"""Build-time dependency pre-flight, shared by the _build_*.py scripts.

PyInstaller bundles whatever is importable on the build machine and says nothing
when a package is missing -- the exe just breaks at runtime. This check runs
before PyInstaller is imported, lists every missing package, and prints a single
command that installs them all.
"""
import importlib
import os
import sys

# import name -> pip package name (None = comes with Python or the system)
_BASE_CHECKS = {
    'hid': 'hidapi',
    'platformdirs': 'platformdirs',
    'pystray': 'pystray',
    'PIL': 'pillow',
    'certifi': 'certifi',
    'tkinter': None,
}

_PLATFORM_CHECKS = {
    'win32': {'ctwin32': 'ctwin32', 'pygetwindow': 'pygetwindow'},
    'darwin': {'AppKit': 'pyobjc', 'Quartz': 'pyobjc'},
    'linux': {'ewmh': 'ewmh', 'psutil': 'psutil', 'Xlib': 'python-xlib'},
}

TKINTER_HINTS = {
    'linux': [
        'sudo apt install python3-tk        # Debian/Ubuntu',
        'sudo dnf install python3-tkinter   # Fedora',
    ],
    'darwin': [
        'brew install python-tk             # Homebrew Python',
        '(python.org installers include tkinter already)',
    ],
}


def run_preflight():
    checks = dict(_BASE_CHECKS)
    checks.update(_PLATFORM_CHECKS.get(sys.platform, {}))

    missing = {}
    for module, pip_name in checks.items():
        try:
            importlib.import_module(module)
        except Exception:
            missing[module] = pip_name

    try:
        importlib.import_module('PyInstaller')
    except Exception:
        missing['PyInstaller'] = 'pyinstaller'

    if not missing:
        return

    pip_names = sorted({name for name in missing.values() if name})
    print('\nMissing build dependencies:')
    for module in sorted(missing):
        pip_name = missing[module]
        if pip_name:
            print(f'  {module:<12} (pip package: {pip_name})')
        else:
            print(f'  {module:<12} (system package, see below)')

    print('\nInstall them all at once:')
    # requirements.txt is the source of truth (pins, platform markers); the
    # absolute path keeps the command valid from any working directory.
    req_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'requirements.txt')
    if os.path.isfile(req_path):
        print(f'  pip install -r "{req_path}" pyinstaller')
    else:
        print(f'  pip install {" ".join(pip_names)}')

    if 'tkinter' in missing:
        print('\ntkinter is not a pip package; install it for your system:')
        for hint in TKINTER_HINTS.get(sys.platform, ['reinstall Python with tkinter included']):
            print(f'  {hint}')

    print('\nThe build cannot continue until these are importable (PyInstaller only')
    print('bundles what it can import -- a missing package means a broken exe).')
    sys.exit(1)


if __name__ == '__main__':
    run_preflight()
