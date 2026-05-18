# build_monitor.spec — PyInstaller spec voor ZZPbot Monitor
#
# Build commando:
#   pip install pyinstaller pywin32 psutil requests
#   pyinstaller build_monitor.spec
#
# Output: dist/monitor.exe (single file, ~15-25MB)

import sys
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ['monitor.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'win32gui',
        'win32process',
        'win32api',
        'win32con',
        'pywintypes',
        'psutil',
        'requests',
        'urllib3',
        'certifi',
        'charset_normalizer',
        'idna',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'PIL',
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
        'scipy',
        'sklearn',
        'torch',
        'tensorflow',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='monitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,           # UPX compressie voor kleinere .exe
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,       # Consolevenster tonen (zodat gebruiker status ziet)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,          # Voeg hier een .ico pad toe voor een eigen icon
    # Versie-informatie (optioneel)
    version=None,
)
