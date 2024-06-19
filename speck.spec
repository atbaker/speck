# -*- mode: python ; coding: utf-8 -*-


speck_analysis = Analysis(
    ['app/main.py'],
    pathex=['./app'],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=['./app/hooks'],
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

worker_analysis = Analysis(
    ['app/worker.py'],
    pathex=['./app'],
    binaries=[],
    datas=[('./app/data/worker/broker/.keep', 'data/worker/broker')],
    hiddenimports=['config', 'emails.tasks'],
    hookspath=['./app/hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
worker_pyz = PYZ(worker_analysis.pure)
worker_exe = EXE(
    worker_pyz,
    worker_analysis.scripts,
    [],
    exclude_binaries=True,
    name='worker',
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
    worker_exe,
    worker_analysis.binaries,
    worker_analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='speck',
)
