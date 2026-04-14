# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[('E:/miniconda/envs/p39/Library/bin', 'bin'), ('E:/miniconda/envs/p39/Library/plugins', 'plugins')],
    datas=[('E:/miniconda/envs/p39/Library/plugins/platforms', 'platforms'), ('E:/miniconda/envs/p39/Library/plugins/imageformats', 'imageformats'), ('E:/miniconda/envs/p39/Library/plugins/iconengines', 'iconengines'), ('resources', 'resources')],
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
    name='AnnotationCheck',
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
    icon=['resources\\icons\\bitbug_favicon.ico'],
)
