# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT, BUNDLE

project_root = Path(SPECPATH)
package_dir = project_root / "tarot_system"

a = Analysis(
    [str(package_dir / "gui.py")],
    pathex=[str(project_root), str(package_dir)],
    binaries=[],
    datas=[
        (str(package_dir / "data"), "data"),
        (str(package_dir / "assets"), "assets"),
    ],
    hiddenimports=[
        "customtkinter",
        "PIL",
        "PIL._imagingtk",
        "PIL._tkinter_finder",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "numpy", "pandas", "scipy"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

# macOS 用 .app bundle，Windows 用单文件夹
code_name = "tarot"
app_name = "塔罗牌占卜"

if sys.platform == "darwin":
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=code_name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    app = BUNDLE(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        name=f"{app_name}.app",
        icon=None,
        bundle_identifier="com.helel.tarot",
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=code_name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name=app_name,
    )
