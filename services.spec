# -*- mode: python ; coding: utf-8 -*-


server_analysis = Analysis(
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
server_pyz = PYZ(server_analysis.pure)
server_exe = EXE(
    server_pyz,
    server_analysis.scripts,
    [],
    exclude_binaries=True,
    name='speck-server',
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
    binaries=[('./app/llamafile', '.')],
    datas=[],
    hiddenimports=['config', 'emails.tasks', 'setup.tasks'],
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
    name='speck-worker',
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

scheduler_analysis = Analysis(
    ['app/scheduler.py'],
    pathex=['./app'],
    binaries=[],
    datas=[],
    hiddenimports=['config', 'emails.tasks', 'setup.tasks'],
    hookspath=['./app/hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
scheduler_pyz = PYZ(scheduler_analysis.pure)
scheduler_exe = EXE(
    scheduler_pyz,
    scheduler_analysis.scripts,
    [],
    exclude_binaries=True,
    name='speck-scheduler',
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
    server_exe,
    server_analysis.binaries,
    server_analysis.datas,
    worker_exe,
    worker_analysis.binaries,
    worker_analysis.datas,
    scheduler_exe,
    scheduler_analysis.binaries,
    scheduler_analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='services',
)
