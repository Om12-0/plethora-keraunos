# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_dynamic_libs

block_cipher = None

# Collect native llama.cpp DLLs
llama_binaries = collect_dynamic_libs('llama_cpp')

a = Analysis(
    ['keraunos.py'],
    pathex=['.'],
    binaries=llama_binaries,
    datas=[
        ('assets', 'assets'),
        ('keraunosICON.png', '.'),
        ('models/smollm2-135m-instruct-q4_k_m.gguf', 'models'),
    ],
    hiddenimports=[
        'keraunos',
        'keraunos.catalog',
        'keraunos.compiler',
        'keraunos.config',
        'keraunos.display',
        'keraunos.drift',
        'keraunos.dsc_exporter',
        'keraunos.executor',
        'keraunos.git_store',
        'keraunos.registry_map',
        'keraunos.scanner',
        'keraunos.schema',
        'keraunos.slm',
        'keraunos.tools',
        'keraunos.updater',
        'keraunos.ui',
        'keraunos.ui.app',
        'keraunos.ui.styles',
        'rapidfuzz',
        'llama_cpp',
        'PySide6',
        'git',
        'pydantic',
        'yaml',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='keraunos',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=r'assets\keraunos.ico',
    version='version_info.txt',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='keraunos',
)
