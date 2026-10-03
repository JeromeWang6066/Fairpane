"""Build 窗景心晴.app. Run this file from the dayplace directory."""

import shutil
import sys
from pathlib import Path

from py2app.build_app import py2app as _py2app
from setuptools import setup

# Anaconda 的扩展模块用 @rpath 指向这些库。py2app 不会把它们放进包里，
# 缺了 libffi 应用在启动时就起不来。
_DYLIBS = (
    "libffi.8.dylib",
    "libssl.3.dylib",
    "libcrypto.3.dylib",
    "libz.1.dylib",
    "liblzma.5.dylib",
    "libbz2.dylib",
)

OPTIONS = {
    "argv_emulation": False,
    "packages": ["flask", "webview", "jinja2", "werkzeug", "objc"],
    "includes": [
        "server",
        "wallpaper",
        "qwen_launch",
        "store",
        "recipe",
        "weather",
        "image_client",
        "AppKit",
        "Foundation",
        "WebKit",
    ],
    "resources": ["web"],
    "plist": {
        "CFBundleName": "Fairpane",
        "CFBundleDisplayName": "窗景心晴",
        "CFBundleIdentifier": "local.fairpane.app",
        "CFBundleShortVersionString": "1.0",
        "NSHighResolutionCapable": True,
        "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
    },
}


class py2app(_py2app):
    def run(self):
        _py2app.run(self)
        self._bundle_python_libs()

    def _bundle_python_libs(self):
        apps = list(Path(self.dist_dir).glob("*.app"))
        if len(apps) != 1:
            raise SystemExit(f"没有唯一的应用包：{apps}")
        dest_root = apps[0] / "Contents" / "Frameworks"
        dest_root.mkdir(parents=True, exist_ok=True)
        lib = Path(sys.base_prefix) / "lib"
        for name in _DYLIBS:
            src = lib / name
            if not src.exists():
                raise SystemExit(f"缺少 {src}，应用打不开")
            shutil.copy2(src, dest_root / name)


setup(
    name="窗景心晴",
    app=["窗景心晴.py"],
    options={"py2app": OPTIONS},
    cmdclass={"py2app": py2app},
    setup_requires=["py2app"],
)
