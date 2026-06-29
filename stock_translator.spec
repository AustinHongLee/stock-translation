# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from app.version import APP_VERSION

ROOT = Path(SPECPATH)
APP_NAME = "股票翻譯機"
VERSION_PARTS = tuple(int(part) for part in APP_VERSION.split("."))
VERSION_FILE = ROOT / "build" / "version_info.txt"
VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
VERSION_FILE.write_text(
    f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({VERSION_PARTS[0]}, {VERSION_PARTS[1]}, {VERSION_PARTS[2]}, 0),
    prodvers=({VERSION_PARTS[0]}, {VERSION_PARTS[1]}, {VERSION_PARTS[2]}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', 'AustinHongLee'),
          StringStruct('FileDescription', '股票翻譯機'),
          StringStruct('FileVersion', '{APP_VERSION}'),
          StringStruct('InternalName', '股票翻譯機'),
          StringStruct('OriginalFilename', '股票翻譯機.exe'),
          StringStruct('ProductName', 'Stock Translator'),
          StringStruct('ProductVersion', '{APP_VERSION}')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""",
    encoding="utf-8",
)

a = Analysis(
    ["app/web/server.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "app" / "ui" / "static"), "app/ui/static"),
        (str(ROOT / "data" / "stock_catalog.json"), "data"),
        (str(ROOT / "data" / "value_screener.json"), "data"),
        (str(ROOT / "data" / "stock_translator.sqlite3"), "data"),
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
    [],
    exclude_binaries=True,
    name=APP_NAME,
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
    version=str(VERSION_FILE),
    icon=str(ROOT / "assets" / "stock_translator.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)
