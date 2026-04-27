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
from datetime import date

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
    extra_condition="", store_name="", warranty_start_date="", warranty_end_date="",
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
        warranty_start_date=warranty_start_date,
        warranty_end_date=warranty_end_date,
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
# ※ extra_condition="家庭用" 指定が必要（未指定は pending になる）
# ============================================================

def test_tc04_daikin_ac():
    d = app.run_decision(make_form(product="エアコン", manufacturer="ダイキン",
                                   extra_condition="家庭用"))
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
# TC11: エアコンのみ入力 → 金額未確定 / メーカー確認要求
# ============================================================

def test_tc11_ac_no_manufacturer():
    d = app.run_decision(make_form(product="エアコン"))
    check("TC11 cost_status → pending",         d["cost_result"]["cost_status"],        "pending")
    check("TC11 cost_estimate → 未確定",         d["cost_estimate"],                     "未確定")
    check("TC11 required_questions 非空",        bool(d["cost_result"]["required_questions"]), True)


# ============================================================
# TC12: エアコン + ダイキンのみ → 金額未確定 / 家庭用・業務用確認要求
# ============================================================

def test_tc12_ac_daikin_no_type():
    d = app.run_decision(make_form(product="エアコン", manufacturer="ダイキン"))
    check("TC12 cost_status → pending",         d["cost_result"]["cost_status"],        "pending")
    check("TC12 cost_estimate → 未確定",         d["cost_estimate"],                     "未確定")
    rq = d["cost_result"]["required_questions"]
    check("TC12 required_questions 含む '業務用'", "業務用" in rq, True)


# ============================================================
# TC13: エアコン + ダイキン + 家庭用 → 7,000円～16,000円前後
# ============================================================

def test_tc13_ac_daikin_katei():
    d = app.run_decision(make_form(product="エアコン", manufacturer="ダイキン",
                                   extra_condition="家庭用"))
    check("TC13 修理形態 → 出張修理",             d["repair_type"],   "出張修理")
    check("TC13 概算費用 → 7,000円～16,000円前後", d["cost_estimate"], "7,000円～16,000円前後")
    check("TC13 cost_status → confirmed",         d["cost_result"]["cost_status"], "confirmed")


# ============================================================
# TC14: エアコン + ダイキン + 業務用 → 15,000円～22,000円前後
# ============================================================

def test_tc14_ac_daikin_gyomu():
    d = app.run_decision(make_form(product="エアコン", manufacturer="ダイキン",
                                   extra_condition="業務用"))
    check("TC14 修理形態 → 出張修理",              d["repair_type"],   "出張修理")
    check("TC14 概算費用 → 15,000円～22,000円前後", d["cost_estimate"], "15,000円～22,000円前後")
    check("TC14 cost_status → confirmed",          d["cost_result"]["cost_status"], "confirmed")


# ============================================================
# TC15: パソコンのみ入力 → 金額未確定 / メーカー確認要求
# ============================================================

def test_tc15_pc_no_manufacturer():
    d = app.run_decision(make_form(product="パソコン"))
    check("TC15 cost_status → pending",         d["cost_result"]["cost_status"], "pending")
    check("TC15 cost_estimate → 未確定",         d["cost_estimate"],              "未確定")
    check("TC15 required_questions 非空",        bool(d["cost_result"]["required_questions"]), True)


# ============================================================
# TC16: パソコン + 富士通 → 2,000円～9,000円
# ============================================================

def test_tc16_pc_fujitsu():
    d = app.run_decision(make_form(product="パソコン", manufacturer="富士通"))
    check("TC16 修理形態 → 持込修理",            d["repair_type"],   "持込修理")
    check("TC16 概算費用 → 2,000円～9,000円",     d["cost_estimate"], "2,000円～9,000円")


# ============================================================
# TC17: パソコン + Dell → 12,000円前後
# ============================================================

def test_tc17_pc_dell():
    d = app.run_decision(make_form(product="パソコン", manufacturer="Dell"))
    check("TC17 修理形態 → 持込修理",            d["repair_type"],   "持込修理")
    check("TC17 概算費用 → 12,000円前後",         d["cost_estimate"], "12,000円前後")


# ============================================================
# TC18: 販売店名に「ビックカメラ」→ case_type 自動推定
# ============================================================

def test_tc18_bic_store_infer():
    d = app.run_decision(make_form(store_name="ビックカメラ新宿店"))
    check("TC18 case_type自動推定 → ビックカメラ案件",
          d["inferred_case_type"], "ビックカメラ案件")
    # case_type が自動設定されるため vendor もソフマップになる
    check("TC18 vendor → ソフマップ修理センター",
          d["vendor"], "ソフマップ修理センター")


# ============================================================
# TC19: 販売店名に「ソフマップ」→ case_type 自動推定
# ============================================================

def test_tc19_sofmap_store_infer():
    d = app.run_decision(make_form(store_name="ソフマップAkiba"))
    check("TC19 case_type自動推定 → ソフマップ案件",
          d["inferred_case_type"], "ソフマップ案件")
    check("TC19 vendor → ソフマップ修理センター",
          d["vendor"], "ソフマップ修理センター")


# ============================================================
# TC20: 滋賀県 → NTT西日本 / TC21: 東京都 → NTT東日本
# ============================================================

def test_tc20_shiga_ntt_west():
    d = app.run_decision(make_form(prefecture="滋賀県"))
    check("TC20 滋賀県 → area_group=NTT西日本", d["area_group"], "NTT西日本")


def test_tc21_tokyo_ntt_east():
    d = app.run_decision(make_form(prefecture="東京都"))
    check("TC21 東京都 → area_group=NTT東日本", d["area_group"], "NTT東日本")


def test_tc22_blank_prefecture_no_area_group():
    d = app.run_decision(make_form(prefecture=""))
    check("TC22 都道府県未選択 → area_group空", d["area_group"], "")


def test_tc23_extract_prefecture_shiga_from_address():
    check("TC23 住所から滋賀県を抽出",
          app.extract_prefecture("滋賀県大津市浜大津1-1-1"), "滋賀県")


def test_tc24_extract_prefecture_tokyo_from_address():
    check("TC24 住所から東京都を抽出",
          app.extract_prefecture("東京都新宿区西新宿1-1-1"), "東京都")


def test_tc25_ac_only_pending_repair_type_visit():
    d = app.run_decision(make_form(product="エアコン"))
    check("TC25 エアコンのみ → 出張修理", d["repair_type"], "出張修理")
    check("TC25 エアコンのみ → pending", d["cost_result"]["cost_status"], "pending")
    check("TC25 エアコンのみ → 未確定", d["cost_estimate"], "未確定")
    check("TC25 エアコンのみ → 金額案内不可", d["cost_result"]["can_announce_cost"], False)
    check("TC25 エアコンのみ → メーカー確認", d["cost_result"]["required_questions"], "メーカーを確認してください")


def test_tc26_ac_daikin_only_pending_type_question():
    d = app.run_decision(make_form(product="エアコン", manufacturer="ダイキン"))
    check("TC26 エアコン+ダイキンのみ → pending", d["cost_result"]["cost_status"], "pending")
    check("TC26 エアコン+ダイキンのみ → 未確定", d["cost_estimate"], "未確定")
    check("TC26 家庭用/業務用確認", d["cost_result"]["required_questions"], "家庭用/業務用を確認してください")


def test_tc27_ac_daikin_home():
    d = app.run_decision(make_form(product="エアコン", manufacturer="ダイキン", extra_condition="家庭用"))
    check("TC27 ダイキン家庭用 → 7,000円～16,000円前後", d["cost_estimate"], "7,000円～16,000円前後")
    check("TC27 ダイキン家庭用 → confirmed", d["cost_result"]["cost_status"], "confirmed")


def test_tc28_ac_daikin_business():
    d = app.run_decision(make_form(product="エアコン", manufacturer="ダイキン", extra_condition="業務用"))
    check("TC28 ダイキン業務用 → 15,000円～22,000円前後", d["cost_estimate"], "15,000円～22,000円前後")
    check("TC28 ダイキン業務用 → confirmed", d["cost_result"]["cost_status"], "confirmed")


def test_tc29_ac_daikin_gas_leak():
    d = app.run_decision(make_form(product="エアコン", manufacturer="ダイキン", extra_condition="ガス漏れ"))
    check("TC29 ダイキンガス漏れ → 30,000円前後", d["cost_estimate"], "30,000円前後")
    check("TC29 ダイキンガス漏れ → eu_asked_only", d["cost_result"]["guidance_scope"], "eu_asked_only")


def test_tc30_ac_iris():
    d = app.run_decision(make_form(product="エアコン", manufacturer="アイリスオーヤマ"))
    check("TC30 アイリスオーヤマ → 15,000円前後", d["cost_estimate"], "15,000円前後")


def test_tc31_ac_hitachi_domestic_generic():
    d = app.run_decision(make_form(product="エアコン", manufacturer="日立"))
    check("TC31 日立 → 5,000円～7,000円前後", d["cost_estimate"], "5,000円～7,000円前後")
    check("TC31 日立 → confirmed", d["cost_result"]["cost_status"], "confirmed")


def test_tc32_ac_panasonic_domestic_generic():
    d = app.run_decision(make_form(product="エアコン", manufacturer="パナソニック"))
    check("TC32 パナソニック → 5,000円～7,000円前後", d["cost_estimate"], "5,000円～7,000円前後")
    check("TC32 パナソニック → confirmed", d["cost_result"]["cost_status"], "confirmed")


def test_tc33_ac_unknown_maker_not_confirmed():
    d = app.run_decision(make_form(product="エアコン", manufacturer="不明メーカー"))
    check("TC33 不明メーカー → pending", d["cost_result"]["cost_status"], "pending")
    check("TC33 不明メーカー → 未確定", d["cost_estimate"], "未確定")
    check("TC33 不明メーカー → 国内汎用金額を確定表示しない",
          d["cost_estimate"] != "5,000円～7,000円前後", True)


def test_tc34_ac_only_never_falls_back_to_generic_visit_cost():
    d = app.run_decision(make_form(product="エアコン"))
    check("TC34 エアコンのみ → 出張修理", d["repair_type"], "出張修理")
    check("TC34 エアコンのみ → 未確定", d["cost_estimate"], "未確定")
    check("TC34 エアコンのみ → pending", d["cost_result"]["cost_status"], "pending")
    check("TC34 エアコンのみ → 金額案内不可", d["cost_result"]["can_announce_cost"], False)
    check("TC34 エアコンのみ → メーカー確認", d["cost_result"]["required_questions"], "メーカーを確認してください")
    check("TC34 エアコンのみ → 汎用出張費用を返さない",
          d["cost_estimate"] != "5,000円～7,000円前後", True)


def test_tc35_pc_only_never_falls_back_to_pc_cost():
    d = app.run_decision(make_form(product="パソコン"))
    check("TC35 パソコンのみ → 未確定", d["cost_estimate"], "未確定")
    check("TC35 パソコンのみ → 金額案内不可", d["cost_result"]["can_announce_cost"], False)


def test_tc36_product_options_from_repair_type_rules():
    options = app.get_product_options()
    check("TC36 product options 生成あり", bool(options), True)
    for product in ["エアコン", "洗濯機", "ドライヤー", "パソコン"]:
        check(f"TC36 product options に {product} を含む", product in options, True)


def test_tc37_series_dryer_alias_reflects_product_select():
    form = app.apply_extracted_fields_to_form(
        {"series": "ドライヤー・ヘアアイロン"},
        make_form(),
    )
    check("TC37 ドライヤー・ヘアアイロン → ドライヤー", form["product"], "ドライヤー")
    check("TC37 原文製品名を保持", form["product_original"], "ドライヤー・ヘアアイロン")


def test_tc38_warranty_before_start():
    r = app.determine_warranty_status(
        make_form(warranty_start_date="2026/05/01", warranty_end_date="2031/04/30"),
        today=date(2026, 4, 27),
    )
    check("TC38 warranty before_start", r["warranty_status"], "before_start")
    check("TC38 can_accept False", r["can_accept"], False)


def test_tc39_warranty_active():
    r = app.determine_warranty_status(
        make_form(warranty_start_date="2026/01/01", warranty_end_date="2030/12/31"),
        today=date(2026, 4, 27),
    )
    check("TC39 warranty active", r["warranty_status"], "active")
    check("TC39 can_accept True", r["can_accept"], True)


def test_tc40_warranty_expired():
    r = app.determine_warranty_status(
        make_form(warranty_start_date="2020/01/01", warranty_end_date="2026/04/26"),
        today=date(2026, 4, 27),
    )
    check("TC40 warranty expired", r["warranty_status"], "expired")
    check("TC40 can_accept False", r["can_accept"], False)


def test_tc41_warranty_unknown_start_blank():
    r = app.determine_warranty_status(
        make_form(warranty_start_date="", warranty_end_date="2031/04/30"),
        today=date(2026, 4, 27),
    )
    check("TC41 start空欄 → unknown", r["warranty_status"], "unknown")
    check("TC41 can_accept False", r["can_accept"], False)


def test_tc42_warranty_unknown_end_blank():
    r = app.determine_warranty_status(
        make_form(warranty_start_date="2026/01/01", warranty_end_date=""),
        today=date(2026, 4, 27),
    )
    check("TC42 end空欄 → unknown", r["warranty_status"], "unknown")
    check("TC42 can_accept False", r["can_accept"], False)


def test_tc43_warranty_hyphen_date_active():
    r = app.determine_warranty_status(
        make_form(warranty_start_date="2026-01-01", warranty_end_date="2030-12-31"),
        today=date(2026, 4, 27),
    )
    check("TC43 YYYY-MM-DD → active", r["warranty_status"], "active")


def test_tc44_warranty_japanese_date_active():
    r = app.determine_warranty_status(
        make_form(warranty_start_date="2026年01月01日", warranty_end_date="2030年12月31日"),
        today=date(2026, 4, 27),
    )
    check("TC44 YYYY年MM月DD日 → active", r["warranty_status"], "active")


def test_tc45_run_decision_includes_warranty_result():
    d = app.run_decision(make_form(warranty_start_date="2026/01/01", warranty_end_date="2030/12/31"))
    check("TC45 warranty_resultあり", "warranty_result" in d, True)
    check("TC45 warranty_statusあり", "warranty_status" in d, True)
    check("TC45 can_acceptあり", "can_accept" in d, True)


def test_tc46_expired_keeps_acceptance_priority_even_when_cost_exists():
    d = app.run_decision(make_form(
        product="洗濯機",
        warranty_start_date="2020/01/01",
        warranty_end_date="2026/04/26",
    ))
    check("TC46 expired", d["warranty_status"], "expired")
    check("TC46 can_accept False", d["can_accept"], False)
    check("TC46 cost can still be calculated behind the scenes", d["cost_estimate"], "5,000円～7,000円前後")
    check("TC46 guidance is受付不可", app.build_warranty_guidance(d["warranty_result"]), "保証期間終了のため受付不可")


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
    test_tc11_ac_no_manufacturer,
    test_tc12_ac_daikin_no_type,
    test_tc13_ac_daikin_katei,
    test_tc14_ac_daikin_gyomu,
    test_tc15_pc_no_manufacturer,
    test_tc16_pc_fujitsu,
    test_tc17_pc_dell,
    test_tc18_bic_store_infer,
    test_tc19_sofmap_store_infer,
    test_tc20_shiga_ntt_west,
    test_tc21_tokyo_ntt_east,
    test_tc22_blank_prefecture_no_area_group,
    test_tc23_extract_prefecture_shiga_from_address,
    test_tc24_extract_prefecture_tokyo_from_address,
    test_tc25_ac_only_pending_repair_type_visit,
    test_tc26_ac_daikin_only_pending_type_question,
    test_tc27_ac_daikin_home,
    test_tc28_ac_daikin_business,
    test_tc29_ac_daikin_gas_leak,
    test_tc30_ac_iris,
    test_tc31_ac_hitachi_domestic_generic,
    test_tc32_ac_panasonic_domestic_generic,
    test_tc33_ac_unknown_maker_not_confirmed,
    test_tc34_ac_only_never_falls_back_to_generic_visit_cost,
    test_tc35_pc_only_never_falls_back_to_pc_cost,
    test_tc36_product_options_from_repair_type_rules,
    test_tc37_series_dryer_alias_reflects_product_select,
    test_tc38_warranty_before_start,
    test_tc39_warranty_active,
    test_tc40_warranty_expired,
    test_tc41_warranty_unknown_start_blank,
    test_tc42_warranty_unknown_end_blank,
    test_tc43_warranty_hyphen_date_active,
    test_tc44_warranty_japanese_date_active,
    test_tc45_run_decision_includes_warranty_result,
    test_tc46_expired_keeps_acceptance_priority_even_when_cost_exists,
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
