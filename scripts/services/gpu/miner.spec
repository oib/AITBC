# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['gpu_miner_host.py'],
    pathex=['/opt/aitbc/scripts/services/gpu'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'httpx',
        'httpx._transports.default',
        'httpx._transports.http2',
        'httpx._transports.http11',
        'httpx._transports.asgi',
        'httpx._transports.wsgi',
        'httpx._client',
        'httpx._transports',
        'httpx._exceptions',
        'httpx._content',
        'httpx._urls',
        'h11',
        'h2',
        'certifi',
        'sniffio',
        'idna',
        'charset_normalizer',
        'anyio',
        'anyio._backends._asyncio',
        'anyio._backends._trio',
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='aitbc-miner-debian',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None
)
