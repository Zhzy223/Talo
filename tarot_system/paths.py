import sys
from pathlib import Path


def resource_path(rel: str) -> Path:
    """获取打包后或开发环境下的只读资源绝对路径。"""
    if getattr(sys, "_MEIPASS", None):
        base = Path(sys._MEIPASS)
        # PyInstaller 6.x onedir + macOS BUNDLE：数据放在 Contents/Resources/，
        # 但 _MEIPASS 指向 Contents/Frameworks/
        if sys.platform == "darwin" and (base.parent / "Resources").is_dir():
            base = base.parent / "Resources"
    else:
        base = Path(__file__).parent
    return base / rel


def user_data_dir() -> Path:
    """获取当前平台下的可写用户数据目录。"""
    if sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / "塔罗牌占卜"
    elif sys.platform == "win32":
        root = Path.home() / "AppData" / "Roaming" / "塔罗牌占卜"
    else:
        root = Path.home() / ".local" / "share" / "塔罗牌占卜"
    root.mkdir(parents=True, exist_ok=True)
    return root
