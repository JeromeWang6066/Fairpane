"""Start the local Qwen server when the Mac app opens and it is not already up."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

_DRIVE = Path("/Volumes/My Passport/qwen35-2b/start_qwen.sh")


def endpoint() -> tuple[str, int]:
    raw = os.environ.get("QWEN_API_BASE", "http://127.0.0.1:8080/v1")
    parsed = urllib.parse.urlsplit(raw)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port if parsed.port is not None else 8080
    return host, port


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def server_running() -> bool:
    try:
        result = subprocess.run(["pgrep", "-x", "llama-server"], capture_output=True)
    except OSError:
        return False
    return result.returncode == 0


def find_script() -> Path | None:
    override = os.environ.get("QWEN_START", "").strip()
    path = Path(override) if override else _DRIVE
    if path.is_file():
        return path
    return None


def ensure_qwen() -> None:
    host, port = endpoint()
    if port_open(host, port) or server_running():
        return
    script = find_script()
    if script is None:
        print("本地 Qwen 没在运行。请挂载 My Passport。", file=sys.stderr)
        return
    print("正在启动本地 Qwen", file=sys.stderr)
    env = os.environ.copy()
    env["QWEN_PORT"] = str(port)
    log = _open_log()
    try:
        proc = subprocess.Popen(
            ["/bin/bash", str(script)],
            cwd=str(script.parent),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
        )
    finally:
        log.close()
    time.sleep(0.3)
    code = proc.poll()
    if code is not None:
        print(f"本地 Qwen 没有启动起来（退出码 {code}）。", file=sys.stderr)


def _open_log():
    directory = Path.home() / "Library" / "Application Support" / "Dayplace"
    directory.mkdir(parents=True, exist_ok=True)
    return open(directory / "qwen.log", "ab")
