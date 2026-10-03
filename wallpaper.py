"""Put today's current-chapter PNG on the macOS desktop."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

# 页面背景 #161311。系统壁纸留出空隙时用同一色。
_FILL = (22 / 255, 19 / 255, 17 / 255, 1.0)
_LOCK = threading.Lock()
_state = {"path": "", "runner": None, "status_hook": None, "held": False, "originals": None}


def reset() -> None:
    with _LOCK:
        _state["path"] = ""
        _state["runner"] = None
        _state["status_hook"] = None
        _state["held"] = False
        _state["originals"] = None


def set_runner(runner) -> None:
    with _LOCK:
        _state["runner"] = runner


def set_status_hook(hook) -> None:
    with _LOCK:
        _state["status_hook"] = hook


def tell_status(mark: str) -> None:
    with _LOCK:
        hook = _state["status_hook"]
        runner = _state["runner"]
    if hook is None:
        return

    def go() -> None:
        hook(mark)

    if runner is None or threading.current_thread() is threading.main_thread():
        go()
        return
    runner(go)


def remember(shots) -> None:
    with _LOCK:
        if _state["originals"] is None:
            _state["originals"] = list(shots)


def holding() -> bool:
    with _LOCK:
        return bool(_state["held"])


def release() -> None:
    with _LOCK:
        _state["held"] = False


def pick_path(store, day: str, hour: int) -> Path | None:
    import server

    row = store.day(day)
    if not row:
        return None
    images = row.get("images")
    if not isinstance(images, dict):
        return None
    name = images.get(server.chapter_for_hour(hour))
    if server._safe_name(name) is None:
        return None
    path = store.path.parent / name
    if not path.is_file():
        return None
    return path


def apply(path: Path | None, setter, *, force: bool = False) -> bool:
    if path is None:
        return False
    target = str(path.resolve())

    def go() -> None:
        setter(Path(target))

    with _LOCK:
        if _state["held"] and not force:
            return False
        if not force and target == _state["path"]:
            return False
        runner = _state["runner"]
        # 主线程再派发会把自己等死。没有界面循环时也直接调用。
        if runner is None or threading.current_thread() is threading.main_thread():
            try:
                go()
            except Exception as exc:
                print(f"桌面没有换上：{exc}", file=sys.stderr)
                return False
            _state["path"] = target
            _state["held"] = False
            return True

    # 锁不包住派发。主线程若在等这把锁，后台线程又在等主线程，两边都会停住。
    try:
        runner(go)
    except Exception as exc:
        print(f"桌面没有换上：{exc}", file=sys.stderr)
        return False
    with _LOCK:
        _state["path"] = target
        _state["held"] = False
    return True


def put_back() -> bool:
    with _LOCK:
        shots = _state["originals"]
        runner = _state["runner"]
        direct = runner is None or threading.current_thread() is threading.main_thread()
    if not shots:
        return False
    if direct:
        _write_originals(shots)
    else:
        runner(lambda: _write_originals(shots))
    with _LOCK:
        _state["held"] = True
        _state["path"] = ""
    return True


def capture_screens():
    from AppKit import NSScreen, NSWorkspace

    workspace = NSWorkspace.sharedWorkspace()
    shots = []
    for screen in NSScreen.screens() or []:
        number = screen.deviceDescription().objectForKey_("NSScreenNumber")
        url = workspace.desktopImageURLForScreen_(screen)
        if number is None or url is None:
            continue
        path = url.path()
        if not path:
            continue
        shots.append((int(number), str(path), workspace.desktopImageOptionsForScreen_(screen)))
    return shots


def _write_originals(shots) -> None:
    from AppKit import NSScreen, NSWorkspace
    from Foundation import NSURL

    by_number = {number: (path, options) for number, path, options in shots}
    screens = NSScreen.screens() or []
    if not screens:
        raise RuntimeError("没有屏幕")
    workspace = NSWorkspace.sharedWorkspace()
    wrote = False
    for screen in screens:
        number = int(screen.deviceDescription().objectForKey_("NSScreenNumber"))
        saved = by_number.get(number)
        if saved is None:
            continue
        path, options = saved
        if not Path(path).is_file():
            raise RuntimeError("原来的壁纸文件已经不在了")
        url = NSURL.fileURLWithPath_(path)
        ok, err = workspace.setDesktopImageURL_forScreen_options_error_(url, screen, options, None)
        if not ok:
            detail = err.localizedDescription() if err is not None else "系统没有接受原来的壁纸"
            raise RuntimeError(detail)
        wrote = True
    if not wrote:
        raise RuntimeError("屏幕对不上，没有换回去")


def desktop_setter(path: Path) -> None:
    from AppKit import (
        NSColor,
        NSImageScaleProportionallyUpOrDown,
        NSScreen,
        NSWorkspace,
        NSWorkspaceDesktopImageAllowClippingKey,
        NSWorkspaceDesktopImageFillColorKey,
        NSWorkspaceDesktopImageScalingKey,
    )
    from Foundation import NSURL

    screens = NSScreen.screens()
    if not screens:
        raise RuntimeError("没有屏幕")
    url = NSURL.fileURLWithPath_(str(path))
    fill = NSColor.colorWithSRGBRed_green_blue_alpha_(*_FILL)
    options = {
        NSWorkspaceDesktopImageScalingKey: NSImageScaleProportionallyUpOrDown,
        NSWorkspaceDesktopImageAllowClippingKey: True,
        NSWorkspaceDesktopImageFillColorKey: fill,
    }
    workspace = NSWorkspace.sharedWorkspace()
    for screen in screens:
        ok, err = workspace.setDesktopImageURL_forScreen_options_error_(url, screen, options, None)
        if not ok:
            detail = err.localizedDescription() if err is not None else "系统没有接受这张图"
            raise RuntimeError(detail)
