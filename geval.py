"""داور G-Eval برای گزارش‌های ذخیره‌شده (LLM-as-a-judge).

روش G-Eval: به‌جای «یه نمره بده»، داور یک وظیفه مشخص، تعریف دقیق هر معیار و
«قدم‌های ارزیابی» از پیش‌ساخته‌شده می‌گیرد، ادعاهای جواب را با منابع تطبیق
می‌دهد و در یک فرم ثابت نمره‌های ۱ تا ۵ برمی‌گرداند. چون فرم و قدم‌ها ثابت‌اند،
نمره‌ها بین نوبت‌ها و نسخه‌ها (مثلاً قبل و بعد از Compression) قابل مقایسه‌اند.

نمره نهایی هر نوبت میانگین چهار معیار است. خروجی بد یا غیرقابل‌پارس، None
برمی‌گرداند تا نبودن داوری هرگز چت یا لاگ را خراب نکند.
"""

import json
import re

CRITERIA = {
    "relevance": "ارتباط با سؤال — جواب دقیقاً به همان چیزی جواب داده که کاربر خواسته؟",
    "grounding": "اتکا به منبع — ادعاهای جواب از منابع آمده‌اند، نه از هوا؟",
    "completeness": "کامل‌بودن — بخش مهمی از سؤال یا منابع جا نیفتاده؟",
    "clarity": "وضوح — ساختار و خواندن جواب روشن و مرتب است؟",
}

# قدم‌های ارزیابی (قلب G-Eval): داور پیش از نمره‌دادن باید همین مسیر را برود.
EVALUATION_STEPS = [
    "۱) سؤال کاربر و ادعاهای اصلی منابع را فهرست کن.",
    "۲) ادعاهای جواب را یک‌به‌یک استخراج کن.",
    "۳) هر ادعا را با منابع تطبیق بده؛ ادعای بدون پشتوانه، نمره «اتکا به منبع» را پایین می‌آورد.",
    "۴) بررسی کن جواب همه بخش‌های سؤال را پوشش داده یا نه (کامل‌بودن) و دقیقاً به سؤال جواب داده (ارتباط).",
    "۵) ساختار و خوانایی متن را جدا از درستی‌اش بسنج (وضوح)؛ لحن خوب نباید نمره بقیه معیارها را بالا ببرد.",
    "۶) برای هر معیار یک نمره صحیح ۱ تا ۵ بده: ۱=خیلی بد، ۲=ضعیف، ۳=متوسط، ۴=خوب، ۵=عالی.",
]

JUDGE_SYSTEM = (
    "تو یک داور سخت‌گیر و بی‌طرف برای ارزیابی کیفیت گزارش‌های تحقیقی هستی. "
    "فقط بر اساس سؤال، منابع و جوابی که می‌گیری نمره می‌دهی و هیچ ادعایی را بدون پشتوانه منبع قبول نمی‌کنی."
)


def build_judge_prompt(question: str, sources: list, answer: str) -> str:
    """پرامپت داور را از سؤال، منابع این نوبت و جواب نهایی می‌سازد."""
    sources_text = "\n\n".join(
        f"[منبع از ابزار {s.get('tool', '?')}]\n{s.get('content', '')}" for s in sources
    ) or "(منبعی ثبت نشده است)"
    criteria_text = "\n".join(f"- {key}: {desc}" for key, desc in CRITERIA.items())
    steps_text = "\n".join(EVALUATION_STEPS)
    return (
        "وظیفه: کیفیت این گزارش تحقیقی را با روش G-Eval ارزیابی کن.\n\n"
        f"## سؤال کاربر\n{question}\n\n"
        f"## منابع (خروجی ابزارها)\n{sources_text[:5000]}\n\n"
        f"## جواب نهایی بات\n{answer[:5000]}\n\n"
        f"## معیارها\n{criteria_text}\n\n"
        f"## قدم‌های ارزیابی (به همین ترتیب انجام بده)\n{steps_text}\n\n"
        "خروجی را فقط و فقط به صورت یک JSON برگردان، بدون هیچ متن اضافه‌ای:\n"
        '{"scores": {"relevance": 1-5, "grounding": 1-5, "completeness": 1-5, "clarity": 1-5}, '
        '"notes": "یک جمله کوتاه درباره مهم‌ترین نقطه قوت یا ضعف"}'
    )


def parse_judge_output(text: str):
    """خروجی داور را پارس و اعتبارسنجی می‌کند؛ نامعتبر یعنی None."""
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        raw_scores = data.get("scores") or {}
        scores = {}
        for key in CRITERIA:
            value = float(raw_scores[key])
            if not 1 <= value <= 5:
                return None
            scores[key] = value
    except (ValueError, TypeError, KeyError):
        return None
    overall = round(sum(scores.values()) / len(scores), 2)
    return {"scores": scores, "overall": overall, "notes": str(data.get("notes", ""))[:200]}


def judge(client, model: str, question: str, sources: list, answer: str):
    """داوری G-Eval یک نوبت؛ هر خطایی None برمی‌گرداند تا جریان اصلی آسیب نبیند."""
    if client is None or not answer.strip():
        return None
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": build_judge_prompt(question, sources, answer)},
            ],
            max_tokens=700,
        )
        return parse_judge_output(response.choices[0].message.content or "")
    except Exception:
        return None
