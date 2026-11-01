"""
app.py — سرور ساده وب (Flask)
================================
- صفحه چت را نشان می‌دهد            (GET    /)
- گفتگوها را مدیریت می‌کند:
    فهرست گفتگوها                   (GET    /api/chats)
    ساخت گفتگوی تازه                (POST   /api/chats)
    خواندن پیام‌های یک گفتگو        (GET    /api/chats/<id>)
    فرستادن پیام به یک گفتگو        (POST   /api/chats/<id>/message)
    حذف یک گفتگو                    (DELETE /api/chats/<id>)
- API های قبلی هم برای سازگاری مانده‌اند و روی گفتگوی پیش‌فرض کار می‌کنند:
    فرستادن پیام                    (POST   /api/chat)
    پاک کردن هیستوری                (POST   /api/clear)

هر گفتگو یک ResearcherChatbot مخصوص خودش دارد، پس هیستوری هر گفتگو جداست.
همه چیز در حافظه سرور نگه داشته می‌شود؛ با ری‌استارت سرور پاک می‌شود.
"""

import uuid
from datetime import datetime

from flask import Flask, jsonify, render_template, request

from chatbot import ResearcherChatbot

app = Flask(__name__)


class ChatSession:
    """یک گفتگو: شناسه، عنوان و چت‌بات خودش (که هیستوری داخل آن است)."""

    def __init__(self, chat_id: str):
        self.id = chat_id
        self.title = "گفتگوی جدید"
        self.created_at = datetime.now().isoformat(timespec="seconds")
        self.bot = ResearcherChatbot()

    def summary(self):
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "message_count": len(self.bot.visible_messages()),
        }


# همه گفتگوها این تو نگه داشته می‌شوند؛ اولی گفتگوی پیش‌فرض است
chats: dict[str, ChatSession] = {}


def new_chat() -> ChatSession:
    chat = ChatSession(uuid.uuid4().hex[:12])
    chats[chat.id] = chat
    return chat


chats["default"] = ChatSession("default")


def get_chat_or_404(chat_id: str):
    chat = chats.get(chat_id)
    if chat is None:
        return None, (jsonify({"error": "این گفتگو پیدا نشد."}), 404)
    return chat, None


@app.route("/")
def home():
    return render_template("index.html")


# ------------------------------------------------------------ گفتگوها
@app.route("/api/chats", methods=["GET"])
def list_chats():
    ordered = sorted(chats.values(), key=lambda c: c.created_at, reverse=True)
    return jsonify([chat.summary() for chat in ordered])


@app.route("/api/chats", methods=["POST"])
def create_chat():
    chat = new_chat()
    return jsonify(chat.summary()), 201


@app.route("/api/chats/<chat_id>", methods=["GET"])
def get_chat(chat_id):
    chat, error = get_chat_or_404(chat_id)
    if error:
        return error
    return jsonify({**chat.summary(), "messages": chat.bot.visible_messages()})


@app.route("/api/chats/<chat_id>/debug", methods=["GET"])
def get_debug_log(chat_id):
    chat, error = get_chat_or_404(chat_id)
    if error:
        return error
    return jsonify({"exchanges": chat.bot.api_log})


# ------------------------------------------------------------ تنظیمات توکن
# از پنل تنظیمات سایدبار خوانده/نوشته می‌شوند و پیش از هر چت روی بات اعمال می‌شوند.
# مقدار ۰ برای max_tokens و history_token_budget یعنی «نامحدود».
SETTINGS = {"max_tokens": 1000, "history_token_budget": 0, "max_tool_rounds": 5}

_SETTINGS_LIMITS = {
    "max_tokens": (0, 8000),
    "history_token_budget": (0, 100000),
    "max_tool_rounds": (1, 10),
}


@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(SETTINGS)


@app.route("/api/settings", methods=["POST"])
def update_settings():
    data = request.get_json() or {}
    for key, (low, high) in _SETTINGS_LIMITS.items():
        if key in data:
            try:
                value = int(data[key])
            except (TypeError, ValueError):
                return jsonify({"error": f"مقدار {key} باید عدد باشد."}), 400
            if not low <= value <= high:
                return jsonify({"error": f"مقدار {key} باید بین {low} و {high} باشد."}), 400
            SETTINGS[key] = value
    return jsonify(SETTINGS)


@app.route("/api/chats/<chat_id>/invoices", methods=["GET"])
def get_chat_invoices(chat_id):
    chat, error = get_chat_or_404(chat_id)
    if error:
        return error
    return jsonify({"invoices": chat.bot.invoices()})


@app.route("/api/chats/<chat_id>/stats", methods=["GET"])
def get_chat_stats(chat_id):
    chat, error = get_chat_or_404(chat_id)
    if error:
        return error
    return jsonify({**chat.bot.usage_estimate(), "exchanges": len(chat.bot.api_log)})


@app.route("/api/chats/<chat_id>/message", methods=["POST"])
def send_message(chat_id):
    chat, error = get_chat_or_404(chat_id)
    if error:
        return error

    message = (request.get_json() or {}).get("message", "").strip()
    if not message:
        return jsonify({"error": "پیام خالی است."}), 400

    # عنوان گفتگو از اولین پیام کاربر ساخته می‌شود
    if chat.title == "گفتگوی جدید":
        chat.title = message[:30] + ("…" if len(message) > 30 else "")

    # تنظیمات توکن فعلی روی بات اعمال می‌شود
    chat.bot.max_output_tokens = SETTINGS["max_tokens"]
    chat.bot.history_token_budget = SETTINGS["history_token_budget"]
    chat.bot.max_tool_rounds = SETTINGS["max_tool_rounds"]

    reply = chat.bot.chat(message)
    return jsonify(
        {"reply": reply, "used_tools": chat.bot.last_used_tools, "chat": chat.summary()}
    )


@app.route("/api/chats/<chat_id>/save-report", methods=["POST"])
def save_report(chat_id):
    chat, error = get_chat_or_404(chat_id)
    if error:
        return error

    content = (request.get_json() or {}).get("content", "").strip()
    if not content:
        return jsonify({"error": "متنی برای ذخیره نیست."}), 400

    result = chat.bot.save_report(content)
    if not result.get("saved"):
        return jsonify({"error": result.get("error", "ذخیره گزارش انجام نشد.")}), 500
    return jsonify(result)


@app.route("/api/chats/<chat_id>", methods=["DELETE"])
def delete_chat(chat_id):
    if chat_id not in chats:
        return jsonify({"error": "این گفتگو پیدا نشد."}), 404
    del chats[chat_id]
    return jsonify({"ok": True})


# -------------------------------------------------- API قبلی (سازگاری)
@app.route("/api/chat", methods=["POST"])
def chat():
    return send_message("default")


@app.route("/api/clear", methods=["POST"])
def clear():
    default = chats["default"]
    default.bot.clear_history()
    default.title = "گفتگوی جدید"
    return jsonify({"ok": True, "history_size": len(default.bot.history)})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
