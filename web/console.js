const COPY = {
  zh: {
    heading: "画面",
    place: "地点",
    style: "风格",
    time: "时间",
    timeHint: "从这时辰开始画，更早的不再画",
    mood: "心情",
    weather: "天气",
    morning: "晨",
    noon: "午",
    dusk: "暮",
    night: "夜",
    moodLow: "低",
    moodHigh: "高",
    moodAria: "心情分数",
    local: "当地",
    clear: "晴",
    cloudy: "多云",
    overcast: "阴",
    rain: "雨",
    snow: "雪",
    fog: "雾",
    viewWish: "还想去其他地方",
    styleWish: "想要其他的画法",
    note: "可以写一句，也可以不写",
    again: "重新生成",
    restore: "换回原来的壁纸",
    langSwitch: "English",
    langAria: "Switch to English",
    views: { street: "街道", shore: "海岸", garden: "庭院" },
    styles: { realistic: "写实", ink: "水彩", anime: "动漫" },
    moods: {
      1: "心情很糟",
      2: "很难受",
      3: "不太好",
      4: "有点低落",
      5: "还好",
      6: "平静",
      7: "不错",
      8: "挺开心",
      9: "很开心",
      10: "非常开心",
    },
    hours: { morning: "清晨", noon: "正午", dusk: "黄昏", night: "夜晚" },
    drawing: "正在画",
    offline: "页面没有连上本地服务",
    restored: "已经换回打开前的壁纸",
    restoreFail: "没有换回去",
    noView: "没有选定地点",
    noStyle: "没有选定风格",
    noImage: "画面没有生成",
    paintingRest: "其余时辰还在画",
    done: "今天的画面好了",
    fallbackOffline: "本地文字模型没连上，这张用了保底配方。",
    fallbackBad: "本地模型的提示没能用上，这张用了保底配方。",
  },
  en: {
    heading: "Picture",
    place: "Place",
    style: "Style",
    time: "Time",
    timeHint: "Painting starts from this hour. Earlier hours are left undrawn.",
    mood: "Mood",
    weather: "Weather",
    morning: "Dawn",
    noon: "Noon",
    dusk: "Dusk",
    night: "Night",
    moodLow: "Low",
    moodHigh: "High",
    moodAria: "Mood score",
    local: "Local",
    clear: "Clear",
    cloudy: "Cloudy",
    overcast: "Overcast",
    rain: "Rain",
    snow: "Snow",
    fog: "Fog",
    viewWish: "Somewhere else",
    styleWish: "Another way of painting",
    note: "A line is optional",
    again: "Generate again",
    restore: "Restore the previous wallpaper",
    langSwitch: "中文",
    langAria: "切换到中文",
    views: { street: "Street", shore: "Shore", garden: "Garden" },
    styles: { realistic: "Realistic", ink: "Watercolor", anime: "Anime" },
    moods: {
      1: "Very bad",
      2: "Miserable",
      3: "Not good",
      4: "A bit low",
      5: "All right",
      6: "Calm",
      7: "Pretty good",
      8: "Glad",
      9: "Happy",
      10: "Very happy",
    },
    hours: { morning: "dawn", noon: "midday", dusk: "dusk", night: "night" },
    drawing: "Painting ",
    offline: "The page is not connected to the local service",
    restored: "The wallpaper from before opening is back",
    restoreFail: "Could not restore the wallpaper",
    noView: "No place chosen",
    noStyle: "No style chosen",
    noImage: "The picture was not made",
    paintingRest: "The other hours are still being painted",
    done: "Today's pictures are ready",
    fallbackOffline: "The local text model is offline. This one used the fallback recipe.",
    fallbackBad: "The local model's prompt could not be used. This one used the fallback recipe.",
  },
};

const ERRORS = {
  "现在没有在换桌面": "The desktop is not being changed",
  "没有记下打开前的壁纸": "The previous wallpaper was not saved",
  "还没有选定窗外的景观": "Choose a view first",
  "还没有选定风格": "Choose a style first",
  "没有这处窗外的景观": "That view is not available",
  "没有这种风格": "That style is not available",
  "今天还没有画面": "There is no picture for today yet",
  "没有这个时辰": "That hour is not available",
  "分数需要是 1 到 10": "The score must be from 1 to 10",
  "没有这种天气": "That weather is not available",
  "那一句需要是文字": "That line needs to be text",
  "需要写一句话": "Write a short line",
  "这个说法没法放进画面，换一种景物或画法": "That cannot go into the picture. Try another view or style.",
  "没有 DASHSCOPE_API_KEY，无法生成画面。": "No DashScope API key, so the picture could not be made.",
  "出图接口超时": "The image service timed out.",
  "图片地址不在预期的存储域名上": "The image address is not on the expected host.",
  "返回的不是 PNG": "The response was not a PNG.",
  "响应里没有图片": "The response had no image.",
};

const statusEl = document.querySelector("#status");
const viewsEl = document.querySelector("#views");
const stylesEl = document.querySelector("#styles");
const viewCustom = document.querySelector("#view-custom");
const styleCustom = document.querySelector("#style-custom");
const mood = document.querySelector("#mood");
const moodValue = document.querySelector("#mood-value");
const moodWord = document.querySelector("#mood-word");
const note = document.querySelector("#note");
const again = document.querySelector("#again");
const restore = document.querySelector("#restore");
const langBtn = document.querySelector("#lang");

let lang = localStorage.getItem("fairpane-lang") === "en" ? "en" : "zh";
let lastStatus = { key: "", sticky: false, extra: "" };
let serverState = null;
let viewId = "";
let styleId = "";
let chapter = "";
let weatherChoice = "";
let chapterChosen = false;
let busy = false;
let pollTimer = 0;
let coords = null;

mood.addEventListener("input", () => showMood(mood.value));
langBtn.addEventListener("click", () => setLang(lang === "zh" ? "en" : "zh"));

document.querySelectorAll("#chapters button").forEach((button) => {
  button.addEventListener("click", () => {
    chapterChosen = true;
    chapter = button.dataset.chapter;
    markChapters();
  });
});

document.querySelectorAll("#weather button").forEach((button) => {
  button.addEventListener("click", () => {
    weatherChoice = button.dataset.weather || "";
    document.querySelectorAll("#weather button").forEach((item) => {
      item.classList.toggle("is-on", item === button);
    });
  });
});

again.addEventListener("click", regenerate);
restore.addEventListener("click", restoreWallpaper);

if (navigator.geolocation) {
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      coords = { lat: pos.coords.latitude, lon: pos.coords.longitude };
    },
    () => {},
    { timeout: 4000, maximumAge: 600000 }
  );
}

applyLang();
load();

function copy() {
  return COPY[lang];
}

function setLang(next) {
  lang = next === "en" ? "en" : "zh";
  localStorage.setItem("fairpane-lang", lang);
  applyLang();
}

function applyLang() {
  const pack = copy();
  document.documentElement.lang = lang === "en" ? "en" : "zh-Hans";
  document.title = lang === "en" ? "Fairpane" : "窗景心晴";
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const key = node.getAttribute("data-i18n");
    if (pack[key]) node.textContent = pack[key];
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    const key = node.getAttribute("data-i18n-placeholder");
    if (pack[key]) node.setAttribute("placeholder", pack[key]);
  });
  document.querySelectorAll("[data-i18n-aria]").forEach((node) => {
    const key = node.getAttribute("data-i18n-aria");
    if (pack[key]) node.setAttribute("aria-label", pack[key]);
  });
  langBtn.textContent = pack.langSwitch;
  langBtn.setAttribute("aria-label", pack.langAria);
  showMood(mood.value);
  if (serverState) fill(serverState);
  renderStatus();
}

function tError(text) {
  if (!text) return copy().noImage;
  if (lang === "zh") return text;
  if (ERRORS[text]) return ERRORS[text];
  if (text.includes("没有 DASHSCOPE_API_KEY")) return ERRORS["没有 DASHSCOPE_API_KEY，无法生成画面。"];
  if (text.startsWith("出图接口返回")) return "The image service returned an error.";
  if (text.startsWith("出图接口没有连上")) return "Could not reach the image service.";
  if (text.includes("本地 Qwen 没有响应")) return "The local Qwen model did not respond.";
  return text;
}

async function load() {
  try {
    const res = await fetch("/api/state");
    serverState = await res.json();
    fill(serverState);
    setStatus("");
    watch();
  } catch (_err) {
    setStatus("offline");
  }
}

function fill(state) {
  renderChoices(viewsEl, state.views, viewId || (state.view && state.view.id) || "", "views", (id) => {
    viewId = id;
    viewCustom.value = "";
  });
  renderChoices(stylesEl, state.styles, styleId || (state.style && state.style.id) || "", "styles", (id) => {
    styleId = id;
    styleCustom.value = "";
  });
  if (!viewId && state.view && state.view.id === "custom") viewCustom.value = state.view.title;
  if (!styleId && state.style && state.style.id === "custom") styleCustom.value = state.style.title;
  if (state.view && state.view.id !== "custom") viewId = state.view.id;
  if (state.style && state.style.id !== "custom") styleId = state.style.id;
  if (!chapterChosen) chapter = state.chapter || "noon";
  markChapters();
  if (state.day && state.day.mood) {
    mood.value = String(state.day.mood);
    showMood(mood.value);
  }
}

function choiceTitle(kind, item) {
  return (copy()[kind] && copy()[kind][item.id]) || item.title;
}

function renderChoices(box, items, selected, kind, onPick) {
  box.replaceChildren();
  (items || []).forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = choiceTitle(kind, item);
    button.classList.toggle("is-on", item.id === selected);
    button.addEventListener("click", () => {
      onPick(item.id);
      box.querySelectorAll("button").forEach((node) => node.classList.toggle("is-on", node === button));
    });
    box.append(button);
  });
}

function markChapters() {
  document.querySelectorAll("#chapters button").forEach((button) => {
    button.classList.toggle("is-on", button.dataset.chapter === chapter);
  });
}

function showMood(value) {
  moodValue.textContent = value;
  moodWord.textContent = copy().moods[Number(value)] || "";
}

async function restoreWallpaper() {
  if (busy) return;
  busy = true;
  restore.disabled = true;
  try {
    const res = await fetch("/api/wallpaper/restore", { method: "POST" });
    const body = await readJson(res);
    if (res.ok) setStatus("restored");
    else setStatus("error", false, body.error || copy().restoreFail);
  } catch (_err) {
    setStatus("offline");
  } finally {
    busy = false;
    restore.disabled = false;
  }
}

async function regenerate() {
  if (busy) return;
  busy = true;
  again.disabled = true;
  setStatus("drawing", true);
  try {
    if (!(await savePair("view", viewCustom.value.trim(), viewId))) return;
    if (!(await savePair("style", styleCustom.value.trim(), styleId))) return;
    const res = await fetch("/api/checkin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mood: Number(mood.value),
        note: note.value,
        weather: weatherChoice,
        chapter,
        ...(coords || {}),
      }),
    });
    const body = await readJson(res);
    if (body.state) serverState = body.state;
    if (!res.ok) {
      setStatus("error", false, body.error || copy().noImage);
      return;
    }
    noteResult(body.state);
    watch();
  } catch (_err) {
    setStatus("offline");
  } finally {
    busy = false;
    again.disabled = false;
  }
}

async function savePair(kind, text, id) {
  if (!text && !id) return true;
  const res = await fetch(kind === "view" ? "/api/view" : "/api/style", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(text ? { id: "custom", text } : { id }),
  });
  const body = await readJson(res);
  if (body.state) serverState = body.state;
  if (!res.ok) {
    setStatus("error", false, body.error || (kind === "view" ? copy().noView : copy().noStyle));
    return false;
  }
  if (text) {
    if (kind === "view") viewId = "";
    else styleId = "";
  }
  return true;
}

function noteResult(state) {
  const day = state && state.day;
  if (!day) return;
  if (day.error) {
    setStatus("error", false, day.error);
    return;
  }
  if (day.prompt_source === "fallback") {
    const reason = day.qwen_error || "";
    const offline = reason.includes("没有响应") || reason.includes("超时");
    setStatus(offline ? "fallbackOffline" : "fallbackBad");
    return;
  }
  if ((day.pending || []).length) setStatus("paintingRest", true);
  else setStatus("done");
}

function watch() {
  window.clearTimeout(pollTimer);
  const pending = (serverState && serverState.day && serverState.day.pending) || [];
  if (!pending.length) return;
  pollTimer = window.setTimeout(pull, 1500);
}

async function pull() {
  try {
    const res = await fetch("/api/state");
    if (!res.ok) {
      watch();
      return;
    }
    serverState = await res.json();
    noteResult(serverState);
    watch();
  } catch (_err) {
    watch();
  }
}

function setStatus(key, sticky, extra) {
  lastStatus = { key: key || "", sticky: !!sticky, extra: extra || "" };
  renderStatus();
}

function statusText() {
  const pack = copy();
  const { key, extra } = lastStatus;
  if (!key) return "";
  if (key === "error") return tError(extra);
  if (key === "drawing") return pack.drawing + (pack.hours[chapter] || "");
  return pack[key] || extra || "";
}

function renderStatus() {
  const text = statusText();
  const sticky = lastStatus.sticky;
  statusEl.hidden = !text;
  statusEl.textContent = text || "";
  if (text && !sticky) {
    window.setTimeout(() => {
      if (statusEl.textContent === text) statusEl.hidden = true;
    }, 6000);
  }
}

async function readJson(res) {
  try {
    return await res.json();
  } catch (_err) {
    return {};
  }
}
