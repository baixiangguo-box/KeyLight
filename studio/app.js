"use strict";

const $ = (id) => document.getElementById(id);

let ROWS = 5, COLS = 22, ROW_OFFSET = 1;
const LED_COUNT = 132;
const SWATCHES = ["#FF2B2B", "#FF8A00", "#FFD400", "#22DD55", "#00E5D0",
                  "#1E7BFF", "#8B5CF6", "#FF4FA3", "#FFFFFF"];

const EFFECTS = [
  { id: "static", label: "纯色" }, { id: "breathe", label: "呼吸" },
  { id: "rainbow", label: "彩虹" }, { id: "wave", label: "双色波" },
  { id: "chase", label: "扫描" }, { id: "sparkle", label: "星光" },
  { id: "ripple", label: "涟漪" }, { id: "audio", label: "音频律动" },
  { id: "meteor", label: "流星" }, { id: "plasma", label: "等离子" },
  { id: "fire", label: "火焰" }, { id: "aurora", label: "极光" },
  { id: "ai", label: "AI 光效" }, { id: "paint", label: "逐键涂色" },
];

const EFFECT_DETAILS = {
  static: ["M5 12h14", "用一种颜色点亮整块键盘。"],
  breathe: ["M3 12c3-11 6 11 9 0s6 11 9 0", "让灯光在明暗之间缓慢呼吸。"],
  rainbow: ["M3 17a9 9 0 0 1 18 0M7 17a5 5 0 0 1 10 0M11 17a1 1 0 0 1 2 0", "彩虹沿键盘流动，速度可以随时调整。"],
  wave: ["M2 9c4-7 6 7 10 0s6 7 10 0M2 16c4-7 6 7 10 0s6 7 10 0", "在主色与副色之间，流动出柔和的波纹。"],
  chase: ["M4 12h16m-5-5 5 5-5 5", "一束光沿键盘来回掠过。"],
  sparkle: ["m12 3 2 7 7 2-7 2-2 7-2-7-7-2 7-2 2-7Z", "零星亮起的光点，像散落的星光。"],
  ripple: ["M4 12a8 8 0 1 1 8 8m-4-8a4 4 0 1 1 4 4M12 11v2", "主色以 20% 亮度铺底，按键泛起副色光环，向四周扩散并渐暗。"],
  audio: ["M4 10v4m4-8v12m4-15v18m4-15v12m4-8v4", "灯位分别随频段起伏，可选交错律动或按键中心辐射。"],
  meteor: ["M4 16 16 4m-8 16L20 8M4 9l5-5M15 20l5-5", "一束带着尾迹的光，划过键盘。"],
  plasma: ["M4 7c10-7 6 17 16 10M4 17C14 24 10 0 20 7", "让颜色像流体一样交融、变化。"],
  fire: ["M12 3c1 5 7 7 7 12a7 7 0 0 1-14 0c0-3 2-5 4-7 0 4 2 5 3 6 3-3 2-7 0-11Z", "从深色到亮色，模拟跳动的火焰。"],
  aurora: ["M4 19c0-7 5-4 5-12m-1 13c0-10 7-5 7-17m-2 17c0-7 7-7 7-15", "柔和的光幕，缓缓起伏。"],
  ai: ["m12 4 2 6 6 2-6 2-2 6-2-6-6-2 6-2 2-6m7-2v4m-2-2h4", "用一句话设计灯光，或应用已保存的 AI 作品。"],
  paint: ["m14 4 6 6-9 9-7 1 1-7 9-9ZM5 13l6 6m2-14 6 6", "选好颜色，直接在上方灯位网格上拖动涂色。"],
};

const NATIVE_COLORS = {"native-main":"hex", "native-secondary":"hex2",
  "native-preset":"phex", "native-preset-secondary":"phex2",
  "native-ai":"ahex", "native-ai-secondary":"ahex2"};
function syncNativeColors() {
  const swatches = {hex:"swatch", hex2:"swatch2", phex:"pswatch", phex2:"pswatch2", ahex:"aswatch", ahex2:"aswatch2"};
  for (const [native, hex] of Object.entries(NATIVE_COLORS)) {
    if ($(native) && hexToRgb($(hex).value)) {
      $(native).value = $(hex).value;
      $(swatches[hex]).style.background = $(hex).value;
    }
  }
}
for (const [native, hex] of Object.entries(NATIVE_COLORS)) {
  $(native).addEventListener("input", () => {
    $(hex).value = $(native).value.toUpperCase();
    $(hex).dispatchEvent(new Event("change", { bubbles: true }));
  });
}
document.addEventListener("change", (ev) => {
  if (["ahex", "ahex2"].includes(ev.target.id)) {
    const rgb = hexToRgb(ev.target.value);
    if (!rgb) return;
    $(ev.target.id === "ahex" ? "aswatch" : "aswatch2").style.background = rgbToHex(rgb);
    if (ev.target.id === "ahex") awheel.set(rgb);
    changeAiColor(ev.target.id === "ahex" ? "color" : "color2", rgb);
  }
  syncNativeColors();
});

const app = {
  params: { effect: "rainbow", color: [255, 90, 60], color2: [30, 123, 255], speed: 1, brightness: 1 },
  paint: [],
  presets: [],
  custom: [],
  ai: { has_key: false },
  aiSpec: null,
  aiHistory: [],
  selectedPreset: null,
  view: "studio",
  device: null,
};

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

// ------------------------------------------------------------------ colours
function hexToRgb(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(hex).trim());
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function rgbToHex([r, g, b]) {
  return "#" + [r, g, b].map((v) => clamp(Math.round(v), 0, 255).toString(16).padStart(2, "0"))
    .join("").toUpperCase();
}
function rgbToHsv([r, g, b]) {
  r /= 255; g /= 255; b /= 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
  let h = 0;
  if (d) {
    if (mx === r) h = ((g - b) / d) % 6;
    else if (mx === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h /= 6; if (h < 0) h += 1;
  }
  return { h, s: mx === 0 ? 0 : d / mx, v: mx };
}
function hsvToRgb(h, s, v) {
  const i = Math.floor(h * 6), f = h * 6 - i;
  const p = v * (1 - s), q = v * (1 - f * s), t = v * (1 - (1 - f) * s);
  let r, g, b;
  switch (i % 6) {
    case 0: r = v; g = t; b = p; break;
    case 1: r = q; g = v; b = p; break;
    case 2: r = p; g = v; b = t; break;
    case 3: r = p; g = q; b = v; break;
    case 4: r = t; g = p; b = v; break;
    default: r = v; g = p; b = q; break;
  }
  return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
}

// --------------------------------------------------------------------- api
async function api(path, body) {
  if (body !== undefined && !["/api/params", "/api/preview"].includes(path)) await flushParams();
  const res = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) {
    const err = new Error(data.error || ("HTTP " + res.status));
    showError(err);
    throw err;
  }
  if (data.params) syncCurrent(data.params, data.spec);
  return data;
}
function debounce(fn, ms) {
  let t = null;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}
let pendingParams = {}, paramsTimer = null;
let paramsQueue = Promise.resolve(), paramsBusy = false, errorUntil = 0;
function postParams(patch) {
  Object.assign(pendingParams, patch);
  clearTimeout(paramsTimer);
  paramsTimer = setTimeout(() => flushParams().catch(showError), 60);
}
function flushParams() {
  clearTimeout(paramsTimer); paramsTimer = null;
  if (!Object.keys(pendingParams).length) return paramsQueue.catch(() => {});
  const patch = pendingParams; pendingParams = {};
  const request = paramsQueue.catch(() => {}).then(async () => {
    paramsBusy = true;
    try { return await api("/api/params", patch); }
    finally { paramsBusy = false; }
  });
  paramsQueue = request;
  return request;
}
function showError(err) {
  errorUntil = Date.now() + 5000;
  const text = String(err.message || err);
  $("status").textContent = "操作失败：" + text;
  if (app.view === "presets") $("p-status").textContent = text;
  if (app.view === "ai") $("ai-status").textContent = text;
  if ($("keymap-dialog")?.open) $("keymap-status").textContent = text;
}
window.addEventListener("unhandledrejection", (ev) => { showError(ev.reason); ev.preventDefault(); });

function syncCurrent(params, spec) {
  app.params = { ...app.params, ...params };
  if (spec !== undefined) app.aiSpec = spec;
  $("speed").value = app.params.speed;
  $("speed-out").textContent = Number(app.params.speed).toFixed(2) + "×";
  $("brightness").value = app.params.brightness;
  $("brightness-out").textContent = Math.round(app.params.brightness * 100) + "%";
  wheel.set(app.params.color);
  syncColorInputs(); syncCards();
  if (app.aiSpec && !app.startNew) syncAiControls();
}

function syncDevice(dev) {
  app.device = dev;
  if(app.keymap && dev.keymap_revision !== undefined && app.keymap.revision !== dev.keymap_revision && !keymapReloadBusy) {
    keymapReloadBusy=true;
    api('/api/keymap').then(data=>{app.keymap=data;if($('keymap-dialog').open)renderMapping(data,true);})
      .catch(showError).finally(()=>keymapReloadBusy=false);
  }
  ROWS = dev.rows || 5; COLS = dev.cols || 22; ROW_OFFSET = dev.row_offset ?? 1;
  const model = dev.model || {};
  $("dot").className = "dot " + (dev.connected ? "on" : "off");
  $("device-name").textContent = dev.connected ? `${model.name || dev.name} 已连接`
    : (model.supported === false ? `${model.name}（未支持）` : "键盘未连接，正在重试");
  $("device-id").textContent = `${dev.vid}:${dev.pid} · ${model.family || "?"} · ${ROWS}×${COLS}`;
  const firmware = dev.control === "firmware";
  $("mode-badge").textContent = !dev.connected ? "未连接" : (firmware ? "固件控制" : "已发送帧");
  $("stage-hint").textContent = firmware ? "已停止软件推流，固件灯效无法在此预览。选择灯效可重新接管。"
    : "预览为最后成功发送的帧；切到「逐键涂色」可拖动上色。";
  $("layout-label").textContent = `${ROWS} 行 × ${COLS} 列 · 灯位网格`;
  if (Date.now() >= errorUntil) $("status").textContent = dev.error || dev.warning || (!dev.connected
    ? "键盘未连接，正在自动重试。" : firmware ? "已交还键盘固件，软件推流已暂停。"
    : `软件已接管灯光，发送约 ${Number(dev.observed_fps || 0).toFixed(1)} 帧/秒。`);
}

function syncOnboardHint() {
  if (!app.onboardEffects) return;
  const label = EFFECTS.find(e => e.id === app.params.effect)?.label || "此效果";
  $("onboard-hint").textContent = app.onboardEffects.includes(app.params.effect)
    ? `${label}可保存为键盘内置版本。动画可能与软件版不同，速度和亮度按 5 档保存。`
    : "此效果由软件计算，不能保存成离线动态动画；关闭时保存到电脑，退出后键盘使用之前的内置灯效。";
}

// ---------------------------------------------------------------- wheel cmp
class ColorWheel {
  constructor(canvas, cursor, onChange) {
    this.canvas = canvas;
    this.cursor = cursor;
    this.onChange = onChange;
    this.rgb = [255, 90, 60];
    this.hsv = rgbToHsv(this.rgb);
    this.radius = 0;
    this._draw();
    let dragging = false;
    const pick = (e) => {
      const rect = canvas.getBoundingClientRect();
      const x = (e.clientX - rect.left) * (canvas.width / rect.width) - canvas.width / 2;
      const y = (e.clientY - rect.top) * (canvas.height / rect.height) - canvas.height / 2;
      const dist = Math.hypot(x, y);
      if (dist > this.radius + 6) return;
      let h = Math.atan2(y, x) / (Math.PI * 2);
      if (h < 0) h += 1;
      this.hsv.h = h;
      this.hsv.s = clamp(dist / this.radius, 0, 1);
      this.rgb = hsvToRgb(this.hsv.h, this.hsv.s, this.hsv.v);
      this._drawCursor();
      this.onChange(this.rgb);
    };
    canvas.addEventListener("pointerdown", (e) => { dragging = true; canvas.setPointerCapture(e.pointerId); pick(e); });
    canvas.addEventListener("pointermove", (e) => { if (dragging) pick(e); });
    canvas.addEventListener("pointerup", () => { dragging = false; });
  }

  set(rgb) {
    this.rgb = rgb;
    const hsv = rgbToHsv(rgb);
    this.hsv = hsv;
    this._drawCursor();
  }

  _draw() {
    const size = this.canvas.width, r = size / 2;
    this.radius = r - 2;
    const ctx = this.canvas.getContext("2d");
    const img = ctx.createImageData(size, size);
    for (let y = 0; y < size; y++) {
      for (let x = 0; x < size; x++) {
        const dx = x - r, dy = y - r, dist = Math.hypot(dx, dy);
        const i = (y * size + x) * 4;
        if (dist > this.radius) { img.data[i + 3] = 0; continue; }
        let h = Math.atan2(dy, dx) / (Math.PI * 2);
        if (h < 0) h += 1;
        const [cr, cg, cb] = hsvToRgb(h, clamp(dist / this.radius, 0, 1), 1);
        img.data[i] = cr; img.data[i + 1] = cg; img.data[i + 2] = cb;
        img.data[i + 3] = dist > this.radius - 1.6 ? 110 : 255;
      }
    }
    ctx.putImageData(img, 0, 0);
  }

  _drawCursor() {
    const ctx = this.cursor.getContext("2d");
    ctx.clearRect(0, 0, this.cursor.width, this.cursor.height);
    const r = this.cursor.width / 2;
    const a = this.hsv.h * Math.PI * 2, d = this.hsv.s * this.radius;
    const x = r + Math.cos(a) * d, y = r + Math.sin(a) * d;
    ctx.beginPath(); ctx.arc(x, y, 9, 0, Math.PI * 2);
    ctx.strokeStyle = "rgba(0,0,0,.55)"; ctx.lineWidth = 4; ctx.stroke();
    ctx.beginPath(); ctx.arc(x, y, 9, 0, Math.PI * 2);
    ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; ctx.stroke();
  }
}

// ------------------------------------------------------------ frame drawing
function drawFrameInto(canvas, hex, gain = 1) {
  if (canvas.id === "ai-canvas" && app.keymap?.keys?.length) return drawPhysicalFrame(canvas,hex,gain);
  const ratio = window.devicePixelRatio || 1;
  const cssW = canvas.clientWidth || 640;
  const cssH = Math.round(cssW * (ROWS / COLS) * 1.02);
  canvas.width = Math.round(cssW * ratio);
  canvas.height = Math.round(cssH * ratio);
  canvas.style.height = cssH + "px";
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);
  ctx.fillStyle = "#262626";
  ctx.fillRect(0, 0, cssW, cssH);

  let bytes = null;
  if (hex) {
    bytes = new Uint8Array(hex.length / 2);
    for (let i = 0; i < bytes.length; i++) bytes[i] = parseInt(hex.substr(i * 2, 2), 16);
  }
  const pad = Math.min(9, cssW * 0.03);
  const cellW0 = (cssW - pad * 2) / COLS;
  const gap = Math.max(1, Math.min(2.1, cellW0 * 0.16));
  const cw = (cssW - pad * 2) / COLS, ch = (cssH - pad * 2) / ROWS;
  for (let row = 0; row < ROWS; row++) {
    for (let col = 0; col < COLS; col++) {
      const led = (row + ROW_OFFSET) * COLS + col;
      let r = 48, g = 48, b = 48;
      if (bytes && bytes.length >= (led + 1) * 3) {
        r = Math.min(255, bytes[led * 3] * gain);
        g = Math.min(255, bytes[led * 3 + 1] * gain);
        b = Math.min(255, bytes[led * 3 + 2] * gain);
      }
      const x = pad + col * cw + gap, y = pad + row * ch + gap;
      const w = cw - gap * 2, h = ch - gap * 2;
      const lit = r + g + b > 30;
      ctx.beginPath();
      roundRect(ctx, x, y, w, h, Math.min(6, w / 3));
      ctx.fillStyle = bytes ? `rgb(${r},${g},${b})` : "#383838";
      ctx.shadowBlur = 0;
      ctx.fill();
      ctx.shadowBlur = 0;
      ctx.strokeStyle = "rgba(255,255,255,.05)";
      ctx.lineWidth = 1;
      ctx.stroke();
    }
  }
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function presetPreview(p) {
  return { ...p.params, paint: p.paint, spec: p.params?.effect === "ai" ? {...p.ai_spec,...p.params} : undefined };
}
async function previewFrame(spec) {
  const res = await api("/api/preview", {
    effect: spec.effect || "static",
    color: spec.color, color2: spec.color2,
    speed: spec.speed ?? 1, brightness: spec.brightness ?? 1,
    audio_style: spec.audio_style || "staggered",
    paint: spec.paint, spec: spec.spec || (spec.kind ? spec : undefined), expression: spec.kind ? undefined : spec.expression, t: 1.4,
  }).catch(() => null);
  return res ? res.f : null;
}

// ================================================================== router
const VIEWS = ["studio", "presets", "ai"];

function showView(name) {
  if (!VIEWS.includes(name)) name = "studio";
  app.view = name;
  document.body.dataset.view = name;
  const titles = {studio:["控制台", "选择一种灯效，调到刚刚好。"],
    presets:["我的预设", "保存喜欢的灯光，随时一键回到。"],
    ai:["AI 创作", "用自己的话，设计一束光。"]};
  $("page-title").textContent = titles[name][0];
  $("page-description").textContent = titles[name][1];
  for (const v of VIEWS) $(`view-${v}`).classList.toggle("active", v === name);
  document.querySelectorAll(".tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.view === name);
    if (t.dataset.view === name) t.setAttribute("aria-current", "page");
    else t.removeAttribute("aria-current");
  });
  if (location.hash !== `#/${name}`) history.replaceState(null, "", `#/${name}`);
  if (name === "presets") renderPresetGrid();
  if (name === "ai") renderChat();
}

$("tabs").addEventListener("click", (e) => {
  const btn = e.target.closest(".tab");
  if (btn) showView(btn.dataset.view);
});

// ================================================================ 控制台
const wheel = new ColorWheel($("wheel"), $("wheel-cursor"), (rgb) => {
  app.params.color = rgb;
  syncColorInputs();
  postParams({ color: rgb });
});

function syncColorInputs() {
  $("swatch").style.background = rgbToHex(app.params.color);
  $("hex").value = rgbToHex(app.params.color);
  $("mini-swatch").style.background = rgbToHex(app.params.color);
  $("mini-hex").value = rgbToHex(app.params.color);
  // UI emphasis is constant; RGB choices affect only the lighting controls.
  $("swatch2").style.background = rgbToHex(app.params.color2);
  $("hex2").value = rgbToHex(app.params.color2);
  syncNativeColors();
}

function buildCards() {
  const box = $("cards");
  box.innerHTML = "";
  for (const fx of EFFECTS) {
    const btn = document.createElement("button");
    btn.className = "card";
    btn.dataset.effect = fx.id;
    btn.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${EFFECT_DETAILS[fx.id][0]}"/></svg><span class="card-copy">${fx.label}${fx.id === "ai" ? '<small id="ai-selected-name">尚未选择</small>' : ''}</span><svg class="check" viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4 10-10"/></svg>`;
    btn.addEventListener("click", () => setEffect(fx.id));
    box.appendChild(btn);
  }
}

function syncCards() {
  syncOnboardHint();
  document.querySelectorAll(".card").forEach((el) => {
    el.classList.toggle("active", el.dataset.effect === app.params.effect);
    el.setAttribute("aria-pressed", String(el.dataset.effect === app.params.effect));
  });
  const badge = $("mode-badge");
  const painting = app.params.effect === "paint";
  badge.textContent = painting ? "涂色" : (app.params.effect === "ai" ? "AI" : "实时");
  badge.className = "badge " + (painting ? "" : "live");
  $("board").classList.toggle("painting", painting);
  $("effect-label").textContent = effectLabel(app.params.effect);
  $("effect-description").textContent = EFFECT_DETAILS[app.params.effect]?.[1] || "";
  $("audio-style-field").hidden = app.params.effect !== "audio";
  if ($("ai-selected-name")) $("ai-selected-name").textContent = app.aiSpec?.name || "尚未选择";
  $("audio-style").value = app.params.audio_style || "staggered";
  $("audio-style-hint").textContent = app.params.audio_style === "radial"
    ? "按任意键移动中心；随声音起伏，离中心越远越暗。"
    : "相邻灯位交错点亮，随不同频段分别起伏，鼓点切换亮起的位置。";
}

$("audio-style").addEventListener("change", (e) => {
  app.params.audio_style = e.target.value;
  syncCards();
  postParams({ audio_style: e.target.value });
});

async function setEffect(id) {
  if (id === "ai") {
    await flushParams();
    showView("ai");
    $("ai-status").textContent = app.creator?.job?.detail || "描述想法，AI 会制作预览；满意后再应用到键盘。";
    return;
  }
  const result = await api("/api/effect", { effect: id });
  await refreshState();
  if (id === "ai") {
    showView("ai");
    $("ai-status").textContent = result.needs_ai
      ? "描述你想要的灯光，生成第一份作品。"
      : `已恢复「${app.aiSpec?.name || "当前作品"}」，可以继续描述修改。`;
  }
}

$("speed").addEventListener("input", (e) => {
  app.params.speed = Number(e.target.value);
  $("speed-out").textContent = app.params.speed.toFixed(2) + "×";
  postParams({ speed: app.params.speed });
});
$("brightness").addEventListener("input", (e) => {
  app.params.brightness = Number(e.target.value);
  $("brightness-out").textContent = Math.round(app.params.brightness * 100) + "%";
  postParams({ brightness: app.params.brightness });
});
$("value").addEventListener("input", (e) => {
  wheel.hsv.v = Number(e.target.value);
  const rgb = hsvToRgb(wheel.hsv.h, wheel.hsv.s, wheel.hsv.v);
  wheel.set(rgb);
  app.params.color = rgb;
  syncColorInputs();
  postParams({ color: rgb });
});
$("hex").addEventListener("change", (e) => {
  const rgb = hexToRgb(e.target.value);
  if (!rgb) { e.target.value = rgbToHex(app.params.color); return; }
  wheel.set(rgb); app.params.color = rgb; syncColorInputs(); postParams({ color: rgb });
});
$("mini-hex").addEventListener("change", (e) => { $("hex").value = e.target.value; $("hex").dispatchEvent(new Event("change")); });
$("hex2").addEventListener("change", (e) => {
  const rgb = hexToRgb(e.target.value);
  if (!rgb) { e.target.value = rgbToHex(app.params.color2); return; }
  app.params.color2 = rgb; syncColorInputs(); postParams({ color2: rgb });
});
$("release").addEventListener("click", async () => {
  await api("/api/off", {});
  await refreshState();
});

$("shutdown").addEventListener("click", async () => {
  try {
    await flushParams();
    await flushPaint();
    const result = await api("/api/shutdown", {});
    $("status").textContent = result.exit?.message || "设置已保存，软件已退出。";
  } catch (err) {
    $("status").textContent = String(err.message || err);
    if (window.confirm(`${err.message || err}\n\n仍然退出吗？未保存的修改可能丢失。退出后软件动态效果停止，键盘将使用之前的内置设置。`)) {
      await api("/api/shutdown", {force:true});
    }
  }
});

$("onboard-save").addEventListener("click", async () => {
  const button = $("onboard-save");
  button.disabled = true;
  try {
    await flushParams();
    await flushPaint();
    const res = await api("/api/onboard/save", {});
    await refreshState();
    $("status").textContent = `「${res.onboard.name}」已保存到键盘并读取核对，可完全退出软件。`;
  } catch (err) {
    $("status").textContent = String(err.message || err);
  } finally { button.disabled = false; }
});

$("close-behavior").addEventListener("change", async (e) => {
  const mode = e.target.value;
  await api("/api/settings", { close_behavior: mode });
  $("status").textContent = mode === "release"
    ? "关闭软件后使用键盘之前的内置设置。"
    : "关闭时将保存支持的内置版本并读取核对，然后完全退出。软件专属效果无法离线继续播放。";
});

function buildSwatches(box, onPick) {
  box.innerHTML = "";
  for (const hex of SWATCHES) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.style.background = hex;
    chip.title = hex;
    chip.setAttribute("aria-label", `选择颜色 ${hex}`);
    chip.addEventListener("click", () => onPick(hexToRgb(hex)));
    box.appendChild(chip);
  }
}
buildSwatches($("swatches"), (rgb) => {
  wheel.set(rgb); wheel.hsv.v = 1; $("value").value = 1;
  app.params.color = rgb; syncColorInputs(); postParams({ color: rgb });
});

// ------------------------------------------------------------- studio board
const board = $("board");
let painting = false, paintTimer = null, paintQueue = Promise.resolve();
const pendingPaint = new Map();
let boardGeom = { cw: 0, ch: 0, ox: 0, oy: 0 };

function measureBoard() {
  const rect = board.getBoundingClientRect();
  const cssW = rect.width, cssH = rect.height;
  const pad = 9;
  boardGeom = { cw: (cssW - pad * 2) / COLS, ch: (cssH - pad * 2) / ROWS, ox: pad, oy: pad };
}

function cellFromEvent(e) {
  const rect = board.getBoundingClientRect();
  const col = Math.floor((e.clientX - rect.left - boardGeom.ox) / boardGeom.cw);
  const row = Math.floor((e.clientY - rect.top - boardGeom.oy) / boardGeom.ch);
  if (row < 0 || row >= ROWS || col < 0 || col >= COLS) return null;
  return { led: (row + ROW_OFFSET) * COLS + col };
}
function paintCell(cell) {
  pendingPaint.set(cell.led, app.params.color);
  if (!paintTimer) paintTimer = setTimeout(() => flushPaint().catch(showError), 40);
}
function flushPaint() {
  clearTimeout(paintTimer);
  paintTimer = null;
  if (!pendingPaint.size) return paintQueue;
  const leds = {};
  for (const [led, rgb] of pendingPaint) leds[led] = rgb;
  pendingPaint.clear();
  paintQueue = paintQueue.catch(() => {}).then(() => api("/api/paint", { leds }));
  return paintQueue;
}
board.addEventListener("pointerdown", (e) => {
  if (app.params.effect !== "paint") return;
  const cell = cellFromEvent(e);
  if (!cell) return;
  painting = true; board.setPointerCapture(e.pointerId); paintCell(cell);
});
board.addEventListener("pointermove", (e) => { if (painting) { const c = cellFromEvent(e); if (c) paintCell(c); } });
board.addEventListener("pointerup", () => { painting = false; flushPaint().catch(showError); });

// ================================================================== 预设
function presetSummary(p) {
  const names = { static: "纯色", breathe: "呼吸", rainbow: "彩虹", wave: "双色波", chase: "扫描",
    sparkle: "星光", ripple: "涟漪", audio: "音频律动", meteor: "流星", plasma: "等离子",
    fire: "火焰", aurora: "极光", ai: "AI 光效", paint: "逐键涂色" };
  return `${names[p.effect] || p.effect} · ${rgbToHex(p.color || [255, 90, 60])}`;
}

async function renderPresetGrid() {
  const grid = $("preset-grid");
  grid.innerHTML = "";
  $("preset-empty").style.display = app.presets.length ? "none" : "block";
  for (const p of app.presets) {
    const card = document.createElement("div");
    card.className = "preset-card" + (app.selectedPreset === p.name ? " active" : "");
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.setAttribute("aria-label", `选择预设 ${p.name}`);
    card.addEventListener("keydown", (ev) => {
      if ((ev.key === "Enter" || ev.key === " ") && ev.target === card) { ev.preventDefault(); selectPreset(p); }
    });
    card.innerHTML = `<canvas width="352" height="80"></canvas>
      <div class="pc-name"><span>${escapeHtml(p.name)}</span><button class="pc-x" title="删除">×</button></div>
      <div class="pc-sub">${escapeHtml(presetSummary(p.params || {}))}</div>`;
    card.addEventListener("click", (e) => {
      if (e.target.classList.contains("pc-x")) return;
      selectPreset(p);
    });
    card.querySelector(".pc-x").addEventListener("click", async (e) => {
      e.stopPropagation();
      await api("/api/presets/delete", { name: p.name });
      if (app.selectedPreset === p.name) app.selectedPreset = null;
      await refreshState();
      renderPresetGrid();
    });
    grid.appendChild(card);
    const hex = await previewFrame(presetPreview(p));
    drawFrameInto(card.querySelector("canvas"), hex, 2.3);
  }
}

const pwheel = new ColorWheel($("pwheel"), $("pwheel-cursor"), (rgb) => {
  $("pswatch").style.background = rgbToHex(rgb);
  $("phex").value = rgbToHex(rgb);
  syncNativeColors();
});

function selectPreset(p) {
  app.selectedPreset = p.name;
  const params = p.params || {};
  $("pname").value = p.name;
  $("phex").value = rgbToHex(params.color || [255, 90, 60]);
  $("phex2").value = rgbToHex(params.color2 || [30, 123, 255]);
  $("pswatch2").style.background = rgbToHex(params.color2 || [30, 123, 255]);
  $("pspeed").value = params.speed ?? 1;
  $("pspeed-out").textContent = Number($("pspeed").value).toFixed(2) + "×";
  $("pbright").value = params.brightness ?? 1;
  $("pbright-out").textContent = Math.round(Number($("pbright").value) * 100) + "%";
  pwheel.set(params.color || [255, 90, 60]);
  syncNativeColors();
  $("p-status").textContent = `已选中「${p.name}」，可调色后保存修改。`;
  previewFrame(presetPreview(p)).then((hex) => drawFrameInto($("preset-thumb"), hex));
  document.querySelectorAll(".preset-card").forEach((el) => {
    el.classList.toggle("active", el.querySelector(".pc-name span").textContent === p.name);
  });
}

$("phex").addEventListener("change", (e) => {
  const rgb = hexToRgb(e.target.value);
  if (!rgb) return;
  pwheel.set(rgb);
  $("pswatch").style.background = rgbToHex(rgb);
});
$("phex2").addEventListener("change", (e) => {
  const rgb = hexToRgb(e.target.value);
  if (!rgb) return;
  $("pswatch2").style.background = rgbToHex(rgb);
});
$("pbright").addEventListener("input", () => {
  $("pbright-out").textContent = Math.round(Number($("pbright").value) * 100) + "%";
});
$("pspeed").addEventListener("input", () => {
  $("pspeed-out").textContent = Number($("pspeed").value).toFixed(2) + "×";
});

function editorParams() {
  return {
    color: hexToRgb($("phex").value) || [255, 90, 60],
    color2: hexToRgb($("phex2").value) || [30, 123, 255],
    brightness: Number($("pbright").value),
    speed: Number($("pspeed").value),
  };
}

async function saveOrApplyPreset(mode) {
  if (!app.selectedPreset) {
    $("p-status").textContent = "先选中左边一个预设。";
    return;
  }
  const oldName = app.selectedPreset;
  const newName = (($("pname").value || "").trim()) || oldName;
  const source = app.presets.find((x) => x.name === oldName);
  const params = { ...(source.params || {}), ...editorParams() };

  if (mode === "save" && newName !== oldName && app.presets.some((p) => p.name === newName)) {
    throw new Error("名字已存在，请换一个名字");
  }
  await api("/api/presets/apply", { name: oldName, params });

  if (mode === "save") {
    if (newName !== oldName) {
      await api("/api/presets/rename", { old: oldName, new: newName });
    }
    await api("/api/presets", { name: newName });
    app.selectedPreset = newName;
    await refreshState();
    renderPresetGrid();
    $("p-status").textContent = `已保存并应用「${newName}」（速度 ${Number(params.speed ?? 1).toFixed(2)}×）。`;
  } else {
    $("p-status").textContent = `已应用到键盘（速度 ${Number(params.speed ?? 1).toFixed(2)}×）。`;
  }
  await refreshState();
  previewFrame({ ...presetPreview(source), ...params }).then((hex) => drawFrameInto($("preset-thumb"), hex));
}

$("p-save-apply").addEventListener("click", () => saveOrApplyPreset("save"));
$("p-apply").addEventListener("click", () => saveOrApplyPreset("apply"));

$("p-delete").addEventListener("click", async () => {
  if (!app.selectedPreset) return;
  await api("/api/presets/delete", { name: app.selectedPreset });
  app.selectedPreset = null;
  await refreshState();
  renderPresetGrid();
  $("p-status").textContent = "已删除。";
});

$("preset-new").addEventListener("click", async () => {
  const name = effectLabel(app.params.effect);
  await api("/api/presets", { name });
  await refreshState();
  renderPresetGrid();
  $("status").textContent = `已保存当前灯效为「${name}」`;
});

function effectLabel(id) {
  if (id === "ai") return (app.aiSpec && app.aiSpec.name) || "AI 光效";
  const found = EFFECTS.find((fx) => fx.id === id);
  return found ? found.label : "我的光效";
}

$("save-preset").addEventListener("click", async () => {
  await flushParams();
  const name = effectLabel(app.params.effect);
  await api("/api/presets", { name });
  await refreshState();
  $("status").textContent = `已保存并应用「${name}」（速度 ${Number(app.params.speed).toFixed(2)}×）`;
});

// =============================================================== 分享码
let shareRevision = 0, shareParsed = null, shareBusy = false;
function openShare(importing) {
  shareRevision++;
  shareParsed = null;
  $("share-title").textContent = importing ? "导入光效" : "分享光效";
  $("share-intro").textContent = importing
    ? "粘贴完整分享码，先查看内容，再保存。同名预设会自动另起名字。"
    : "复制整段分享码发给朋友，对方在键光中导入即可获得相同光效。分享码可离线使用，不包含 API Key 和聊天记录。";
  $("share-code").value = "";
  $("share-code").readOnly = !importing;
  $("share-export-actions").hidden = importing;
  $("share-import-actions").hidden = !importing;
  $("share-result").hidden = true;
  $("share-status").textContent = "";
  $("share-copy").disabled = true;
  if (!$("share-dialog").open) $("share-dialog").showModal();
  return shareRevision;
}
async function exportShare(options) {
  const revision = openShare(false);
  $("share-status").textContent = "正在生成分享码…";
  try {
    await flushParams();
    await flushPaint();
    const res = await api("/api/share/export", options);
    if (revision !== shareRevision) return;
    $("share-code").value = res.code;
    $("share-copy").disabled = false;
    $("share-status").textContent = `「${res.name}」 · ${res.layout.rows} 行键盘。音频、按键类效果会随接收方输入变化。`;
  } catch (err) {
    if (revision === shareRevision) $("share-status").textContent = err.message;
  }
}
$("share-current").addEventListener("click", () => exportShare({source:"current", name:effectLabel(app.params.effect)}));
$("p-share").addEventListener("click", () => {
  if (!app.selectedPreset) { $("p-status").textContent = "先选中一个预设。"; return; }
  exportShare({source:"preset", name:app.selectedPreset, params:editorParams()});
});
$("ai-share").addEventListener("click", () => {
  if (!app.aiDraft) { $("ai-status").textContent = "先生成或选择一个光效。"; return; }
  const name = $("ai-name").value.trim() || app.aiDraft.name || "AI 光效";
  exportShare({source:"ai", name, spec:aiSpecWithSliders(name)});
});
$("share-open-import").addEventListener("click", () => { openShare(true); $("share-code").focus(); });
$("share-close").addEventListener("click", () => { shareRevision++; $("share-dialog").close(); });
$("share-dialog").addEventListener("close", () => { if (!$("share-dialog").open) shareRevision++; });
$("share-dialog").addEventListener("cancel", (e) => { if (shareBusy) e.preventDefault(); else shareRevision++; });
$("share-copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("share-code").value);
    $("share-status").textContent = "分享码已复制，发送给朋友即可。";
  } catch {
    $("share-code").focus(); $("share-code").select();
    $("share-status").textContent = "分享码已选中，请按 Ctrl+C 复制。";
  }
});
$("share-code").addEventListener("input", () => {
  shareRevision++; shareParsed = null;
  $("share-result").hidden = true;
  $("share-status").textContent = "";
});
$("share-inspect").addEventListener("click", async () => {
  const revision = ++shareRevision;
  shareParsed = null;
  $("share-result").hidden = true;
  $("share-status").textContent = "正在解析…";
  try {
    const res = await api("/api/share/inspect", {code:$("share-code").value});
    if (revision !== shareRevision) return;
    shareParsed = res;
    $("share-name").value = res.name;
    $("share-summary").textContent = `${presetSummary(res.snapshot.params)} · 速度 ${res.snapshot.params.speed}× · 亮度 ${Math.round(res.snapshot.params.brightness*100)}% · ${res.layout.rows} 行键盘`;
    $("share-result").hidden = false;
    $("share-save").disabled = $("share-save-apply").disabled = !res.compatible;
    $("share-status").textContent = res.compatible
      ? "内容已解析，尚未保存或应用。响应类光效会随声音、按键变化。"
      : "分享码与本机键盘布局不同，无法原样导入。";
    const hex = await previewFrame(presetPreview(res.snapshot));
    if (revision === shareRevision) drawFrameInto($("share-preview"), hex);
  } catch (err) {
    if (revision === shareRevision) $("share-status").textContent = err.message;
  }
});
async function importShare(apply) {
  if (shareBusy || !shareParsed?.compatible) return;
  shareBusy = true;
  $("share-save").disabled = $("share-save-apply").disabled = true;
  $("share-code").readOnly = true;
  $("share-inspect").disabled = true;
  $("share-close").disabled = $("share-name").disabled = true;
  try {
    const res = await api("/api/share/import", {code:$("share-code").value, name:$("share-name").value.trim(), apply});
    shareParsed = null;
    $("share-result").hidden = true;
    await refreshState();
    await renderPresetGrid();
    $("share-status").textContent = `已${apply ? "保存并应用" : "保存"}「${res.name}」，可在“我的预设”中找到。`;
  } catch (err) {
    $("share-status").textContent = err.message;
  } finally {
    shareBusy = false;
    $("share-code").readOnly = false;
    $("share-inspect").disabled = false;
    $("share-close").disabled = $("share-name").disabled = false;
    $("share-save").disabled = $("share-save-apply").disabled = !shareParsed?.compatible;
  }
}
$("share-save").addEventListener("click", () => importShare(false));
$("share-save-apply").addEventListener("click", () => importShare(true));

// ================================================================== AI
const awheel = new ColorWheel($("awheel"), $("awheel-cursor"), (rgb) => {
  $("aswatch").style.background = rgbToHex(rgb);
  $("ahex").value = rgbToHex(rgb);
  syncNativeColors();
  changeAiColor("color", rgb);
});

buildSwatches($("aswatches"), (rgb) => {
  awheel.set(rgb);
  $("aswatch").style.background = rgbToHex(rgb);
  $("ahex").value = rgbToHex(rgb);
  syncNativeColors();
  changeAiColor("color", rgb);
});

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

let aiBusy = false, aiPending = "";
let aiControlQueue = Promise.resolve(), aiControlsPending = 0;
function changeAiColor(key, rgb) { changeAiParameters({[key]: rgb}); }
function changeAiParameters(patch) {
  if (!app.aiDraft || app.startNew || aiBusy) return;
  app.aiDraft = {...app.aiDraft, ...patch};
  aiControlsPending++;
  aiControlQueue = aiControlQueue.catch(() => {}).then(async () => {
    try { const result=await api("/api/creator/params",patch); if(aiControlsPending===1) applyCreatorView(result); }
    catch (err) { showError(err); await refreshState(); }
    finally { aiControlsPending--; }
  });
}
function syncAiControls() {
  const spec = app.aiDraft;
  if (!spec) return;
  syncAiSliders(spec.speed, spec.brightness);
  const hasMain = /\bc1\b/.test(spec.expression || ""), hasSecond = /\bc2\b/.test(spec.expression || "");
  $("ai-palette-hint").textContent = spec.kind !== "program" ? "旧版作品的颜色可能固定在公式中，可继续描述以转为可调作品。" : hasMain && hasSecond ? "作品使用主色与副色，调色会即时更新。" : hasMain ? "当前作品使用主色。可继续描述如何加入副色。" : "当前作品使用副色。可继续描述如何加入主色。";
  $("ahex").value = rgbToHex(spec.color || app.params.color);
  $("ahex2").value = rgbToHex(spec.color2 || app.params.color2);
  awheel.set(spec.color || app.params.color);
  syncNativeColors();
}
$("ai-back").addEventListener("click", async () => {
  await aiControlQueue;
  await flushParams();
  showView("studio");
});
function syncAiConversation() {
  const editing = app.aiDraft && !app.startNew;
  $("ai-legacy-note").hidden = !editing || app.aiDraft.kind === "program";
  $("ai-intent").hidden = !editing || !app.aiDraft?.intent;
  $("ai-intent").textContent = app.aiDraft?.intent ? "需求理解：" + app.aiDraft.intent : "";
  $("ai-send").firstChild.textContent = "发送";
  $("ai-send").disabled = aiBusy;
  $("ai-compose").textContent = "重新制作预览"; $("ai-compose").hidden=app.creator?.job?.state!=="failed"; $("ai-cancel").hidden=!aiBusy;
  $("ai-compose").disabled = aiBusy || !app.aiHistory.some(m=>m.role === "user");
  $("ai-chat-model").textContent = app.ai.model ? `当前模型：${app.ai.model}` : "";
  $("ai-reset").disabled = false;
  $("ai-undo").disabled = aiBusy || !app.aiUndo;
  for (const id of ["ai-save-apply", "ai-save-effect", "ai-share", "ai-name", "aispeed", "aibright", "ahex", "ahex2", "native-ai", "native-ai-secondary"]) {
    $(id).disabled = aiBusy || !editing;
  }
  $("custom-list").querySelectorAll("button").forEach(b => b.disabled = aiBusy);
  $("ai-input").placeholder = editing ? "继续描述想怎么改，例如：速度再慢一点，背景更暗，其他不变。" : "例如：深蓝色暗底，一道柔和的白光从左向右缓慢扫过。";
}
function renderChat() {
  syncAiConversation();
  const log = $("chat-log");
  log.innerHTML = "";
  if (!app.aiHistory.length && !aiPending) {
    log.innerHTML = `<div class="chat-hint">描述你的想法，AI 会制作可试用的预览；也可以先聊方案。看见哪里不对，直接在这里说，它会结合运行反馈继续修改。满意后再应用到键盘。</div>`;
    return;
  }
  for (const msg of app.aiHistory) {
    const div = document.createElement("div");
    div.className = "chat-msg " + (msg.role === "user" ? "user" : "ai");
    if (msg.role === "user") {
      div.textContent = msg.content;
    } else {
      let text = msg.content;
      try {
        const spec = JSON.parse(msg.content);
        if (spec && typeof spec === "object" && ["program","expression","preset","layers"].includes(spec.kind)) {
          text = `「${spec.name || "光效"}」${spec.change || spec.explain ? "：" + (spec.change || spec.explain) : "已更新"}`;
        }
      } catch { /* ordinary model reply */ }
      div.innerHTML = `<span class="tag">${text.startsWith("【程序反馈】") ? "系统" : "AI"}</span>${escapeHtml(text)}`;
    }
    log.appendChild(div);
  }
  if (aiPending) {
    const pending = document.createElement("div");
    pending.className = "chat-msg user pending";
    pending.textContent = aiPending + "\n模型正在回复…";
    log.appendChild(pending);
  }
  log.scrollTop = log.scrollHeight;
}

function aiColorsHint() {
  return [$("ahex").value.trim().toUpperCase(), $("ahex2").value.trim().toUpperCase()]
    .filter((v) => /^#[0-9A-F]{6}$/.test(v));
}

let creatorPoll=0;
function applyCreatorView(res) {
  if (app.creator && res.revision < app.creator.revision) return;
  const old=app.aiDraft?.expression;
  app.creator=res;app.aiDraft=res.draft;app.aiHistory=res.history||[];
  app.startNew=!res.draft;app.aiUndo=res.undo||0;aiBusy=res.job?.state==='running';aiPending='';
  if(old!==app.aiDraft?.expression)clearAiPreviewInputs();
  $('ai-name').value=app.aiDraft?.name||'';
  $('ai-meta').textContent=app.aiDraft?.change||app.aiDraft?.explain||'描述想法后，在这里试用自己的光效。';
  $('ai-expr').textContent=app.aiDraft?.expression||'';
  $('ai-status').textContent=res.job?.detail||'直接描述想法，或先和 AI 聊聊。';
  $('ai-diagnostics').textContent=res.diagnostics?JSON.stringify(res.diagnostics,null,2):'本轮尚无错误记录。';
  $('ai-diagnostics-wrap').hidden=!res.diagnostics;
  if(app.aiDraft)syncAiControls();else drawFrameInto($('ai-canvas'),null);
  renderCustom();renderChat();
  clearTimeout(creatorPoll);
  if(aiBusy)creatorPoll=setTimeout(pollCreator,400);
}
async function pollCreator(){
  try{applyCreatorView(await api('/api/creator'));}
  catch(err){$('ai-status').textContent='连接暂时中断，正在重新获取创作进度…';creatorPoll=setTimeout(pollCreator,1500);}
}
function previewObservation(){
  const now=performance.now();
  const t=(now-previewStart)/1000;
  return {t,audio:simulatedAudio(t),keys:[...previewKeys.values()].map(k=>({vk:k.vk,held:k.held,
    age:(now-k.time)/1000,count:k.count,...(k.releaseTime!==undefined?{release_age:(now-k.releaseTime)/1000}:{})}))};
}
async function sendAI(forcedPrompt){
  const input=$('ai-input'),prompt=typeof forcedPrompt==='string'?forcedPrompt:input.value.trim();
  if(!prompt||aiBusy)return;
  aiBusy=true;aiPending=prompt;renderChat();$('ai-status').textContent='正在开始本轮创作…';
  try{
    await aiControlQueue;
    const result=await api('/api/creator/message',{prompt,observation:app.aiDraft?previewObservation():undefined});
    if(input.value.trim()===prompt)input.value='';applyCreatorView(result);
  }catch(err){aiBusy=false;aiPending='';renderChat();$('ai-status').textContent=String(err.message||err);}
}
async function composeAI(){await sendAI('请根据刚才明确的需求重新制作预览，并自行处理运行反馈。');}
$('ai-cancel').addEventListener('click',async()=>{
  try{applyCreatorView(await api('/api/creator/cancel',{}));}
  catch(err){$('ai-status').textContent=String(err.message||err);}
});
window.addEventListener('pagehide',()=>clearTimeout(creatorPoll));

document.querySelectorAll("[data-ai-prompt]").forEach((button) => button.addEventListener("click", () => {
  $("ai-input").value = button.dataset.aiPrompt;
  $("ai-input").focus();
}));

$("ai-send").addEventListener("click", sendAI);
$("ai-compose").addEventListener("click", composeAI);
$("ai-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) sendAI();
});

$("aispeed").addEventListener("input", (e) => {
  $("aispeed-out").textContent = Number(e.target.value).toFixed(2) + "×";
  changeAiParameters({ speed: Number(e.target.value) });
});
$("aibright").addEventListener("input", (e) => {
  $("aibright-out").textContent = Math.round(Number(e.target.value) * 100) + "%";
  changeAiParameters({ brightness: Number(e.target.value) });
});
$('ai-reset').addEventListener('click',async()=>{
  try{applyCreatorView(await api('/api/creator/reset',{}));clearAiPreviewInputs();$('ai-status').textContent='新作品从空白开始，实体键盘保持原来的灯光。';}
  catch(err){$('ai-status').textContent=String(err.message||err);}
});
$('ai-undo').addEventListener('click',async()=>{
  try{applyCreatorView(await api('/api/creator/undo',{}));$('ai-status').textContent='已恢复上一版预览，实体键盘未改变。';}
  catch(err){$('ai-status').textContent=String(err.message||err);}
});

$("ai-save").addEventListener("click", async () => {
  try {
    const res = await api("/api/ai/config", {
      api_key: $("ai-key").value.trim(),
      base_url: $("ai-base").value.trim(),
      model: $("ai-model").value.trim(),
    });
    app.ai = res.ai;
    $("ai-key").value = "";
    updateAiBadge();
    $("ai-status").textContent = "接口设置已保存";
  } catch (err) { $("ai-status").textContent = String(err.message || err); }
});

function aiSpecWithSliders(name) {
  return {
    ...app.aiDraft,
    name,
    speed: Number($("aispeed").value),
    brightness: Number($("aibright").value),
    color: hexToRgb($("ahex").value) || app.aiDraft.color,
    color2: hexToRgb($("ahex2").value) || app.aiDraft.color2,
  };
}

async function saveAiEffect(apply) {
  await aiControlQueue;
  await flushParams();
  if (!app.aiDraft) {
    $("ai-status").textContent = "先生成一个光效";
    return;
  }
  const name = ($("ai-name").value || app.aiDraft.name || "").trim() || "AI 光效";
  const spec = aiSpecWithSliders(name);
  const sameName = app.custom.find(item => item.name === name);
  if (sameName && !window.confirm(`覆盖已保存的「${name}」？`)) return;
  try {
    const res = await api("/api/custom", { name, spec });
    app.custom = res.custom;
    renderCustom();
    if (apply) {
      await api("/api/creator/params",{name}); await api("/api/creator/apply",{}); await refreshState();
      app.aiDraft = spec;
      syncCards();
      renderCustom();
      $("ai-status").textContent = `已保存并应用「${name}」（速度 ${spec.speed.toFixed(2)}×）`;
    } else {
      $("ai-status").textContent = `已保存「${name}」`;
    }
  } catch (err) {
    $("ai-status").textContent = String(err.message || err);
  }
}

$("ai-save-apply").addEventListener("click", () => saveAiEffect(true));
$("ai-save-effect").addEventListener("click", () => saveAiEffect(false));

function syncAiSliders(speed, brightness) {
  $("aispeed").value = speed ?? 1;
  $("aispeed-out").textContent = Number($("aispeed").value).toFixed(2) + "×";
  $("aibright").value = brightness ?? 1;
  $("aibright-out").textContent = Math.round(Number($("aibright").value) * 100) + "%";
}

function renderCustom() {
  const box = $("custom-list");
  box.innerHTML = "";
  if (!app.custom.length) {
    box.innerHTML = `<p class="hint">保存第一份作品后，它会出现在这里。可以随时选择、继续修改或删除。</p>`;
    return;
  }
  for (const item of app.custom) {
    const card = document.createElement("article");
    card.className = "custom-work" + (app.aiDraft?.name === item.name ? " selected" : "");
    card.innerHTML = `<div class="custom-work-head"><strong>${escapeHtml(item.name)}</strong><span class="quiet-label">${item.kind === "program" ? "自主创作" : "旧版作品"}</span></div><p>${escapeHtml(item.explain || "自定义灯光")}</p><div class="custom-work-actions"><button class="ghost small" data-action="select">编辑预览</button><button class="text-button" data-action="rename">改名</button><button class="text-button delete-work" data-action="delete">删除</button></div>`;
    card.querySelector('[data-action="select"]').addEventListener("click", async () => {
      if (aiBusy) return;
      await aiControlQueue;
      applyCreatorView(await api("/api/creator/select",{name:item.name}));
      clearAiPreviewInputs();
      $("ai-status").textContent = `已选择「${item.name}」，可试按、修改或返回控制台。`;
    });
    card.querySelector('[data-action="rename"]').addEventListener("click", async () => {
      const name = window.prompt("作品名称", item.name)?.trim();
      if (!name || name === item.name) return;
      await api("/api/custom/rename", {old:item.name,new:name});
      if (app.aiDraft?.name === item.name) {
        applyCreatorView(await api("/api/creator/params",{name}));
      }
      await refreshState();
    });
    card.querySelector('[data-action="delete"]').addEventListener("click", async () => {
      if (!window.confirm(`删除已保存的「${item.name}」？当前灯光会保留，需要时可重新保存。`)) return;
      const res = await api("/api/custom/delete", {name:item.name});
      app.custom = res.custom;
      renderCustom();
      $("ai-status").textContent = `已删除「${item.name}」的保存副本。`;
    });
    box.appendChild(card);
  }
}

// Preview uses the server renderer; virtual keys never reach the OS or hardware.
const previewKeys = new Map();
let previewAudio = false;
function clearAiPreviewInputs() {
  previewKeys.clear(); previewAudio = false;
  $("ai-preview-audio").textContent = "模拟音乐";
  $("ai-preview-audio").setAttribute("aria-pressed","false");
}
$("ai-preview-audio").addEventListener("click",()=>{
  previewAudio = !previewAudio;
  $("ai-preview-audio").textContent = previewAudio ? "停止模拟音乐" : "模拟音乐";
  $("ai-preview-audio").setAttribute("aria-pressed",String(previewAudio));
});
let previewRequest = false, previewStart = performance.now();
function previewGeometry() {
  return (app.keymap?.keys || []).filter(k=>k.vk !== null).map(k=>({...k,row:Math.floor(k.led/22)-1,col:k.led%22}));
}

function previewPress(vk, held) {
  if (!previewGeometry().some(k=>k.vk===vk)) return;
  const prev = previewKeys.get(vk);
  if (held && !prev?.held) previewKeys.set(vk,{vk,held:true,time:performance.now(),releaseTime:prev?.releaseTime,count:(prev?.count||0)+1});
  else if (!held && prev?.held) { prev.held = false; prev.releaseTime = performance.now(); }
}
let previewPointerVk = null;
$("ai-canvas").addEventListener("pointerdown", e => {
  if (!app.aiDraft || app.startNew) return;
  const rect = e.currentTarget.getBoundingClientRect();
  const bounds = physicalBounds(app.keymap.keys);
  const x = (e.clientX-rect.left)/rect.width*bounds.width+bounds.x;
  const y = (e.clientY-rect.top)/rect.height*bounds.height+bounds.y;
  const nearest = previewGeometry().find(k=>x>=k.x&&x<=k.x+k.width&&y>=k.y&&y<=k.y+k.height);
  if (!nearest) return;
  previewPointerVk = nearest.vk;
  previewPress(previewPointerVk,true);
  e.currentTarget.setPointerCapture(e.pointerId);
});
for (const event of ["pointerup","pointercancel","lostpointercapture"]) $("ai-canvas").addEventListener(event,()=>{
  if (previewPointerVk !== null) previewPress(previewPointerVk,false);
  previewPointerVk = null;
});
function previewKeyCode(e) {
  return (app.keymap?.keys || []).find(k=>k.code===e.code)?.vk ?? null;
}

window.addEventListener("keydown",e=>{
  if (app.view!=="ai" || $('keymap-dialog').open || /INPUT|TEXTAREA|SELECT/.test(e.target.tagName) || e.repeat) return;
  previewPress(previewKeyCode(e),true);
});
window.addEventListener("keyup",e=>previewPress(previewKeyCode(e),false));
window.addEventListener("blur",()=>{for(const k of previewKeys.values())if(k.held){k.held=false;k.releaseTime=performance.now();}});
$("ai-preview-clear").addEventListener("click",clearAiPreviewInputs);
let testHeldVk = null;
$("ai-test-press").addEventListener("pointerdown",e=>{
  if(!app.aiDraft || app.startNew) return;
  testHeldVk = Number($("ai-test-key").value);
  previewPress(testHeldVk,true);
  e.currentTarget.setPointerCapture(e.pointerId);
});
for (const event of ["pointerup","pointercancel","lostpointercapture"]) $("ai-test-press").addEventListener(event,()=>{
  if(testHeldVk!==null) previewPress(testHeldVk,false);
  testHeldVk=null;
});
function simulatedAudio(t){
  return previewAudio ? {levels:Array.from({length:22},(_,i)=>Math.max(0,Math.sin(t*3+i*.6))*.8),pulse:.5+.5*Math.sin(t*6),energy:.65,beat:Math.floor(t*2)} : undefined;
}
setInterval(async()=>{
  if (app.view!=="ai" || previewRequest || !app.aiDraft || app.startNew || document.hidden) return;
  const usingSimulation = previewKeys.size > 0 || previewAudio;
  previewRequest = true;
  const source = app.aiDraft;
  try {
    const tick=(performance.now()-previewStart)/1000;
    const audio=simulatedAudio(tick);
    const res = await api("/api/preview", {spec:source,t:tick,audio,
      keys:[...previewKeys.values()].map(k=>({vk:k.vk,held:k.held,age:(performance.now()-k.time)/1000,count:k.count,release_age:k.releaseTime === undefined ? undefined : (performance.now()-k.releaseTime)/1000}))});
    if (app.view === "ai" && app.aiDraft === source) {
      drawFrameInto($("ai-canvas"),res.f);
      $("ai-preview-status").textContent = previewAudio ? "模拟音乐预览 · 不发声、不改变实体键盘" : usingSimulation ? "模拟按键预览 · 不改变实体键盘" : "动画预览 · 点击灯位试按";
    }
  } catch { /* error is already visible in status */ }
  finally {previewRequest=false;}
},100);

function updateAiBadge() {
  const badge = $("ai-badge");
  badge.textContent = app.ai.has_key ? "已配置" : "未配置";
  badge.className = "badge " + (app.ai.has_key ? "live" : "warn");
}

// ======================================================== exact key layout
function physicalBounds(keys) {
  const x=Math.min(...keys.map(k=>k.x))-5, y=Math.min(...keys.map(k=>k.y))-5;
  return {x,y,width:Math.max(...keys.map(k=>k.x+k.width))-x+5,height:Math.max(...keys.map(k=>k.y+k.height))-y+5};
}
function drawPhysicalFrame(canvas,hex,gain=1) {
  const keys=app.keymap.keys, bounds=physicalBounds(keys), ratio=devicePixelRatio||1;
  const width=canvas.clientWidth||640, height=width*bounds.height/bounds.width;
  canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);canvas.style.height=height+"px";
  const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);ctx.fillStyle='#252525';ctx.fillRect(0,0,width,height);
  for(const k of keys) {
    const x=(k.x-bounds.x)/bounds.width*width,y=(k.y-bounds.y)/bounds.height*height,w=k.width/bounds.width*width,h=k.height/bounds.height*height;
    const pixel=hex?.slice(k.led*6,k.led*6+6);
    const rgb=pixel?.length===6?[0,2,4].map(i=>Math.min(255,parseInt(pixel.slice(i,i+2),16)*gain)):[0,0,0];
    ctx.beginPath();roundRect(ctx,x,y,w,h,3);ctx.fillStyle=`rgb(${rgb.map(v=>Math.round(v)).join(',')})`;ctx.fill();
    ctx.strokeStyle='#4a4a4a';ctx.lineWidth=.6;ctx.stroke();ctx.fillStyle=Math.max(...rgb)>155?'#171717':'#aaa';
    ctx.font=`${Math.max(7,Math.min(11,w*.32))}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(k.label,x+w/2,y+h/2,w-3);
  }
}
let keymapPolling=null, keymapPollBusy=false, keymapReloadBusy=false, keymapData=null;
function renderMapping(data,rebuild=false) {
  rebuild = rebuild || keymapData?.revision !== data.revision;
  keymapData=data;app.keymap=data;
  $('keymap-profile').textContent=`${data.connected?"":"未连接；参考配列："}${data.model} · ${data.physical_keys} 个物理键 / ${data.mapped_keys} 个系统键 · ${data.source}${data.calibrated?'（含本机校准）':''}`;
  $('keymap-single').checked=!!data.single_key;
  if(rebuild) {
    const board=$('keymap-board');board.innerHTML='';
    const bounds=physicalBounds(data.keys);board.style.aspectRatio=`${bounds.width}/${bounds.height}`;
    for(const k of data.keys) {
      const key=document.createElement('span');key.className='physical-key';key.dataset.led=k.led;
      key.style.left=(k.x-bounds.x)/bounds.width*100+'%';key.style.top=(k.y-bounds.y)/bounds.height*100+'%';key.style.width=k.width/bounds.width*100+'%';key.style.height=k.height/bounds.height*100+'%';
      key.textContent=k.label;key.title=`${k.code} · LED ${k.led}`;board.appendChild(key);
    }
    const select=$('keymap-key'),selected=select.value;select.innerHTML='';
    for(const k of data.keys.filter(k=>k.vk!==null)) {const option=document.createElement('option');option.value=k.vk;option.textContent=`${k.label} (${k.code})`;select.appendChild(option);}
    select.value=data.keys.some(k=>String(k.vk)===selected)?selected:'65';
    $('keymap-led').value=data.keys.find(k=>String(k.vk)===select.value)?.led??22;
  }
  const event=data.event;
  $('keymap-event').textContent=event?`${event.action} · VK ${event.vk} (0x${event.vk.toString(16).toUpperCase()}) · 扫描码 ${event.scan_code}${event.extended?' / E0':''} · ${event.code||'未映射'} → ${event.led===null?'此配列没有对应灯位':`LED ${event.led}（物理行 ${Math.floor(event.led/22)}，矩阵列 ${event.led%22+1}）`}`:'等待实体按键…';
  $('keymap-sent').textContent=`最近成功发送帧中亮起的灯位：${data.sent_leds.length?data.sent_leds.join(', '):'无'}。${data.control==='firmware'?'当前是固件控制，自检不会接管灯光。':'这表示软件发送的编号，实际哪个键帽亮起需要目视核对。'}`;
  $('keymap-board').querySelectorAll('.physical-key').forEach(el=>{el.classList.toggle('lit',data.sent_leds.includes(Number(el.dataset.led)));el.classList.toggle('pressed',Number(el.dataset.led)===event?.led);});
  if(!data.debug) $('keymap-status').textContent='调试已结束或已自动超时；关闭窗口后可重新打开。';
}
async function closeMapping() {
  clearInterval(keymapPolling);keymapPolling=null;
  try {await api('/api/keymap/debug',{enabled:false});} finally {$('keymap-dialog').close();}
}
$('keymap-open').addEventListener('click',async()=>{
  const res=await api('/api/keymap/debug',{enabled:true});renderMapping(res.keymap,true);$('keymap-dialog').showModal();$('keymap-dialog').tabIndex=-1;$('keymap-dialog').focus();
  $('keymap-status').textContent='只保留最后一次按键，不记录输入历史；五分钟后自动结束。普通查看不改变当前光效。';
  keymapPolling=setInterval(async()=>{if(keymapPollBusy)return;keymapPollBusy=true;try{renderMapping(await api('/api/keymap'));}finally{keymapPollBusy=false;}},200);
});
$('keymap-close').addEventListener('click',closeMapping);
$('keymap-dialog').addEventListener('cancel',e=>e.preventDefault()); // Esc itself is a key under test.
$('keymap-dialog').addEventListener('keydown',e=>{if(e.target===$('keymap-dialog')&&['Tab','Space','Enter','Escape'].includes(e.code))e.preventDefault();});
$('keymap-board').addEventListener('click',()=>$('keymap-dialog').focus());
$('keymap-single').addEventListener('change',async e=>{const res=await api('/api/keymap/debug',{enabled:true,single_key:e.target.checked});renderMapping(res.keymap);$('keymap-dialog').focus();});
$('keymap-key').addEventListener('change',()=>{$('keymap-led').value=keymapData.keys.find(k=>k.vk===Number($('keymap-key').value))?.led??22;});
$('keymap-probe').addEventListener('click',async()=>{await api('/api/keymap/probe',{led:Number($('keymap-led').value)});$('keymap-status').textContent='已请求试亮此编号两秒，请目视确认实际键帽。';});
$('keymap-save').addEventListener('click',async()=>{
  if(!confirm('将所选物理键绑定到此灯位？已有占用时将交换两键，仅保存本机灯光对照。'))return;
  const res=await api('/api/keymap/calibrate',{vk:Number($('keymap-key').value),led:Number($('keymap-led').value)});renderMapping(res.keymap,true);clearAiPreviewInputs();$('keymap-status').textContent='已保存此型号的本机校准，重开后仍有效。';
});
$('keymap-reset').addEventListener('click',async()=>{if(!confirm('清除此型号的本机校准，恢复厂商逐键表？'))return;const res=await api('/api/keymap/calibrate',{reset:true});renderMapping(res.keymap,true);clearAiPreviewInputs();});
window.addEventListener('pagehide',()=>{if(keymapPolling)fetch('/api/keymap/debug',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:false}),keepalive:true}).catch(()=>{});});

// ================================================================== boot
async function refreshState() {
  const s = await api("/api/state");
  app.params = { ...app.params, ...s.params };
  app.keymap = s.keymap;
  app.presets = s.presets || [];
  app.custom = s.custom || [];
  app.ai = s.ai || { has_key: false };
  app.aiSpec = s.ai_spec;
  applyCreatorView(s.creator);

  syncCurrent(s.params, s.ai_spec);
  const dev = s.device;
  $("close-behavior").value = (s.settings && s.settings.close_behavior) || "hold";
  app.onboardEffects = s.onboard?.effects || [];
  syncOnboardHint();

  $("speed").value = app.params.speed;
  $("speed-out").textContent = Number(app.params.speed).toFixed(2) + "×";
  $("brightness").value = app.params.brightness;
  $("brightness-out").textContent = Math.round(Number(app.params.brightness) * 100) + "%";

  wheel.set(app.params.color);
  syncColorInputs();
  syncCards();

  $("ai-key").placeholder = app.ai.has_key ? `已保存 ${app.ai.api_key}（留空则不修改）` : "API Key（只保存在本机）";  $("ai-base").value = app.ai.base_url || "https://api.deepseek.com";
  $("ai-model").value = app.ai.model || "deepseek-chat";
  updateAiBadge();

  awheel.set(hexToRgb($("ahex").value) || [90, 140, 255]);
  syncAiControls();
  $("aswatch").style.background = $("ahex").value;
  $("aswatch2").style.background = $("ahex2").value;
  syncNativeColors();

  if (app.aiDraft && !app.startNew) {
    $("ai-name").value = app.aiDraft.name || "";
    $("ai-expr").textContent = app.aiDraft.expression || "";
    $("ai-meta").textContent = app.aiDraft.change || app.aiDraft.explain || "";
  } else {
    drawFrameInto($("ai-canvas"),null);
    $("ai-name").value = "";
    $("ai-expr").textContent = "";
    $("ai-meta").textContent = "描述想要的光，开始创作。";
  }
  renderCustom();
  syncDevice(dev);
  return s;
}

async function boot() {
  $("ahex").value = "#5A8CFF";
  $("ahex2").value = "#FF5A3C";
  $("phex").value = "#FF5A3C";
  $("phex2").value = "#1E7BFF";
  $("pswatch").style.background = "#FF5A3C";
  $("pswatch2").style.background = "#1E7BFF";
  pwheel.set([255, 90, 60]);
  buildCards();
  showView((location.hash || "#/studio").replace("#/", ""));
  try { await refreshState(); } catch (err) {
    $("dot").className = "dot off";
    $("device-name").textContent = "服务未就绪";
    $("status").textContent = String(err);
  }
  if (app.view === "presets") renderPresetGrid();
  if (app.view === "ai") renderChat();

  const stream = new EventSource("/api/stream");
  stream.onerror = () => {
    $("dot").className = "dot off";
    $("device-name").textContent = "服务连接中断";
    $("status").textContent = "服务连接中断，正在重连；若已退出，请用桌面入口重新启动。";
  };
  let revision = -1;
  stream.onmessage = (ev) => {
    let payload;
    try { payload = JSON.parse(ev.data); } catch { return; }
    if (payload.v !== revision && !paramsBusy && !aiControlsPending && !Object.keys(pendingParams).length) {
      syncCurrent(payload.p || {}, payload.s);
      revision = payload.v;
    }
    if (payload.d) syncDevice(payload.d);
    const visibleFrame = payload.c && payload.d?.control === "software" ? payload.f : null;
    if (app.view === "studio") {
      measureBoard();
      drawFrameInto(board, visibleFrame);
    } else if (!app.creator && app.view === "ai" && app.aiSpec && !app.startNew && !previewKeys.size && !previewAudio && visibleFrame && (app.params.effect === "ai" || app.params.effect === app.aiSpec.effect)) {
      drawFrameInto($("ai-canvas"), visibleFrame);
      $("ai-preview-status").textContent = "实体键盘实时预览 · 点击灯位模拟试按";
    }
  };

  window.addEventListener("hashchange", () => showView(location.hash.replace("#/", "")));
  window.addEventListener("resize", () => {
    if (app.view === "studio") { measureBoard(); }
    if (app.view === "presets" && app.selectedPreset) {
      const p = app.presets.find((x) => x.name === app.selectedPreset);
      if (p) previewFrame(presetPreview(p)).then((hex) => drawFrameInto($("preset-thumb"), hex));
    }
  });
}

boot();
