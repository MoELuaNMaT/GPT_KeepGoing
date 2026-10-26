# -*- coding: utf-8 -*-
"""多语言与额度解析的单元测试。"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import i18n, ratelimit


def test_all_languages_have_same_keys():
    base = set(i18n.STRINGS["zh-CN"])
    for code, table in i18n.STRINGS.items():
        assert set(table) == base, code + " 键不一致: " + str(base ^ set(table))


def test_native_names_present_and_distinct():
    names = [i18n.LANG_NATIVE[c] for c in i18n.LANG_ORDER]
    assert len(set(names)) == len(names)
    assert names[0] == "简体中文" and "日本語" in names and "한국어" in names


def test_continue_text_is_localized_and_nonempty():
    seen = set()
    for code in i18n.LANG_ORDER:
        text = i18n.continue_text(code)
        assert text and isinstance(text, str)
        seen.add(text)
    # 中日韩英必须有明显不同的写法
    assert i18n.continue_text("zh-CN") == "继续"
    assert i18n.continue_text("en") == "Continue"
    assert i18n.continue_text("ja") == "続けて"


def test_unknown_language_falls_back():
    assert i18n.normalize("xx-YY") == i18n.DEFAULT_LANG
    assert i18n.normalize("en_US") == "en"
    assert i18n.normalize(None) == i18n.DEFAULT_LANG


def test_state_and_phase_text():
    assert i18n.state_text("zh-CN", "quota_exhausted") == "额度已用尽"
    assert i18n.state_text("en", "quota_exhausted") == "Quota exhausted"
    assert i18n.phase_text("en", "wait_reset") == "Waiting for the limit to reset"
    assert i18n.state_text("en", "unknown_code") == "unknown_code"


def test_missing_key_falls_back_to_default_language():
    assert i18n.t("en", "no_such_key_xyz") == "no_such_key_xyz"


def test_parse_record_computes_remaining():
    payload = {
        "limit_id": "codex",
        "primary": {"used_percent": 96.0, "window_minutes": 300, "resets_at": 1793014647},
        "secondary": {"used_percent": 15.0, "window_minutes": 10080, "resets_at": 1793601447},
        "credits": {"balance": "0"},
        "plan_type": "plus",
    }
    out = ratelimit.parse_record(payload, "2026-10-26T18:08:05+08:00")
    assert out["five_hour"]["remaining_percent"] == 4.0
    assert out["weekly"]["remaining_percent"] == 85.0
    assert out["five_hour"]["resets_at"].startswith("2026-10-26T19:37:27")
    assert out["plan_type"] == "plus"


def test_parse_record_rejects_empty():
    assert ratelimit.parse_record({}, None) is None
    assert ratelimit.parse_record({"primary": None}, None) is None


def _now():
    from datetime import datetime
    return datetime(2026, 10, 26, 23, 55).astimezone()


def test_parse_reset_cjk_with_year():
    from app.reader import parse_reset_time
    dt, text = parse_reset_time(
        "你已达到使用上限。升级套餐或充值额度以继续，或在 2026年10月27日 00:45后重试。", _now())
    assert dt is not None
    assert (dt.month, dt.day, dt.hour, dt.minute) == (10, 27, 0, 45)


def test_parse_reset_cjk_without_year():
    from app.reader import parse_reset_time
    dt, text = parse_reset_time(
        "添加额度或升级套餐，或等待使用量于 10月27日 0:45 重置", _now())
    assert dt is not None
    assert (dt.month, dt.day, dt.hour, dt.minute) == (10, 27, 0, 45)


def test_parse_reset_time_only_rolls_to_next_day():
    from app.reader import parse_reset_time
    dt, text = parse_reset_time("请在 19:37 后重试", _now())
    assert dt is not None
    assert dt.day == 27 and dt.hour == 19 and dt.minute == 37


def test_parse_reset_iso():
    from app.reader import parse_reset_time
    dt, text = parse_reset_time("2026-11-02 14:37 重置", _now())
    assert dt is not None
    assert (dt.month, dt.day, dt.hour) == (11, 2, 14)


def test_parse_reset_needs_hint_word():
    from app.reader import parse_reset_time
    dt, text = parse_reset_time("上下文用量 80%，当前时间 12:30", _now())
    assert dt is None


def run():
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print("PASS", name)
        except AssertionError as exc:
            failed += 1
            print("FAIL", name, exc)
        except Exception as exc:
            failed += 1
            print("ERROR", name, repr(exc))
    print("---")
    print("total", len(fns), "failed", failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
