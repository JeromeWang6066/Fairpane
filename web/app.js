const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const stage = document.querySelector("#stage");
const photoA = document.querySelector("#photo-a");
const photoB = document.querySelector("#photo-b");
const statusEl = document.querySelector("#status");
const picker = document.querySelector("#picker");
const wish = document.querySelector("#wish");
const wishForm = document.querySelector("#wish-form");
const reveal = document.querySelector("#reveal");
const checkin = document.querySelector("#checkin");
const checkinForm = document.querySelector("#checkin-form");
const REVEAL_MS = reduceMotion ? 80 : 900;
const REVEAL_FADE_MS = reduceMotion ? 0 : 700;
const mood = document.querySelector("#mood");
const moodValue = document.querySelector("#mood-value");
const moodWord = document.querySelector("#mood-word");
const MOOD_WORDS = {
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
};
const note = document.querySelector("#note");
const begin = document.querySelector("#begin");
const skip = document.querySelector("#skip");
const failure = document.querySelector("#failure");
const failureText = document.querySelector("#failure-text");
const retry = document.querySelector("#retry");
const fit = document.querySelector("#fit");
const nextDay = document.querySelector("#next-day");
const scrub = document.querySelector("#scrub");
const moodDock = document.querySelector("#mood-dock");
const moodMark = document.querySelector("#mood-mark");
const moodPop = document.querySelector("#mood-pop");
const moodEdit = document.querySelector("#mood-edit");
const moodEditValue = document.querySelector("#mood-edit-value");

let serverState = null;
let step = "view";
let manualChapter = null;
let fadeMs = 0;
let lastPayload = null;
let statusTimer = 0;
let pollTimer = 0;
let revealTimer = 0;
let fallbackNoted = false;
let shown = photoA;
let coords = null;
let busy = false;
let wishKind = "view";
let weatherChoice = "";

mood.addEventListener("input", () => {
  showMood(mood.value);
});

document.querySelectorAll("#weather button").forEach((button) => {
  button.addEventListener("click", () => {
    weatherChoice = button.dataset.weather || "";
    document.querySelectorAll("#weather button").forEach((item) => {
      item.classList.toggle("is-on", item === button);
    });
  });
});

checkinForm.addEventListener("submit", (event) => {
  event.preventDefault();
  submitCheckin({
    skip: false,
    mood: Number(mood.value),
    note: note.value,
    weather: weatherChoice,
    ...coordsPayload(),
  });
});

skip.addEventListener("click", () => {
  submitCheckin({ skip: true, note: "", weather: weatherChoice, ...coordsPayload() });
});

retry.addEventListener("click", () => {
  const day = serverState && serverState.day;
  const payload = lastPayload || {
    skip: Boolean(day && day.skipped),
    mood: day && day.mood ? day.mood : 5,
    note: "",
    ...coordsPayload(),
  };
  submitCheckin(payload);
});

document.querySelector("#fit-up").addEventListener("click", () => sendFit("up"));
document.querySelector("#fit-down").addEventListener("click", openFitNote);
document.querySelector("#fit-note").addEventListener("submit", (event) => {
  event.preventDefault();
  sendFit("down", document.querySelector("#fit-feeling").value);
});
document.querySelector("#fit-skip").addEventListener("click", () => sendFit("down", ""));
nextDay.addEventListener("click", enterNextDay);

scrub.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  manualChapter = button.dataset.chapter;
  applyChapter(manualChapter);
  const day = serverState && serverState.day;
  const url = day && day.images && day.images[manualChapter];
  if (!url) {
    const pending = (day && day.pending) || [];
    setStatus(pending.includes(manualChapter) ? "这一张还在画" : "这一张没有画成");
    return;
  }
  showPhoto(url, reduceMotion ? 400 : 1000);
  renderFit();
});

moodMark.addEventListener("click", () => {
  moodPop.hidden = !moodPop.hidden;
  if (!moodPop.hidden && serverState && serverState.day && serverState.day.mood) {
    moodEdit.value = String(serverState.day.mood);
    moodEditValue.textContent = moodEdit.value;
  }
});

moodEdit.addEventListener("input", () => {
  moodEditValue.textContent = moodEdit.value;
});

moodEdit.addEventListener("change", () => {
  const value = Number(moodEdit.value);
  if (!serverState || !serverState.day || serverState.day.mood === value || busy) return;
  submitMood(value);
});

if (navigator.geolocation) {
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      coords = { lat: pos.coords.latitude, lon: pos.coords.longitude };
    },
    () => {},
    { timeout: 4000, maximumAge: 600000 }
  );
}

setStatus("正在打开", true);
load();

async function load() {
  try {
    const res = await fetch("/api/state");
    serverState = await res.json();
    setStatus("");
    step = "view";
    render();
  } catch (_err) {
    setStatus("页面没有连上本地服务");
  }
}

function render() {
  if (!serverState) return;
  applyChapter(chapterNow());
  if (serverState.view) stage.style.background = serverState.view.wash;
  if (step === "view") {
    showChoices("先选窗外的景观", serverState.views, chooseView, {
      title: "还想去其他地方",
      line: "写下窗外想看见的",
      kind: "view",
    });
    return;
  }
  if (step === "style") {
    showChoices("再选一种风格", serverState.styles, chooseStyle, {
      title: "想要其他的风格",
      line: "写下想要的画法",
      kind: "style",
    });
    return;
  }
  if (step === "score") {
    showCheckin();
    return;
  }
  const day = serverState.day;
  if (!anyPhoto(day)) {
    showFailure((day && day.error) || "画面没有生成");
    return;
  }
  showWall(day);
}

function showChoices(lead, items, onChoose, custom) {
  leaveWall();
  picker.hidden = false;
  document.querySelector("#picker-lead").textContent = lead;
  picker.querySelectorAll("button.place").forEach((node) => node.remove());
  (items || []).forEach((item) => {
    picker.append(choiceButton(item, () => onChoose(item.id)));
  });
  if (custom) {
    picker.append(choiceButton(
      { title: custom.title, line: custom.line, wash: "#d9cfc3" },
      () => openWish(custom),
      true,
    ));
  }
}

function choiceButton(item, onClick, custom) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = custom ? "place place-custom" : "place";
  button.style.setProperty("--wash", item.wash);
  const name = document.createElement("span");
  name.className = "name";
  name.textContent = item.title;
  const line = document.createElement("span");
  line.className = "line";
  line.textContent = item.line;
  button.append(name, line);
  button.addEventListener("click", onClick);
  return button;
}

function openWish(custom) {
  wishKind = custom.kind;
  picker.hidden = true;
  wish.hidden = false;
  document.querySelector("#wish-title").textContent = custom.title;
  document.querySelector("#wish-lead").textContent = custom.kind === "view" ? "窗外" : "画法";
  const input = document.querySelector("#wish-text");
  input.placeholder = custom.kind === "view" ? "例如：京都的枫叶" : "例如：淡淡的水彩";
  input.value = "";
  input.focus();
}

wishForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = document.querySelector("#wish-text").value;
  if (wishKind === "view") {
    chooseOption("/api/view", "custom", "没有选定窗外的景观", "style", text);
    return;
  }
  chooseOption("/api/style", "custom", "没有选定风格", "score", text);
});

document.querySelector("#wish-back").addEventListener("click", () => {
  wish.hidden = true;
  render();
});

function chooseView(id) {
  chooseOption("/api/view", id, "没有选定窗外的景观", "style");
}

function chooseStyle(id) {
  chooseOption("/api/style", id, "没有选定风格", "score");
}

async function chooseOption(url, id, errorText, nextStep, text) {
  if (busy) return;
  busy = true;
  try {
    const payload = text ? { id, text } : { id };
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await readJson(res);
    if (body.state) serverState = body.state;
    if (!res.ok) {
      setStatus(body.error || errorText);
      return;
    }
    if (nextStep === "score") {
      mood.value = "5";
      showMood("5");
      note.value = "";
    }
    step = nextStep;
    render();
  } catch (_err) {
    setStatus("页面没有连上本地服务");
  } finally {
    busy = false;
  }
}

function showMood(value) {
  moodValue.textContent = value;
  moodWord.textContent = MOOD_WORDS[Number(value)] || "";
}

function showCheckin() {
  leaveWall();
  checkin.hidden = false;
  const kicker = document.querySelector(".kicker");
  if (kicker && serverState.view && serverState.style) {
    kicker.textContent = serverState.view.title + " · " + serverState.style.title;
  }
  document.body.classList.add("is-plain");
  stage.style.background = "#161311";
}

function showFailure(message) {
  leaveWall();
  failure.hidden = false;
  failureText.textContent = message || "画面没有生成";
  showBackdrop(0);
}

function showWall(day) {
  picker.hidden = true;
  checkin.hidden = true;
  failure.hidden = true;
  document.body.classList.remove("is-plain");
  moodDock.hidden = false;
  scrub.hidden = false;
  const ms = fadeMs;
  fadeMs = 0;
  const url = photoFor(day);
  if (!url) setStatus("这一张没有画成");
  else showPhoto(url, ms);
  if (day.error) setStatus(day.error);
  else if (day.prompt_source === "fallback" && !fallbackNoted) {
    fallbackNoted = true;
    const reason = day.qwen_error || "";
    const offline = reason.includes("没有响应") || reason.includes("超时");
    setStatus(offline ? "本地文字模型没连上，这张用了保底配方。" : "本地模型的提示没能用上，这张用了保底配方。");
  }
  renderFit();
  renderNext();
}

function leaveWall() {
  picker.hidden = true;
  wish.hidden = true;
  checkin.hidden = true;
  failure.hidden = true;
  moodDock.hidden = true;
  moodPop.hidden = true;
  scrub.hidden = true;
  fit.hidden = true;
  nextDay.hidden = true;
  document.body.classList.remove("is-plain");
  if (step !== "wall") stopReveal();
}

function showBackdrop(ms) {
  const today = photoFor(serverState.day) || firstPhoto(serverState.day);
  const url = today || serverState.yesterday_image_url;
  if (url) showPhoto(url, ms);
}

function photoFor(day) {
  const images = (day && day.images) || {};
  return images[chapterNow()] || "";
}

function firstPhoto(day) {
  const images = (day && day.images) || {};
  return images.morning || images.noon || images.dusk || images.night || "";
}

function anyPhoto(day) {
  return Boolean(firstPhoto(day));
}

async function submitCheckin(payload) {
  if (busy) return;
  lastPayload = payload;
  busy = true;
  begin.disabled = true;
  skip.disabled = true;
  fadeMs = reduceMotion ? 400 : 2000;
  const started = Date.now();
  startReveal();
  document.body.classList.add("is-busy");
  try {
    const res = await fetch("/api/checkin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await readJson(res);
    if (body.state) serverState = body.state;
    step = "wall";
    if (!res.ok) {
      fadeMs = 0;
      stopReveal();
      setStatus("");
      render();
      if (!serverState.day || !serverState.day.error) setStatus(body.error || "画面没有生成");
      return;
    }
    await holdReveal(started);
    manualChapter = null;
    applyChapter(chapterNow());
    render();
    stopReveal();
    notePending();
  } catch (_err) {
    fadeMs = 0;
    stopReveal();
    setStatus("页面没有连上本地服务");
  } finally {
    busy = false;
    begin.disabled = false;
    skip.disabled = false;
    document.body.classList.remove("is-busy");
  }
}

function startReveal() {
  window.clearTimeout(revealTimer);
  reveal.setAttribute("aria-hidden", "false");
  document.body.classList.add("is-revealing");
  requestAnimationFrame(() => {
    requestAnimationFrame(() => reveal.classList.add("is-on"));
  });
}

function stopReveal() {
  reveal.classList.remove("is-on");
  window.clearTimeout(revealTimer);
  revealTimer = window.setTimeout(() => {
    document.body.classList.remove("is-revealing");
    reveal.setAttribute("aria-hidden", "true");
  }, REVEAL_FADE_MS);
}

function holdReveal(started) {
  const wait = Math.max(0, REVEAL_MS - (Date.now() - started));
  if (!wait) return Promise.resolve();
  return new Promise((resolve) => window.setTimeout(resolve, wait));
}

async function submitMood(value) {
  busy = true;
  moodEdit.disabled = true;
  fadeMs = reduceMotion ? 400 : 60000;
  setStatus("正在画清晨", true);
  document.body.classList.add("is-busy");
  try {
    const res = await fetch("/api/mood", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mood: value, ...coordsPayload() }),
    });
    const body = await readJson(res);
    if (body.state) serverState = body.state;
    if (!res.ok) {
      fadeMs = 0;
      setStatus(body.error || "没有换成新的画面");
      render();
      return;
    }
    manualChapter = "morning";
    applyChapter("morning");
    render();
    notePending();
  } catch (_err) {
    fadeMs = 0;
    setStatus("页面没有连上本地服务");
  } finally {
    busy = false;
    moodEdit.disabled = false;
    document.body.classList.remove("is-busy");
  }
}

function showFitChoices() {
  document.querySelector("#fit-ask").hidden = false;
  document.querySelector("#fit-up").hidden = false;
  document.querySelector("#fit-down").hidden = false;
  document.querySelector("#fit-note").hidden = true;
  document.querySelector("#fit-feeling").value = "";
  fit.classList.remove("is-open");
}

function openFitNote() {
  document.querySelector("#fit-ask").hidden = true;
  document.querySelector("#fit-up").hidden = true;
  document.querySelector("#fit-down").hidden = true;
  document.querySelector("#fit-note").hidden = false;
  fit.classList.add("is-open");
  document.querySelector("#fit-feeling").focus();
}

async function sendFit(value, feeling) {
  if (busy) return;
  busy = true;
  const payload = { fit: value };
  if (value === "down") payload.feeling = feeling || "";
  try {
    const res = await fetch("/api/fit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await readJson(res);
    if (body.state) serverState = body.state;
    if (!res.ok) {
      setStatus(body.error || "没有记下这次反馈");
      fit.hidden = false;
      if (value === "down") openFitNote();
      return;
    }
    renderFit();
    renderNext();
  } catch (_err) {
    setStatus("页面没有连上本地服务");
    if (value === "down") openFitNote();
  } finally {
    busy = false;
  }
}

function showPhoto(url, ms) {
  if (!url) return;
  if (shown.dataset.src === url && shown.style.opacity === "1") return;
  const incoming = shown.style.opacity === "1" ? (shown === photoA ? photoB : photoA) : shown;
  if (incoming.dataset.pending === url) return;
  const outgoing = incoming === photoA ? photoB : photoA;
  const paint = () => {
    incoming.dataset.pending = "";
    incoming.dataset.src = url;
    incoming.style.transitionDuration = ms + "ms";
    outgoing.style.transitionDuration = ms + "ms";
    const finish = () => {
      incoming.style.opacity = "1";
      outgoing.style.opacity = "0";
      shown = incoming;
    };
    if (ms === 0) {
      finish();
      return;
    }
    incoming.style.opacity = "0";
    requestAnimationFrame(() => requestAnimationFrame(finish));
  };
  if (incoming.dataset.src === url && incoming.complete && incoming.naturalWidth) {
    paint();
    return;
  }
  incoming.dataset.pending = url;
  incoming.onload = paint;
  incoming.onerror = () => {
    incoming.dataset.pending = "";
    setStatus("画面没有加载出来");
  };
  incoming.src = url;
}

function renderFit() {
  const day = serverState && serverState.day;
  const evening = chapterNow() === "night" || new Date().getHours() >= 20;
  const show = Boolean(day && anyPhoto(day) && !day.fit && evening && scrub.hidden === false);
  const wasHidden = fit.hidden;
  fit.hidden = !show;
  if (!show || wasHidden) showFitChoices();
}

function renderNext() {
  const day = serverState && serverState.day;
  nextDay.hidden = !(scrub.hidden === false && anyPhoto(day) && day.fit);
}

async function enterNextDay() {
  if (busy) return;
  busy = true;
  nextDay.disabled = true;
  try {
    const res = await fetch("/api/next", { method: "POST" });
    const body = await readJson(res);
    if (body.state) serverState = body.state;
    if (!res.ok) {
      setStatus(body.error || "没有进入下一天");
      renderNext();
      return;
    }
    manualChapter = null;
    fallbackNoted = false;
    step = "view";
    render();
  } catch (_err) {
    setStatus("页面没有连上本地服务");
  } finally {
    busy = false;
    nextDay.disabled = false;
  }
}

function chapterNow() {
  if (manualChapter) return manualChapter;
  const hour = new Date().getHours();
  if (hour >= 5 && hour < 10) return "morning";
  if (hour >= 10 && hour < 16) return "noon";
  if (hour >= 16 && hour < 19) return "dusk";
  return "night";
}

function applyChapter(name) {
  stage.dataset.chapter = name;
  scrub.querySelectorAll("[data-chapter]").forEach((button) => {
    const on = button.dataset.chapter === name;
    button.classList.toggle("is-on", on);
    button.setAttribute("aria-pressed", on ? "true" : "false");
  });
}

function notePending() {
  const pending = (serverState && serverState.day && serverState.day.pending) || [];
  if (!pending.length) {
    setStatus("");
    return;
  }
  setStatus("其余时辰还在画", true);
  watchPending();
}

function watchPending() {
  window.clearTimeout(pollTimer);
  const pending = (serverState && serverState.day && serverState.day.pending) || [];
  if (!pending.length) return;
  pollTimer = window.setTimeout(pullState, 1500);
}

async function pullState() {
  try {
    const res = await fetch("/api/state");
    if (!res.ok) {
      watchPending();
      return;
    }
    serverState = await res.json();
    const url = photoFor(serverState.day);
    if (url) showPhoto(url, reduceMotion ? 400 : 1000);
    notePending();
  } catch (_err) {
    watchPending();
  }
}

function setStatus(text, sticky) {
  window.clearTimeout(statusTimer);
  statusEl.hidden = !text;
  statusEl.textContent = text || "";
  if (text && !sticky) {
    statusTimer = window.setTimeout(() => {
      statusEl.hidden = true;
    }, 6000);
  }
}

function coordsPayload() {
  return coords ? { lat: coords.lat, lon: coords.lon } : {};
}

async function readJson(res) {
  try {
    return await res.json();
  } catch (_err) {
    return {};
  }
}
