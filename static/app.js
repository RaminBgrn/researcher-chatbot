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

function addMessage(text, who) {
  const wrap = document.createElement("div");
  wrap.className = "msg " + who;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  wrap.appendChild(bubble);
  messagesEl.appendChild(wrap);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return bubble;
}

async function openChat(id) {
  currentChatId = id;
  const chat = await api("/api/chats/" + id);
  messagesEl.innerHTML = "";
  if (!chat.messages || !chat.messages.length) {
    addMessage(WELCOME, "bot");
  } else {
    chat.messages.forEach((m) => addMessage(m.content, m.role === "user" ? "user" : "bot"));
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
  const typing = addMessage("در حال تحقیق... 🔎", "bot");
  typing.classList.add("typing");

  try {
    const data = await api("/api/chats/" + currentChatId + "/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    typing.classList.remove("typing");
    typing.textContent = data.reply || data.error || "پاسخی نیامد.";
  } catch (err) {
    typing.classList.remove("typing");
    typing.textContent = "خطا در اتصال به سرور. مطمئن شو سرور روشنه.";
  } finally {
    sendBtn.disabled = false;
    await loadChats(); // عنوان و تعداد پیام‌ها تازه شود
    await loadDebugLog(); // لاگ JSON این گفتگو هم تازه شود
    input.focus();
  }
});

/* ================= پنل دیباگ: لاگ JSON درخواست/پاسخ ================= */
const debugToggle = document.getElementById("debugToggle");
const debugBody = document.getElementById("debugBody");
const debugLogEl = document.getElementById("debugLog");

debugToggle.addEventListener("click", async () => {
  const willOpen = debugBody.hidden;
  debugBody.hidden = !willOpen;
  debugToggle.setAttribute("aria-expanded", willOpen ? "true" : "false");
  if (willOpen) await loadDebugLog();
});

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
  copyBtn.textContent = "کپی";
  const text = JSON.stringify(payload, null, 2);
  copyBtn.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(text); copyBtn.textContent = "کپی شد ✓"; }
    catch (e) { copyBtn.textContent = "خطا"; }
    setTimeout(() => { copyBtn.textContent = "کپی"; }, 1500);
  });
  head.append(span, copyBtn);
  const pre = document.createElement("pre");
  pre.className = "debug-pre";
  pre.dir = "ltr";
  pre.textContent = text;
  wrap.append(head, pre);
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
  debugLogEl.scrollTop = debugLogEl.scrollHeight;
}

/* ================= شروع ================= */
(async function start() {
  ThemeManager.init();
  const chats = await loadChats();
  if (chats.length) await openChat(chats[0].id);
  else await newChat();
})();
