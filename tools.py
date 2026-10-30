"""
tools.py — ابزارهایی که مدل می‌تواند صدا بزند (Tool Calls)
===========================================================
هر ابزار = یک تابع ساده پایتون + یک توضیح (schema) برای مدل.
مدل خودش تصمیم می‌گیرد کی و با چه ورودی‌ای ابزار را صدا بزند.

سه ابزار داریم:
1. search_wikipedia : تحقیق دانشنامه‌ای درباره یک موضوع (بدون نیاز به API key)
2. search_web       : جستجو در کل وب با Tavily (برای اطلاعات تازه؛ نیازمند TAVILY_API_KEY)
3. save_research    : ذخیره گزارش نهایی در یک فایل داخل پوشه outputs/
"""

import os
import re
from datetime import datetime

import requests

# پوشه‌ای که گزارش‌ها داخلش ذخیره می‌شوند
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "outputs")

OPEN_WEATHER_KEY = os.getenv("OPEN_WEATHER_KEY", "")

def get_weather(city_name: str) -> dict:

    if not OPEN_WEATHER_KEY:
        return {"error": "کلید OpenWeather تنظیم نشده است (OPEN_WEATHER_KEY در .env خالی است)."}

    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city_name,           
        "appid": OPEN_WEATHER_KEY,
        "units": "metric",        
        "lang": "fa",            
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        return {"error": f"دریافت آب‌وهوا ناموفق بود: {exc}"}

    # فقط فیلدهایی که مدل برای جواب لازم دارد
    return {
        "city": data.get("name", city_name),
        "temperature": data["main"]["temp"],
        "feels_like": data["main"]["feels_like"],
        "humidity": data["main"]["humidity"],
        "description": data["weather"][0]["description"],
        "wind_speed": data["wind"]["speed"],
    }

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
def search_web(query: str, max_results: int = 5) -> dict:
    """در وب جستجو می‌کند (Tavily) و چند نتیجه با عنوان، لینک و متن برمی‌گرداند.

    برای اطلاعات تازه و روز مناسب است (اخبار، قیمت، آب‌وهوا، رویدادهای اخیر)
    و هر موضوعی که در ویکی‌پدیا نیست. کلید از متغیر TAVILY_API_KEY در .env خوانده می‌شود.
    """
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        return {"error": "کلید Tavily تنظیم نشده است (TAVILY_API_KEY در فایل .env خالی است)."}

    try:
        count = max(1, min(int(max_results), 10))
    except (TypeError, ValueError):
        count = 5

    try:
        response = requests.post(
            "https://api.tavily.com/search",
            json={"query": query, "max_results": count, "search_depth": "basic"},
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:  # شبکه، کلید نامعتبر، یا هر خطای دیگر
        return {"error": f"جستجوی وب ناموفق بود: {exc}"}

    results = []
    for item in data.get("results", [])[:count]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": (item.get("content") or "")[:800],  # هر نتیجه را کوتاه نگه می‌داریم
        })

    if not results:
        return {"error": f"برای «{query}» در وب نتیجه‌ای پیدا نشد."}

    return {"query": query, "results": results}


# ---------------------------------------------------------------- ابزار ۳
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
        "function" : {
            "name" : "get_weather", 
            "description" : "آب‌وهوای فعلی یک شهر را برمی‌گرداند. وقتی کاربر درباره آب‌وهوای امروز یک شهر می‌پرسد از این ابزار استفاده کن.",
            "parameters" : {
                "type" : 'object',
                "properties" : {
                    "city_name" : {
                        "type" : "string", 
                        "description" : "نام شهر به انگلیسی، مثلا: Tehran",
                    }
                },
                "required" : ["city_name"]
            },
        }
    },
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
            "name": "search_web",
            "description": "در کل وب جستجو می‌کند و چند نتیجه با عنوان، لینک و متن برمی‌گرداند. برای اطلاعات تازه و روز (اخبار، قیمت، آب‌وهوا، رویدادهای اخیر) یا موضوع‌هایی که در ویکی‌پدیا نیستند از این ابزار استفاده کن.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "عبارتی که باید در وب جستجو شود، مثلا: Tehran weather today",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "تعداد نتایج (اختیاری، پیش‌فرض ۵، حداکثر ۱۰)",
                    },
                },
                "required": ["query"],
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
    "get_weather" : get_weather,
    "search_wikipedia": search_wikipedia,
    "search_web": search_web,
    "save_research": save_research,
}
