"""
chatbot.py — مغز چت‌بات: مدیریت هیستوری + حلقه Tool Call
=========================================================
سه ایده اصلی این تمرین اینجاست:
1. سیستم پرامپت : از prompts.py خوانده می‌شود و اول هیستوری می‌نشیند.
2. هیستوری      : لیست پیام‌ها؛ هر پیام تازه به آن اضافه و کل لیست
                  در هر درخواست برای مدل فرستاده می‌شود. مدل حافظه ندارد،
                  این لیست حافظه اوست.
3. Tool Call     : اگر مدل ابزاری خواست، ما اجرایش می‌کنیم، نتیجه را
                  به هیستوری اضافه می‌کنیم و دوباره از مدل می‌پرسیم.
"""

import json
import os
from datetime import datetime

from dotenv import load_dotenv
from openai import OpenAI

from prompts import SYSTEM_PROMPT
from tools import TOOLS, TOOL_FUNCTIONS, save_research

load_dotenv()  # خواندن .env

API_KEY = os.getenv("API_KEY", "")
BASE_URL = os.getenv("BASE_URL", "")      # همان endpoint ای که داده می‌شود
MODEL_NAME = os.getenv("MODEL_NAME", "")  # همان اسم مدلی که داده می‌شود

MAX_TOOL_ROUNDS = 5  # سقف دفعات رفت‌وبرگشت ابزار، تا حلقه بی‌نهایت نشود

# ابزارهای تحقیقی: اگر در یک نوبت چت یکی از این‌ها با موفقیت اجرا شود،
# جواب نهایی آن نوبت «گزارش» حساب می‌شود و کد خودش آن را در فایل ذخیره می‌کند.
RESEARCH_TOOLS = {"search_wikipedia", "search_web", "get_weather"}


# ------------------------------------------------------------- شمارش توکن
# شمارش با tiktoken (انکودینگ cl100k_base) «تخمینی» است؛ عدد قطعی را خود API
# در فیلد usage پاسخ می‌دهد. اگر tiktoken نصب نباشد، برآورد کاراکتری جایگزین می‌شود.
try:
    import tiktoken

    _ENC = tiktoken.get_encoding("cl100k_base")
except Exception:  # pragma: no cover
    _ENC = None


def count_text_tokens(text: str) -> int:
    """تعداد تقریبی توکن‌های یک متن."""
    if not text:
        return 0
    if _ENC is not None:
        return len(_ENC.encode(text))
    return max(1, len(text) // 2)


def count_messages_tokens(messages) -> int:
    """تعداد تقریبی توکن‌های یک لیست پیام (با سربار قالب هر پیام)."""
    total = 0
    for message in messages:
        total += 4  # سربار تقریبی نقش و قالب هر پیام
        content = message.get("content")
        if isinstance(content, str):
            total += count_text_tokens(content)
        if message.get("tool_calls"):
            total += count_text_tokens(json.dumps(message["tool_calls"], ensure_ascii=False))
    return total


def _derive_title(content: str, fallback: str) -> str:
    """عنوان گزارش را از اولین خط معنادار جواب نهایی می‌سازد."""
    for line in content.splitlines():
        title = line.strip().lstrip("#").strip()
        title = title.replace("**", "").strip()
        if title.lower().startswith("عنوان:"):
            title = title.split(":", 1)[1].strip()
        if len(title) >= 3:
            return title[:60]
    return fallback[:60]


class ResearcherChatbot:
    def __init__(self):
        # اگر کلید هنوز داده نشده باشد، چت‌بات بالا می‌آید ولی موقع چت خطای واضح می‌دهد
        self.client = None
        if API_KEY:
            self.client = OpenAI(api_key=API_KEY, base_url=BASE_URL or None)
        # تنظیمات توکن؛ از پنل تنظیمات UI قابل تغییرند (۰ یعنی نامحدود)
        self.max_output_tokens = 1000
        self.history_token_budget = 0
        self.max_tool_rounds = MAX_TOOL_ROUNDS
        # آیا در آخرین نوبت ابزاری صدا زده شد؟ (برای دکمه «ذخیره گزارش» زیر حباب)
        self.last_used_tools = False
        self.clear_history()

    # ---------------------------------------------------------- آمار توکن
    def usage_estimate(self) -> dict:
        """برآورد توکنی وضعیت فعلی، برای نمایش در پنل تنظیمات."""
        return {
            "system_tokens": count_text_tokens(SYSTEM_PROMPT),
            "tools_tokens": count_text_tokens(json.dumps(TOOLS, ensure_ascii=False)),
            "history_tokens": count_messages_tokens(self.history),
            "history_messages": len(self.history),
        }

    def invoices(self) -> list:
        """فاکتور توکنی هر دور رفت‌وبرگشت با مدل، برای تب «فاکتورها».

        اعداد usage واقعیِ خود API هستند؛ شکست ورودی به اجزا (سیستم / ابزارها /
        هیستوری) با شمارش‌گر خودمان تخمین زده می‌شود تا معلوم شود هر بخش چقدر از
        ورودی را ساخته است.
        """
        result = []
        for entry in self.api_log:
            request = entry.get("request") or {}
            response = entry.get("response") or {}
            messages = request.get("messages") or []

            system_tokens = 0
            if messages and messages[0].get("role") == "system":
                system_tokens = count_text_tokens(messages[0].get("content") or "") + 4
            tools_tokens = count_text_tokens(json.dumps(request.get("tools") or [], ensure_ascii=False))
            all_messages_tokens = count_messages_tokens(messages)
            history_tokens = max(0, all_messages_tokens - system_tokens)

            usage = response.get("usage") or {}
            choices = response.get("choices") or []
            finish_reason = choices[0].get("finish_reason") if choices else None
            called_tools = []
            if choices:
                for tc in (choices[0].get("message") or {}).get("tool_calls") or []:
                    name = ((tc.get("function") or {}).get("name"))
                    if name:
                        called_tools.append(name)

            result.append(
                {
                    "round": entry.get("round"),
                    "time": entry.get("time"),
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "total_tokens": usage.get("total_tokens"),
                    "est_system_tokens": system_tokens,
                    "est_tools_tokens": tools_tokens,
                    "est_history_tokens": history_tokens,
                    "est_prompt_tokens": system_tokens + tools_tokens + history_tokens,
                    "finish_reason": finish_reason,
                    "called_tools": called_tools,
                }
            )
        return result

    def _trim_history(self):
        """اگر بودجه توکنی هیستوری رد شده باشد، قدیمی‌ترین بلوک‌ها حذف می‌شوند.

        سیستم پرامپت (عضو اول) و بلوک جاری (آخرین پیام کاربر و ادامه‌اش) هرگز
        حذف نمی‌شوند و حذف همیشه بلوکی است تا جفت tool_call و نتیجه‌اش از هم جدا نشوند.
        """
        budget = self.history_token_budget
        if not budget or budget <= 0:
            return
        while count_messages_tokens(self.history) > budget:
            user_starts = [
                i for i, m in enumerate(self.history) if m.get("role") == "user"
            ]
            if len(user_starts) <= 1:
                break  # فقط بلوک جاری مانده؛ دست نمی‌زنیم
            del self.history[user_starts[0] : user_starts[1]]

    # ---------------------------------------------------------- هیستوری
    def clear_history(self):
        """هیستوری را پاک می‌کند؛ فقط سیستم پرامپت می‌ماند."""
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]
        # لاگ خام رفت‌وبرگشت با مدل، برای پنل دیباگ UI (نمایش JSON درخواست و پاسخ)
        self.api_log = []
        # شناسه پیام‌های نهایی‌ای که در نوبتشان ابزار صدا زده شده (برای دکمه ذخیره)
        self._tool_msg_ids = set()
        self.last_used_tools = False

    def save_report(self, content: str) -> dict:
        """ذخیره دستی یک جواب به‌عنوان گزارش در outputs (دکمه زیر حباب چت)."""
        return save_research(_derive_title(content, "گزارش"), content)

    def visible_messages(self):
        """فقط پیام‌هایی که کاربر باید ببیند: پیام‌های او و جواب‌های نهایی بات.

        پیام سیستم و رفت‌وبرگشت ابزارها جزو هیستوری داخلی‌اند، نه نمایش.
        """
        visible = []
        for message in self.history:
            role = message.get("role")
            content = message.get("content")
            if role in ("user", "assistant") and content:
                visible.append(
                    {
                        "role": role,
                        "content": content,
                        "used_tools": id(message) in self._tool_msg_ids,
                    }
                )
        return visible

    # -------------------------------------------------------------- چت
    def chat(self, user_message: str) -> str:
        if self.client is None:
            # پیام و جواب خطا هم در هیستوری می‌مانند تا گفتگو در UI گم نشود
            warning = (
                "⚠️ هنوز API key تنظیم نشده است. "
                "فایل .env را با API_KEY و BASE_URL و MODEL_NAME کامل کن و دوباره تلاش کن."
            )
            self.history.append({"role": "user", "content": user_message})
            self.history.append({"role": "assistant", "content": warning})
            return warning

        # ۱) پیام کاربر به هیستوری اضافه می‌شود
        self.history.append({"role": "user", "content": user_message})

        # در این نوبت ابزاری صدا زده شد یا نه؟ (ذخیره گزارش دیگر خودکار نیست؛
        # این پرچم فقط مشخص می‌کند زیر جواب نهایی دکمه «ذخیره گزارش» بیاید یا نه)
        used_tools = False
        self.last_used_tools = False

        # بودجه توکنی هیستوری اعمال می‌شود (اگر در تنظیمات فعال شده باشد)
        self._trim_history()

        # ۲) حلقه اصلی: پرسیدن از مدل + اجرای ابزارها تا جواب نهایی
        for _ in range(self.max_tool_rounds):
            # اسنپ‌شات درخواست، برای پنل دیباگ: دقیقاً همان چیزی که برای مدل می‌رود
            request_payload = {
                "model": MODEL_NAME,
                "messages": json.loads(json.dumps(self.history, ensure_ascii=False)),
                "tools": TOOLS,
                "tool_choice": "auto",
            }
            create_kwargs = {}
            if self.max_output_tokens:
                create_kwargs["max_tokens"] = self.max_output_tokens
                request_payload["max_tokens"] = self.max_output_tokens
            response = self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=self.history,
                tools=TOOLS,
                tool_choice="auto",
                **create_kwargs,
            )
            # پاسخ خام مدل را هم کنار درخواستش نگه می‌داریم
            try:
                response_payload = response.model_dump()
            except Exception:
                response_payload = {"raw": str(response)}
            self.api_log.append(
                {
                    "round": len(self.api_log) + 1,
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "request": request_payload,
                    "response": response_payload,
                }
            )
            message = response.choices[0].message
            print(response.choices)

            # جواب/درخواست مدل هم وارد هیستوری می‌شود
            self.history.append(message.model_dump(exclude_none=True))

            # اگر ابزاری نخواسته، یعنی جواب نهایی آماده است
            if not message.tool_calls:
                reply = message.content or ""
                # ذخیره گزارش دستی است (دکمه زیر حباب)؛ این‌جا فقط پرچم می‌خورد
                self.last_used_tools = used_tools
                if used_tools:
                    self._tool_msg_ids.add(id(self.history[-1]))
                return reply

            # ۳) هر ابزاری که خواسته را اجرا و نتیجه را به هیستوری اضافه می‌کنیم
            used_tools = True
            for tool_call in message.tool_calls:
                name = tool_call.function.name
                args = json.loads(tool_call.function.arguments or "{}")

                function = TOOL_FUNCTIONS.get(name)
                if function is None:
                    result = {"error": f"ابزار ناشناخته: {name}"}
                else:
                    try:
                        result = function(**args)
                    except Exception as e:
                        result = {"error": str(e)}

                self.history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
            # و حلقه ادامه پیدا می‌کند تا مدل با نتیجه ابزارها جواب نهایی بدهد

        self.last_used_tools = used_tools
        return "متأسفم، تعداد مراحل تحقیق بیش از حد شد. لطفا دوباره تلاش کن."
