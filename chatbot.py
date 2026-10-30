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

from dotenv import load_dotenv
from openai import OpenAI

from prompts import SYSTEM_PROMPT
from tools import TOOLS, TOOL_FUNCTIONS

load_dotenv()  # خواندن .env

API_KEY = os.getenv("API_KEY", "")
BASE_URL = os.getenv("BASE_URL", "")      # همان endpoint ای که داده می‌شود
MODEL_NAME = os.getenv("MODEL_NAME", "")  # همان اسم مدلی که داده می‌شود

MAX_TOOL_ROUNDS = 5  # سقف دفعات رفت‌وبرگشت ابزار، تا حلقه بی‌نهایت نشود


class ResearcherChatbot:
    def __init__(self):
        # اگر کلید هنوز داده نشده باشد، چت‌بات بالا می‌آید ولی موقع چت خطای واضح می‌دهد
        self.client = None
        if API_KEY:
            self.client = OpenAI(api_key=API_KEY, base_url=BASE_URL or None)
        self.clear_history()

    # ---------------------------------------------------------- هیستوری
    def clear_history(self):
        """هیستوری را پاک می‌کند؛ فقط سیستم پرامپت می‌ماند."""
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]

    # -------------------------------------------------------------- چت
    def chat(self, user_message: str) -> str:
        if self.client is None:
            return (
                "⚠️ هنوز API key تنظیم نشده است. "
                "فایل .env را با API_KEY و BASE_URL و MODEL_NAME کامل کن و دوباره تلاش کن."
            )

        # ۱) پیام کاربر به هیستوری اضافه می‌شود
        self.history.append({"role": "user", "content": user_message})

        # ۲) حلقه اصلی: پرسیدن از مدل + اجرای ابزارها تا جواب نهایی
        for _ in range(MAX_TOOL_ROUNDS):
            response = self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=self.history,
                tools=TOOLS,
                tool_choice="auto",
            )
            message = response.choices[0].message

            # جواب/درخواست مدل هم وارد هیستوری می‌شود
            self.history.append(message.model_dump(exclude_none=True))

            # اگر ابزاری نخواسته، یعنی جواب نهایی آماده است
            if not message.tool_calls:
                return message.content or ""

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

                self.history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
            # و حلقه ادامه پیدا می‌کند تا مدل با نتیجه ابزارها جواب نهایی بدهد

        return "متأسفم، تعداد مراحل تحقیق بیش از حد شد. لطفا دوباره تلاش کن."
