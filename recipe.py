"""Turn a mood score into a regulated picture prompt.

Warmth, shelter, openness, drama, brightness, and saturation are computed
here. Qwen only writes the sentence that goes to the image model, so a 2B
model cannot wander into a harsher picture.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request

# 视角和室内陈设固定。变的是窗外、画法和时辰。句子不能含「人」，否则会被当成要画人。
# 窗、灯、植物的样式和位置各写死一处，四张图才能对上同一套器物。
_WINDOW_LOOK = "浅褐色方格木窗，窗框细，两扇对开，没有窗帘"
_WALL = "木窗嵌在浅色室内墙里，窗左右和上方都是墙。房子、树、天、雨和雪只留在窗玻璃里，不要画到室内墙上，也不要延伸出窗框"
_PLANT_LOOK = "书桌左前角靠近窗放着一盆阔叶绿植，陶盆浅灰"
_LAMP_LOOK = "书桌右后角一盏台灯，灯罩是米白色圆锥，灯杆细，底座是浅木色圆盘"
WINDOW = (
    f"视线正对一扇{_WINDOW_LOOK}，平视窗面。{_WALL}。"
    "窗前一张浅木色书桌，桌上有书本文具，中央摊开一本浅色封面的书，桌前一把浅木色直背椅。"
    f"{_PLANT_LOOK}。{_LAMP_LOOK}"
)

VIEWS = {
    "street": {
        "id": "street",
        "title": "街道",
        "line": "对面的房子和树",
        "wash": "#b7a394",
        "outside": "安静的街道，对面是压得很低的房子和一棵树，树和天空留得出来",
    },
    "shore": {
        "id": "shore",
        "title": "海岸",
        "line": "沙滩和大海",
        "wash": "#8aa4ae",
        "outside": "一片沙滩连着大海，近处是细沙，海面平静地铺向远处",
    },
    "garden": {
        "id": "garden",
        "title": "庭院",
        "line": "树、石径和矮墙",
        "wash": "#8b9a78",
        "outside": "一座安静的庭院，有树、石径和矮墙，树冠之间留出天空",
    },
}

STYLES = {
    "realistic": {
        "id": "realistic",
        "title": "写实",
        "line": "像拍下来的",
        "wash": "#c4b6a4",
        "phrase": "写实质感，像安静的摄影，颗粒细，色彩自然",
    },
    "ink": {
        "id": "ink",
        "title": "水彩",
        "line": "柔和的水色",
        "wash": "#c5d4ce",
        "phrase": "水彩插画，柔和梦幻，笔触温柔，透明水色晕开，色彩铺满整幅",
    },
    "anime": {
        "id": "anime",
        "title": "动漫",
        "line": "平整的色块",
        "wash": "#c9b7c4",
        "phrase": "动画景物，色块平整，轮廓清楚，色彩柔和",
    },
}

_SYSTEM = """只输出一个 JSON 对象，写完立刻停止，不要重复同一句。
对象只有 detail 和 prompt 两个键。
detail 是桌上已有的一件东西，4到12个字。
prompt 是 70到140个字的中文，每句只写一次。
构图必须沿用给定的器物，不要改样式和位置：浅褐色方格木窗，两扇对开，没有窗帘；浅木色书桌和直背椅，书在书桌中央；阔叶绿植在书桌左前角，陶盆浅灰；台灯在书桌右后角，米白色圆锥灯罩，细灯杆，浅木色圆盘底座。
不要写台灯是开是关，也不要写灯亮或灯灭。开关由时辰另外接上。
不要加窗帘，不要改灯罩颜色和形状，不要挪动绿植。不要改成侧面、俯视，也不要写成空窗台。画法写在最前面。
窗外的风景只留在窗玻璃里，不要画到室内墙上，也不要延伸出窗框。
只写景物和光线，不要写数目，不要写清晨、正午、黄昏或夜晚。
色彩以绿为主，可带一点蓝。近处的遮挡要能看透，天空要留得出。
不要黑暗的空房间，不要强烈对比，不要让雷暴成为主体，不要让红色占主色。
"""

# 四张照片共用同一张书桌和同一个正面视角，只换光线。夜里台灯打开。句子里不能出现「人」。
HOURS = {
    "morning": "清晨，时间很早，还在正午之前很久。太阳贴着地平线，天色是深的蓝灰，不是白昼的亮光。窗外只亮起一条，室内大部分仍暗，书桌上只有一点点冷的晨光",
    "noon": "正午。照在书桌上的光来自窗外，直而亮，均匀，这是一天里最亮的时候",
    "dusk": "黄昏。照在书桌上的暖光来自窗外低处的太阳，天空偏暖，整幅不要发红",
    "night": "夜晚。天近乎全黑。窗外的房子、树和岸都沉进黑暗，不容易看清，只剩很淡的轮廓。没有日光",
}

_FORBIDDEN = re.compile("人|脸|文字|水印|字母|字幕|招牌")
_LATIN = re.compile(r"[A-Za-z0-9]")
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_OPEN = re.compile(r"^```(?:json)?", re.IGNORECASE)


class QwenError(Exception):
    pass


def resolve_score(mood: int | None, recent: list[float], skipped: bool) -> tuple[float, bool]:
    if skipped or mood is None:
        if recent:
            return sum(recent) / len(recent), True
        return 5.5, True
    return float(mood), False


def compute_params(
    score: float,
    recent: list[float],
    *,
    skipped: bool,
    yesterday_unfit: bool,
    severity: float,
    repeat_unfit: bool = False,
) -> dict[str, float]:
    severity = _clamp(severity)
    tail = recent[-3:]
    chronic = len(tail) == 3 and all(item <= 4 for item in tail)
    # 连续低落走开阔和日照。单次低分仍用庇护，避免把刚低下来的一天封进近景。
    sustained = score < 4 and chronic
    if sustained:
        warmth, shelter, openness = 0.62, 0.42, 0.78
        brightness, saturation = 0.76, 0.28
    elif score < 4:
        warmth, shelter, openness = 0.74, 0.72, 0.40
        brightness, saturation = 0.52, 0.22
    elif score < 7:
        warmth, shelter, openness = 0.52, 0.46, 0.58
        brightness, saturation = 0.66, 0.38
    else:
        warmth, shelter, openness = 0.56, 0.22, 0.86
        brightness, saturation = 0.82, 0.50

    if score < 4:
        drama = min(0.30, 0.10 + 0.10 * severity)
    elif score < 7:
        drama = min(0.58, 0.34 + 0.22 * severity)
    else:
        drama = min(0.40, 0.16 + 0.16 * severity)

    if chronic and not sustained:
        openness += 0.08
        brightness += 0.08
        shelter -= 0.08
        drama -= 0.08
    elif len(tail) == 3 and all(item >= 7 for item in tail):
        openness += 0.10

    if len(recent) >= 3 and recent[-1] <= recent[0] - 2:
        warmth += 0.08
        drama -= 0.08

    if skipped:
        warmth = (warmth + 0.55) / 2
        shelter = (shelter + 0.45) / 2
        openness = (openness + 0.55) / 2
        brightness = (brightness + 0.60) / 2
        saturation = (saturation + 0.34) / 2
        drama = min(drama, 0.32)
        sustained = False

    if yesterday_unfit:
        warmth += 0.10
        drama -= 0.10
    if repeat_unfit:
        warmth += 0.05
        drama -= 0.05

    return {
        "warmth": round(_clamp(warmth), 4),
        "shelter": round(_clamp(shelter), 4),
        "openness": round(_clamp(openness), 4),
        "drama": round(_clamp(drama), 4),
        "brightness": round(_clamp(brightness), 4),
        "saturation": round(_clamp(saturation), 4),
        "sustained": 1.0 if sustained else 0.0,
    }


def intent_phrase(score: float, sustained: bool) -> str:
    if sustained:
        return "窗外留开，光仍淡"
    if score < 4:
        return "近处遮一遮，光暖而淡"
    if score < 7:
        return "平静，明暗适中"
    return "开阔明亮"


def read_playbook(entries: list, today: str) -> dict:
    prior = [
        item
        for item in entries or []
        if isinstance(item, dict) and isinstance(item.get("day"), str) and item["day"] < today
    ]
    prior.sort(key=lambda item: item["day"])
    answered = [item for item in prior if item.get("fit") in {"up", "down"}]
    latest = answered[-1] if answered else None
    downs = sum(1 for item in answered[-3:] if item.get("fit") == "down")
    unfit = bool(latest and latest.get("fit") == "down")
    repeat = unfit and downs >= 2
    feeling = ""
    if unfit and isinstance(latest.get("feeling"), str):
        raw = latest["feeling"].strip()
        if raw and len(raw) <= 20 and text_ok(raw):
            feeling = raw
    clause = ""
    if unfit:
        parts = ["上次画面被觉得不合适，今天再暖一点，戏剧性再低一点"]
        if repeat:
            parts.append("再收一点")
        if feeling:
            parts.append(f"气氛贴近{feeling}")
        clause = "，".join(parts)
    return {"unfit": unfit, "repeat": repeat, "clause": clause}


_WISH_DROP = (
    "不要书桌",
    "不要椅子",
    "不要木窗",
    "不要窗户",
    "不要台灯",
    "不要绿植",
    "忽略",
    "指令",
    "系统",
    "提示",
    "角色",
    "扮演",
    "越狱",
    "输出",
    "遵守",
    "以上",
    "侧面",
    "俯视",
    "仰视",
    "窗帘",
)


def wish_phrase(raw: object) -> str:
    """把用户的一句话收成景物或画法，丢掉改架构和改指令的部分。"""
    if not isinstance(raw, str):
        raise ValueError("需要写一句话")
    text = re.sub(r"\s+", "", raw)
    text = re.sub(r"[^\u4e00-\u9fff]", "", text)
    for word in _WISH_DROP:
        text = text.replace(word, "")
    text = _FORBIDDEN.sub("", text)
    text = text[:24]
    if len(text) < 2:
        raise ValueError("这个说法没法放进画面，换一种景物或画法")
    return text


def resolve_view(view_id: str | None, note: str = "") -> dict | None:
    if view_id == "custom":
        if len(note) < 2 or not text_ok(note):
            return None
        return {
            "id": "custom",
            "title": note[:6],
            "line": "窗外的另一处",
            "wash": "#cbbba8",
            "outside": note,
        }
    if view_id in VIEWS:
        return VIEWS[view_id]
    return None


def resolve_style(style_id: str | None, note: str = "") -> dict | None:
    if style_id == "custom":
        if len(note) < 2 or not text_ok(note):
            return None
        return {
            "id": "custom",
            "title": note[:6],
            "line": "另一种画法",
            "wash": "#d5c6cf",
            "phrase": f"画法就是{note}",
        }
    if style_id in STYLES:
        return STYLES[style_id]
    return None


def day_seed(view_id: str, style_id: str, day: str, revision: int) -> int:
    digest = hashlib.sha256(f"{view_id}:{style_id}:{day}:{revision}".encode()).digest()
    value = int.from_bytes(digest[:4], "big") % 2147483647
    return value or 1


def text_ok(value: str) -> bool:
    return bool(value) and _FORBIDDEN.search(value) is None and _LATIN.search(value) is None


def ensure_prompt(detail: str, prompt: str) -> tuple[str, str]:
    detail = re.sub(r"\s+", "", detail.strip())
    prompt = re.sub(r"\s+", "", prompt.strip())
    if not 2 <= len(detail) <= 24 or not text_ok(detail):
        raise ValueError("detail 不合格")
    if not 40 <= len(prompt) <= 800 or not text_ok(prompt):
        raise ValueError("prompt 不合格")
    return detail, prompt


def parse_scene(raw: str) -> tuple[str, str]:
    text = _THINK.sub("", raw).strip()
    text = _FENCE_OPEN.sub("", text.strip()).strip()
    text = re.sub(r"```$", "", text).strip()
    detail, prompt = _extract_fields(text)
    plain = re.sub(r"\s+", "", prompt.strip())
    collapsed = _collapse_repeats(plain)
    if collapsed == plain:
        try:
            return ensure_prompt(detail, prompt)
        except ValueError:
            pass
    detail = _fit_detail(detail) or "桌上的一盆绿植"
    prompt = _fit_prompt(collapsed)
    return ensure_prompt(detail, prompt)


def build_messages(view: dict, style: dict, sky: dict, params: dict, note: str, yesterday_unfit: bool, skipped: bool, guide: str = "") -> list[dict]:
    parts = [
        f"固定构图：{WINDOW}。窗外必须写成：{view['outside']}。这些词要原样出现，不要换成别的风景。",
        f"画法必须写在最前面，整幅包括书桌、椅子、木窗和窗外都用这个画法：{style['phrase']}。",
        "画法不是写实时，不要写成摄影或清楚的实景。",
        f"天气：{sky['summary']}。",
        (
            f"暖度 {params['warmth']:.2f}，遮蔽 {params['shelter']:.2f}，"
            f"开阔 {params['openness']:.2f}，天气戏剧性 {params['drama']:.2f}，"
            f"明度 {params['brightness']:.2f}，饱和度 {params['saturation']:.2f}。"
        ),
        _tone_clause(sky["summary"]),
        "书桌上的绿植保持不动。天空要留得出，水体保持平静。不要密林挡死视线，不要空荡的硬质地面。",
        "这些数目只用于把握分寸，不要写进画面描述。",
    ]
    look = _weather_look(sky["summary"])
    if look:
        parts.append(f"天气必须写成：{look}。不要改成雨，也不要收成薄薄一层。")
    if params.get("sustained", 0) >= 0.5:
        parts.append("这是持续的低落：遮蔽降到中等，窗外更开敞，视距更远，蓝天和日照变多，绿色仍是主色，饱和度仍然偏低。")
    elif params["shelter"] >= 0.65 and params["warmth"] >= 0.65:
        line = "这是刚低下来的一天：近处有遮挡，天空仍要留着，光暖而淡。"
        if not look:
            line += "天气只是薄薄一层。"
        parts.append(line)
    if skipped:
        parts.append("今天没有打分，请按平静来画。")
    if note:
        parts.append(f"今天留下的一句，可以化进静物，不要原句出现在画面里：{note}")
    if guide:
        parts.append(guide + "。")
    elif yesterday_unfit:
        parts.append("昨天的画面被觉得不合适，今天再暖一点，戏剧性再低一点。")
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": "".join(parts)},
    ]


def hour_prompts(shared: str, style: dict, view: dict, params: dict | None = None, sky: dict | None = None, guide: str = "") -> dict[str, str]:
    body = _without_layout_conflicts(_strip_style(shared, style))
    body = _hour_safe_body(body, view)
    summary = (sky or {}).get("summary") or ""
    look = _weather_look(summary)
    if _weather_family(summary):
        body = _without_conflicting_sky(body, summary)
    outside = _outside_line(view, summary)
    tone = params or {}
    custom = view.get("id") == "custom"
    prompts = {}
    for key in HOURS:
        parts = [f"{style['phrase']}，整幅包括书桌、椅子、木窗和窗外都用这个画法"]
        if look:
            parts.append(look)
        if custom:
            parts.append(outside)
        parts.extend([WINDOW, _lamp(key), _hour_clause(key, tone, view, summary)])
        if not custom:
            parts.append(outside)
        text = "。".join(parts)
        kept = _hour_body(body, key) if body else ""
        if kept:
            text = f"{text}。{kept}"
        closing_parts = [_hour_clause(key, tone, view, summary)]
        if custom:
            closing_parts.append(f"窗外的主体就是{view['outside']}，占满窗玻璃，不越出窗框")
        if style.get("id") == "custom":
            closing_parts.append(style["phrase"])
        closing_parts.append(_lamp(key))
        if look:
            closing_parts.append(look)
        if guide:
            closing_parts.append(guide)
        closing_parts.append(_WALL)
        closing = "。".join(closing_parts)
        room = 800 - len(closing) - 1
        if len(text) <= room:
            text = f"{text}。{closing}"
        elif look and room >= 40:
            text = f"{_limit(text, room)}。{closing}"
        elif guide and guide not in text and len(text) + len(guide) + 1 <= 800:
            text = f"{text}。{guide}"
        prompts[key] = text
    return prompts


def write_scene(view: dict, style: dict, sky: dict, params: dict, note: str, yesterday_unfit: bool, skipped: bool, guide: str = "") -> dict:
    messages = build_messages(view, style, sky, params, note, yesterday_unfit, skipped, guide)
    error = ""
    for _ in range(2):
        try:
            detail, prompt = parse_scene(qwen_complete(messages))
            prompt = _lead_style(prompt, style)
            return {"detail": detail, "prompt": prompt, "source": "qwen", "qwen_error": ""}
        except (QwenError, ValueError) as exc:
            error = str(exc)
    # 2B 或本地服务不可用时仍要出图，来源标成 fallback，页面会说明。
    detail, prompt = fallback_scene(view, style, sky, params, note, guide)
    return {"detail": detail, "prompt": prompt, "source": "fallback", "qwen_error": error}


def fallback_scene(view: dict, style: dict, sky: dict, params: dict, note: str, guide: str = "") -> tuple[str, str]:
    detail = _pick_detail(params)
    safe_note = note.strip()
    use_note = bool(safe_note) and len(safe_note) <= 20 and text_ok(safe_note)
    kept_guide = guide if guide and text_ok(guide) else ""
    return ensure_prompt(detail, _fallback_prompt(view, style, sky, params, detail, safe_note if use_note else "", kept_guide))


def qwen_complete(messages: list[dict], *, opener=urllib.request.urlopen) -> str:
    base = os.environ.get("QWEN_API_BASE", "http://127.0.0.1:8080/v1").rstrip("/")
    model = os.environ.get("QWEN_MODEL", "qwen3.5-2b")
    key = os.environ.get("QWEN_API_KEY", "local")
    body = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 240,
            # 2B 会把同一句复制到 token 上限，惩罚重复才能收住 JSON。
            "repeat_penalty": 1.2,
        },
        ensure_ascii=False,
    ).encode()
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with opener(req, timeout=90) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:180]
        raise QwenError(f"本地 Qwen 返回 {exc.code}：{detail}") from exc
    except TimeoutError as exc:
        raise QwenError("本地 Qwen 超时。请确认 start_qwen.sh 已在运行。") from exc
    except urllib.error.URLError as exc:
        raise QwenError(f"本地 Qwen 没有响应：{exc.reason}。请挂载移动硬盘并运行 start_qwen.sh。") from exc
    return _message_text(payload)


def _fallback_prompt(view: dict, style: dict, sky: dict, params: dict, detail: str, note: str, guide: str = "") -> str:
    parts = [
        f"{style['phrase']}，整幅包括书桌、椅子、木窗和窗外都用这个画法",
        f"{WINDOW}，窗外是{view['outside']}",
        _weather_clause(sky["summary"], params["drama"]),
        _warmth_clause(params["warmth"]),
        _shelter_clause(params["shelter"]),
        _open_clause(params["openness"]),
        _brightness_clause(params["brightness"]),
        _saturation_clause(params["saturation"]),
        "绿色是主色，可以带一点蓝，不要让红色占住画面",
        _air(sky.get("temp_c")),
        f"画面里有{detail}",
    ]
    if note:
        parts.append(f"气氛贴近{note}")
    if guide:
        parts.append(guide)
    text = "，".join(parts) + "。"
    if len(text) <= 800:
        return text
    if guide:
        parts.pop()
    return "，".join(parts) + "。"


def _lead_style(prompt: str, style: dict) -> str:
    if prompt.startswith(style["phrase"]):
        text = prompt
    else:
        text = style["phrase"] + "，整幅包括书桌、椅子、木窗和窗外都用这个画法。" + prompt
    return _limit(text, 800)


def _extract_fields(text: str) -> tuple[str, str]:
    start = text.find("{")
    if start < 0:
        raise ValueError("Qwen 没有返回 JSON")
    body = text[start:]
    end = body.rfind("}")
    if end > 0:
        try:
            obj = json.loads(body[: end + 1])
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict) and isinstance(obj.get("detail"), str) and isinstance(obj.get("prompt"), str):
            return obj["detail"], obj["prompt"]
    detail = _json_string(body, "detail")
    prompt = _json_string(body, "prompt")
    if not detail and not prompt:
        raise ValueError("Qwen 没有返回 JSON")
    return detail, prompt


def _json_string(body: str, key: str) -> str:
    match = re.search(rf'"{key}"\s*:\s*"', body)
    if not match:
        return ""
    chars: list[str] = []
    index = match.end()
    while index < len(body):
        char = body[index]
        if char == "\\" and index + 1 < len(body):
            chars.append(body[index + 1])
            index += 2
            continue
        if char == '"':
            break
        chars.append(char)
        index += 1
    return "".join(chars)


def _collapse_repeats(text: str) -> str:
    window = 12
    limit = len(text)
    for index in range(0, max(0, limit - window)):
        piece = text[index : index + window]
        found = text.find(piece, index + window)
        if found < 0:
            continue
        cycle = text[index:found]
        if len(cycle) >= window and text.startswith(cycle, found):
            return text[:found]
    return text


def _fit_detail(value: str) -> str:
    cleaned = _clean_text(value)
    if not cleaned:
        return ""
    first = cleaned.split("，")[0]
    if 2 <= len(first) <= 24 and text_ok(first):
        return first
    if 2 <= len(cleaned) <= 24 and text_ok(cleaned):
        return cleaned
    short = cleaned[:24]
    if len(short) >= 2 and text_ok(short):
        return short
    return ""


def _fit_prompt(value: str) -> str:
    cleaned = _limit(_clean_text(value), 800)
    if len(cleaned) < 40 or not text_ok(cleaned):
        raise ValueError("prompt 不合格")
    return cleaned


def _clean_text(value: str) -> str:
    collapsed = _collapse_repeats(re.sub(r"\s+", "", value.strip()))
    kept: list[str] = []
    for clause in re.split(r"[，。；、]", collapsed):
        if not clause or _FORBIDDEN.search(clause) or _LATIN.search(clause):
            continue
        if clause not in kept:
            kept.append(clause)
    return "，".join(kept)


def _limit(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    pivot = cut.rfind("，")
    if pivot >= 40:
        return cut[:pivot]
    return cut


def _pick_detail(params: dict) -> str:
    if params["brightness"] >= 0.7 and params["openness"] >= 0.7:
        return "窗光里的绿叶"
    if params["warmth"] >= 0.65:
        return "绿植叶子上的暖光"
    return "桌上摊开的书本"


def _hour_clause(chapter: str, params: dict, view: dict | None = None, summary: str = "") -> str:
    family = _weather_family(summary)
    text = _HOUR_BY_WEATHER.get((chapter, family), "")
    if not text:
        if view and view.get("id") == "custom" and chapter == "night":
            text = "夜晚。天近乎全黑。窗外沉进黑暗，不容易看清，只剩很淡的轮廓。没有日光"
        else:
            text = HOURS[chapter]
    if chapter == "morning" and params.get("sustained", 0) >= 0.5 and family not in ("fog", "rain", "cloud"):
        return text + "，天仍很早，日照只在地平线附近，不要写成正午"
    return text


def _outside_line(view: dict, summary: str = "") -> str:
    family = _weather_family(summary)
    if view.get("id") == "custom":
        words = view["outside"]
        line = f"窗外是{words}，{words}占满窗玻璃，不越出窗框，贴近窗前，清楚可辨"
        extra = _CUSTOM_WEATHER.get(family, "")
        if extra and extra not in words:
            line = f"{line}，{extra}"
        return line
    outside = _OUTSIDE.get(family, {}).get(view.get("id"), view["outside"])
    return f"窗外是{outside}"


def _hour_safe_body(text: str, view: dict) -> str:
    if view.get("id") != "custom":
        return text
    wish = view.get("outside") or ""
    banned = ("遮挡", "午后", "低矮", "院子", "沙滩", "密林", "树和岸", "房子")
    kept = []
    for clause in re.split(r"[。，]", text):
        if not clause:
            continue
        if any(token in clause and token not in wish for token in banned):
            continue
        kept.append(clause)
    return "，".join(kept)


def _lamp(chapter: str) -> str:
    if chapter == "night":
        state = "台灯亮着，灯是开的，暖光照在桌面、书本文具和绿植上，房间里只有这盏台灯发光"
    else:
        state = "台灯关着，灯是暗的，台灯不发光，桌面的光只来自窗外"
    return f"{_LAMP_LOOK}，{state}"


def _hour_body(text: str, chapter: str) -> str:
    banned = {
        "morning": ("正午", "最亮", "大亮", "白昼", "白天的日光"),
        "night": ("日光", "蓝天", "明亮", "大亮", "清晨", "正午", "日照", "晨光"),
    }.get(chapter, ())
    if not banned:
        return text
    kept = []
    for clause in re.split(r"[。，]", text):
        if clause and not any(token in clause for token in banned):
            kept.append(clause)
    return "，".join(kept)


def _strip_style(shared: str, style: dict) -> str:
    prefix = style["phrase"]
    if shared.startswith(prefix):
        return shared[len(prefix) :].lstrip("，。")
    return shared


def _without_layout_conflicts(text: str) -> str:
    kept = []
    for clause in re.split(r"[。，]", text):
        if not clause:
            continue
        if any(token in clause for token in ("台灯", "灯罩", "灯光", "灯亮", "窗帘", "百叶", "纱帘", "窗台空着", "侧面", "俯视", "仰视")):
            continue
        kept.append(clause)
    return "，".join(kept)


_SNOW_LOOK = "窗外正在下大雪，雪花是白的片状，又大又清楚，不是斜着的雨线。地面积雪很厚，近处的地面整个被雪盖住，枝头也挂着雪。没有下雨，没有雨丝"
_RAIN_LOOK = "窗外正在下雨，雨丝清楚，能看出是雨不是雪，也不是雾。地面被雨打湿。没有下雪，没有浓雾"
_FOG_LOOK = "窗外是浓雾，白雾很厚，远处完全看不清，近处也发白发灰。近处的窗和书桌还在，远处被雾吞掉。没有下雨，没有雨丝，没有雨点，地面是干的"
_CLEAR_LOOK = "窗外是晴天，天空干净，能看见太阳，光线清楚。没有下雨，没有雪，没有雾"
_CLOUD_LOOK = "窗外是阴天，天空整片发灰，看不见太阳。没有下雨，没有雪，没有雾"
_WEATHER_LOOK = {
    "晴": _CLEAR_LOOK,
    "少云": "窗外大体是晴的，只有很少的云，能看见太阳。没有下雨，没有雪，没有雾",
    "多云": "窗外多云，云挡住一部分天空，不是晴空，也没有雨和雪",
    "阴": _CLOUD_LOOK,
    "雾": _FOG_LOOK,
    "毛毛雨": _RAIN_LOOK,
    "小雨": _RAIN_LOOK,
    "雨": _RAIN_LOOK,
    "阵雨": _RAIN_LOOK,
    "雷雨": "窗外在下雨，雨清楚，不要画成雷暴，不要让闪电占住画面。地面被雨打湿。没有下雪",
    "雪": _SNOW_LOOK,
    "阵雪": _SNOW_LOOK,
}
_WEATHER_FAMILY = {
    "雪": "snow",
    "阵雪": "snow",
    "雾": "fog",
    "雨": "rain",
    "毛毛雨": "rain",
    "小雨": "rain",
    "阵雨": "rain",
    "雷雨": "rain",
    "晴": "clear",
    "少云": "clear",
    "多云": "cloud",
    "阴": "cloud",
}
_OUTSIDE = {
    "snow": {
        "shore": "一片沙滩连着大海，沙子完全被积雪埋住，岸上只看见厚雪，大片雪花正在落下，海还在远处",
        "street": "安静的街道，路面、屋顶和树都盖着厚雪，大片雪花正在落下，树和天空仍留得出来",
        "garden": "一座安静的庭院，石径、矮墙和树枝都盖着厚雪，大片雪花正在落下，树冠之间仍留出天空",
    },
    "fog": {
        "street": "安静的街道，对面的房子和树只剩近处发白的轮廓，远处和天空都被浓雾挡住",
        "shore": "一片沙滩连着大海，近处的沙子是干的，远处的海和天都被浓雾挡住，看不远",
        "garden": "一座安静的庭院，近处的树、石径和矮墙发白发虚，天空被浓雾挡住",
    },
    "rain": {
        "street": "安静的街道，对面是压得很低的房子和一棵树，雨丝落在路面和树上，地面是湿的",
        "shore": "一片沙滩连着大海，沙子被雨打湿，颜色变深，雨丝落在岸上，海面仍在远处",
        "garden": "一座安静的庭院，雨落在树、石径和矮墙上，石径是湿的，树冠之间留出灰蒙蒙的天空",
    },
    "clear": {
        "street": "安静的街道，对面是压得很低的房子和一棵树，天空干净，树和天空都看得清楚",
        "shore": "一片沙滩连着大海，近处是细沙，海面平静地铺向远处，天空干净",
        "garden": "一座安静的庭院，有树、石径和矮墙，树冠之间留出干净的天空",
    },
    "cloud": {
        "street": "安静的街道，对面是压得很低的房子和一棵树，天空灰白，没有太阳，树和天空仍留得出来",
        "shore": "一片沙滩连着大海，近处是细沙，海面平静地铺向远处，天空灰白，没有太阳",
        "garden": "一座安静的庭院，有树、石径和矮墙，树冠之间留出灰白的天空，没有太阳",
    },
}
_CUSTOM_WEATHER = {
    "snow": "地面被厚雪盖住，雪花正在落下",
    "fog": "远处被浓雾挡住",
    "rain": "雨落在窗外，近处是湿的",
    "clear": "天空干净，是晴天",
    "cloud": "天空发灰，没有太阳，也没有雨",
}
_HOUR_BY_WEATHER = {
    ("morning", "fog"): "清晨，时间很早，还在正午之前很久。天色发白发灰，是浓雾里的亮，看不见太阳。窗外只亮起一条，室内大部分仍暗，书桌上只有一点点冷的晨光",
    ("noon", "fog"): "正午。这是一天里相对亮一些的时候，光是散的，从浓雾里来，不是直射的太阳，远处仍然看不清",
    ("dusk", "fog"): "黄昏。光从雾里透出来，暖而淡，看不见清楚的太阳，整幅不要发红，远处仍然看不清",
    ("morning", "rain"): "清晨，时间很早，还在正午之前很久。天色是深的蓝灰，太阳被云和雨挡住。窗外只亮起一条，室内大部分仍暗，书桌上只有一点点冷的晨光，雨还在下",
    ("noon", "rain"): "正午。照在书桌上的光来自窗外，被云和雨压着，不是晴天，这是一天里相对最亮的时候，雨还在下",
    ("dusk", "rain"): "黄昏。暖光从云和雨后面透出来，天空偏暖，整幅不要发红，雨还在下",
    ("morning", "cloud"): "清晨，时间很早，还在正午之前很久。天色是深的蓝灰，太阳没有露出来。窗外只亮起一条，室内大部分仍暗，书桌上只有一点点冷的晨光",
    ("noon", "cloud"): "正午。照在书桌上的光来自窗外，被云压着，均匀，没有直射的太阳，也没有雨，这是一天里相对最亮的时候",
    ("dusk", "cloud"): "黄昏。暖光从云后面透出来，看不见清楚的太阳，天空偏暖，整幅不要发红，没有雨",
    ("night", "snow"): "夜晚。天近乎全黑。窗外的景物沉进黑暗，不容易看清，但地面的积雪仍是一块发白的厚雪，雪还在下。没有日光",
}
_SKY_BAN = {
    "fog": ("雨", "雪", "淋", "湿", "晴", "太阳", "蓝天", "日照", "纵深", "细沙", "沙地"),
    "snow": ("雨", "淋", "湿", "雾", "晴", "蓝天", "细沙", "沙地"),
    "rain": ("雪", "雾", "晴", "太阳", "蓝天", "细沙", "沙地", "小雨"),
    "clear": ("雨", "雪", "雾", "雷", "阴", "湿", "淋", "水滴"),
    "cloud": ("雨", "雪", "雾", "晴", "蓝天", "日照", "湿", "淋", "水滴"),
}


def _weather_family(summary: str) -> str:
    return _WEATHER_FAMILY.get(summary, "")


def _weather_look(summary: str) -> str:
    return _WEATHER_LOOK.get(summary, "")


def _tone_clause(summary: str) -> str:
    family = _weather_family(summary)
    distance = "开阔高就多留天空，把视距拉远。"
    if family == "snow":
        weather_rule = "这种天气不要收成薄薄一层，也不要写成雨。"
    elif family == "fog":
        weather_rule = "雾要写得很厚，不要收成薄薄一层，也不要写成雨。"
        distance = "即使开阔，远处也要被雾挡住，不要把视距拉远。"
    elif family == "rain":
        weather_rule = "雨要看得见，不要写成雪或雾，也不要收成几乎看不出的一层。"
    elif family == "clear":
        weather_rule = "写成晴天，不要写成雨、雪或雾。"
    elif family == "cloud":
        weather_rule = "写成云天，不要写成雨、雪，也不要写成大太阳。"
    else:
        weather_rule = "戏剧性低就把天气收成薄薄一层，阵雨和雷雨也写成缓慢、低对比，不要占满视线。"
    return (
        "暖度高就在低处留暖色。遮蔽高时近处有植物遮挡，边缘大约一半能看透，不要封死。"
        + distance
        + weather_rule
        + "明度高就更亮。饱和度低就色彩淡、对比弱。"
    )


def _without_conflicting_sky(text: str, summary: str) -> str:
    look = _weather_look(summary)
    family = _weather_family(summary)
    banned = ("轻轻的一层", "薄薄一层", "薄雾", "轻雾", "淡雾", "薄雪", "小雪", "零星") + _SKY_BAN.get(family, ())
    kept = []
    for clause in re.split(r"[。，]", text):
        if not clause or (look and clause in look):
            continue
        if any(token in clause for token in banned):
            continue
        kept.append(clause)
    return "，".join(kept)


def _weather_clause(summary: str, drama: float) -> str:
    look = _weather_look(summary)
    if look:
        return look
    if drama < 0.35:
        return f"天气只是轻轻的一层{summary}"
    if drama < 0.65:
        return f"天气清楚可辨，是{summary}"
    return f"天气占住视线，是{summary}，仍然缓慢"


def _warmth_clause(warmth: float) -> str:
    if warmth >= 0.65:
        return "低处留着暖色的光"
    if warmth >= 0.45:
        return "日光中性而柔和"
    return "色调偏凉，光比较均匀"


def _shelter_clause(shelter: float) -> str:
    if shelter >= 0.65:
        return "近处有植物遮挡，边缘大约一半能看透，天空仍留着"
    if shelter >= 0.4:
        return "窗框住视线，远处仍可辨"
    return "空间比较舒展"


def _open_clause(openness: float) -> str:
    if openness >= 0.72:
        return "天空留得宽，纵深比较远"
    if openness >= 0.5:
        return "天空留出一角，视线能往外走"
    return "视线停在近处"


def _brightness_clause(brightness: float) -> str:
    if brightness >= 0.72:
        return "画面偏亮，日照清楚"
    if brightness >= 0.5:
        return "明度适中"
    return "光线收着，景物仍清楚"


def _saturation_clause(saturation: float) -> str:
    if saturation >= 0.46:
        return "色彩清楚不过艳"
    if saturation >= 0.32:
        return "色彩偏淡"
    return "色彩很淡，对比很弱"


def _air(temp: float | None) -> str:
    if temp is None:
        return "空气平稳"
    if temp < 12:
        return "空气偏凉"
    if temp > 28:
        return "空气偏暖"
    return "空气温和"


def _message_text(payload: dict) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise QwenError("Qwen 的响应里没有文本") from exc
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        if parts:
            return "".join(parts)
    raise QwenError("Qwen 的响应里没有文本")


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
