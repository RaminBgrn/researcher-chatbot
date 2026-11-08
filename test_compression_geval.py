"""تست‌های Compression هیستوری و داور G-Eval (بدون شبکه، با کلاینت جعلی)."""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import chatbot as chatbot_module
import eval_store
import geval
from chatbot import ResearcherChatbot, _compress_tool_content

PASS = []


def check(name, cond):
    PASS.append((name, bool(cond)))
    print(("✅" if cond else "❌"), name)


# --------------------------------------------------------------- کلاینت جعلی
class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, exclude_none=False):
        d = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in self.tool_calls
            ]
        return d


class FakeToolCall:
    def __init__(self, name, arguments, call_id="call_1"):
        self.id = call_id
        self.function = type("F", (), {"name": name, "arguments": arguments})()


class FakeChoice:
    def __init__(self, message, finish_reason):
        self.message = message
        self.finish_reason = finish_reason


class FakeResponse:
    def __init__(self, message, finish_reason, prompt=1000, completion=100):
        self.choices = [FakeChoice(message, finish_reason)]
        self._prompt, self._completion = prompt, completion

    def model_dump(self):
        msg = self.choices[0].message
        return {
            "choices": [
                {
                    "finish_reason": self.choices[0].finish_reason,
                    "message": msg.model_dump(exclude_none=True),
                }
            ],
            "usage": {
                "prompt_tokens": self._prompt,
                "completion_tokens": self._completion,
                "total_tokens": self._prompt + self._completion,
            },
        }


class FakeCompletions:
    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.chat = type("C", (), {"completions": FakeCompletions(responses)})()


# ------------------------------------------------------------ Compression واحدی
fat = {
    "query": "مدل‌های محبوب",
    "results": [
        {"title": f"نتیجه {i}", "url": f"https://example.com/{i}", "content": "x" * 900}
        for i in range(6)
    ],
}
compressed = _compress_tool_content(json.dumps(fat, ensure_ascii=False))
parsed = json.loads(compressed)
check("فشرده‌سازی حجم را کم می‌کند", len(compressed) < len(json.dumps(fat, ensure_ascii=False)) / 2)
check("ساختار حفظ می‌شود: حداکثر ۳ نتیجه", len(parsed["results"]) == 3)
check("متن هر نتیجه کوتاه شده", all(len(r["content"]) <= 260 for r in parsed["results"]))
check("عنوان و لینک می‌مانند", parsed["results"][0]["title"] == "نتیجه 0" and "example.com" in parsed["results"][0]["url"])

# ------------------------------------------------- Compression در جریان چت
fat_result = {"query": "q", "results": [{"title": "t", "url": "u", "content": "y" * 5000}]}
original_fn = chatbot_module.TOOL_FUNCTIONS.get("search_web")
chatbot_module.TOOL_FUNCTIONS["search_web"] = lambda query: fat_result
try:
    bot = ResearcherChatbot()
    bot.client = FakeClient(
        [
            FakeResponse(FakeMessage(tool_calls=[FakeToolCall("search_web", '{"query": "q"}')]), "tool_calls"),
            FakeResponse(FakeMessage(content="گزارش نهایی درباره مدل‌ها"), "stop"),
            FakeResponse(FakeMessage(content="جواب دوم ساده"), "stop"),
        ]
    )
    reply = bot.chat("مدل‌های محبوب را بگو")
    tool_msgs = [m for m in bot.history if m.get("role") == "tool"]
    check("پیام tool در هیستوری هست", len(tool_msgs) == 1)
    check("tool_call_id حفظ شده", tool_msgs[0].get("tool_call_id") == "call_1")
    check("نتیجه خام در هیستوری فشرده شده", len(tool_msgs[0]["content"]) < 1500 and "فشرده شد" in tool_msgs[0]["content"])
    check("جواب نهایی دست‌نخورده مانده", "گزارش نهایی درباره مدل‌ها" in reply)
    check("صرفه‌جویی توکن ثبت شده", (bot.last_turn or {}).get("compressed_saved_tokens", 0) > 500)
    check("منابع نوبت برای داور نگه داشته شده", len(bot.last_sources) == 1 and bot.last_sources[0]["tool"] == "search_web")
    # نوبت دوم: مدل باید هیستوری فشرده را ببیند، نه متن خام را
    bot.chat("سؤال دوم")
    second_turn_messages = json.dumps(
        bot.client.chat.completions.requests[-1]["messages"], ensure_ascii=False
    )
    check("در نوبت بعد متن خام ۵۰۰۰ حرفی فرستاده نمی‌شود", "y" * 500 not in second_turn_messages)
finally:
    if original_fn:
        chatbot_module.TOOL_FUNCTIONS["search_web"] = original_fn

# ------------------------------------------------------------------- G-Eval
good = geval.parse_judge_output(
    'متن قبل {"scores": {"relevance": 5, "grounding": 4, "completeness": 4, "clarity": 5}, "notes": "خوب"} بعد'
)
check("پارس خروجی داور", good is not None and good["overall"] == 4.5)
check("خروجی نامعتبر None می‌شود", geval.parse_judge_output("هیچ JSONی نیست") is None)
check(
    "نمره بیرون از بازه رد می‌شود",
    geval.parse_judge_output('{"scores": {"relevance": 9, "grounding": 4, "completeness": 4, "clarity": 5}}') is None,
)


class JudgeCompletions:
    def create(self, **kwargs):
        msg = FakeMessage(
            content='{"scores": {"relevance": 4, "grounding": 3, "completeness": 4, "clarity": 4}, "notes": "بد نیست"}'
        )
        return FakeResponse(msg, "stop")


judge_client = type("JC", (), {"chat": type("CC", (), {"completions": JudgeCompletions()})()})()
result = geval.judge(judge_client, "m", "سؤال", [{"tool": "search_web", "content": "..."}], "جواب")
check("داوری کامل با کلاینت جعلی", result is not None and result["overall"] == 3.75)
check("بدون کلاینت None", geval.judge(None, "m", "س", [], "جواب") is None)

# ------------------------------------------------------------- eval_store اتصال
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "eval.json")
    rec = eval_store.append_record(
        {"id": "t1", "user": "س", "tools": ["search_web"], "finish_reason": "stop",
         "used_tools": True, "saved": "r.txt", "total_tokens": 100},
        path=path,
    )
    check("set_geval روی رکورد می‌نشیند", eval_store.set_geval("t1", result, path=path))
    summary = eval_store.summarize(eval_store.load_records(path))
    check("میانگین G-Eval در خلاصه", summary["geval_avg"] == 3.75 and summary["geval_count"] == 1)

failed = [n for n, ok in PASS if not ok]
print(f"\n{len(PASS) - len(failed)}/{len(PASS)} چک پاس شد")
sys.exit(1 if failed else 0)
