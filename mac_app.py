"""Mac console for Fairpane. The picture itself is the system desktop wallpaper."""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path

from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyRegular,
    NSMenu,
    NSMenuItem,
    NSObject,
    NSStatusBar,
    NSVariableStatusItemLength,
)
from Foundation import NSOperationQueue

import qwen_launch
import server
import wallpaper

_KEEP = []


class _Run:
    quitting = False
    window = None
    flask = None


class Actions(NSObject):
    def openConsole_(self, _sender) -> None:
        _show()

    def reapply_(self, _sender) -> None:
        _reapply()

    def restore_(self, _sender) -> None:
        _restore()

    def quit_(self, _sender) -> None:
        _Run.quitting = True
        NSApplication.sharedApplication().terminate_(None)

    def applicationShouldTerminate_(self, _sender) -> bool:
        _Run.quitting = True
        return True

    def applicationShouldHandleReopen_hasVisibleWindows_(self, _sender, _visible) -> bool:
        if not _Run.quitting:
            _show()
        return True


def main() -> None:
    _prepare_home()
    app = server.create_app()
    qwen_launch.ensure_qwen()
    app.config["STORE"].set_current("")
    _Run.flask = app
    wallpaper.set_runner(_on_main)
    server.arm_wallpaper(app)
    host = os.environ.get("DAYPLACE_HOST", "127.0.0.1")
    port = int(os.environ.get("DAYPLACE_PORT", "8770"))
    thread = threading.Thread(
        target=lambda: app.run(host=host, port=port, threaded=True, use_reloader=False),
        name="fairpane",
        daemon=True,
    )
    thread.start()
    _wait_until_up(host, port)
    _open_console(host, port)


def support_dir() -> Path:
    path = Path.home() / "Library" / "Application Support" / "Dayplace"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _prepare_home() -> None:
    if not getattr(sys, "frozen", False):
        return
    home = support_dir()
    os.environ.setdefault("DAYPLACE_DATA", str(home))
    server._load_file(home / ".env")


def _wait_until_up(host: str, port: int) -> None:
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise SystemExit("本地页面没有起来")


def _on_main(fn) -> None:
    done = threading.Event()
    box: list[BaseException] = []

    def wrapped() -> None:
        try:
            fn()
        except BaseException as exc:
            box.append(exc)
        finally:
            done.set()

    NSOperationQueue.mainQueue().addOperationWithBlock_(wrapped)
    done.wait()
    if box:
        raise box[0]


def _open_console(host: str, port: int) -> None:
    import webview

    nsapp = NSApplication.sharedApplication()
    nsapp.setActivationPolicy_(NSApplicationActivationPolicyRegular)

    window = webview.create_window(
        "窗景心晴",
        f"http://{host}:{port}/console",
        width=760,
        height=880,
        resizable=True,
        fullscreen=False,
        background_color="#161311",
    )
    _Run.window = window

    actions = Actions.alloc().init()
    _KEEP.append(actions)
    menu = NSMenu.alloc().init()
    for title, selector in (
        ("打开控制台", "openConsole:"),
        ("按当前时辰再铺一次", "reapply:"),
        ("换回原来的壁纸", "restore:"),
    ):
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, selector, "")
        item.setTarget_(actions)
        menu.addItem_(item)
    menu.addItem_(NSMenuItem.separatorItem())
    quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("退出", "quit:", "q")
    quit_item.setTarget_(actions)
    menu.addItem_(quit_item)

    status = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
    button = status.button()
    button.setToolTip_("窗景心晴")
    button.setAccessibilityTitle_("窗景心晴")
    wallpaper.set_status_hook(button.setTitle_)
    if _Run.flask is not None:
        server.publish_status(_Run.flask)
    status.setMenu_(menu)
    _KEEP.append(status)

    def keep_open():
        # 红灯只藏窗口。退出会先把 quitting 设上，窗口才真正关掉。
        if _Run.quitting:
            return True
        window.hide()
        return False

    def take_delegate():
        _on_main(lambda: nsapp.setDelegate_(actions))

    window.events.closing += keep_open
    window.events.shown += take_delegate
    webview.start()


def _show() -> None:
    window = _Run.window
    if window is None:
        return
    window.show()
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)


def _restore() -> None:
    try:
        ok = wallpaper.put_back()
    except RuntimeError as exc:
        print(f"没有换回去：{exc}", file=sys.stderr)
        return
    if not ok:
        print("没有记下打开前的壁纸", file=sys.stderr)


def _reapply() -> None:
    app = _Run.flask
    if app is None:
        return
    server.publish_wallpaper(app, force=True)


if __name__ == "__main__":
    main()
