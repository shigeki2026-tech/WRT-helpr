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
import re
from datetime import date, datetime

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
    prefecture="", call_line="", appliance_type="",
    extra_condition="", store_name="", warranty_start_date="", warranty_end_date="",
    is_over_10years=False, manufacturer_original="", pc_manufacturer_type="",
):
    """Build a minimal form dict for run_decision()."""
    form = app.empty_form()
    form.update(
        product=product,
        series=series,
        manufacturer=manufacturer,
        model_number=model_number,
        prefecture=prefecture,
        call_line=call_line,
        appliance_type=appliance_type,
        extra_condition=extra_condition,
        store_name=store_name,
        warranty_start_date=warranty_start_date,
        warranty_end_date=warranty_end_date,
        is_over_10years=is_over_10years,
        manufacturer_original=manufacturer_original,
        pc_manufacturer_type=pc_manufacturer_type,
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
    d = app.run_decision(make_form(call_line="ビックカメラ"))
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


def test_tc17b_pc_lenovo_original_infers_foreign_and_clears_question():
    form = app.apply_extracted_fields_to_form(
        {
            "series": "タブレットPC",
            "manufacturer": "Lenovo（レノボ・ジャパン）",
        },
        app.empty_form(),
    )
    d = app.run_decision(form)
    rq = d["cost_result"].get("required_questions", "")

    check("TC17b product → パソコン", form["product"], "パソコン")
    check("TC17b PCメーカー区分 → 海外メーカー", form["pc_manufacturer_type"], "海外メーカー")
    check("TC17b 概算費用 → 12,000円前後", d["cost_estimate"], "12,000円前後")
    check("TC17b 確認項目に国内/海外確認が残らない", "国内メーカー/海外メーカーを確認してください" in rq, False)


def test_tc17c_pc_type_domestic_overrides_unknown_select_manufacturer():
    d = app.run_decision(make_form(
        product="パソコン",
        manufacturer=app.MANUFACTURER_OTHER,
        pc_manufacturer_type="国内メーカー",
    ))

    check("TC17c 国内PC区分 → 2,000円～9,000円", d["cost_estimate"], "2,000円～9,000円")
    check("TC17c cost_status → confirmed", d["cost_result"]["cost_status"], "confirmed")


def test_tc17d_pc_unknown_type_requires_confirmation():
    d = app.run_decision(make_form(
        product="パソコン",
        manufacturer=app.MANUFACTURER_OTHER,
        manufacturer_original="謎メーカー",
    ))

    check("TC17d PCメーカー区分 → 未確認", d["working_form"]["pc_manufacturer_type"], "未確認")
    check("TC17d cost_status → pending", d["cost_result"]["cost_status"], "pending")
    check("TC17d 国内/海外確認あり",
          "国内メーカー/海外メーカーを確認してください" in d["cost_result"]["required_questions"], True)


def test_tc17e_watch_quartz_and_casio_are_normalized_with_specific_confirmation():
    form = app.apply_extracted_fields_to_form(
        {
            "series": "腕時計（クォーツ）",
            "manufacturer": "CASIO（カシオ計算機）",
            "model_number": "WVA-M630D-7A2JF",
        },
        app.empty_form(),
    )
    d = app.run_decision(form)
    qs = app.build_required_questions(form, d["repair_type"], d["needs_data_erase"])
    q_text = "\n".join(qs)
    repair_reason = next(
        item["reason"] for item in d["diagnostics"]["items"]
        if item["area"] == "修理形態判定"
    )

    check("TC17e 製品 → 腕時計", form["product"], "腕時計")
    check("TC17e 製品原文保持", form["product_original"], "腕時計（クォーツ）")
    check("TC17e メーカー → CASIO", form["manufacturer"], "CASIO")
    check("TC17e メーカー原文保持", form["manufacturer_original"], "CASIO（カシオ計算機）")
    check("TC17e 型番保持", form["model_number"], "WVA-M630D-7A2JF")
    check("TC17e 修理形態 → 要確認", d["repair_type"], "要確認")
    check("TC17e 腕時計理由", "腕時計ルール未登録 / 担当確認" in repair_reason, True)
    check("TC17e 確認項目 型番なし", "型番" in q_text, False)
    check("TC17e 確認項目 汎用メーカーなし", "\nメーカー\n" in f"\n{q_text}\n", False)
    check("TC17e 確認項目 製品分類", "製品分類が腕時計でよいか" in q_text, True)
    check("TC17e 確認項目 CASIO", "メーカーがCASIOでよいか" in q_text, True)
    check("TC17e 確認項目 スクリプトURL", "スクリプトURL未登録のため手動参照" in q_text, True)


# ============================================================
# TC18: 販売店名に「ビックカメラ」→ 回線属性推定
# ============================================================

def test_tc18_bic_store_infer():
    d = app.run_decision(make_form(store_name="ビックカメラ新宿店"))
    check("TC18 ビック/ソフマップ属性 → True",
          d["inferred_call_line_attrs"]["is_bic_sofmap"], True)
    # store_name からビック/ソフマップ属性が立つため vendor もソフマップになる
    check("TC18 vendor → ソフマップ修理センター",
          d["vendor"], "ソフマップ修理センター")


# ============================================================
# TC19: 販売店名に「ソフマップ」→ 回線属性推定
# ============================================================

def test_tc19_sofmap_store_infer():
    d = app.run_decision(make_form(store_name="ソフマップAkiba"))
    check("TC19 ビック/ソフマップ属性 → True",
          d["inferred_call_line_attrs"]["is_bic_sofmap"], True)
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


def test_tc47_extract_warranty_dates_slash():
    ext = app.extract_fields_from_pasted_text("保証開始日 2026/05/01\n保証終了日 2031/04/30")
    check("TC47 slash start", ext.get("warranty_start_date"), "2026/05/01")
    check("TC47 slash end", ext.get("warranty_end_date"), "2031/04/30")


def test_tc48_extract_warranty_dates_hyphen():
    ext = app.extract_fields_from_pasted_text("保証開始日 2026-05-01\n保証終了日 2031-04-30")
    check("TC48 hyphen start normalized", ext.get("warranty_start_date"), "2026/05/01")
    check("TC48 hyphen end normalized", ext.get("warranty_end_date"), "2031/04/30")


def test_tc49_extract_warranty_dates_japanese():
    ext = app.extract_fields_from_pasted_text("保証開始日 2026年5月1日\n保証終了日 2031年4月30日")
    check("TC49 japanese start normalized", ext.get("warranty_start_date"), "2026/05/01")
    check("TC49 japanese end normalized", ext.get("warranty_end_date"), "2031/04/30")


def test_tc50_normalize_date_text():
    check("TC50 hyphen normalize", app.normalize_date_text("2026-05-01"), "2026/05/01")
    check("TC50 japanese normalize", app.normalize_date_text("2026年5月1日"), "2026/05/01")


def test_tc51_warranty_guidance_before_start_contains_destination():
    r = app.determine_warranty_status(
        make_form(warranty_start_date="2026/05/01", warranty_end_date="2031/04/30"),
        today=date(2026, 4, 27),
    )
    check("TC51 before_start", r["warranty_status"], "before_start")
    check("TC51 can_accept False", r["can_accept"], False)
    check("TC51 guidance contains maker destination",
          "メーカー保証または販売店・メーカー窓口へ誘導" in app.build_warranty_guidance(r), True)


def test_tc52_warranty_guidance_expired_contains_unacceptable():
    r = app.determine_warranty_status(
        make_form(warranty_start_date="2020/01/01", warranty_end_date="2026/04/26"),
        today=date(2026, 4, 27),
    )
    check("TC52 expired", r["warranty_status"], "expired")
    check("TC52 can_accept False", r["can_accept"], False)
    check("TC52 guidance contains expired",
          "保証期間終了のため受付不可" in app.build_warranty_guidance(r), True)


def test_tc53_warranty_unknown_required_questions():
    r = app.determine_warranty_status(
        make_form(warranty_start_date="", warranty_end_date="2031/04/30"),
        today=date(2026, 4, 27),
    )
    check("TC53 unknown", r["warranty_status"], "unknown")
    check("TC53 can_accept False", r["can_accept"], False)
    check("TC53 required_questions contains dates", "保証開始日・保証終了日" in r["required_questions"], True)


def test_tc54_warranty_active_accepts():
    r = app.determine_warranty_status(
        make_form(warranty_start_date="2026/01/01", warranty_end_date="2030/12/31"),
        today=date(2026, 4, 27),
    )
    check("TC54 active", r["warranty_status"], "active")
    check("TC54 can_accept True", r["can_accept"], True)


def test_tc55_manufacturer_options_include_required_names():
    options = app.get_manufacturer_options()
    for manufacturer in [
        "ダイキン", "アイリスオーヤマ", "パナソニック", "富士通",
        "Dell", "ダイソン", "エレクトロラックス・ジャパン", "その他・要確認",
    ]:
        check(f"TC55 manufacturer options に {manufacturer} を含む", manufacturer in options, True)


def test_tc56_normalize_manufacturer_for_select_daikin():
    check("TC56 DAIKIN → ダイキン", app.normalize_manufacturer_for_select("DAIKIN"), "ダイキン")


def test_tc57_normalize_manufacturer_for_select_panasonic():
    check("TC57 Panasonic → パナソニック", app.normalize_manufacturer_for_select("Panasonic"), "パナソニック")


def test_tc58_normalize_manufacturer_for_select_dyson():
    check("TC58 Dyson → ダイソン", app.normalize_manufacturer_for_select("Dyson"), "ダイソン")


def test_tc59_normalize_manufacturer_for_select_unknown():
    check("TC59 不明メーカーX → その他・要確認",
          app.normalize_manufacturer_for_select("不明メーカーX"), "その他・要確認")


def test_tc60_extract_manufacturer_daikin_preserves_original():
    form = app.apply_extracted_fields_to_form({"manufacturer": "DAIKIN"}, make_form())
    check("TC60 manufacturer normalized", form["manufacturer"], "ダイキン")
    check("TC60 manufacturer original", form["manufacturer_original"], "DAIKIN")


def test_tc61_ac_other_manufacturer_blocks_cost():
    d = app.run_decision(make_form(product="エアコン", manufacturer="その他・要確認"))
    check("TC61 エアコン+その他 → 未確定", d["cost_estimate"], "未確定")
    check("TC61 エアコン+その他 → pending", d["cost_result"]["cost_status"], "pending")
    check("TC61 エアコン+その他 → 案内不可", d["cost_result"]["can_announce_cost"], False)


def test_tc62_pc_other_manufacturer_blocks_cost():
    d = app.run_decision(make_form(product="パソコン", manufacturer="その他・要確認"))
    check("TC62 パソコン+その他 → 未確定", d["cost_estimate"], "未確定")
    check("TC62 パソコン+その他 → pending", d["cost_result"]["cost_status"], "pending")
    check("TC62 パソコン+その他 → 案内不可", d["cost_result"]["can_announce_cost"], False)


def test_tc63_ecocute_daikin_cost():
    d = app.run_decision(make_form(product="エコキュート", manufacturer="ダイキン"))
    check("TC63 エコキュート+ダイキン → 出張修理", d["repair_type"], "出張修理")
    check("TC63 エコキュート+ダイキン → 15,000円～20,000円前後",
          d["cost_estimate"], "15,000円～20,000円前後")


def test_tc64_ecocute_panasonic_cost():
    d = app.run_decision(make_form(product="エコキュート", manufacturer="パナソニック"))
    check("TC64 エコキュート+パナソニック → 8,000円～10,000円前後",
          d["cost_estimate"], "8,000円～10,000円前後")


def test_tc65_gas_water_heater_cost():
    d = app.run_decision(make_form(product="ガス給湯器"))
    check("TC65 ガス給湯器 → 5,000円～7,000円前後",
          d["cost_estimate"], "5,000円～7,000円前後")


def test_tc66_oil_water_heater_cost():
    d = app.run_decision(make_form(product="石油給湯器"))
    check("TC66 石油給湯器 → 5,000円～7,000円前後",
          d["cost_estimate"], "5,000円～7,000円前後")


def test_tc67_hybrid_water_heater_cost():
    d = app.run_decision(make_form(product="ハイブリッド給湯器"))
    check("TC67 ハイブリッド給湯器 → 8,000円～10,000円前後",
          d["cost_estimate"], "8,000円～10,000円前後")


def test_tc68_enefarm_requires_gas_company():
    d = app.run_decision(make_form(product="エネファーム"))
    check("TC68 エネファーム → 5,000円～7,000円前後",
          d["cost_estimate"], "5,000円～7,000円前後")
    check("TC68 required_questions にガス会社",
          "ガス会社" in d["cost_result"]["required_questions"], True)
    check("TC68 internal_note にガス会社",
          "ガス会社" in d["cost_result"]["internal_note"], True)


def test_tc69_electric_water_heater_cost():
    d = app.run_decision(make_form(product="電気温水器"))
    check("TC69 電気温水器 → 8,000円～10,000円前後",
          d["cost_estimate"], "8,000円～10,000円前後")


def test_tc70_electric_heating_water_boiler_cost():
    d = app.run_decision(make_form(product="電気暖房温水ボイラー"))
    check("TC70 電気暖房温水ボイラー → 8,000円～10,000円前後",
          d["cost_estimate"], "8,000円～10,000円前後")


def test_tc71_generic_water_heater_pending():
    d = app.run_decision(make_form(product="給湯器"))
    check("TC71 給湯器のみ → pending", d["cost_result"]["cost_status"], "pending")
    check("TC71 給湯器のみ → 未確定", d["cost_estimate"], "未確定")
    check("TC71 required_questions に給湯器種別",
          "ガス給湯器・石油給湯器・ハイブリッド給湯器" in d["cost_result"]["required_questions"], True)


def test_tc72_water_heater_products_in_options():
    options = app.get_product_options()
    for product in [
        "エコキュート", "ガス給湯器", "石油給湯器", "ハイブリッド給湯器",
        "エネファーム", "電気温水器", "電気暖房温水ボイラー",
    ]:
        check(f"TC72 product options に {product} を含む", product in options, True)


def test_tc73_digital_camera_cost():
    d = app.run_decision(make_form(product="デジカメ"))
    check("TC73 デジカメ → 持込修理", d["repair_type"], "持込修理")
    check("TC73 デジカメ → 2,000円前後", d["cost_estimate"], "2,000円前後")


def test_tc74_slr_camera_cost():
    d = app.run_decision(make_form(product="一眼レフカメラ"))
    check("TC74 一眼レフカメラ → 2,000円前後", d["cost_estimate"], "2,000円前後")


def test_tc75_video_camera_cost():
    d = app.run_decision(make_form(product="ビデオカメラ"))
    check("TC75 ビデオカメラ → 2,000円前後", d["cost_estimate"], "2,000円前後")


def test_tc76_roland_electric_piano_cost():
    d = app.run_decision(make_form(product="電子ピアノ脚なし", manufacturer="ローランド"))
    check("TC76 電子ピアノ脚なし+ローランド → 6,000円～15,000円前後",
          d["cost_estimate"], "6,000円～15,000円前後")


def test_tc77_roland_piano_alias_and_cost():
    form = make_form(product="ピアノ脚なし", manufacturer="Roland")
    d = app.run_decision(form)
    check("TC77 Roland正規化", d["working_form"]["manufacturer"], "ローランド")
    check("TC77 ピアノ脚なし+Roland → 6,000円～15,000円前後",
          d["cost_estimate"], "6,000円～15,000円前後")


def test_tc78_non_roland_electric_piano_generic_carry_in():
    d = app.run_decision(make_form(product="電子ピアノ脚なし", manufacturer="ヤマハ"))
    check("TC78 ローランド以外電子ピアノ → 汎用持込",
          d["cost_estimate"], "2,000円～5,000円前後")


def test_tc79_airdog_cost_and_note():
    d = app.run_decision(make_form(product="Airdog"))
    check("TC79 Airdog → 7,000円～10,000円前後",
          d["cost_estimate"], "7,000円～10,000円前後")
    check("TC79 Airdog note includes送料",
          ("返送料" in d["cost_result"]["internal_note"] or "送料" in d["cost_result"]["internal_note"]), True)


def test_tc80_power_wave_fit_project_cost_and_note():
    d = app.run_decision(make_form(product="パワーウエーブ", manufacturer="FITプロジェクト"))
    check("TC80 パワーウエーブ+FIT → 4,000円～5,000円前後",
          d["cost_estimate"], "4,000円～5,000円前後")
    check("TC80 FIT note includes phone", "0800-919-0757" in d["cost_result"]["internal_note"], True)


def test_tc81_power_wave_tk_create_cost():
    d = app.run_decision(make_form(product="パワーウエーブ", manufacturer="TKクリエイト"))
    check("TC81 パワーウエーブ+TK → 4,000円～5,000円前後",
          d["cost_estimate"], "4,000円～5,000円前後")


def test_tc82_pioneer_av_cost_escalation():
    d = app.run_decision(make_form(product="AV製品", manufacturer="パイオニア"))
    check("TC82 AV製品+パイオニア → 16,000円前後",
          d["cost_estimate"], "16,000円前後")
    check("TC82 needs_escalation", d["cost_result"]["needs_escalation"], True)
    note = d["cost_result"]["internal_note"]
    check("TC82 note includes AV撤退 or 委託先", ("AV事業から撤退" in note or "委託先" in note), True)


def test_tc83_pioneer_car_navi_not_av_cost():
    d = app.run_decision(make_form(product="カーナビ", manufacturer="パイオニア"))
    check("TC83 カーナビ+パイオニア → AV費用ではない",
          d["cost_estimate"] != "16,000円前後", True)


def test_tc84_special_carry_in_products_in_options():
    options = app.get_product_options()
    for product in [
        "デジカメ", "一眼レフカメラ", "ビデオカメラ", "電子ピアノ脚なし",
        "ピアノ脚なし", "Airdog", "パワーウエーブ", "AV製品",
    ]:
        check(f"TC84 product options に {product} を含む", product in options, True)


# ============================================================
# TC85–TC94: 判定診断パネル
# ============================================================

def _diag_area(diagnostics: dict, area: str) -> dict:
    """指定 area のアイテムを返す。見つからなければ空 dict。"""
    for item in diagnostics.get("items", []):
        if item["area"] == area:
            return item
    return {}


def test_tc85_diagnostics_warranty_expired_overall_error():
    d = app.run_decision(make_form(
        product="洗濯機",
        warranty_start_date="2020/01/01",
        warranty_end_date="2026/04/26",
    ))
    diag = d["diagnostics"]
    check("TC85 overall_status=error",           diag["overall_status"], "error")
    w = _diag_area(diag, "保証期間判定")
    check("TC85 保証期間 status=error",           w["status"],            "error")
    check("TC85 保証期間 title 受付不可を含む",  "受付不可" in w["title"], True)


def test_tc86_diagnostics_warranty_unknown_blank_missing_fields():
    d = app.run_decision(make_form(
        warranty_start_date="",
        warranty_end_date="",
    ))
    diag = d["diagnostics"]
    w = _diag_area(diag, "保証期間判定")
    check("TC86 保証期間 status=warning",         w["status"], "warning")
    check("TC86 warranty_start_date in missing",
          "warranty_start_date" in w["missing_fields"], True)
    check("TC86 warranty_end_date in missing",
          "warranty_end_date" in w["missing_fields"], True)


def test_tc87_diagnostics_warranty_unknown_invalid_date():
    d = app.run_decision(make_form(
        warranty_start_date="not-a-date",
        warranty_end_date="2030/12/31",
    ))
    diag = d["diagnostics"]
    w = _diag_area(diag, "保証期間判定")
    check("TC87 保証期間 status=warning",         w["status"], "warning")
    check("TC87 warranty_start_date in invalid",
          "warranty_start_date" in w["invalid_fields"], True)
    check("TC87 invalid_fields 非空",            bool(w["invalid_fields"]), True)


def test_tc88_diagnostics_ac_no_mfr_cost_pending():
    d = app.run_decision(make_form(product="エアコン"))
    diag = d["diagnostics"]
    c = _diag_area(diag, "概算費用判定")
    check("TC88 概算費用 status=warning",         c["status"], "warning")
    check("TC88 概算費用 title 未確定を含む",    "未確定" in c["title"], True)
    check("TC88 overall_status=warning",          diag["overall_status"], "warning")


def test_tc89_diagnostics_ac_daikin_no_type_cost_pending():
    d = app.run_decision(make_form(product="エアコン", manufacturer="ダイキン"))
    diag = d["diagnostics"]
    c = _diag_area(diag, "概算費用判定")
    check("TC89 概算費用 status=warning",         c["status"], "warning")
    check("TC89 reason 業務用を含む",            "業務用" in c["reason"], True)


def test_tc90_diagnostics_pc_no_mfr_cost_pending():
    d = app.run_decision(make_form(product="パソコン"))
    diag = d["diagnostics"]
    c = _diag_area(diag, "概算費用判定")
    check("TC90 概算費用 status=warning",         c["status"], "warning")
    check("TC90 概算費用 title 未確定を含む",    "未確定" in c["title"], True)


def test_tc91_diagnostics_kyutoki_only_pending():
    d = app.run_decision(make_form(product="給湯器"))
    diag = d["diagnostics"]
    c = _diag_area(diag, "概算費用判定")
    check("TC91 概算費用 status=warning",         c["status"], "warning")
    check("TC91 reason 給湯器種別を含む",
          "ガス給湯器" in c["reason"], True)


def test_tc92_diagnostics_empty_product_repair_warning():
    d = app.run_decision(make_form(product=""))
    diag = d["diagnostics"]
    r = _diag_area(diag, "修理形態判定")
    check("TC92 修理形態 status=warning",         r["status"], "warning")
    check("TC92 product in missing_fields",
          "product" in r["missing_fields"], True)


def test_tc93_diagnostics_empty_prefecture_vendor_warning():
    d = app.run_decision(make_form(product="洗濯機", prefecture=""))
    diag = d["diagnostics"]
    v = _diag_area(diag, "修理拠点判定")
    check("TC93 修理拠点 status=warning",         v["status"], "warning")
    check("TC93 prefecture in missing_fields",
          "prefecture" in v["missing_fields"], True)


def test_tc94_diagnostics_pioneer_av_escalation_warning():
    d = app.run_decision(make_form(product="AV製品", manufacturer="パイオニア"))
    diag = d["diagnostics"]
    c = _diag_area(diag, "概算費用判定")
    check("TC94 概算費用 status=warning (escalation)", c["status"], "warning")
    check("TC94 title 高額エスカを含む",         "高額エスカ" in c["title"], True)


# ============================================================
# TC95–TC99: 診断パネル表示用の並び替え・ラベル
# ============================================================

def test_tc95_diagnostics_items_sorted_error_warning_ok():
    d = app.run_decision(make_form(
        product="洗濯機",
        prefecture="滋賀県",
        appliance_type="家電",
        warranty_start_date="2020/01/01",
        warranty_end_date="2026/04/26",
    ))
    items = d["diagnostics"]["items"]
    order = {"error": 0, "warning": 1, "ok": 2}
    sorted_statuses = sorted([i["status"] for i in items], key=lambda s: order[s])
    check("TC95 diagnostics status order error/warning/ok",
          [i["status"] for i in items], sorted_statuses)
    check("TC95 error内で保証期間判定が先頭", items[0]["area"], "保証期間判定")


def test_tc96_field_label_warranty_start_date():
    check("TC96 warranty_start_date → 保証開始日",
          app.field_label("warranty_start_date"), "保証開始日")
    check("TC96 missing_fields 日本語結合",
          app.format_field_labels(["warranty_start_date", "warranty_end_date"]),
          "保証開始日、保証終了日")


def test_tc97_diagnostics_overall_error_expired_warranty():
    d = app.run_decision(make_form(
        product="洗濯機",
        prefecture="滋賀県",
        appliance_type="家電",
        warranty_start_date="2020/01/01",
        warranty_end_date="2026/04/26",
    ))
    check("TC97 expired保証 overall_status=error",
          d["diagnostics"]["overall_status"], "error")


def test_tc98_diagnostics_overall_warning_aircon_no_manufacturer():
    d = app.run_decision(make_form(
        product="エアコン",
        prefecture="東京都",
        appliance_type="家電",
        warranty_start_date="2026/01/01",
        warranty_end_date="2030/12/31",
    ))
    c = _diag_area(d["diagnostics"], "概算費用判定")
    check("TC98 エアコン+メーカー未入力 overall_status=warning",
          d["diagnostics"]["overall_status"], "warning")
    check("TC98 概算費用 next_action=メーカー確認",
          c["next_action"], "メーカーを確認してください")


def test_tc99_diagnostics_overall_ok_active_washer():
    d = app.run_decision(make_form(
        product="洗濯機",
        manufacturer="パナソニック",
        prefecture="滋賀県",
        appliance_type="家電",
        warranty_start_date="2026/01/01",
        warranty_end_date="2030/12/31",
    ))
    check("TC99 保証期間内+必要項目あり overall_status=ok",
          d["diagnostics"]["overall_status"], "ok")
    check("TC99 diagnostics items all ok",
          all(i["status"] == "ok" for i in d["diagnostics"]["items"]), True)


# ============================================================
# TC100–TC105: 診断 impact と実務向け overall_status
# ============================================================

def test_tc100_vendor_only_warning_is_after_call_and_overall_ok():
    d = app.run_decision(make_form(
        product="ドライヤー",
        manufacturer="パナソニック",
        prefecture="",
        appliance_type="家電",
        warranty_start_date="2026/01/01",
        warranty_end_date="2030/12/31",
    ))
    v = _diag_area(d["diagnostics"], "修理拠点判定")
    check("TC100 修理拠点のみ未確定 status=warning", v["status"], "warning")
    check("TC100 修理拠点 impact=after_call_ok", v["impact"], "after_call_ok")
    check("TC100 修理拠点のみ未確定 overall_status=ok",
          d["diagnostics"]["overall_status"], "ok")


def test_tc101_ac_no_manufacturer_cost_is_call_time_required():
    d = app.run_decision(make_form(
        product="エアコン",
        prefecture="東京都",
        appliance_type="家電",
        warranty_start_date="2026/01/01",
        warranty_end_date="2030/12/31",
    ))
    c = _diag_area(d["diagnostics"], "概算費用判定")
    check("TC101 エアコンメーカー未入力 概算費用 status=warning", c["status"], "warning")
    check("TC101 概算費用 impact=call_time_required", c["impact"], "call_time_required")
    check("TC101 overall_status=warning", d["diagnostics"]["overall_status"], "warning")


def test_tc102_expired_warranty_is_blocking_error():
    d = app.run_decision(make_form(
        product="洗濯機",
        prefecture="滋賀県",
        appliance_type="家電",
        warranty_start_date="2020/01/01",
        warranty_end_date="2026/04/26",
    ))
    w = _diag_area(d["diagnostics"], "保証期間判定")
    check("TC102 保証期間終了 status=error", w["status"], "error")
    check("TC102 保証期間終了 impact=blocking", w["impact"], "blocking")
    check("TC102 overall_status=error", d["diagnostics"]["overall_status"], "error")


def test_tc103_generic_water_heater_is_call_time_required():
    d = app.run_decision(make_form(
        product="給湯器",
        prefecture="東京都",
        appliance_type="住設",
        warranty_start_date="2026/01/01",
        warranty_end_date="2030/12/31",
    ))
    c = _diag_area(d["diagnostics"], "概算費用判定")
    check("TC103 給湯器のみ 概算費用 status=warning", c["status"], "warning")
    check("TC103 給湯器のみ impact=call_time_required", c["impact"], "call_time_required")
    check("TC103 overall_status=warning", d["diagnostics"]["overall_status"], "warning")


def test_tc104_after_call_vendor_warning_keeps_overall_ok():
    d = app.run_decision(make_form(
        product="ドライヤー",
        manufacturer="パナソニック",
        prefecture="",
        appliance_type="家電",
        warranty_start_date="2026/01/01",
        warranty_end_date="2030/12/31",
    ))
    v = _diag_area(d["diagnostics"], "修理拠点判定")
    check("TC104 修理拠点判定は終話後確認", "終話後確認" in v["title"], True)
    check("TC104 修理拠点 impact=after_call_ok", v["impact"], "after_call_ok")
    check("TC104 overall_status=ok", d["diagnostics"]["overall_status"], "ok")


def test_tc105_diagnostics_items_sorted_by_impact_then_status_then_area():
    d = app.run_decision(make_form(
        product="エアコン",
        prefecture="",
        appliance_type="家電",
        warranty_start_date="2026/01/01",
        warranty_end_date="2030/12/31",
    ))
    items = d["diagnostics"]["items"]
    sorted_items = app.sort_diagnostic_items(list(items))
    check("TC105 diagnostics impact順ソート",
          [(i["impact"], i["status"], i["area"]) for i in items],
          [(i["impact"], i["status"], i["area"]) for i in sorted_items])
    check("TC105 先頭は通話中確認の概算費用", items[0]["area"], "概算費用判定")


# ============================================================
# TC106–TC112: 不足項目リンク・STEP表示・スクリプトリンク
# ============================================================

def test_tc106_next_action_steps_aircon_no_manufacturer():
    d = app.run_decision(make_form(
        product="エアコン",
        prefecture="東京都",
        appliance_type="家電",
        warranty_start_date="2026/01/01",
        warranty_end_date="2030/12/31",
    ))
    steps = app.build_next_action_steps(d["diagnostics"])
    check("TC106 steps にメーカー確認を含む",
          "メーカーを確認してください" in steps, True)


def test_tc107_next_action_steps_daikin_missing_extra_condition():
    d = app.run_decision(make_form(
        product="エアコン",
        manufacturer="ダイキン",
        prefecture="東京都",
        appliance_type="家電",
        warranty_start_date="2026/01/01",
        warranty_end_date="2030/12/31",
    ))
    steps = app.build_next_action_steps(d["diagnostics"])
    check("TC107 steps に家庭用/業務用確認を含む",
          "家庭用/業務用を確認してください" in steps, True)


def test_tc108_next_action_steps_warranty_unknown():
    d = app.run_decision(make_form(product="洗濯機", prefecture="滋賀県", appliance_type="家電"))
    steps = app.build_next_action_steps(d["diagnostics"])
    check("TC108 steps に保証日確認を含む",
          "保証開始日・保証終了日を確認" in steps, True)


def test_tc109_after_call_steps_do_not_mix_into_call_time_steps():
    d = app.run_decision(make_form(
        product="ドライヤー",
        manufacturer="パナソニック",
        prefecture="",
        appliance_type="家電",
        warranty_start_date="2026/01/01",
        warranty_end_date="2030/12/31",
    ))
    call_steps = app.build_next_action_steps(d["diagnostics"])
    after_steps = app.build_after_call_steps(d["diagnostics"])
    check("TC109 call_time steps に終話後拠点確定を含めない",
          any("終話後に担当へエスカレーション" in s for s in call_steps), False)
    check("TC109 after_call steps に終話後拠点確定を含む",
          any("終話後に担当へエスカレーション" in s for s in after_steps), True)


def test_tc110_missing_field_link_generation():
    check("TC110 manufacturer field link",
          app.field_link("manufacturer"), "[メーカー欄へ移動](#field-manufacturer)")
    check("TC110 warranty_start_date field link",
          app.field_link("warranty_start_date"), "[保証開始日欄へ移動](#field-warranty_start_date)")


def test_tc111_master_script_links_csv_exists():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "master_script_links.csv")
    check("TC111 master_script_links.csv exists", os.path.exists(path), True)


def test_tc112_script_link_lookup_registered_and_blank_url():
    registered = app.lookup_script_link({
        "sheet_name": "家電出張・持込・新築住設",
        "part": "家電・出張修理",
    })
    blank = app.lookup_script_link({
        "sheet_name": "住設【既築／中古のみ】",
        "part": "住設受付",
    })
    check("TC112 registered script link matched", registered["matched"], True)
    check("TC112 registered script link has URL", bool(registered["url"]), True)
    check("TC112 also_registered matched", blank["matched"], True)


# ============================================================
# TC113–TC120: 保証日付カレンダー入力用ヘルパー
# ============================================================

def test_tc113_form_date_text_to_date_slash():
    check("TC113 2026/01/01 -> date",
          app.form_date_text_to_date("2026/01/01"), date(2026, 1, 1))


def test_tc114_form_date_text_to_date_hyphen():
    check("TC114 2026-01-01 -> date",
          app.form_date_text_to_date("2026-01-01"), date(2026, 1, 1))


def test_tc115_form_date_text_to_date_japanese():
    check("TC115 2026年1月1日 -> date",
          app.form_date_text_to_date("2026年1月1日"), date(2026, 1, 1))


def test_tc116_date_to_form_date_text():
    check("TC116 date -> YYYY/MM/DD",
          app.date_to_form_date_text(date(2026, 1, 1)), "2026/01/01")


def test_tc117_blank_date_helpers_do_not_default_today():
    check("TC117 blank -> None", app.form_date_text_to_date(""), None)
    check("TC117 None date -> blank text", app.date_to_form_date_text(None), "")


def test_tc118_unknown_warranty_when_dates_blank():
    d = app.determine_warranty_status(
        {"warranty_start_date": "", "warranty_end_date": ""},
        today=date(2026, 4, 30),
    )
    check("TC118 blank dates warranty_status=unknown", d["warranty_status"], "unknown")
    check("TC118 blank dates can_accept=False", d["can_accept"], False)


def test_tc119_extracted_dates_convert_for_date_input():
    extracted = app.extract_fields_from_pasted_text(
        "保証開始日\t2026-05-01\n保証終了日\t2031年4月30日\n"
    )
    check("TC119 extracted start normalized", extracted["warranty_start_date"], "2026/05/01")
    check("TC119 extracted end normalized", extracted["warranty_end_date"], "2031/04/30")
    check("TC119 start converts to date_input date",
          app.form_date_text_to_date(extracted["warranty_start_date"]), date(2026, 5, 1))
    check("TC119 end converts to date_input date",
          app.form_date_text_to_date(extracted["warranty_end_date"]), date(2031, 4, 30))


def test_tc120_empty_form_does_not_auto_fill_today_for_warranty():
    form = app.empty_form()
    check("TC120 empty form start remains blank", form["warranty_start_date"], "")
    check("TC120 empty form end remains blank", form["warranty_end_date"], "")
    for key in ["operator_name", "rakuteru_no", "contact_phone", "extracted_time"]:
        check(f"TC120 empty form includes blank {key}", form[key], "")
    check("TC120 empty form caller_type default", form["caller_type"], "加入者")

    class SessionState(dict):
        def __getattr__(self, name):
            try:
                return self[name]
            except KeyError as exc:
                raise AttributeError(name) from exc

        def __setattr__(self, name, value):
            self[name] = value

    original_session_state = app.st.session_state
    try:
        app.st.session_state = SessionState({
            "form": {"warranty_start_date": "", "warranty_end_date": ""}
        })
        app.init_session()
        for key in ["operator_name", "rakuteru_no", "contact_phone", "caller_type", "extracted_time"]:
            assert key in app.st.session_state.form
    finally:
        app.st.session_state = original_session_state

    extracted_time = app._format_extracted_time(datetime(2026, 5, 3, 9, 4))
    assert re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2} \d{2}：\d{2}", extracted_time)
    check("TC120 extracted_time format", extracted_time, "2026/5/3 09：04")
    d = app.run_decision(make_form(product="洗濯機", prefecture="滋賀県", appliance_type="家電"))
    check("TC120 run_decision blank dates warranty_status=unknown",
          d["warranty_status"], "unknown")


def test_tc_template_code_options_loaded():
    df = app.load_template_codes()
    assert not df.empty
    assert "template_code" in df.columns

    rows = [
        {
            "category": "家電保証対応業務（24時間）",
            "label": "【出張修理】自然故障",
            "template_code": "0009",
        },
        {
            "category": "家電保証対応業務（24時間）",
            "label": "【出張修理】ダブルプロテクト",
            "template_code": "0010",
        },
        {
            "category": "家電保証対応業務（24時間）",
            "label": "【持込修理】自然故障",
            "template_code": "0001",
        },
        {
            "category": "家電保証対応業務（24時間）",
            "label": "【持込修理】ダブルプロテクト",
            "template_code": "0002",
        },
    ]
    df_sample = app.pd.DataFrame(rows)
    check(
        "template auto select visit natural",
        app._auto_select_template("家電保証対応業務（24時間）", "出張修理", "自然故障", df_sample),
        "【出張修理】自然故障",
    )
    check(
        "template auto select carry in natural",
        app._auto_select_template("家電保証対応業務（24時間）", "持込修理", "自然故障", df_sample),
        "【持込修理】自然故障",
    )
    for plan in ["物損保証", "ダブルプロテクト", "DP"]:
        check(
            f"template auto select DP priority {plan}",
            app._auto_select_template("家電保証対応業務（24時間）", "出張修理", plan, df_sample),
            "【出張修理】ダブルプロテクト",
        )

    form = app.empty_form()
    form.update({
        "operator_name": "大濱",
        "rakuteru_no": "RT-123",
        "extracted_time": "2026/5/3 09：04",
        "contact_phone": "090-1111-2222",
        "phone_number": "090-0000-0000",
        "call_line": "家電保証対応業務（24時間）",
        "wrt_no": "WRT-999",
        "customer_name": "山田太郎",
        "product": "洗濯機",
        "manufacturer": "日立",
        "model_number": "BW-X",
        "store_name": "テスト販売店",
    })
    notes = app._fill_template_notes("販売店：〇〇〇〇〇 TEL：", form)
    report = app._build_teams_report(form, "加入者", notes)
    for expected in [
        "大濱", "RT-123", "WRT-999", "山田太郎", "洗濯機",
        "日立", "テスト販売店", "TEL：090-0000-0000",
    ]:
        assert expected in report


def test_tc_call_line_options_from_csv():
    options = app.get_call_line_options()
    assert "ビックカメラ" in options
    assert "住設業務" in options
    assert "GIGA案件" not in options


def test_tc_call_line_options_loaded():
    options = app.get_call_line_options()
    assert "ビックカメラ" in options
    assert "住設業務" in options
    assert "京阪不動産" in options


def test_tc_bic_camera_call_line_vendor():
    d = app.run_decision(make_form(call_line="ビックカメラ", product="洗濯機"))
    assert d["vendor"] == "ソフマップ修理センター"


def test_tc_is_over_10years_rentals_tokyo():
    d = app.run_decision(make_form(
        call_line="住設業務",
        prefecture="東京都",
        is_over_10years=True,
    ))
    assert d["vendor"] == "㈱リファテック"


def test_tc_is_under_10years_rentals_tokyo():
    d = app.run_decision(make_form(
        call_line="住設業務",
        prefecture="東京都",
        is_over_10years=False,
    ))
    assert d["vendor"] == "ユナイトサービス㈱"


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
    test_tc47_extract_warranty_dates_slash,
    test_tc48_extract_warranty_dates_hyphen,
    test_tc49_extract_warranty_dates_japanese,
    test_tc50_normalize_date_text,
    test_tc51_warranty_guidance_before_start_contains_destination,
    test_tc52_warranty_guidance_expired_contains_unacceptable,
    test_tc53_warranty_unknown_required_questions,
    test_tc54_warranty_active_accepts,
    test_tc55_manufacturer_options_include_required_names,
    test_tc56_normalize_manufacturer_for_select_daikin,
    test_tc57_normalize_manufacturer_for_select_panasonic,
    test_tc58_normalize_manufacturer_for_select_dyson,
    test_tc59_normalize_manufacturer_for_select_unknown,
    test_tc60_extract_manufacturer_daikin_preserves_original,
    test_tc61_ac_other_manufacturer_blocks_cost,
    test_tc62_pc_other_manufacturer_blocks_cost,
    test_tc63_ecocute_daikin_cost,
    test_tc64_ecocute_panasonic_cost,
    test_tc65_gas_water_heater_cost,
    test_tc66_oil_water_heater_cost,
    test_tc67_hybrid_water_heater_cost,
    test_tc68_enefarm_requires_gas_company,
    test_tc69_electric_water_heater_cost,
    test_tc70_electric_heating_water_boiler_cost,
    test_tc71_generic_water_heater_pending,
    test_tc72_water_heater_products_in_options,
    test_tc73_digital_camera_cost,
    test_tc74_slr_camera_cost,
    test_tc75_video_camera_cost,
    test_tc76_roland_electric_piano_cost,
    test_tc77_roland_piano_alias_and_cost,
    test_tc78_non_roland_electric_piano_generic_carry_in,
    test_tc79_airdog_cost_and_note,
    test_tc80_power_wave_fit_project_cost_and_note,
    test_tc81_power_wave_tk_create_cost,
    test_tc82_pioneer_av_cost_escalation,
    test_tc83_pioneer_car_navi_not_av_cost,
    test_tc84_special_carry_in_products_in_options,
    test_tc85_diagnostics_warranty_expired_overall_error,
    test_tc86_diagnostics_warranty_unknown_blank_missing_fields,
    test_tc87_diagnostics_warranty_unknown_invalid_date,
    test_tc88_diagnostics_ac_no_mfr_cost_pending,
    test_tc89_diagnostics_ac_daikin_no_type_cost_pending,
    test_tc90_diagnostics_pc_no_mfr_cost_pending,
    test_tc91_diagnostics_kyutoki_only_pending,
    test_tc92_diagnostics_empty_product_repair_warning,
    test_tc93_diagnostics_empty_prefecture_vendor_warning,
    test_tc94_diagnostics_pioneer_av_escalation_warning,
    test_tc95_diagnostics_items_sorted_error_warning_ok,
    test_tc96_field_label_warranty_start_date,
    test_tc97_diagnostics_overall_error_expired_warranty,
    test_tc98_diagnostics_overall_warning_aircon_no_manufacturer,
    test_tc99_diagnostics_overall_ok_active_washer,
    test_tc100_vendor_only_warning_is_after_call_and_overall_ok,
    test_tc101_ac_no_manufacturer_cost_is_call_time_required,
    test_tc102_expired_warranty_is_blocking_error,
    test_tc103_generic_water_heater_is_call_time_required,
    test_tc104_after_call_vendor_warning_keeps_overall_ok,
    test_tc105_diagnostics_items_sorted_by_impact_then_status_then_area,
    test_tc106_next_action_steps_aircon_no_manufacturer,
    test_tc107_next_action_steps_daikin_missing_extra_condition,
    test_tc108_next_action_steps_warranty_unknown,
    test_tc109_after_call_steps_do_not_mix_into_call_time_steps,
    test_tc110_missing_field_link_generation,
    test_tc111_master_script_links_csv_exists,
    test_tc112_script_link_lookup_registered_and_blank_url,
    test_tc113_form_date_text_to_date_slash,
    test_tc114_form_date_text_to_date_hyphen,
    test_tc115_form_date_text_to_date_japanese,
    test_tc116_date_to_form_date_text,
    test_tc117_blank_date_helpers_do_not_default_today,
    test_tc118_unknown_warranty_when_dates_blank,
    test_tc119_extracted_dates_convert_for_date_input,
    test_tc120_empty_form_does_not_auto_fill_today_for_warranty,
    test_tc_template_code_options_loaded,
    test_tc_call_line_options_from_csv,
    test_tc_call_line_options_loaded,
    test_tc_bic_camera_call_line_vendor,
    test_tc_is_over_10years_rentals_tokyo,
    test_tc_is_under_10years_rentals_tokyo,
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
