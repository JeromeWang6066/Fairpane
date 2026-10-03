"""Wallpaper stand-in. One page, one picture a day.

独立读取环境变量，不导入 run_web，避免带起疗愈应用。
"""

from __future__ import annotations

import os
import re
import sys
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import image_client
import weather
from flask import Flask, abort, jsonify, request, send_from_directory
from recipe import (
    HOURS,
    STYLES,
    VIEWS,
    compute_params,
    day_seed,
    hour_prompts,
    intent_phrase,
    read_playbook,
    resolve_score,
    resolve_style,
    resolve_view,
    wish_phrase,
    write_scene,
)
import wallpaper
from store import Store

def _resource_root() -> Path:
    resource = os.environ.get("RESOURCEPATH")
    if resource:
        return Path(resource)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent.parent / "Resources"
    return Path(__file__).resolve().parent


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
WEB = _resource_root() / "web"
_LOCK = threading.Lock()
_ORDER = ("morning", "noon", "dusk", "night")
_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}-\d+-(?:morning|noon|dusk|night)\.png$")
_HOUR_LABEL = {"morning": "清晨", "noon": "正午", "dusk": "黄昏", "night": "夜晚"}
_SPACE = re.compile(r"\s+")


def load_env() -> None:
    _load_file(ROOT / ".env")
    if not os.environ.get("DASHSCOPE_API_KEY"):
        _load_key(REPO / ".env", "DASHSCOPE_API_KEY")


def create_app(store: Store | None = None) -> Flask:
    load_env()
    app = Flask(__name__)
    app.json.ensure_ascii = False
    if store is None:
        data_dir = Path(os.environ.get("DAYPLACE_DATA", str(ROOT / "data")))
        store = Store(data_dir / "state.json")
    app.config["STORE"] = store

    @app.get("/")
    def index():
        return send_from_directory(WEB, "index.html")

    @app.get("/app.css")
    def css():
        return send_from_directory(WEB, "app.css")

    @app.get("/app.js")
    def js():
        return send_from_directory(WEB, "app.js")

    @app.get("/console")
    def console():
        return send_from_directory(WEB, "console.html")

    @app.get("/console.css")
    def console_css():
        return send_from_directory(WEB, "console.css")

    @app.get("/console.js")
    def console_js():
        return send_from_directory(WEB, "console.js")

    @app.get("/api/state")
    def state():
        return jsonify(_public(app))

    @app.post("/api/view")
    def choose_view():
        return _choose(app, VIEWS, "view", "没有这处窗外的景观")

    @app.post("/api/style")
    def choose_style():
        return _choose(app, STYLES, "style", "没有这种风格")

    @app.post("/api/wallpaper/restore")
    def restore_wallpaper():
        if app.config.get("WALLPAPER") is None:
            return jsonify(error="现在没有在换桌面"), 400
        try:
            ok = wallpaper.put_back()
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 500
        if not ok:
            return jsonify(error="没有记下打开前的壁纸"), 400
        return jsonify(ok=True)

    @app.post("/api/checkin")
    def checkin():
        body = request.get_json(silent=True) or {}
        store_obj: Store = app.config["STORE"]
        if resolve_view(store_obj.view_id(), store_obj.view_note()) is None:
            return jsonify(error="还没有选定窗外的景观"), 400
        if resolve_style(store_obj.style_id(), store_obj.style_note()) is None:
            return jsonify(error="还没有选定风格"), 400
        try:
            skipped = bool(body.get("skip"))
            mood = None if skipped else _parse_mood(body.get("mood"))
            note = "" if skipped else _parse_note(body.get("note", ""))
            lat, lon, city = _location(body)
            weather_choice = _parse_weather(body.get("weather"))
            today, hour = focus_day(app)
            start = _parse_chapter(body.get("chapter"), hour)
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        with _LOCK:
            existing = store_obj.day(today)
            has_picture = bool(_saved_names(store_obj, existing))
            revision = int((existing or {}).get("revision") or 1) + 1 if has_picture else 1
            try:
                record = produce(
                    store_obj, today, mood, note, skipped, lat, lon, city, revision, weather_choice, start
                )
            except image_client.ImageError as exc:
                print(f"画面生成失败：{exc}", file=sys.stderr)
                if has_picture:
                    return jsonify(error=str(exc), state=_public(app)), 502
                score, did_skip = resolve_score(mood, store_obj.recent_scores(today), skipped)
                store_obj.put_day(
                    today,
                    {
                        "mood": None if did_skip else mood,
                        "skipped": did_skip,
                        "note": note,
                        "score": score,
                        "fit": None,
                        "revision": 1,
                        "images": {},
                        "pending": [],
                        "prompt_source": "",
                        "error": str(exc),
                    },
                )
                return jsonify(error=str(exc), state=_public(app)), 502
            store_obj.put_day(today, record)
            store_obj.remember_picture(today, record, keep_feedback=False)
            snapshot = _public(app)
            _paint_later(app, store_obj, today, record)
            publish_wallpaper(app, force=True)
        return jsonify(state=snapshot)

    @app.post("/api/mood")
    def change_mood():
        body = request.get_json(silent=True) or {}
        try:
            mood = _parse_mood(body.get("mood"))
            lat, lon, city = _location(body)
            today, hour = focus_day(app)
            start = _parse_chapter(body.get("chapter"), hour)
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        store_obj: Store = app.config["STORE"]
        with _LOCK:
            existing = store_obj.day(today)
            if not _saved_names(store_obj, existing):
                return jsonify(error="今天还没有画面"), 400
            revision = int(existing.get("revision") or 1) + 1
            if "chapter" not in body and existing.get("start") in _ORDER:
                start = existing["start"]
            try:
                record = produce(
                    store_obj,
                    today,
                    mood,
                    existing.get("note") or "",
                    False,
                    lat,
                    lon,
                    city,
                    revision,
                    existing.get("weather_choice") or "",
                    start,
                )
            except image_client.ImageError as exc:
                print(f"画面生成失败：{exc}", file=sys.stderr)
                return jsonify(error=str(exc), state=_public(app)), 502
            record["fit"] = existing.get("fit")
            record["note"] = existing.get("note") or ""
            if existing.get("fit") == "down" and isinstance(existing.get("feeling"), str):
                record["feeling"] = existing["feeling"]
            store_obj.put_day(today, record)
            store_obj.remember_picture(today, record, keep_feedback=True)
            snapshot = _public(app)
            _paint_later(app, store_obj, today, record)
            publish_wallpaper(app, force=True)
        return jsonify(state=snapshot)

    @app.post("/api/fit")
    def fit():
        body = request.get_json(silent=True) or {}
        value = body.get("fit")
        if value not in {"up", "down"}:
            return jsonify(error="需要说明合适或不合适"), 400
        feeling = ""
        if value == "down":
            try:
                feeling = _parse_feeling(body.get("feeling", ""))
            except ValueError as exc:
                return jsonify(error=str(exc)), 400
        store_obj: Store = app.config["STORE"]
        today, _hour = focus_day(app)
        with _LOCK:
            row = store_obj.day(today)
            if not _saved_names(store_obj, row):
                return jsonify(error="今天还没有画面"), 400
            row["fit"] = value
            if value == "down":
                row["feeling"] = feeling
            else:
                row.pop("feeling", None)
            store_obj.put_day(today, row)
            store_obj.remember_fit(today, value, feeling)
        return jsonify(state=_public(app))

    @app.post("/api/next")
    def next_day():
        store_obj: Store = app.config["STORE"]
        today, _hour = focus_day(app)
        row = store_obj.day(today)
        if not _saved_names(store_obj, row):
            return jsonify(error="今天还没有画面"), 400
        if row.get("fit") not in {"up", "down"}:
            return jsonify(error="先说一下今天这张还合适吗"), 400
        nxt = (date.fromisoformat(today) + timedelta(days=1)).isoformat()
        store_obj.set_current(nxt)
        return jsonify(state=_public(app))

    @app.get("/media/<name>")
    def media(name: str):
        if _safe_name(name) is None:
            abort(404)
        return send_from_directory(app.config["STORE"].path.parent, name)

    @app.after_request
    def no_cache(resp):
        if request.path.startswith("/api/") or request.path in {
            "/",
            "/app.js",
            "/app.css",
            "/console",
            "/console.js",
            "/console.css",
        }:
            resp.headers["Cache-Control"] = "no-store"
        return resp

    return app


def chapters_from(start: str) -> tuple[str, ...]:
    return _ORDER[_ORDER.index(start) :]


def produce(
    store: Store,
    today: str,
    mood: int | None,
    note: str,
    skipped: bool,
    lat: float,
    lon: float,
    city: str,
    revision: int,
    weather_choice: str,
    start: str,
) -> dict:
    view_id = store.view_id()
    style_id = store.style_id()
    view = resolve_view(view_id, store.view_note())
    style = resolve_style(style_id, store.style_note())
    if view is None:
        raise ValueError("还没有选定窗外的景观")
    if style is None:
        raise ValueError("还没有选定风格")
    recent = store.recent_scores(today)
    score, did_skip = resolve_score(mood, recent, skipped)
    book = read_playbook(store.playbook(), today)
    if weather_choice:
        sky = weather.preset(weather_choice)
    else:
        sky = weather.fetch_weather(lat, lon, city)
    params = compute_params(
        score,
        recent,
        skipped=did_skip,
        yesterday_unfit=book["unfit"],
        repeat_unfit=book["repeat"],
        severity=float(sky["severity"]),
    )
    kept_note = "" if did_skip else note
    scene = write_scene(view, style, sky, params, kept_note, book["unfit"], did_skip, book["clause"])
    prompts = hour_prompts(scene["prompt"], style, view, params, sky, book["clause"])
    seed = day_seed(
        f"{view_id}:{store.view_note()}",
        f"{style_id}:{store.style_note()}",
        today,
        revision,
    )
    plan = chapters_from(start)
    first, rest = plan[0], plan[1:]
    filename = f"{today}-{revision}-{first}.png"
    try:
        image_client.generate_image(prompts[first], store.path.parent / filename, seed)
    except image_client.ImageError as exc:
        print(f"{_HOUR_LABEL[first]}没有画成：" + str(exc), file=sys.stderr)
        raise
    return {
        "mood": None if did_skip else mood,
        "skipped": did_skip,
        "note": kept_note,
        "score": score,
        "intent": intent_phrase(score, params["sustained"] >= 0.5),
        "fit": None,
        "revision": revision,
        "warmth": params["warmth"],
        "shelter": params["shelter"],
        "openness": params["openness"],
        "drama": params["drama"],
        "brightness": params["brightness"],
        "saturation": params["saturation"],
        "view_id": view_id,
        "style_id": style_id,
        "detail": scene["detail"],
        "prompt": scene["prompt"],
        "prompts": prompts,
        "prompt_source": scene["source"],
        "qwen_error": scene["qwen_error"],
        "images": {first: filename},
        "missing": [],
        "pending": list(rest),
        "chapters": list(plan),
        "start": start,
        "seed": seed,
        "weather": sky,
        "weather_choice": weather_choice,
        "error": "",
    }


def _paint_later(app: Flask, store: Store, today: str, record: dict) -> None:
    thread = threading.Thread(
        target=_paint_rest,
        args=(app, store, today, record["revision"], record["prompts"], record["seed"]),
        daemon=True,
    )
    thread.start()


def _paint_rest(app: Flask, store: Store, today: str, revision: int, prompts: dict, seed: int) -> None:
    pending = tuple((store.day(today) or {}).get("pending") or ())
    for chapter in pending:
        with _LOCK:
            if not _same_revision(store, today, revision):
                return
        filename = f"{today}-{revision}-{chapter}.png"
        try:
            image_client.generate_image(prompts[chapter], store.path.parent / filename, seed)
        except image_client.ImageError as exc:
            print(f"{_HOUR_LABEL[chapter]}没有画成：{exc}", file=sys.stderr)
            _mark_chapter(store, today, revision, chapter, "", str(exc))
            continue
        if _mark_chapter(store, today, revision, chapter, filename, ""):
            publish_wallpaper(app)


def _mark_chapter(store: Store, today: str, revision: int, chapter: str, filename: str, error: str) -> bool:
    with _LOCK:
        row = store.day(today)
        if not row or int(row.get("revision") or 0) != revision:
            return False
        images = dict(row.get("images") or {})
        missing = list(row.get("missing") or [])
        if filename:
            images[chapter] = filename
        elif chapter not in missing:
            missing.append(chapter)
        planned = [item for item in (row.get("chapters") or _ORDER) if item in _ORDER]
        pending = [item for item in planned if item not in images and item not in missing]
        row["images"] = images
        row["missing"] = missing
        row["pending"] = pending
        if missing and not pending:
            gap = "、".join(_HOUR_LABEL[item] for item in missing)
            row["error"] = f"没画成：{gap}"
        elif not pending:
            row["error"] = ""
        store.put_day(today, row)
        return bool(filename)


def _same_revision(store: Store, today: str, revision: int) -> bool:
    row = store.day(today)
    return bool(row) and int(row.get("revision") or 0) == revision


def clock_now(app) -> tuple[str, int]:
    custom = app.config.get("CLOCK")
    if custom is not None:
        return custom()
    now = datetime.now().astimezone()
    return now.date().isoformat(), now.hour


def focus_day(app) -> tuple[str, int]:
    day, hour = clock_now(app)
    current = app.config["STORE"].current()
    if _later_day(current, day):
        return current, hour
    return day, hour


def _later_day(current: str, day: str) -> bool:
    try:
        return bool(current) and date.fromisoformat(current) > date.fromisoformat(day)
    except ValueError:
        return False


def chapter_for_hour(hour: int) -> str:
    if 5 <= hour < 10:
        return "morning"
    if 10 <= hour < 16:
        return "noon"
    if 16 <= hour < 19:
        return "dusk"
    return "night"


def _public(app) -> dict:
    store: Store = app.config["STORE"]
    today, hour = focus_day(app)
    view_id = store.view_id()
    style_id = store.style_id()
    view = resolve_view(view_id, store.view_note())
    style = resolve_style(style_id, store.style_note())
    row = store.day(today)
    day = None
    if row:
        day = {
            "mood": row.get("mood"),
            "skipped": bool(row.get("skipped")),
            "fit": row.get("fit"),
            "images": _image_urls(store, row.get("images")),
            "pending": [chapter for chapter in _ORDER if chapter in (row.get("pending") or [])],
            "missing": [chapter for chapter in HOURS if chapter in (row.get("missing") or [])],
            "prompt_source": row.get("prompt_source") or "",
            "qwen_error": row.get("qwen_error") or "",
            "error": row.get("error") or "",
        }
    return {
        "today": today,
        "hour": hour,
        "chapter": chapter_for_hour(hour),
        "views": [_card(key, item) for key, item in VIEWS.items()],
        "styles": [_card(key, item) for key, item in STYLES.items()],
        "view": None if view is None else _card(view_id, view),
        "style": None if style is None else _card(style_id, style),
        "day": day,
        "yesterday_image_url": _previous_image(store, today),
    }


def _choose(app, table: dict, kind: str, missing: str):
    body = request.get_json(silent=True) or {}
    choice = body.get("id")
    store: Store = app.config["STORE"]
    note = ""
    if choice == "custom":
        try:
            note = wish_phrase(body.get("text"))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
    elif choice not in table:
        return jsonify(error=missing), 400
    if kind == "view":
        store.set_view(choice, note)
    else:
        store.set_style(choice, note)
    return jsonify(state=_public(app))


def _card(key: str, item: dict) -> dict:
    return {"id": key, "title": item["title"], "line": item["line"], "wash": item["wash"]}


def _previous_image(store: Store, today: str) -> str | None:
    days = store.read()["days"]
    for key in sorted((item for item in days if isinstance(item, str) and item < today), reverse=True):
        row = days[key]
        if isinstance(row, dict):
            url = _any_url(store, row)
            if url:
                return url
    return None


def _saved_names(store: Store, row: dict | None) -> dict[str, str]:
    if not row or not isinstance(row.get("images"), dict):
        return {}
    return {key: name for key, name in row["images"].items() if _file_url(store, name)}


def _image_urls(store: Store, images: object) -> dict[str, str]:
    if not isinstance(images, dict):
        return {}
    urls = {}
    for chapter in HOURS:
        url = _file_url(store, images.get(chapter))
        if url:
            urls[chapter] = url
    return urls


def _any_url(store: Store, row: dict) -> str | None:
    urls = _image_urls(store, row.get("images"))
    for chapter in HOURS:
        if chapter in urls:
            return urls[chapter]
    return None


def _file_url(store: Store, name: object) -> str | None:
    safe = _safe_name(name)
    if safe is None or not (store.path.parent / safe).is_file():
        return None
    return "/media/" + safe


def _safe_name(name: object) -> str | None:
    if not isinstance(name, str) or _NAME.fullmatch(name) is None:
        return None
    return name


def _parse_chapter(value: object, hour: int) -> str:
    if value is None or value == "":
        return chapter_for_hour(hour)
    if not isinstance(value, str) or value not in _ORDER:
        raise ValueError("没有这个时辰")
    return value


def _parse_mood(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10:
        raise ValueError("分数需要是 1 到 10")
    return value


def _parse_weather(value: object) -> str:
    if value is None or value == "":
        return ""
    if not isinstance(value, str) or value not in weather.PRESETS:
        raise ValueError("没有这种天气")
    return value


def _parse_note(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("那一句需要是文字")
    return _SPACE.sub(" ", value).strip()[:80]


def _parse_feeling(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("那一句需要是文字")
    if not value.strip():
        return ""
    return wish_phrase(value)


def _location(body: dict) -> tuple[float, float, str]:
    lat = body.get("lat")
    lon = body.get("lon")
    if (
        isinstance(lat, (int, float))
        and isinstance(lon, (int, float))
        and not isinstance(lat, bool)
        and not isinstance(lon, bool)
    ):
        lat_f, lon_f = float(lat), float(lon)
        if -90 <= lat_f <= 90 and -180 <= lon_f <= 180:
            return lat_f, lon_f, ""
    return _env_float("DAYPLACE_LAT", 31.2304), _env_float("DAYPLACE_LON", 121.4737), os.environ.get("DAYPLACE_CITY", "")


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "")
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _load_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _load_key(path: Path, key: str) -> None:
    if not path.is_file() or os.environ.get(key):
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        found, _, value = line.partition("=")
        if found.strip() == key:
            os.environ[key] = value.strip().strip('"').strip("'")
            return


def publish_status(app: Flask) -> None:
    today, hour = focus_day(app)
    row = app.config["STORE"].day(today) or {}
    sky = row.get("weather")
    summary = sky.get("summary") if isinstance(sky, dict) else ""
    if not isinstance(summary, str):
        summary = ""
    wallpaper.tell_status(weather.status_mark(summary, chapter_for_hour(hour)))


def publish_wallpaper(app: Flask, *, force: bool = False) -> None:
    publish_status(app)
    setter = app.config.get("WALLPAPER")
    if setter is None:
        return
    if wallpaper.holding() and not force:
        return
    today, hour = focus_day(app)
    path = wallpaper.pick_path(app.config["STORE"], today, hour)
    if path is None:
        return
    if force:
        wallpaper.release()
    wallpaper.apply(path, setter, force=force)


def wallpaper_enabled() -> bool:
    return os.environ.get("DAYPLACE_WALLPAPER") != "0" and sys.platform == "darwin"


def arm_wallpaper(app: Flask) -> None:
    if not wallpaper_enabled() or app.config.get("_WALLPAPER_ARMED"):
        return
    try:
        wallpaper.remember(wallpaper.capture_screens())
    except Exception as exc:
        print(f"没有记下原来的壁纸：{exc}", file=sys.stderr)
    app.config["WALLPAPER"] = wallpaper.desktop_setter
    app.config["_WALLPAPER_ARMED"] = True
    publish_wallpaper(app)
    thread = threading.Thread(target=_wallpaper_loop, args=(app,), name="wallpaper", daemon=True)
    thread.start()


def _wallpaper_loop(app: Flask) -> None:
    while True:
        time.sleep(60)
        publish_wallpaper(app)


def main() -> None:
    app = create_app()
    app.config["STORE"].set_current("")
    arm_wallpaper(app)
    host = os.environ.get("DAYPLACE_HOST", "127.0.0.1")
    port = int(os.environ.get("DAYPLACE_PORT", "8770"))
    print(f"窗景心晴：http://{host}:{port}", file=sys.stderr)
    app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
