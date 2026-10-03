"""Local JSON for the chosen view, style, and each day's picture."""

from __future__ import annotations

import json
import threading
from pathlib import Path


def _playbook_rows(data: dict) -> list[dict]:
    rows = data.get("playbook")
    if not isinstance(rows, list):
        return []
    return [item for item in rows if isinstance(item, dict)]


def _trim_playbook(rows: list[dict]) -> list[dict]:
    rows.sort(key=lambda item: item.get("day") if isinstance(item.get("day"), str) else "")
    return rows[-14:]


def _blank() -> dict:
    return {
        "view_id": None,
        "style_id": None,
        "view_note": "",
        "style_note": "",
        "current": "",
        "playbook": [],
        "days": {},
    }


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def read(self) -> dict:
        with self._lock:
            return self._read()

    def view_id(self) -> str | None:
        return self._choice("view_id")

    def style_id(self) -> str | None:
        return self._choice("style_id")

    def view_note(self) -> str:
        value = self.read().get("view_note")
        return value if isinstance(value, str) else ""

    def style_note(self) -> str:
        value = self.read().get("style_note")
        return value if isinstance(value, str) else ""

    def current(self) -> str:
        value = self.read().get("current")
        return value if isinstance(value, str) else ""

    def set_current(self, day: str) -> None:
        def fn(data: dict) -> None:
            data["current"] = day

        self._update(fn)

    def set_view(self, view_id: str, note: str = "") -> None:
        self._set_pair("view_id", view_id, "view_note", note)

    def set_style(self, style_id: str, note: str = "") -> None:
        self._set_pair("style_id", style_id, "style_note", note)

    def _choice(self, key: str) -> str | None:
        value = self.read().get(key)
        return value if isinstance(value, str) else None

    def _set_pair(self, key: str, value: str, note_key: str, note: str) -> None:
        def fn(data: dict) -> None:
            data[key] = value
            data[note_key] = note

        self._update(fn)

    def day(self, day: str) -> dict | None:
        value = self.read()["days"].get(day)
        return value if isinstance(value, dict) else None

    def put_day(self, day: str, record: dict) -> None:
        def fn(data: dict) -> None:
            data["days"][day] = record

        self._update(fn)

    def recent_scores(self, before: str, limit: int = 7) -> list[float]:
        days = self.read()["days"]
        keys = sorted(
            key
            for key, row in days.items()
            if isinstance(key, str)
            and key < before
            and isinstance(row, dict)
            and isinstance(row.get("score"), (int, float))
            and not isinstance(row.get("score"), bool)
        )
        return [float(days[key]["score"]) for key in keys[-limit:]]

    def playbook(self) -> list[dict]:
        value = self.read().get("playbook")
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def remember_picture(self, day: str, record: dict, *, keep_feedback: bool) -> None:
        score = record.get("score")
        intent = record.get("intent") if isinstance(record.get("intent"), str) else ""
        detail = record.get("detail") if isinstance(record.get("detail"), str) else ""

        def fn(data: dict) -> None:
            rows = _playbook_rows(data)
            previous = next((item for item in rows if item.get("day") == day), None)
            fit = ""
            feeling = ""
            if keep_feedback and previous and previous.get("fit") in {"up", "down"}:
                fit = previous["fit"]
                if fit == "down" and isinstance(previous.get("feeling"), str):
                    feeling = previous["feeling"]
            kept = [item for item in rows if item.get("day") != day]
            kept.append({
                "day": day,
                "score": score,
                "intent": intent,
                "detail": detail,
                "fit": fit,
                "feeling": feeling,
            })
            data["playbook"] = _trim_playbook(kept)

        self._update(fn)

    def remember_fit(self, day: str, fit: str, feeling: str) -> None:
        def fn(data: dict) -> None:
            rows = _playbook_rows(data)
            found = False
            for item in rows:
                if item.get("day") == day:
                    item["fit"] = fit
                    item["feeling"] = feeling if fit == "down" else ""
                    found = True
                    break
            if not found:
                rows.append({
                    "day": day,
                    "score": None,
                    "intent": "",
                    "detail": "",
                    "fit": fit,
                    "feeling": feeling if fit == "down" else "",
                })
            data["playbook"] = _trim_playbook(rows)

        self._update(fn)

    def _update(self, fn) -> None:
        with self._lock:
            data = self._read()
            fn(data)
            self._write(data)

    def _read(self) -> dict:
        if not self.path.is_file():
            return _blank()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("state.json 不是对象")
        data.setdefault("view_id", None)
        data.setdefault("style_id", None)
        data.setdefault("view_note", "")
        data.setdefault("style_note", "")
        data.setdefault("current", "")
        if not isinstance(data.get("playbook"), list):
            data["playbook"] = []
        if not isinstance(data.get("days"), dict):
            data["days"] = {}
        return data

    def _write(self, data: dict) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)
