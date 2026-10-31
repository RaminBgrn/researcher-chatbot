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

    def visible_messages(self):
        """فقط پیام‌هایی که کاربر باید ببیند: پیام‌های او و جواب‌های نهایی بات.

        پیام سیستم و رفت‌وبرگشت ابزارها جزو هیستوری داخلی‌اند، نه نمایش.
        """
        visible = []
        for message in self.history:
            role = message.get("role")
            content = message.get("content")
            if role in ("user", "assistant") and content:
                visible.append({"role": role, "content": content})
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

        # در این نوبت تحقیقی انجام شده یا نه؟ (برای ذخیره خودکار گزارش)
        researched = False

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
                # ذخیره خودکار و قطعی توسط کد (نه مدل): اگر این نوبت تحقیق داشت،
                # جواب نهایی گزارش است و بدون یک دور اضافه و تولید دوباره متن،
                # همان‌جا در فایل ذخیره می‌شود؛ اسم فایل را هم کد به جواب اضافه می‌کند.
                if researched and reply.strip():
                    try:
                        saved = save_research(_derive_title(reply, user_message), reply)
                        if saved.get("saved"):
                            reply = f"{reply}\n\n📁 این گزارش به صورت خودکار در فایل «{saved['filename']}» ذخیره شد."
                            # همان نسخه کامل در هیستوری هم بنشیند تا با نمایش UI یکی باشد
                            self.history[-1]["content"] = reply
                    except Exception:
                        pass  # ذخیره نباید جواب کاربر را خراب کند
                return reply

            # ۳) هر ابزاری که خواسته را اجرا و نتیجه را به هیستوری اضافه می‌کنیم
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

                # تحقیق موفق در این نوبت؟ برای ذخیره خودکار جواب نهایی
                if name in RESEARCH_TOOLS and isinstance(result, dict) and "error" not in result:
                    researched = True

                self.history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
            # و حلقه ادامه پیدا می‌کند تا مدل با نتیجه ابزارها جواب نهایی بدهد

        return "متأسفم، تعداد مراحل تحقیق بیش از حد شد. لطفا دوباره تلاش کن."
