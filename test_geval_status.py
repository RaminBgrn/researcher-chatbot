"""تست وضعیت داوری G-Eval: pending/error/done و دلیل خطا (بدون شبکه)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import eval_store
import geval

PASS = []


def check(name, cond):
    PASS.append((name, bool(cond)))
    print(("✅" if cond else "❌"), name)


class FakeMsg:
    def __init__(self, content):
        self.content = content


class FakeResp:
    def __init__(self, content):
        self.choices = [type("C", (), {"message": FakeMsg(content)})()]


def client_returning(content):
    class Comp:
        def create(self, **kwargs):
            return FakeResp(content)

    return type("K", (), {"chat": type("H", (), {"completions": Comp()})()})()


class RaisingComp:
    def create(self, **kwargs):
        raise RuntimeError("timeout 30s")


raising_client = type("K", (), {"chat": type("H", (), {"completions": RaisingComp()})()})()

# خروجی سالم → (result, None)
res, err = geval.judge_detailed(
    client_returning('{"scores": {"relevance": 5, "grounding": 4, "completeness": 4, "clarity": 5}, "notes": "ok"}'),
    "m", "سؤال", [], "جواب",
)
check("خروجی سالم: نتیجه بدون خطا", res is not None and res["overall"] == 4.5 and err is None)

# خروجی غیر JSON → خطای پارس با نمونه متن
res, err = geval.judge_detailed(client_returning("متأسفم نمی‌توانم نمره بدهم"), "m", "س", [], "جواب")
check("خروجی نامعتبر: خطا با دلیل", res is None and err and "JSON" in err)

# خطای API → خطای فراخوانی
res, err = geval.judge_detailed(raising_client, "m", "س", [], "جواب")
check("خطای API: دلیل ثبت می‌شود", res is None and err and "timeout" in err)

# بدون کلاینت
res, err = geval.judge_detailed(None, "m", "س", [], "جواب")
check("بدون کلاینت: خطا", res is None and err is not None)

# چرخه وضعیت در eval_store
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "eval.json")
    eval_store.append_record(
        {"id": "t1", "user": "س", "tools": [], "finish_reason": "stop",
         "used_tools": True, "saved": "r.txt", "total_tokens": 10},
        path=path,
    )
    check("pending ثبت می‌شود", eval_store.set_geval_status("t1", "pending", path=path))
    rec = eval_store.load_records(path)[0]
    check("وضعیت pending روی رکورد است", rec.get("geval_status") == "pending")
    check("error با دلیل ثبت می‌شود", eval_store.set_geval_status("t1", "error", "خروجی JSON نبود", path=path))
    rec = eval_store.load_records(path)[0]
    check("وضعیت error + متن دلیل", rec.get("geval_status") == "error" and rec.get("geval_error") == "خروجی JSON نبود")
    check("set_geval وضعیت را done می‌کند", eval_store.set_geval("t1", {"scores": {}, "overall": 4.0, "notes": ""}, path=path))
    rec = eval_store.load_records(path)[0]
    check("done و پاک‌شدن خطا", rec.get("geval_status") == "done" and "geval_error" not in rec)
    check("وضعیت نامعتبر رد می‌شود", not eval_store.set_geval_status("t1", "weird", path=path))

failed = [n for n, ok in PASS if not ok]
print(f"\n{len(PASS) - len(failed)}/{len(PASS)} چک پاس شد")
sys.exit(1 if failed else 0)
