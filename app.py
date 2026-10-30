"""
app.py — سرور ساده وب (Flask)
================================
فقط سه کار می‌کند:
- صفحه چت را نشان می‌دهد       (GET  /)
- پیام را به چت‌بات می‌دهد     (POST /api/chat)
- هیستوری را پاک می‌کند        (POST /api/clear)
"""

from flask import Flask, jsonify, render_template, request

from chatbot import ResearcherChatbot

app = Flask(__name__)
bot = ResearcherChatbot()


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    message = (request.get_json() or {}).get("message", "").strip()
    if not message:
        return jsonify({"error": "پیام خالی است."}), 400

    reply = bot.chat(message)
    return jsonify({"reply": reply, "history_size": len(bot.history)})


@app.route("/api/clear", methods=["POST"])
def clear():
    bot.clear_history()
    return jsonify({"ok": True, "history_size": len(bot.history)})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
