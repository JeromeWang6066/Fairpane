"""One still from DashScope z-image-turbo. The link expires, so save the PNG."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# 16:9。总像素约 236 万，落在百炼允许的 512²–2048² 里。
SIZE = "2048*1152"
_PNG = b"\x89PNG\r\n\x1a\n"


class ImageError(Exception):
    pass


def generate_image(prompt: str, dest: Path, seed: int, *, opener=urllib.request.urlopen) -> None:
    key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not key:
        raise ImageError("没有 DASHSCOPE_API_KEY，无法生成画面。")
    base = os.environ.get("DASHSCOPE_API_BASE", "https://dashscope.aliyuncs.com/api/v1").rstrip("/")
    body = {
        "model": "z-image-turbo",
        "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
        "parameters": {
            "prompt_extend": False,  # 关掉云端改写，保留本地配方。
            "size": SIZE,
            "seed": int(seed) % 2147483647,
        },
    }
    payload = json.loads(
        _read(
            opener,
            urllib.request.Request(
                f"{base}/services/aigc/multimodal-generation/generation",
                data=json.dumps(body, ensure_ascii=False).encode(),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
                method="POST",
            ),
            180,
        )
    )
    if payload.get("code"):
        raise ImageError(str(payload.get("message") or payload["code"]))
    image_url = _find_image(payload)
    if not _https_aliyun(image_url):
        raise ImageError("图片地址不在预期的存储域名上")
    blob = _read(opener, urllib.request.Request(image_url), 60)
    if not blob.startswith(_PNG):
        raise ImageError("返回的不是 PNG")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(blob)


def _find_image(payload: dict) -> str:
    try:
        content = payload["output"]["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ImageError("响应里没有图片") from exc
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("image"), str):
                return part["image"]
    raise ImageError("响应里没有图片")


def _https_aliyun(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    return parsed.scheme == "https" and (host == "aliyuncs.com" or host.endswith(".aliyuncs.com"))


def _read(opener, req: urllib.request.Request, timeout: int) -> bytes:
    try:
        with opener(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:180]
        raise ImageError(f"出图接口返回 {exc.code}：{detail}") from exc
    except TimeoutError as exc:
        raise ImageError("出图接口超时") from exc
    except urllib.error.URLError as exc:
        raise ImageError(f"出图接口没有连上：{exc.reason}") from exc
