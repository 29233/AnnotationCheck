# -*- mode: python ; coding: utf-8 -*-

env_root = r'E:\miniconda\envs\p39'

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[
        (os.path.join(env_root, 'Library', 'bin'), 'bin'),
        (os.path.join(env_root, 'Library', 'plugins'), 'plugins'),
    ],
    datas=[
        (os.path.join(env_root, 'Library', 'plugins', 'platforms'), 'platforms'),
        (os.path.join(env_root, 'Library', 'plugins', 'imageformats'), 'imageformats'),
        (os.path.join(env_root, 'Library', 'plugins', 'iconengines'), 'iconengines'),
        ('resources', 'resources'),
        ('config.json', '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AnnotationCheckv1.3',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['resources/icons/bitbug_favicon.ico'],
)
