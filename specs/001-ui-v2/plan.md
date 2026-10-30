# Implementation Plan: UI v2

**Spec**: `spec.md` همین پوشه — **Constitution Check**: سادگی ✓ (بدون وابستگی تازه، بدون دیتابیس)، جدایی سه مفهوم ✓ (فقط app.py و یک متد کمکی در chatbot.py عوض می‌شود)، راز در گیت نیست ✓، تست قبل از اتمام ✓.

## Technical Context

- بک‌اند: همان Flask فعلی. فرانت: همان HTML/CSS/JS خالص.
- ذخیره گفتگوها: دیکشنری در حافظه سرور (`{id: ChatSession}`) — عمداً ساده و آموزشی، مثل هیستوری فعلی.

## Data Model

```
ChatSession
  id: str (uuid4 hex کوتاه)
  title: str  (از اولین پیام کاربر، حداکثر ~۳۰ کاراکتر؛ پیش‌فرض «گفتگوی جدید»)
  created_at: str (ISO)
  bot: ResearcherChatbot  (هیستوری داخل خودش است)
```

متد کمکی روی chatbot: ‏`visible_messages()` فقط پیام‌های user و پاسخ نهایی assistant را از هیستوری برمی‌گرداند (بدون system و tool).

## Contracts (API)

| Method | Path | کار |
|---|---|---|
| GET | `/api/chats` | فهرست گفتگوها: id, title, created_at, message_count |
| POST | `/api/chats` | ساخت گفتگوی تازه |
| GET | `/api/chats/<id>` | پیام‌های قابل نمایش یک گفتگو |
| POST | `/api/chats/<id>/message` | ارسال پیام `{message}` ← `{reply, chat}` |
| DELETE | `/api/chats/<id>` | حذف گفتگو |
| POST | `/api/chat`, `/api/clear` | قبلی‌ها، روی گفتگوی پیش‌فرض (`default`) |

## Frontend Architecture (بر اساس پاس Agency)

- **توکن‌ها (UI Designer)**: رنگ‌های معنایی (`--bg`, `--surface`, `--text`, `--muted`, `--border`, `--accent`, `--accent-2`)، مقیاس فاصله 4/8/12/16/24، شعاع و سایه؛ تم روشن با `[data-theme="light"]` و حالت سیستم با `prefers-color-scheme` روی `:root` بدون ویژگی.
- **چیدمان (UX Architect)**: ‏Grid دو ستونه (سایدبار 300px + اصلی) در دسکتاپ؛ در ≤860px سایدبار Drawer ثابت با Overlay؛ سوییچ تم سه‌حالته در هدر؛ ThemeManager کوچک با localStorage و try/catch.
- **حالت‌ها**: فوکوس قابل مشاهده (`:focus-visible`)، دکمه‌ها حداقل 44px، حالت خالی برای فهرست و گفتگو، حالت «در حال تحقیق» مثل قبل.

## Verification

1. کامپایل پایتون.
2. تست‌کلاینت Flask: ساخت/فهرست/ارسال (بدون کلید ← پاسخ خطای واضح ولی ذخیره‌شده در همان گفتگو)/خواندن پیام‌ها/حذف + سازگاری API قبلی.
3. وجود اجزای فرانت در HTML (سایدبار، سوییچ تم، همبرگری) و توکن‌های تم در CSS.
