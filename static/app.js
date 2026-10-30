// app.js — منطق ساده فرانت: فرستادن پیام و نشان دادن جواب
const form = document.getElementById("chatForm");
const input = document.getElementById("input");
const messages = document.getElementById("messages");
const sendBtn = document.getElementById("sendBtn");
const clearBtn = document.getElementById("clearBtn");

function addMessage(text, who) {
  const wrap = document.createElement("div");
  wrap.className = "msg " + who;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  wrap.appendChild(bubble);
  messages.appendChild(wrap);
  messages.scrollTop = messages.scrollHeight;
  return bubble;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;

  addMessage(text, "user");
  input.value = "";
  sendBtn.disabled = true;

  const typing = addMessage("در حال تحقیق... 🔎", "bot");
  typing.classList.add("typing");

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    const data = await res.json();
    typing.classList.remove("typing");
    typing.textContent = data.reply || data.error || "پاسخی نیامد.";
  } catch (err) {
    typing.classList.remove("typing");
    typing.textContent = "خطا در اتصال به سرور. مطمئن شو سرور روشنه.";
  } finally {
    sendBtn.disabled = false;
    input.focus();
  }
});

clearBtn.addEventListener("click", async () => {
  await fetch("/api/clear", { method: "POST" });
  messages.innerHTML = "";
  addMessage("هیستوری پاک شد. 🧹 از اول شروع می‌کنیم؛ یه موضوع بهم بده.", "bot");
});
