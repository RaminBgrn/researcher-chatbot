"""
tools.py — ابزارهایی که مدل می‌تواند صدا بزند (Tool Calls)
===========================================================
هر ابزار = یک تابع ساده پایتون + یک توضیح (schema) برای مدل.
مدل خودش تصمیم می‌گیرد کی و با چه ورودی‌ای ابزار را صدا بزند.

دو ابزار داریم:
1. search_wikipedia : تحقیق درباره یک موضوع (بدون نیاز به API key)
2. save_research    : ذخیره گزارش نهایی در یک فایل داخل پوشه outputs/
"""

import os
import re
from datetime import datetime

import requests

# پوشه‌ای که گزارش‌ها داخلش ذخیره می‌شوند
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "outputs")


# ---------------------------------------------------------------- ابزار ۱
def search_wikipedia(topic: str) -> dict:
    """خلاصه یک موضوع را از ویکی‌پدیا می‌گیرد (اول انگلیسی، بعد فارسی)."""
    for lang in ("en", "fa"):
        url = f"https://{lang}.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "prop": "extracts",
            "explaintext": 1,
            "redirects": 1,
            "titles": topic,
            "format": "json",
        }
        try:
            response = requests.get(
                url, params=params, timeout=10,
                headers={"User-Agent": "ResearcherChatbot/1.0 (learning project)"},
            )
            pages = response.json()["query"]["pages"]
            page = next(iter(pages.values()))
            extract = page.get("extract", "").strip()
            if extract:
                return {
                    "title": page.get("title", topic),
                    "summary": extract[:3000],  # خلاصه را کوتاه نگه می‌داریم
                    "source": f"https://{lang}.wikipedia.org/wiki/{page.get('title', topic)}",
                }
        except Exception:
            continue  # اگر یک زبان نشد، زبان بعدی را امتحان کن

    return {"error": f"برای موضوع «{topic}» در ویکی‌پدیا چیزی پیدا نشد."}


# ---------------------------------------------------------------- ابزار ۲
def save_research(title: str, content: str) -> dict:
    """گزارش را در یک فایل متنی داخل پوشه outputs/ ذخیره می‌کند."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # از عنوان، یک اسم فایل امن و خوانا می‌سازیم
    safe_title = re.sub(r"[^\w\- ]", "", title).strip().replace(" ", "_")[:50]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_title}_{timestamp}.md"
    filepath = os.path.join(OUTPUT_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n{content}\n")

    return {"saved": True, "filename": filename, "path": filepath}


# ------------------------------------------------------- تعریف ابزارها برای مدل
# این لیست همان چیزی است که به API داده می‌شود تا مدل ابزارها را بشناسد.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_wikipedia",
            "description": "درباره یک موضوع در ویکی‌پدیا تحقیق می‌کند و خلاصه آن را برمی‌گرداند.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "موضوعی که باید درباره‌اش تحقیق شود، مثلا: Artificial Intelligence",
                    }
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_research",
            "description": "گزارش نهایی تحقیق را در یک فایل ذخیره می‌کند.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "عنوان گزارش"},
                    "content": {"type": "string", "description": "متن کامل گزارش"},
                },
                "required": ["title", "content"],
            },
        },
    },
]

# اسم ابزار -> خود تابع؛ برای اجرا کردن tool call ای که مدل خواسته است
TOOL_FUNCTIONS = {
    "search_wikipedia": search_wikipedia,
    "save_research": save_research,
}
