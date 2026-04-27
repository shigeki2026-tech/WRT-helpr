# -*- coding: utf-8 -*-
"""
tests/test_decision_rules.py
4-layer CSV pipeline decision tests.

pytest (recommended):
    python -m pytest tests/test_decision_rules.py -v

Standalone:
    python tests/test_decision_rules.py
"""

import sys
import os

# Add project root to path so `import app` works from any working directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock streamlit so app.py can be imported without a running Streamlit server.
# st.cache_data is replaced with a pass-through lambda so decorated functions
# behave like plain functions in tests.
import unittest.mock as mock

_st_mock = mock.MagicMock()
_st_mock.cache_data = lambda f: f
sys.modules["streamlit"] = _st_mock

import app  # noqa: E402  (must come after sys.modules patch)

# ============================================================
# Helpers
# ============================================================

def make_form(
    product="", series="", manufacturer="", model_number="",
    prefecture="", case_type="", appliance_type="",
    extra_condition="", store_name="",
):
    """Build a minimal form dict for run_decision()."""
    form = app.empty_form()
    form.update(
        product=product,
        series=series,
        manufacturer=manufacturer,
        model_number=model_number,
        prefecture=prefecture,
        case_type=case_type,
        appliance_type=appliance_type,
        extra_condition=extra_condition,
        store_name=store_name,
    )
    return form


# Standalone runner accumulates results here.
# check() appends BEFORE asserting, so even when an assertion fails the entry
# is already recorded and the standalone summary stays complete.
_results: list = []


def check(label: str, actual, expected, *, contains: bool = False) -> None:
    """
    Assert that `actual` equals (or contains) `expected`.

    - Records the outcome in _results for the standalone summary.
    - Raises AssertionError on mismatch so pytest detects the failure.
    """
    if contains:
        ok = expected in str(actual)
    else:
        ok = actual == expected

    status = "PASS" if ok else "FAIL"
    _results.append((status, label, actual, expected))

    assert ok, (
        f"\n  Label   : {label}"
        f"\n  Expected: {expected!r}"
        f"\n  Actual  : {actual!r}"
    )


# ============================================================
# TC01: ドライヤー・ヘアアイロン → alias normalisation
# ============================================================

def test_tc01_dryer_alias():
    d = app.run_decision(make_form(series="ドライヤー・ヘアアイロン"))
    check("TC01 製品正規化 → ドライヤー",            d["normalized_product"], "ドライヤー")
    check("TC01 修理形態 → 持込修理",                d["repair_type"],        "持込修理")
    check("TC01 概算費用 → 2,000円～5,000円前後",    d["cost_estimate"],      "2,000円～5,000円前後")


# ============================================================
# TC02: 洗濯機 → 出張修理
# ============================================================

def test_tc02_washer():
    d = app.run_decision(make_form(product="洗濯機"))
    check("TC02 修理形態 → 出張修理",                d["repair_type"],   "出張修理")
    check("TC02 概算費用 → 5,000円～7,000円前後",    d["cost_estimate"], "5,000円～7,000円前後")


# ============================================================
# TC03: エレクトロラックス × 洗濯機 → 45,000円前後 / escalation あり
# ============================================================

def test_tc03_electrolux_washer():
    d = app.run_decision(make_form(product="洗濯機", manufacturer="エレクトロラックス"))
    check("TC03 修理形態 → 出張修理",                d["repair_type"],                     "出張修理")
    check("TC03 概算費用 → 45,000円前後",            d["cost_estimate"],                   "45,000円前後")
    check("TC03 escalation あり",                    d["cost_result"]["needs_escalation"], True)


# ============================================================
# TC04: ダイキン家庭用エアコン → 出張修理 / 7,000円～16,000円前後
# ============================================================

def test_tc04_daikin_ac():
    d = app.run_decision(make_form(product="エアコン", manufacturer="ダイキン"))
    check("TC04 修理形態 → 出張修理",                d["repair_type"],   "出張修理")
    check("TC04 概算費用 → 7,000円～16,000円前後",   d["cost_estimate"], "7,000円～16,000円前後")


# ============================================================
# TC05: パソコン × 国内メーカー（富士通）→ 2,000円～9,000円
# ============================================================

def test_tc05_domestic_pc():
    d = app.run_decision(make_form(product="パソコン", manufacturer="富士通"))
    check("TC05 修理形態 → 持込修理",                d["repair_type"],   "持込修理")
    check("TC05 概算費用 → 2,000円～9,000円",        d["cost_estimate"], "2,000円～9,000円")


# ============================================================
# TC06: パソコン × 海外メーカー → 12,000円前後
# ============================================================

def test_tc06_foreign_pc():
    d = app.run_decision(make_form(product="パソコン", manufacturer="Dell"))
    check("TC06 修理形態 → 持込修理",                d["repair_type"],   "持込修理")
    check("TC06 概算費用 → 12,000円前後",            d["cost_estimate"], "12,000円前後")


# ============================================================
# TC07: 滋賀県 × 洗濯機 → ユナイトサービス㈱
# ============================================================

def test_tc07_shiga_washer():
    d = app.run_decision(make_form(product="洗濯機", prefecture="滋賀県"))
    check("TC07 修理拠点 → ユナイトサービス㈱",      d["vendor"], "ユナイトサービス㈱")


# ============================================================
# TC08: 東京都 × 洗濯機 → WRT修理センター
# ============================================================

def test_tc08_tokyo_washer():
    d = app.run_decision(make_form(product="洗濯機", prefecture="東京都"))
    check("TC08 修理拠点 → WRT修理センター",         d["vendor"], "WRT修理センター")


# ============================================================
# TC09: 沖縄県 → 宗建リノベーション
# ============================================================

def test_tc09_okinawa():
    d = app.run_decision(make_form(prefecture="沖縄県"))
    check("TC09 修理拠点 → 宗建リノベーション",      d["vendor"], "宗建リノベーション")


# ============================================================
# TC10: ビックカメラ案件 → ソフマップ修理センター / 金額案内不可
# ============================================================

def test_tc10_bic_camera():
    d = app.run_decision(make_form(case_type="ビックカメラ案件"))
    check("TC10 修理拠点 → ソフマップ修理センター",  d["vendor"], "ソフマップ修理センター")
    check("TC10 金額案内不可",
          d["script_result"]["price_guidance_allowed"], False)


# ============================================================
# Standalone runner
# ============================================================

_ALL_TESTS = [
    test_tc01_dryer_alias,
    test_tc02_washer,
    test_tc03_electrolux_washer,
    test_tc04_daikin_ac,
    test_tc05_domestic_pc,
    test_tc06_foreign_pc,
    test_tc07_shiga_washer,
    test_tc08_tokyo_washer,
    test_tc09_okinawa,
    test_tc10_bic_camera,
]

if __name__ == "__main__":
    # Run every test function; catch AssertionError so the summary is always
    # printed even when some checks fail.
    for fn in _ALL_TESTS:
        try:
            fn()
        except AssertionError:
            pass  # result already appended to _results by check()

    total  = len(_results)
    passed = sum(1 for r in _results if r[0] == "PASS")
    failed = total - passed

    print(f"\n{'='*60}")
    print(f"Test result: {passed}/{total} PASS  ({failed} FAIL)")
    print(f"{'='*60}")
    for status, label, actual, expected in _results:
        mark = "OK" if status == "PASS" else "NG"
        print(f"  [{mark}] {label}")
        if status == "FAIL":
            print(f"       expected : {expected!r}")
            print(f"       actual   : {actual!r}")
    print()

    if failed:
        sys.exit(1)
