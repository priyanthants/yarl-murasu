const el = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
})[c]);
const stateLabels = { pending: "காத்திருப்பு", approved: "வெளியிடப்பட்டது", rejected: "நிராகரிப்பு" };
let stories = [];
let selected = null;
let filter = "pending";
let me = null;

async function api(path, options = {}) {
  const response = await fetch(path, { credentials: "same-origin", cache: "no-store", ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) } });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw Object.assign(new Error(data.error || "சேவையை அணுக முடியவில்லை"), { status: response.status });
  return data;
}

function notice(message, error = false) {
  el("notice").textContent = message;
  el("notice").className = `notice${error ? " error" : ""}`;
}

function dateLabel(iso) {
  try { return new Intl.DateTimeFormat("ta-LK", { dateStyle: "medium", timeStyle: "short",
    timeZone: "Asia/Colombo" }).format(new Date(iso)); } catch { return iso || ""; }
}

function renderList() {
  for (const key of Object.keys(stateLabels)) el(`count-${key}`).textContent = stories.filter((s) => s.state === key).length;
  document.querySelectorAll(".tabs button").forEach((button) => {
    button.classList.toggle("active", button.dataset.state === filter);
  });
  const shown = stories.filter((s) => s.state === filter);
  el("story-list").innerHTML = shown.length ? shown.map((s) => `
    <button class="story-row${selected?.id === s.id ? " selected" : ""}" type="button" data-id="${escapeHtml(s.id)}">
      <span class="row-date">${escapeHtml(dateLabel(s.published))}</span>
      <strong>${escapeHtml(s.title)}</strong><small>${escapeHtml(s.source || "மூல அறிக்கை")}</small>
    </button>`).join("") : `<div class="list-empty">${filter === "pending" ? "ஒப்புதலுக்குக் காத்திருக்கும் செய்தி இல்லை." : "இந்தப் பிரிவில் செய்தி இல்லை."}</div>`;
  el("story-list").querySelectorAll("[data-id]").forEach((button) => {
    button.addEventListener("click", () => choose(button.dataset.id));
  });
}

function choose(id) {
  selected = stories.find((story) => story.id === id) || null;
  if (!selected) return;
  const s = selected;
  el("editor").classList.remove("empty");
  el("empty-editor").classList.add("hidden");
  el("story-form").classList.remove("hidden");
  el("status-pill").textContent = stateLabels[s.state] || s.state;
  el("status-pill").className = `pill ${s.state}`;
  el("story-date").textContent = dateLabel(s.published);
  el("original-title").textContent = s.originalTitle;
  const source = /^https:\/\//i.test(s.sourceUrl) ? s.sourceUrl : "";
  el("source-link").href = source || "#";
  el("source-link").textContent = source ? `${s.source || "மூலம்"} ↗` : "இணைப்பு இல்லை";
  el("headline").value = s.title;
  el("summary").value = s.summary;
  el("body").value = (s.body || []).join("\n\n");
  el("category").value = s.category;
  el("review-history").textContent = s.updatedAt ? `கடைசியாக ${s.updatedBy} · ${dateLabel(s.updatedAt)}` : "";
  renderList();
  if (innerWidth < 800) el("editor").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function load() {
  const data = await api("/api/stories");
  stories = data.stories;
  renderList();
  const wanted = new URLSearchParams(location.search).get("story");
  if (wanted && stories.some((s) => s.id === wanted)) choose(wanted);
  else if (selected && stories.some((s) => s.id === selected.id)) choose(selected.id);
}

async function decide(state) {
  if (!selected) return;
  const edits = {
    title: el("headline").value.trim(), summary: el("summary").value.trim(),
    body: el("body").value.split(/\n\s*\n/).map((s) => s.trim()).filter(Boolean),
    category: el("category").value
  };
  const buttons = document.querySelectorAll("[data-decision]");
  buttons.forEach((button) => button.disabled = true);
  try {
    const { story } = await api(`/api/stories/${selected.id}`, { method: "PUT",
      body: JSON.stringify({ state, edits, revision: selected.revision }) });
    stories = stories.map((s) => s.id === story.id ? story : s);
    selected = story;
    filter = state;
    choose(story.id);
    notice(state === "approved" ? "ஒப்புதல் சேமிக்கப்பட்டது. செய்தி சில நிமிடங்களில் தளத்தில் தெரியும்." :
      state === "rejected" ? "செய்தி நிராகரிக்கப்பட்டது; தளத்தில் வெளியிடப்படாது." : "திருத்தப்பட்ட வரைவு சேமிக்கப்பட்டது.");
  } catch (error) {
    notice(error.status === 409 ? "மற்றொரு ஆசிரியர் இந்தச் செய்தியை மாற்றியுள்ளார். புதுப்பித்து மீண்டும் பார்க்கவும்." : error.message, true);
  } finally { buttons.forEach((button) => button.disabled = false); }
}

function pushKey(key) {
  const padded = key.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(key.length / 4) * 4, "=");
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
}

async function enablePush() {
  if (!me?.vapidPublicKey) return notice("அறிவிப்பு சேவை இன்னும் இணைக்கப்படவில்லை.", true);
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    return notice("iPhone-இல் Safari-யின் பகிர்வு பட்டியலில் ‘முகப்புத் திரையில் சேர்’ என்பதைத் தேர்ந்தெடுத்து இந்தச் செயலியைத் திறக்கவும்.", true);
  }
  try {
    const permission = await Notification.requestPermission();
    if (permission !== "granted") return notice("அறிவிப்பு அனுமதி வழங்கப்படவில்லை.", true);
    const registration = await navigator.serviceWorker.register("/sw.js");
    const ready = await navigator.serviceWorker.ready;
    const subscription = await ready.pushManager.subscribe({ userVisibleOnly: true,
      applicationServerKey: pushKey(me.vapidPublicKey) });
    await api("/api/push/subscribe", { method: "POST", body: JSON.stringify(subscription.toJSON()) });
    el("test-push").classList.remove("hidden");
    el("push-help").textContent = "அறிவிப்புகள் இயக்கப்பட்டுள்ளன. புதிய வரைவு வரும்போது இந்தத் தொலைபேசியில் தெரியும்.";
    notice("அறிவிப்புகள் இயக்கப்பட்டன.");
  } catch (error) { notice(`அறிவிப்புகளை இயக்க முடியவில்லை: ${error.message}`, true); }
}

async function start() {
  try {
    me = await api("/api/me");
    el("signin").classList.add("hidden");
    el("app").classList.remove("hidden");
    el("logout").classList.remove("hidden");
    await load();
    if (("standalone" in navigator && navigator.standalone) || matchMedia("(display-mode: standalone)").matches) {
      el("push-help").textContent = "அறிவிப்புகளை இயக்கி, புதிய வரைவு வந்ததும் பூட்டுத் திரையில் பெறுங்கள்.";
    }
  } catch (error) {
    if (error.status === 401) el("signin").classList.remove("hidden");
    else { el("signin").classList.remove("hidden"); notice(error.message, true); }
  }
}

document.querySelectorAll(".tabs button").forEach((button) => button.addEventListener("click", () => {
  filter = button.dataset.state; selected = null; renderList();
  el("story-form").classList.add("hidden"); el("empty-editor").classList.remove("hidden");
}));
document.querySelectorAll("[data-decision]").forEach((button) => button.addEventListener("click", () => decide(button.dataset.decision)));
el("refresh").addEventListener("click", () => load().then(() => notice("செய்திப் பட்டியல் புதுப்பிக்கப்பட்டது.")).catch((e) => notice(e.message, true)));
el("enable-push").addEventListener("click", enablePush);
el("test-push").addEventListener("click", () => api("/api/push/test", { method: "POST" })
  .then((data) => notice(data.delivered ? "சோதனை அறிவிப்பு அனுப்பப்பட்டது." : "இயங்கும் சாதனச் சந்தா இல்லை.", !data.delivered))
  .catch((e) => notice(e.message, true)));
start();
