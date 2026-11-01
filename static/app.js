// app.js — فرانت UI v2: مدیریت تم + سایدبار گفتگوها + ارسال پیام

/* ================= مدیریت تم (روشن / تیره / سیستم) ================= */
const ThemeManager = {
  current: "system",
  init() {
    try { this.current = localStorage.getItem("theme") || "system"; } catch (e) {}
    if (!["light", "dark", "system"].includes(this.current)) this.current = "system";
    this.apply(this.current);
    document.querySelectorAll(".theme-option").forEach((btn) => {
      btn.addEventListener("click", () => this.apply(btn.dataset.themeValue));
    });
  },
  apply(theme) {
    this.current = theme;
    if (theme === "system") {
      document.documentElement.removeAttribute("data-theme");
      try { localStorage.removeItem("theme"); } catch (e) {}
    } else {
      document.documentElement.setAttribute("data-theme", theme);
      try { localStorage.setItem("theme", theme); } catch (e) {}
    }
    document.querySelectorAll(".theme-option").forEach((btn) => {
      const active = btn.dataset.themeValue === theme;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-checked", active ? "true" : "false");
    });
  },
};

/* ================= المان‌ها و وضعیت ================= */
const form = document.getElementById("chatForm");
const input = document.getElementById("input");
const messagesEl = document.getElementById("messages");
const sendBtn = document.getElementById("sendBtn");
const chatListEl = document.getElementById("chatList");
const sidebar = document.getElementById("sidebar");
const overlay = document.getElementById("overlay");

let currentChatId = null;

const WELCOME = "سلام رامین 👋\nیه موضوع بهم بده تا درباره‌اش تحقیق کنم؛ مثلاً: «هوش مصنوعی» یا «Quantum Computing»";

async function api(path, options) {
  const res = await fetch(path, options);
  return res.json();
}

/* ================= سایدبار موبایل (Drawer) ================= */
function openSidebar() { sidebar.classList.add("open"); overlay.classList.add("show"); }
function closeSidebar() { sidebar.classList.remove("open"); overlay.classList.remove("show"); }
document.getElementById("menuBtn").addEventListener("click", openSidebar);
overlay.addEventListener("click", closeSidebar);

/* ================= گفتگوها ================= */
async function loadChats() {
  const chats = await api("/api/chats");
  chatListEl.innerHTML = "";
  if (!chats.length) {
    chatListEl.innerHTML = '<p class="chat-empty">هنوز گفتگویی نیست.</p>';
    return chats;
  }
  chats.forEach((chat) => {
    const item = document.createElement("button");
    item.className = "chat-item" + (chat.id === currentChatId ? " active" : "");
    item.innerHTML = "";
    const title = document.createElement("span");
    title.className = "chat-title";
    title.textContent = chat.title;
    const meta = document.createElement("span");
    meta.className = "chat-meta";
    meta.textContent = chat.message_count ? chat.message_count + " پیام" : "";
    const del = document.createElement("span");
    del.className = "chat-del";
    del.textContent = "✕";
    del.title = "حذف گفتگو";
    del.addEventListener("click", (e) => { e.stopPropagation(); deleteChat(chat.id); });
    item.append(title, meta, del);
    item.addEventListener("click", () => openChat(chat.id));
    chatListEl.appendChild(item);
  });
  return chats;
}

function addMessage(text, who, opts) {
  const wrap = document.createElement("div");
  wrap.className = "msg " + who;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  wrap.appendChild(bubble);
  // دکمه ذخیره گزارش فقط زیر جواب‌هایی می‌آید که در نوبتشان ابزار صدا زده شده
  if (who === "bot" && opts && opts.usedTools) addSaveButton(wrap, text);
  messagesEl.appendChild(wrap);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return bubble;
}

/* حباب لودینگ سه‌نقطه متحرک، تا وقتی جواب مدل برسد */
function addTyping() {
  const wrap = document.createElement("div");
  wrap.className = "msg bot";
  const bubble = document.createElement("div");
  bubble.className = "bubble typing-dots";
  bubble.setAttribute("aria-label", "در حال تحقیق");
  for (let i = 0; i < 3; i++) {
    const dot = document.createElement("span");
    dot.className = "tdot";
    bubble.appendChild(dot);
  }
  wrap.appendChild(bubble);
  messagesEl.appendChild(wrap);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return wrap;
}

/* دکمه «ذخیره گزارش» زیر حباب بات؛ ذخیره دستی و فقط با کلیک کاربر */
function addSaveButton(wrap, content) {
  const actions = document.createElement("div");
  actions.className = "msg-actions";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "save-report-btn";
  btn.textContent = "📁 ذخیره گزارش";
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    btn.textContent = "در حال ذخیره...";
    try {
      const res = await fetch("/api/chats/" + currentChatId + "/save-report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: content }),
      });
      const d = await res.json();
      if (res.ok && d.saved) {
        btn.textContent = "✓ ذخیره شد — " + d.filename;
        btn.classList.add("saved");
      } else {
        btn.textContent = "خطا در ذخیره — دوباره تلاش کن";
        btn.disabled = false;
      }
    } catch (err) {
      btn.textContent = "خطا در ذخیره — دوباره تلاش کن";
      btn.disabled = false;
    }
  });
  actions.appendChild(btn);
  wrap.appendChild(actions);
}

async function openChat(id) {
  currentChatId = id;
  const chat = await api("/api/chats/" + id);
  messagesEl.innerHTML = "";
  if (!chat.messages || !chat.messages.length) {
    addMessage(WELCOME, "bot");
  } else {
    chat.messages.forEach((m) => addMessage(m.content, m.role === "user" ? "user" : "bot", { usedTools: m.used_tools }));
  }
  await loadChats();
  await loadDebugLog();
  closeSidebar();
  input.focus();
}

async function newChat() {
  const chat = await api("/api/chats", { method: "POST" });
  await openChat(chat.id);
}

async function deleteChat(id) {
  await api("/api/chats/" + id, { method: "DELETE" });
  if (id === currentChatId) {
    const chats = await loadChats();
    if (chats.length) { await openChat(chats[0].id); return; }
    await newChat();
    return;
  }
  await loadChats();
}

document.getElementById("newChatBtn").addEventListener("click", newChat);

/* پاک کردن گفتگوی فعال = حذفش و ساخت یک گفتگوی تازه */
document.getElementById("clearBtn").addEventListener("click", async () => {
  if (currentChatId) await api("/api/chats/" + currentChatId, { method: "DELETE" });
  await newChat();
});

/* ================= ارسال پیام ================= */
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text || !currentChatId) return;

  addMessage(text, "user");
  input.value = "";
  sendBtn.disabled = true;
  const typing = addTyping();

  try {
    const data = await api("/api/chats/" + currentChatId + "/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    typing.remove();
    addMessage(data.reply || data.error || "پاسخی نیامد.", "bot", { usedTools: data.used_tools });
  } catch (err) {
    typing.remove();
    addMessage("خطا در اتصال به سرور. مطمئن شو سرور روشنه.", "bot");
  } finally {
    sendBtn.disabled = false;
    await loadChats(); // عنوان و تعداد پیام‌ها تازه شود
    await loadDebugLog(); // لاگ JSON این گفتگو هم تازه شود
    await loadInvoices(); // فاکتورهای توکنی هم تازه شوند
    await loadStats(); // آمار توکن هم تازه شود
    input.focus();
  }
});

/* ================= تب‌های سایدبار ================= */
const sideTabBtns = document.querySelectorAll(".side-tab");
function switchTab(name) {
  sideTabBtns.forEach((b) => {
    const on = b.dataset.tab === name;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  document.getElementById("pane-chats").hidden = name !== "chats";
  document.getElementById("pane-json").hidden = name !== "json";
  document.getElementById("pane-invoices").hidden = name !== "invoices";
  document.getElementById("pane-settings").hidden = name !== "settings";
  if (name === "json") loadDebugLog();
  if (name === "invoices") loadInvoices();
  if (name === "settings") { loadSettings(); loadStats(); }
}
sideTabBtns.forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));

/* ================= تب JSON: نمایش ردیفی (کلید و مقدار) ================= */
const debugLogEl = document.getElementById("debugLog");

function jsonValueSpan(value) {
  const span = document.createElement("span");
  if (value === null) { span.className = "jv jv-null"; span.textContent = "null"; return span; }
  if (typeof value === "number") { span.className = "jv jv-num"; span.textContent = String(value); return span; }
  if (typeof value === "boolean") { span.className = "jv jv-bool"; span.textContent = String(value); return span; }
  span.className = "jv jv-str";
  const text = JSON.stringify(value);
  if (text.length > 160) {
    const short = document.createElement("span");
    short.textContent = text.slice(0, 160) + "…";
    const more = document.createElement("button");
    more.type = "button"; more.className = "jv-more"; more.textContent = "بیشتر";
    more.addEventListener("click", () => {
      const full = span.dataset.full === "1";
      span.dataset.full = full ? "0" : "1";
      short.textContent = full ? text.slice(0, 160) + "…" : text;
      more.textContent = full ? "بیشتر" : "کمتر";
    });
    span.append(short, more);
  } else {
    span.textContent = text;
  }
  return span;
}

function jsonNode(key, value, depth) {
  const wrap = document.createElement("div");
  wrap.className = "jt-node";
  const row = document.createElement("div");
  row.className = "jt-row";
  const keyEl = document.createElement("span");
  keyEl.className = "jk";
  keyEl.textContent = key;
  row.appendChild(keyEl);
  if (value !== null && typeof value === "object") {
    const isArr = Array.isArray(value);
    const keys = Object.keys(value);
    const badge = document.createElement("button");
    badge.type = "button";
    badge.className = "jt-badge";
    badge.textContent = (isArr ? "[ ] " : "{ } ") + keys.length + (isArr ? " آیتم" : " فیلد") + " ▾";
    row.appendChild(badge);
    const children = document.createElement("div");
    children.className = "jt-children";
    keys.forEach((k) => children.appendChild(jsonNode(k, value[k], depth + 1)));
    if (depth >= 2) children.hidden = true;
    badge.addEventListener("click", () => { children.hidden = !children.hidden; });
    wrap.append(row, children);
  } else {
    row.appendChild(jsonValueSpan(value));
    wrap.appendChild(row);
  }
  return wrap;
}

function debugBlock(label, payload) {
  const wrap = document.createElement("div");
  wrap.className = "debug-block";
  const head = document.createElement("div");
  head.className = "debug-block-head";
  const span = document.createElement("span");
  span.textContent = label;
  const copyBtn = document.createElement("button");
  copyBtn.type = "button";
  copyBtn.className = "debug-copy";
  copyBtn.textContent = "کپی JSON";
  const text = JSON.stringify(payload, null, 2);
  copyBtn.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(text); copyBtn.textContent = "کپی شد ✓"; }
    catch (e) { copyBtn.textContent = "خطا"; }
    setTimeout(() => { copyBtn.textContent = "کپی JSON"; }, 1500);
  });
  head.append(span, copyBtn);
  const tree = document.createElement("div");
  tree.className = "jt-wrap";
  tree.appendChild(jsonNode("root", payload, 0));
  wrap.append(head, tree);
  return wrap;
}

async function loadDebugLog() {
  if (!currentChatId) return;
  const data = await api("/api/chats/" + currentChatId + "/debug");
  const exchanges = (data && data.exchanges) || [];
  debugLogEl.innerHTML = "";
  if (!exchanges.length) {
    debugLogEl.innerHTML = '<p class="debug-empty">هنوز درخواستی ثبت نشده است.</p>';
    return;
  }
  exchanges.forEach((ex) => {
    const entry = document.createElement("div");
    entry.className = "debug-entry";
    const title = document.createElement("p");
    title.className = "debug-round";
    title.textContent = "دور " + ex.round + " — " + (ex.time || "");
    entry.appendChild(title);
    entry.appendChild(debugBlock("📤 فرستنده — Request", ex.request));
    entry.appendChild(debugBlock("📥 گیرنده — Response", ex.response));
    debugLogEl.appendChild(entry);
  });
}


/* ================= تب فاکتورها: قبض توکنی هر دور ================= */
const invoiceListEl = document.getElementById("invoiceList");

function invoiceRow(label, value, bold) {
  const row = document.createElement("div");
  row.className = "stat-row";
  const a = document.createElement("span"); a.textContent = label;
  const b = document.createElement(bold ? "strong" : "span");
  b.textContent = value;
  row.append(a, b);
  return row;
}

async function loadInvoices() {
  if (!currentChatId) return;
  const data = await api("/api/chats/" + currentChatId + "/invoices");
  const invoices = (data && data.invoices) || [];
  invoiceListEl.innerHTML = "";
  if (!invoices.length) {
    invoiceListEl.innerHTML = '<p class="debug-empty">هنوز فاکتوری ثبت نشده است.</p>';
    return;
  }
  invoices.slice().reverse().forEach((inv) => {
    const card = document.createElement("article");
    card.className = "invoice-card";
    const head = document.createElement("div");
    head.className = "invoice-head";
    const t = document.createElement("strong");
    t.textContent = "🧾 فاکتور دور " + inv.round;
    const time = document.createElement("span");
    time.textContent = inv.time || "";
    head.append(t, time);
    card.appendChild(head);
    if (inv.called_tools && inv.called_tools.length) {
      card.appendChild(invoiceRow("ابزار صدا زده‌شده", inv.called_tools.join("، ")));
    }
    card.appendChild(invoiceRow("ورودی (prompt) — واقعی", inv.prompt_tokens != null ? inv.prompt_tokens + " توکن" : "—"));
    card.appendChild(invoiceRow("↳ سیستم پرامپت (تخمینی)", inv.est_system_tokens + " توکن"));
    card.appendChild(invoiceRow("↳ اسکیمای ابزارها (تخمینی)", inv.est_tools_tokens + " توکن"));
    card.appendChild(invoiceRow("↳ هیستوری (تخمینی)", inv.est_history_tokens + " توکن"));
    card.appendChild(invoiceRow("خروجی (completion) — واقعی", inv.completion_tokens != null ? inv.completion_tokens + " توکن" : "—"));
    card.appendChild(invoiceRow("جمع کل — واقعی", inv.total_tokens != null ? inv.total_tokens + " توکن" : "—", true));
    if (inv.finish_reason) {
      card.appendChild(invoiceRow("دلیل پایان (finish_reason)", inv.finish_reason));
    }
    invoiceListEl.appendChild(card);
  });
}

/* ================= تب تنظیمات: مقادیر توکن و آمار ================= */
const settingsForm = document.getElementById("settingsForm");
const settingsMsg = document.getElementById("settingsMsg");
const statsBody = document.getElementById("statsBody");

async function loadSettings() {
  const s = await api("/api/settings");
  document.getElementById("setMaxTokens").value = s.max_tokens;
  document.getElementById("setHistoryBudget").value = s.history_token_budget;
  document.getElementById("setMaxRounds").value = s.max_tool_rounds;
}

settingsForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    max_tokens: Number(document.getElementById("setMaxTokens").value),
    history_token_budget: Number(document.getElementById("setHistoryBudget").value),
    max_tool_rounds: Number(document.getElementById("setMaxRounds").value),
  };
  const res = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  settingsMsg.textContent = res.ok ? "اعمال شد ✓ از پیام بعدی اثرش را می‌بینی." : (data.error || "خطا در تنظیمات");
  if (res.ok) loadStats();
});

function statRow(label, value) {
  const row = document.createElement("div");
  row.className = "stat-row";
  const a = document.createElement("span"); a.textContent = label;
  const b = document.createElement("strong"); b.textContent = value;
  row.append(a, b);
  return row;
}

async function loadStats() {
  if (!currentChatId) return;
  const s = await api("/api/chats/" + currentChatId + "/stats");
  statsBody.innerHTML = "";
  statsBody.appendChild(statRow("سیستم پرامپت", s.system_tokens + " توکن"));
  statsBody.appendChild(statRow("اسکیمای ابزارها", s.tools_tokens + " توکن"));
  statsBody.appendChild(statRow("هیستوری فعلی", s.history_tokens + " توکن (" + s.history_messages + " پیام)"));
  statsBody.appendChild(statRow("برآورد ورودی تماس بعدی", "≈ " + (s.system_tokens + s.tools_tokens + s.history_tokens) + " توکن"));
  statsBody.appendChild(statRow("تماس‌های ثبت‌شده در تب JSON", s.exchanges + " دور"));
}

/* ================= شروع ================= */
(async function start() {
  ThemeManager.init();
  const chats = await loadChats();
  if (chats.length) await openChat(chats[0].id);
  else await newChat();
})();
