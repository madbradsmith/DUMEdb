import os
import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

SPEC_CONTENT = """# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None

datas = [
    ('dume/ui/inspector', 'dume/ui/inspector'),
    ('dume/schemas/presets', 'dume/schemas/presets'),
    ('data/registered_schemas.json', 'data'),
]

hiddenimports = [
    'dume',
    'dume.server',
    'dume.server.app',
    'dume.core.seed',
    'dume.core.record',
    'dume.proxy.routes',
    'dume.proxy.config',
    'dume.proxy.parser',
    'dume.scribe.committer',
    'dume.scribe.worker',
    'dume.scribe.ingest',
    'dume.storage.lmdb_engine',
    'dume.schema.dictionary',
    'dume.inference.grounded_engine',
    'dume.inference.local_llm',
    'dume.session.dispatcher',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'lmdb',
    'fastapi',
    'pydantic',
    'httpx',
    'anyio',
]

a = Analysis(
    ['dume/__main__.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='dumedb',
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
)
"""


def build():
    print("[DUME Build] Generating dumedb.spec...")
    spec_path = BASE_DIR / "dumedb.spec"
    with open(spec_path, "w", encoding="utf-8") as f:
        f.write(SPEC_CONTENT)

    print("[DUME Build] Running PyInstaller...")
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "dumedb.spec"]
    try:
        subprocess.run(cmd, check=True)
        print("[DUME Build] Build complete! Executable located in dist/")
    except subprocess.CalledProcessError as e:
        print(f"[DUME Build] PyInstaller build failed: {e}")
    except FileNotFoundError:
        print("[DUME Build] PyInstaller not installed in current environment. Install via 'pip install pyinstaller'")


if __name__ == "__main__":
    build()
