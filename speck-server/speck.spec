# -*- mode: python ; coding: utf-8 -*-


speck_analysis = Analysis(
    ['speck/main.py'],
    pathex=['./speck'],
    binaries=[('./speck/llamafile', '.')],
    datas=[],
    hiddenimports=[],
    hookspath=['./speck/hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
speck_pyz = PYZ(speck_analysis.pure)
speck_exe = EXE(
    speck_pyz,
    speck_analysis.scripts,
    [],
    exclude_binaries=True,
    name='speck',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    speck_exe,
    speck_analysis.binaries,
    speck_analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='speck',
)
