# -*- mode: python ; coding: utf-8 -*-
"""
Obscura - PyInstaller Build Specification
Run: pyinstaller build_config/obscura.spec
"""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Get the base directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))

# Collect data files for transformers and torch
datas = [
    # Bundle the local model if it exists
    (os.path.join(BASE_DIR, 'models'), 'models'),
    # Include sessions file template
    (os.path.join(BASE_DIR, 'sessions.json'), '.') if os.path.exists(os.path.join(BASE_DIR, 'sessions.json')) else None,
]
datas = [d for d in datas if d is not None]

# Add transformers and gliner data files
datas += collect_data_files('transformers', include_py_files=True)
datas += collect_data_files('gliner', include_py_files=True)

# Hidden imports for ML libraries
hiddenimports = [
    'torch',
    'transformers',
    'gliner',
    'flask',
    'flask_cors',
    'huggingface_hub',
    'safetensors',
    'tokenizers',
    'numpy',
    'onnxruntime',
    'requests',
]
hiddenimports += collect_submodules('transformers')
hiddenimports += collect_submodules('gliner')

a = Analysis(
    [os.path.join(BASE_DIR, 'main.py')],
    pathex=[BASE_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'PIL',
        'cv2',
        'scipy.spatial.cKDTree',
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
    [],
    exclude_binaries=True,
    name='Obscura',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(BASE_DIR, 'build_config', 'icon.ico') if os.path.exists(os.path.join(BASE_DIR, 'build_config', 'icon.ico')) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Obscura',
)
