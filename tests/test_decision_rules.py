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
from pathlib import Path
from datetime import date, datetime

# Add project root to path so `import app` works from any working directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = Path(__file__).resolve().parents[1]

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
    prefecture="", call_line="", appliance_type="", appliance_category="",
    extra_condition="", store_name="", warranty_start_date="", warranty_end_date="",
    is_over_10years=False, manufacturer_original="", pc_manufacturer_type="",
    warranty_plan="", symptom="",
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
        appliance_category=appliance_category,
        extra_condition=extra_condition,
        store_name=store_name,
        warranty_start_date=warranty_start_date,
        warranty_end_date=warranty_end_date,
        is_over_10years=is_over_10years,
        manufacturer_original=manufacturer_original,
        pc_manufacturer_type=pc_manufacturer_type,
        warranty_plan=warranty_plan,
        symptom=symptom,
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


def test_appendix_repair_policy_visit_and_carry_in_rules():
    cases = [
        ({"product": "エアコン"}, "出張修理"),
        ({"product": "洗濯機"}, "出張修理"),
        ({"product": "冷蔵庫"}, "出張修理"),
        ({"product": "ドライヤー"}, "持込修理"),
        ({"product": "パソコン"}, "持込修理"),
        ({"product": "電子レンジ", "manufacturer": "ユアサプライム"}, "持込修理"),
        ({"product": "電子レンジ", "manufacturer": "バルミューダ"}, "持込修理"),
        ({"product": "オーブンレンジ", "manufacturer": "バルミューダ"}, "要確認"),
    ]
    for values, expected in cases:
        decision = app.run_decision(make_form(**values))
        assert decision["repair_type"] == expected
        assert decision["repair_result"]["reason"]


def test_appendix_repair_policy_needs_check_and_notes():
    printer = app.run_decision(make_form(product="プリンター"))
    assert printer["repair_type"] == "要確認"
    assert printer["repair_result"]["certainty"] == "needs_check"
    assert "型番" in printer["repair_result"]["reason"]

    purifier = app.run_decision(make_form(product="空気清浄機"))
    assert purifier["repair_type"] == "要確認"
    assert purifier["repair_result"]["certainty"] == "needs_check"
    assert "引取修理" in purifier["repair_result"]["notes"]


def test_toilet_seat_visit_repair_does_not_require_manufacturer():
    for product in ["多機能便座", "温水便座", "温水洗浄便座", "シャワートイレ", "ウォシュレット"]:
        decision = app.run_decision(make_form(product=product, manufacturer="", appliance_category="住設（既築）"))
        assert decision["repair_type"] == "出張修理"
        assert decision["repair_result"]["manufacturer_required"] is False
        assert "manufacturer" not in decision["repair_result"].get("missing_fields", [])
        assert "manufacturer" not in app.decision_tag_missing_fields(decision)["修理方針"]


def test_maker_dependent_products_request_manufacturer_or_model_only_when_needed():
    microwave = app.run_decision(make_form(product="電子レンジ", manufacturer="", appliance_category="家電"))
    assert microwave["repair_type"] == "要確認"
    assert microwave["repair_result"]["manufacturer_required"] is True
    assert "manufacturer" in microwave["repair_result"]["missing_fields"]
    assert "manufacturer" in app.decision_tag_missing_fields(microwave)["修理方針"]

    printer = app.run_decision(make_form(product="プリンター", manufacturer="", model_number="", appliance_category="家電"))
    assert printer["repair_type"] == "要確認"
    assert printer["repair_result"]["manufacturer_required"] is True
    assert printer["repair_result"]["model_required"] is True
    assert set(printer["repair_result"]["missing_fields"]) >= {"manufacturer", "model_number"}


def test_repair_policy_missing_display_is_product_first_then_conditional_fields():
    initial = app.run_decision(make_form())
    assert app.decision_tag_missing_fields(initial)["修理方針"] == ["product"]
    assert app._missing_text(app.decision_tag_missing_fields(initial)["修理方針"]) == "不足：製品"

    toilet = app.run_decision(make_form(product="多機能便座", manufacturer="", appliance_category="住設（既築）"))
    assert "manufacturer" not in app.decision_tag_missing_fields(toilet)["修理方針"]

    microwave = app.run_decision(make_form(product="電子レンジ", manufacturer="", appliance_category="家電"))
    assert "manufacturer" in app.decision_tag_missing_fields(microwave)["修理方針"]


def test_master_repair_type_rules_have_required_flags_and_toilet_seat_aliases():
    df = app.load_repair_type_rules()
    for col in ["manufacturer_required", "model_required", "manual_required"]:
        assert col in df.columns

    aliases = {"温水便座", "多機能便座", "温水洗浄便座", "シャワートイレ", "ウォシュレット"}
    rows = df[df["product_keyword"].isin(aliases)]
    assert aliases <= set(rows["product_keyword"])
    assert set(rows["repair_type"]) == {"出張修理"}
    assert set(rows["manufacturer_required"]) == {"0"}


def test_master_script_routes_csv_exists_and_japannext_url_is_unconfirmed():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "master_script_routes.csv")
    assert os.path.exists(path)
    df = app.load_script_routes()
    assert len(df) == 29
    row = df[df["script_key"] == "japannext_greenhouse"].iloc[0]
    assert row["display_name"] == "ジャパンネクストorグリーンハウス"
    assert row["url"] == ""
    assert row["confidence"] == "needs_url"
    assert df[df["script_key"] == "0099_jusetsu"].empty


def test_judge_script_route_store_and_plan_priority_cases():
    cases = [
        (make_form(store_name="ビックカメラ"), "ビックカメラ・ソフマップ", "high"),
        (make_form(store_name="ソフマップ"), "ビックカメラ・ソフマップ", "high"),
        (make_form(store_name="ビックカメラ", warranty_plan="官舎向け保証"), "ビックカメラ（官舎向け）", "high"),
        (make_form(store_name="コーナン", appliance_category="家電"), "コーナン家電", "high"),
        (make_form(store_name="コーナン", appliance_category="住設（既築）"), "コーナン住設", "high"),
        (make_form(call_line="0099", warranty_plan="賃貸住宅プラン"), "0099回線（賃貸）", "high"),
        (make_form(call_line="0099", warranty_plan="既築住宅プラン"), "0099回線（既築/中古）", "high"),
        (make_form(call_line="0099", warranty_plan="中古住宅プラン"), "0099回線（既築/中古）", "high"),
        (make_form(call_line="0099", warranty_plan="駆けつけサービス"), "0099回線（駆けつけ）", "high"),
        (make_form(call_line="0099", warranty_plan="24hサポート"), "0099回線（駆けつけ）", "high"),
        (make_form(call_line="0099", warranty_plan="24時間サポート"), "0099回線（駆けつけ）", "high"),
    ]
    for form, display_name, confidence in cases:
        result = app.judge_script_route(form)
        assert result["display_name"] == display_name
        assert result["confidence"] == confidence
        assert result["url"]


def test_judge_script_route_line_first_basic_and_store_overrides():
    cases = [
        (make_form(call_line="家電"), "0099回線（家電/新築）", "high", True),
        (make_form(call_line="家電回線"), "0099回線（家電/新築）", "high", True),
        (make_form(call_line="0099", appliance_category="家電"), "0099回線（家電/新築）", "high", True),
        (make_form(call_line="0099", appliance_category="住設（既築）"), "0099回線（住設既築）", "high", True),
        (make_form(call_line="住設", store_name="コーナン"), "コーナン住設", "high", True),
        (make_form(call_line="家電", store_name="コーナン"), "コーナン家電", "high", True),
        (make_form(call_line="家電", store_name="ビックカメラ"), "ビックカメラ・ソフマップ", "high", True),
        (make_form(call_line="家電", store_name="ビックカメラ", warranty_plan="官舎"), "ビックカメラ（官舎向け）", "high", True),
    ]
    for form, display_name, confidence, has_url in cases:
        result = app.judge_script_route(form)
        assert result["display_name"] == display_name
        assert result["confidence"] == confidence
        assert bool(result["url"]) is has_url
        assert result["initial_line"]
        assert "回線名" in result["matched_by"]


def test_judge_script_route_jusetsu_line_waits_for_category_selection():
    for call_line in ("住設", "住設回線"):
        result = app.judge_script_route(make_form(call_line=call_line))

        assert result["script_key"] == "needs_jusetsu_type"
        assert result["display_name"] == "住設区分を選択してください"
        assert result["confidence"] == "needs_selection"
        assert result["url"] == ""
        assert result["matched_by"] == ["回線名"]
        assert "住設新築" in result["memo"]
        assert "住設賃貸" in result["memo"]
        assert "URL未確認" not in result["memo"]


def test_judge_script_route_jusetsu_category_confirms_new_or_existing_script():
    cases = [
        ("住設新築", "0099回線（住設新築）"),
        ("住設（新築）", "0099回線（住設新築）"),
        ("住設新設", "0099回線（住設新築）"),
        ("住設既築", "0099回線（住設既築）"),
        ("住設（既築）", "0099回線（住設既築）"),
        ("住設中古", "0099回線（住設既築）"),
        ("住設既築/中古", "0099回線（住設既築）"),
        ("住設賃貸", "0099回線（賃貸）"),
        ("住設（賃貸）", "0099回線（賃貸）"),
    ]
    for category, display_name in cases:
        result = app.judge_script_route(make_form(call_line="住設", appliance_category=category))

        assert result["display_name"] == display_name
        assert result["confidence"] == "high"
        assert result["url"]
        assert result["matched_by"] == ["回線名", "案件分類"]
        if display_name == "0099回線（賃貸）":
            assert "賃貸" in result["memo"]
        else:
            assert "URLは0099回線" in result["memo"]


def test_judge_script_route_business_category_routes_to_expected_scripts():
    cases = [
        (make_form(call_line="家電", appliance_category="家電"), "0099回線（家電/新築）"),
        (make_form(call_line="住設", appliance_category="住設（新築）"), "0099回線（住設新築）"),
        (make_form(call_line="住設", appliance_category="住設新設"), "0099回線（住設新築）"),
        (make_form(call_line="住設", appliance_category="住設既築/中古"), "0099回線（住設既築）"),
        (make_form(call_line="住設", appliance_category="住設（賃貸）"), "0099回線（賃貸）"),
        (make_form(call_line="住設", appliance_category="賃貸", appliance_type="住設"), "0099回線（賃貸）"),
        (make_form(call_line="住設", appliance_category="住設（既築）", warranty_plan="駆けつけ"), "0099回線（駆けつけ）"),
    ]
    for form, display_name in cases:
        result = app.judge_script_route(form)

        assert result["display_name"] == display_name
        assert result["confidence"] == "high"


def test_enabled_call_lines_route_to_script_or_selection_waiting():
    df = app.load_call_lines()
    enabled = df[df["enabled"].astype(str).str.strip() == "1"]
    assert not enabled.empty

    unresolved = []
    for _, row in enabled.iterrows():
        call_line = row.get("display_name") or row.get("call_line")
        line_group = row.get("line_group", "")
        form = make_form(
            call_line=call_line,
            appliance_category="家電" if line_group == "家電" else "",
            appliance_type="家電" if line_group == "家電" else "",
        )
        result = app.judge_script_route(form)
        if result["confidence"] == "none":
            unresolved.append(call_line)
            continue
        if not result.get("url"):
            assert result["confidence"] in ("needs_selection", "needs_url")

    assert unresolved == []


def test_judge_script_route_keihan_lines_use_dedicated_scripts():
    cases = [
        ("京阪不動産", "京阪不動産", "keihan_real_estate"),
        ("京阪不動産（浦添）", "京阪不動産（浦添）", "keihan_real_estate_urasoe"),
        ("京阪（夜間）", "京阪（夜間）", "keihan_night"),
        ("京阪大津", "京阪（夜間）", "keihan_night"),
    ]
    for call_line, display_name, script_key in cases:
        result = app.judge_script_route(make_form(call_line=call_line))

        assert result["script_key"] == script_key
        assert result["display_name"] == display_name
        assert result["confidence"] == "high"
        assert result["url"]
        assert result["matched_by"] == ["回線名"]


def test_judge_script_route_fukuya_and_mitsui_lines_use_dedicated_scripts():
    cases = [
        ("福屋工務店", "福屋工務店", "fukuya_ys"),
        ("三井デザイン", "三井デザイン", "mitsui_design"),
    ]
    for call_line, display_name, script_key in cases:
        result = app.judge_script_route(make_form(call_line=call_line))

        assert result["script_key"] == script_key
        assert result["display_name"] == display_name
        assert result["confidence"] == "high"
        assert result["url"]
        assert result["matched_by"] == ["回線名"]


def test_judge_script_route_yamada_homes_stays_on_generic_jusetsu_routes():
    cases = [
        ("住設（新築）", "0099回線（住設新築）"),
        ("住設（既築）", "0099回線（住設既築）"),
        ("住設（賃貸）", "0099回線（賃貸）"),
    ]
    for category, display_name in cases:
        result = app.judge_script_route(make_form(call_line="ヤマダホームズ", appliance_category=category))

        assert result["script_key"] != "yamada_homes"
        assert result["display_name"] == display_name
        assert result["confidence"] == "high"
        assert result["url"]


def test_judge_script_route_existing_dedicated_call_lines_are_preserved():
    cases = [
        (make_form(call_line="ビックカメラ"), "ビックカメラ・ソフマップ"),
        (make_form(call_line="ソフマップ"), "ビックカメラ・ソフマップ"),
        (make_form(call_line="コーナン（家電）", appliance_category="家電"), "コーナン家電"),
        (make_form(call_line="コーナン（住設）"), "コーナン住設"),
        (make_form(call_line="トライアルカンパニー", appliance_category="家電"), "トライアル/アークランズ"),
        (make_form(call_line="マッハユカコ"), "マッハ・YUCACO"),
        (make_form(call_line="なかやしき"), "なかやしき"),
        (make_form(call_line="駆けつけサブスク"), "0099回線（駆けつけ）"),
    ]
    for form, display_name in cases:
        result = app.judge_script_route(form)

        assert result["display_name"] == display_name
        assert result["confidence"] in ("high", "medium")
        assert result["url"]


def test_judge_script_route_jusetsu_kaketsuke_plan_overrides_base_script_with_reason():
    cases = ["駆けつけ", "24h", "24時間"]
    for warranty_plan in cases:
        result = app.judge_script_route(make_form(
            call_line="住設",
            appliance_category="住設（既築）",
            warranty_plan=warranty_plan,
        ))

        assert result["display_name"] == "0099回線（駆けつけ）"
        assert result["confidence"] == "high"
        assert result["matched_by"] == ["回線名", "保証プラン"]
        assert "駆けつけ条件" in result["correction_reason"]
        assert result["script_changed"] is True
        assert result["previous_script_display"] == "0099回線（住設既築）"


def test_judge_script_route_nakayashiki_matches_call_line_without_legacy_fallback():
    result = app.judge_script_route(make_form(call_line="なかやしき"))

    assert result["script_key"] == "nakayashiki"
    assert result["display_name"] == "なかやしき"
    assert result["url"]
    assert "回線名" in result["matched_by"]

    decision = app.run_decision(make_form(call_line="なかやしき"))
    info = app.build_script_reference_info(decision)
    assert info["script_key"] == "nakayashiki"
    assert info["display"] == "なかやしき"
    assert info["display"] != "住設受付"


def test_judge_script_route_nakayashiki_matches_store_name():
    result = app.judge_script_route(make_form(store_name="なかやしき"))

    assert result["script_key"] == "nakayashiki"
    assert result["display_name"] == "なかやしき"
    assert result["url"]
    assert "販売店" in result["matched_by"]


def test_judge_script_route_plan_only_is_medium_candidate_not_high():
    rental = app.judge_script_route(make_form(warranty_plan="賃貸住宅プラン"))
    assert rental["display_name"] == "0099回線（賃貸）"
    assert rental["confidence"] == "medium"
    assert "回線名" not in rental["matched_by"]
    assert "候補扱い" in rental["memo"]

    none = app.judge_script_route(make_form())
    assert none["display_name"] == "未判定"
    assert none["confidence"] == "none"


def test_judge_script_route_product_manufacturer_cancel_and_no_match_cases():
    cases = [
        (make_form(product="蓄電池"), "◆蓄電池（太陽光・V2H）", "high", True),
        (make_form(product="太陽光パネル"), "◆蓄電池（太陽光・V2H）", "high", True),
        (make_form(product="V2H"), "◆蓄電池（太陽光・V2H）", "high", True),
        (make_form(manufacturer="LG"), "LG", "high", True),
        (make_form(manufacturer="TOKAI"), "TOKAI", "high", True),
        (make_form(manufacturer="ジャパンネクスト"), "ジャパンネクストorグリーンハウス", "needs_url", False),
        (make_form(manufacturer="グリーンハウス"), "ジャパンネクストorグリーンハウス", "needs_url", False),
        (make_form(warranty_plan="解約希望"), "解約・返金スクリプト", "medium", True),
        (make_form(warranty_plan="返金相談"), "解約・返金スクリプト", "medium", True),
        (make_form(product="未登録製品", manufacturer="未登録メーカー"), "未判定", "none", False),
    ]
    for form, display_name, confidence, has_url in cases:
        result = app.judge_script_route(form)
        assert result["display_name"] == display_name
        assert result["confidence"] == confidence
        assert bool(result["url"]) is has_url


def test_script_reference_for_japannext_greenhouse_keeps_url_unconfirmed_candidate():
    decision = app.run_decision(make_form(manufacturer="JAPANNEXT"))
    info = app.build_script_reference_info(decision)

    assert info["display"] == "ジャパンネクストorグリーンハウス"
    assert info["confidence"] == "needs_url"
    assert info["matched"] is False
    assert info["url"] == ""
    assert "URL未確認" in info["message"]


def _script_tag_for_form(form: dict) -> tuple[dict, dict]:
    decision = app.run_decision(form)
    script_reference = app.build_script_reference_info(decision)
    tags = app.build_decision_tag_items(decision, form, script_reference)
    return tags[3], script_reference


def test_script_tag_uses_reference_route_for_kaden_lines():
    for call_line in ("家電", "家電回線"):
        script_tag, script_reference = _script_tag_for_form(make_form(call_line=call_line))

        assert script_reference["display"] == "0099回線（家電/新築）"
        assert script_tag["primary"] == "参照スクリプト"
        assert script_tag["secondary"] == "0099回線（家電/新築）"
        assert script_tag["secondary"] == script_reference["display"]
        assert script_tag["matched"] is True
        assert script_tag["color"] != app.TAG_COLOR_MISSING
        assert "根拠：回線名" in script_tag["tertiary"]
        assert script_tag["quaternary"] == "confidence: high"


def test_script_tag_uses_reference_route_for_jusetsu_lines_with_selection_waiting():
    for call_line in ("住設", "住設回線"):
        script_tag, script_reference = _script_tag_for_form(make_form(call_line=call_line))

        assert script_reference["display"] == "住設区分を選択してください"
        assert script_reference["confidence"] == "needs_selection"
        assert script_tag["primary"] == "参照スクリプト"
        assert script_tag["secondary"] == "住設区分を選択してください"
        assert script_tag["secondary"] == script_reference["display"]
        assert script_tag["matched"] is False
        assert script_tag["url"] == ""
        assert script_tag["color"] == app.TAG_COLOR_WARNING
        assert "住設新築 / 住設既築 / 住設賃貸" in script_tag["quaternary"]
        assert "URL未確認" not in script_tag["quaternary"]


def test_jusetsu_selection_waiting_keeps_upper_and_lower_script_display_in_sync():
    script_tag, script_reference = _script_tag_for_form(make_form(call_line="住設"))

    assert script_reference["display"] == "住設区分を選択してください"
    assert script_reference["current_script_display"] == "住設区分を選択してください"
    assert script_reference["confidence"] == "needs_selection"
    assert script_tag["secondary"] == script_reference["display"]
    assert script_tag["primary"] == "参照スクリプト"
    assert script_tag["primary"] != "未判定"
    assert script_tag["matched"] is False
    assert script_tag["color"] == app.TAG_COLOR_WARNING


def test_next_confirmation_prompts_jusetsu_category_selection():
    form = make_form(call_line="住設")
    decision = app.run_decision(form)
    sections = app.build_next_confirmation_sections(decision, form)

    assert "案件分類で「住設新築 / 住設既築 / 住設賃貸」を選択" in sections["call_required"]


def test_script_reference_marks_jusetsu_kaketsuke_script_change():
    decision = app.run_decision(make_form(
        call_line="住設",
        appliance_category="住設（既築）",
        warranty_plan="駆けつけ",
    ))
    info = app.build_script_reference_info(decision)

    assert info["display"] == "0099回線（駆けつけ）"
    assert info["current_script_display"] == "0099回線（駆けつけ）"
    assert info["previous_script_display"] == "0099回線（住設既築）"
    assert info["script_changed"] is True
    assert "駆けつけ条件" in info["correction_reason"]


def test_script_tag_shows_jusetsu_kaketsuke_correction_and_matches_reference_display():
    script_tag, script_reference = _script_tag_for_form(make_form(
        call_line="住設",
        appliance_category="住設（既築）",
        warranty_plan="駆けつけ",
    ))

    assert script_reference["display"] == "0099回線（駆けつけ）"
    assert script_tag["secondary"] == script_reference["display"]
    assert script_tag["secondary"] == "0099回線（駆けつけ）"
    assert "根拠：回線名 / 保証プラン" in script_tag["tertiary"]
    assert "補正理由：" in script_tag["quaternary"]
    assert "駆けつけ条件" in script_tag["quaternary"]
    assert script_tag["quinary"] == "confidence: high"


def test_script_tag_and_reference_show_nakayashiki_for_call_line():
    script_tag, script_reference = _script_tag_for_form(make_form(call_line="なかやしき"))

    assert script_reference["script_key"] == "nakayashiki"
    assert script_reference["display"] == "なかやしき"
    assert script_tag["secondary"] == "なかやしき"
    assert script_tag["secondary"] == script_reference["display"]
    assert script_tag["matched"] is True


def test_script_tag_does_not_fall_back_to_missing_when_line_route_exists_without_category():
    script_tag, script_reference = _script_tag_for_form(make_form(call_line="家電"))

    assert script_reference["confidence"] == "high"
    assert script_tag["primary"] == "参照スクリプト"
    assert script_tag["secondary"] == "0099回線（家電/新築）"
    assert script_tag["primary"] != "未判定"


def test_script_tag_missing_only_when_script_reference_confidence_none():
    decision = app.run_decision(make_form())
    script_reference = app.build_script_reference_info(decision)
    assert script_reference["confidence"] == "none"

    tags = app.build_decision_tag_items(decision, {}, script_reference)
    script_tag = tags[3]

    assert script_tag["title"] == "スクリプト"
    assert script_tag["primary"] == "未判定"
    assert script_tag["color"] == app.TAG_COLOR_MISSING


def test_appendix_repair_policy_manufacturer_and_condition_priority():
    ricoh_projector = app.run_decision(make_form(product="プロジェクター", manufacturer="リコー"))
    assert ricoh_projector["repair_type"] == "出張修理"

    yamazen_visit = app.run_decision(make_form(
        product="トースター",
        manufacturer="山善",
        extra_condition="取説に出張修理明記あり",
    ))
    assert yamazen_visit["repair_type"] == "出張修理"

    yamazen_carry_in = app.run_decision(make_form(
        product="トースター",
        manufacturer="山善",
        extra_condition="取説に出張修理明記なし",
    ))
    assert yamazen_carry_in["repair_type"] == "持込修理"


def test_appliance_category_maps_to_legacy_type_and_housing_phase():
    assert "住設（賃貸）" in app.APPLIANCE_CATEGORY_OPTIONS

    new_home = app.apply_appliance_category_to_form({"appliance_category": "住設（新築）"})
    assert new_home["appliance_type"] == "住設"
    assert new_home["housing_phase"] == "新築"

    existing_home = app.apply_appliance_category_to_form({"appliance_category": "住設（既築）"})
    assert existing_home["appliance_type"] == "住設"
    assert existing_home["housing_phase"] == "既築"

    rental_home = app.apply_appliance_category_to_form({"appliance_category": "住設（賃貸）"})
    assert rental_home["appliance_type"] == "住設"
    assert rental_home["housing_phase"] == "賃貸"

    home_appliance = app.apply_appliance_category_to_form({"appliance_category": "家電"})
    assert home_appliance["appliance_type"] == "家電"
    assert home_appliance["housing_phase"] == ""


def test_script_route_uses_call_line_and_appliance_category_without_repair_type_blocking():
    appliance = app.run_decision(make_form(call_line="家電", appliance_category="家電", product="電子レンジ"))
    assert appliance["script_result"]["sheet_name"] == "家電出張・持込・新築住設"
    assert appliance["script_result"]["part"] == "家電・出張修理"
    assert appliance["script_result"]["sheet_name"] != "要確認"

    new_home = app.run_decision(make_form(call_line="住設", appliance_category="住設（新築）", product="多機能便座"))
    assert new_home["script_result"]["display_name"] == "住設新築受付"
    assert new_home["working_form"]["appliance_type"] == "住設"
    assert new_home["working_form"]["housing_phase"] == "新築"

    existing_home = app.run_decision(make_form(call_line="住設", appliance_category="住設（既築）", product="多機能便座"))
    assert existing_home["script_result"]["part"] == "既築・中古住設受付"
    assert existing_home["working_form"]["housing_phase"] == "既築"


def test_initial_decision_tags_are_unjudged_with_missing_items():
    form = app.empty_form()
    decision = app.run_decision(form)
    script_reference = app.build_script_reference_info(decision)
    tags = app.build_decision_tag_items(decision, form, script_reference)

    assert [tag["primary"] for tag in tags] == ["未判定", "未判定", "未判定", "未判定"]
    assert all(tag["color"] == app.TAG_COLOR_MISSING for tag in tags)
    assert "保証期間" in tags[0]["secondary"]
    assert "製品" in tags[1]["secondary"]
    assert "住所/都道府県" in tags[2]["secondary"]
    assert "回線名" in tags[3]["secondary"]


def test_decision_tags_confirm_only_when_required_information_is_present():
    form = make_form(
        product="エアコン",
        manufacturer="ダイキン",
        model_number="AN123",
        prefecture="東京都",
        appliance_type="家電",
        call_line="家電",
        warranty_plan="A3_E2_一般家電延長保証【5年】",
        warranty_start_date="2026/01/01",
        warranty_end_date="2031/12/31",
    )
    decision = app.run_decision(form)
    script_reference = app.build_script_reference_info(decision)
    tags = app.build_decision_tag_items(decision, form, script_reference)

    assert tags[0]["primary"] == "保証期間内"
    assert tags[0]["color"] != app.TAG_COLOR_MISSING
    assert tags[1]["primary"] == "出張修理"
    assert tags[1]["color"] != app.TAG_COLOR_MISSING
    assert tags[2]["primary"]
    assert tags[2]["color"] != app.TAG_COLOR_MISSING
    assert tags[3]["primary"] == "参照スクリプト"
    assert tags[3]["secondary"] == "0099回線（家電/新築）"
    assert tags[3]["color"] != app.TAG_COLOR_MISSING


def test_repair_tag_shows_missing_manufacturer_and_model_when_needed():
    ac_form = make_form(product="エアコン", model_number="AN123")
    ac_decision = app.run_decision(ac_form)
    ac_repair_tag = app.build_decision_tag_items(ac_decision, ac_form)[1]
    assert ac_repair_tag["primary"] == "出張修理"
    assert "メーカー" not in ac_repair_tag["secondary"]
    assert ac_repair_tag["color"] != app.TAG_COLOR_MISSING

    printer_form = make_form(product="プリンター", manufacturer="キヤノン")
    printer_decision = app.run_decision(printer_form)
    printer_repair_tag = app.build_decision_tag_items(printer_decision, printer_form)[1]
    assert "型番" in printer_repair_tag["secondary"]


def test_vendor_tag_shows_missing_prefecture_when_vendor_needs_area():
    form = make_form(product="エアコン", manufacturer="ダイキン", model_number="AN123", appliance_type="家電")
    decision = app.run_decision(form)
    vendor_tag = app.build_decision_tag_items(decision, form)[2]

    assert vendor_tag["primary"] == "未判定"
    assert "都道府県" in vendor_tag["secondary"]


def test_call_line_is_not_auto_filled_from_copy_or_residential_evidence():
    form = app.apply_extracted_fields_to_form(
        {
            "plan": "アイ工務店_住宅設備機器【10年保証】",
            "genre": "(新品)住宅設備機器",
            "category": "システムキッチン",
            "series": "システムキッチン",
            "manufacturer": "パナソニック",
        },
        app.empty_form(),
    )
    decision = app.run_decision(form)

    assert form["call_line"] == ""
    assert decision["working_form"]["call_line"] == ""
    assert decision["working_form"]["appliance_type"] == "住設"


def test_manual_call_line_is_preserved_even_for_residential_case():
    form = make_form(
        call_line="家電保証対応業務（24時間）",
        appliance_type="家電",
        warranty_plan="アイ工務店_住宅設備機器【10年保証】",
        product="システムキッチン",
        series="システムキッチン",
        manufacturer="パナソニック",
    )
    decision = app.run_decision(form)

    assert decision["working_form"]["appliance_type"] == "住設"
    assert decision["working_form"]["call_line"] == "家電"


def test_next_confirmation_sections_collect_call_required_items():
    form = app.empty_form()
    decision = app.run_decision(form)
    sections = app.build_next_confirmation_sections(decision, form)

    assert sections["initial"] is True
    assert sections["call_required"] == ["回線名を選択", "保証情報を貼り付け"]
    assert "メーカーを確認" not in sections["call_required"]
    assert "型番を確認" not in sections["call_required"]
    assert "住所/都道府県を確認" not in sections["call_required"]


def test_next_confirmation_sections_after_paste_are_short_and_limited():
    form = make_form(product="エアコン")
    decision = app.run_decision(form)
    sections = app.build_next_confirmation_sections(decision, form)

    assert sections["initial"] is False
    assert "保証期間を確認" in sections["call_required"]
    assert "保証開始日・保証終了日を確認してください" not in sections["call_required"]
    assert "メーカーを確認" in sections["call_required"]
    assert "住所/都道府県を確認" in sections["call_required"]
    assert len(sections["call_required"]) <= 5


def test_next_confirmation_sections_dedupe_warranty_period():
    form = make_form(product="ドライヤー", manufacturer="パナソニック")
    decision = app.run_decision(form)
    sections = app.build_next_confirmation_sections(decision, form)

    assert sections["call_required"].count("保証期間を確認") == 1


def test_next_confirmation_sections_keep_detail_missing_by_area():
    form = make_form(product="エアコン")
    decision = app.run_decision(form)
    sections = app.build_next_confirmation_sections(decision, form)

    assert "detail_missing" in sections
    assert "受付可否" in sections["detail_missing"]
    assert "修理方針" in sections["detail_missing"]
    assert "拠点対応" in sections["detail_missing"]
    assert "スクリプト" in sections["detail_missing"]
    assert "warranty_start_date" in sections["detail_missing"]["受付可否"]
    assert "manufacturer" not in sections["detail_missing"]["修理方針"]


def test_missing_text_compacts_related_fields_for_tags():
    text = app._missing_text([
        "warranty_start_date",
        "warranty_end_date",
        "warranty_plan",
        "product_price",
        "prefecture",
        "address",
        "repair_type",
    ])

    assert text == "不足：保証期間 / 保証プラン / 商品価格 / 住所/都道府県 / 修理方針"


def test_next_confirmation_ui_uses_cards_and_collapsed_detail():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert "次にやること" in source
    assert "next-confirmation-cards" in source
    assert 'st.expander("不足項目の詳細を開く", expanded=False)' in source


def test_rakutel_heading_requires_manual_call_line_selection():
    blank_text = app._build_rakutel_text(app.empty_form(), "加入者", "")
    assert "【●●回線に入電】" in blank_text
    assert "未選択回線" not in blank_text

    form = app.empty_form()
    form["call_line"] = "家電保証対応業務（24時間）"
    selected_text = app._build_rakutel_text(form, "加入者", "")
    assert "【家電回線に入電】" in selected_text


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
    repair_diag = next(
        item for item in d["diagnostics"]["items"]
        if item["area"] == "修理形態判定"
    )
    cost_diag = next(
        item for item in d["diagnostics"]["items"]
        if item["area"] == "概算費用判定"
    )
    display = app.build_summary_card_display(d)

    check("TC17e 製品 → 腕時計", form["product"], "腕時計")
    check("TC17e 製品原文保持", form["product_original"], "腕時計（クォーツ）")
    check("TC17e メーカー → CASIO", form["manufacturer"], "CASIO")
    check("TC17e メーカー原文保持", form["manufacturer_original"], "CASIO（カシオ計算機）")
    check("TC17e 型番保持", form["model_number"], "WVA-M630D-7A2JF")
    check("TC17e 修理形態 → 要確認", d["repair_type"], "要確認")
    check("TC17e 腕時計理由", "腕時計ルール未登録 / 担当確認" in repair_reason, True)
    check("TC17e 確認項目 型番なし", "型番" in q_text, False)
    check("TC17e 確認項目 汎用メーカーなし", "\nメーカー\n" in f"\n{q_text}\n", False)
    check("TC17e 確認項目 汎用製品詳細なし", "製品詳細" in q_text, False)
    check("TC17e 確認項目 SV対応可否", "腕時計案件の対応可否をSV/担当へ確認" in q_text, True)
    check("TC17e 確認項目 スクリプトURL", "スクリプトURL未登録のため手動参照" in q_text, True)
    check("TC17e 修理形態カード 担当確認", display["repair"]["value"], "担当確認")
    check("TC17e 修理形態カード 腕時計SV", "腕時計はSV/担当確認" in display["repair"]["status"], True)
    check("TC17e 概算費用カード 理由", "腕時計は担当確認後に案内" in display["cost"]["status"], True)
    check("TC17e 参照スクリプト 腕時計", display["script_sheet"], "腕時計")
    check("TC17e 参照スクリプト SV担当確認", display["script_part"], "SV担当確認")
    check("TC17e 診断 修理形態 担当確認", repair_diag["title"], "修理形態: 担当確認")
    check("TC17e 診断 腕時計SV明示", "腕時計はSV/担当確認" in repair_diag["reason"], True)
    check("TC17e 診断 概算費用理由", "腕時計は担当確認後に案内" in cost_diag["reason"], True)


def test_tc17f_unknown_product_pending_is_not_watch_confirmation_display():
    d = app.run_decision(make_form(
        product="その他・要確認",
        manufacturer="CASIO",
        model_number="UNKNOWN-001",
    ))
    display = app.build_summary_card_display(d)
    repair_diag = next(
        item for item in d["diagnostics"]["items"]
        if item["area"] == "修理形態判定"
    )

    check("TC17f unknown 修理形態 → 要確認", d["repair_type"], "要確認")
    check("TC17f unknown card remains 要確認", display["repair"]["value"], "要確認")
    check("TC17f unknown not watch confirmation", display["watch_confirmation"], False)
    check("TC17f unknown no 腕時計SV reason", "腕時計はSV/担当確認" in repair_diag["reason"], False)


# ============================================================
# TC18: 販売店名に「ビックカメラ」→ 回線属性推定
# ============================================================

def test_tc18_bic_store_infer():
    d = app.run_decision(make_form(store_name="ビックカメラ新宿店"))
    check("TC18 ビック/ソフマップ属性 → True",
          d["inferred_call_line_attrs"]["is_bic_sofmap"], True)
    check("TC18 回線名は自動入力しない",
          d["inferred_call_line_attrs"]["call_line"], "")
    check("TC18 vendor は回線名未選択ではソフマップ確定しない",
          d["vendor"] != "ソフマップ修理センター", True)


# ============================================================
# TC19: 販売店名に「ソフマップ」→ 回線属性推定
# ============================================================

def test_tc19_sofmap_store_infer():
    d = app.run_decision(make_form(store_name="ソフマップAkiba"))
    check("TC19 ビック/ソフマップ属性 → True",
          d["inferred_call_line_attrs"]["is_bic_sofmap"], True)
    check("TC19 回線名は自動入力しない",
          d["inferred_call_line_attrs"]["call_line"], "")
    check("TC19 vendor は回線名未選択ではソフマップ確定しない",
          d["vendor"] != "ソフマップ修理センター", True)


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


def test_master_script_guidance_csv_exists_and_loads():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "master_script_guidance.csv")
    df = app.load_script_guidance_csv()

    assert os.path.exists(path)
    assert not df.empty
    assert "hearing_items" in df.columns


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


def test_normalize_template_code_preserves_0009_format():
    assert app.normalize_template_code("9") == "0009"
    assert app.normalize_template_code("09") == "0009"
    assert app.normalize_template_code("009") == "0009"
    assert app.normalize_template_code("0009") == "0009"


def test_residential_visit_natural_candidates_keep_0009_with_special_template():
    df_tpl = app.pd.DataFrame([
        {
            "priority": 10,
            "enabled": 1,
            "template_code": "0019",
            "category": "住設業務",
            "label": "【出張修理】住宅資材センター【メーカー保証期間】",
            "data_erase_required": "不要",
            "cost_guidance_allowed": "可",
            "notes": "",
        },
        {
            "priority": 20,
            "enabled": 1,
            "template_code": "009",
            "category": "家電保証対応業務（24時間）",
            "label": "【出張修理】自然故障",
            "data_erase_required": "不要",
            "cost_guidance_allowed": "可",
            "notes": "通常テンプレート",
        },
    ])
    form = make_form(
        call_line="住設",
        appliance_type="住設",
        store_name="日本ライフサポート",
        warranty_plan="fonl_IHクッキングヒーター【10年保証】",
        product="IHクッキングヒーター",
        series="IHクッキングヒーター",
        manufacturer="三菱電機",
    )
    form.update({
        "genre": "(新品)住宅設備機器",
        "category": "クッキングヒーター",
        "model_number": "CS-T316VSR",
        "wrt_no": "W001310000016",
    })

    selected = app.select_template_for_form(
        form,
        "出張修理",
        "fonl_IHクッキングヒーター【10年保証】",
        df_tpl,
        app.pd.DataFrame(columns=app._STORE_RULE_COLS),
    )
    candidates = selected["candidates"]
    labels_by_code = {item["template_code"]: item["label"] for item in candidates}

    assert selected["template_code"] == "0019"
    assert labels_by_code["0019"] == "【出張修理】住宅資材センター【メーカー保証期間】"
    assert labels_by_code["0009"] == "【出張修理】自然故障"
    assert [item["template_code"] for item in candidates] == ["0019", "0009"]


def test_tc_template_store_rules_loaded_and_match_required_stores():
    df = app.load_store_rules()
    assert not df.empty
    assert "store_keyword" in df.columns

    ai = app.match_store_template_rule(make_form(store_name="株式会社アイ工務店 大阪支店"), df)
    ai_short = app.match_store_template_rule(make_form(store_name="アイ工務店"), df)
    ai_operator = app.match_store_template_rule(
        dict(make_form(store_name="滋賀支店"), store_original="株式会社アイ工務店")
    )
    keihan = app.match_store_template_rule(make_form(store_name="京阪電鉄"), df)
    kabaya = app.match_store_template_rule(make_form(store_name="ライフデザイン・カバヤ株式会社 岡山中央展示場"), df)

    check("store rule アイ工務店 matched", ai["matched"], True)
    check("store rule アイ工務店 group", ai["template_group"], "上位5社")
    check("store rule アイ工務店 direct code", ai["template_code"], "0058")
    check("store rule アイ工務店 short matched", ai_short["matched"], True)
    check("store rule アイ工務店 operator matched", ai_operator["matched"], True)
    check("store rule 京阪電鉄 matched", keihan["matched"], True)
    check("store rule 京阪電鉄 group", keihan["template_group"], "上位5社")
    check("store rule ライフデザイン・カバヤ matched", kabaya["matched"], True)
    check("store rule ライフデザイン・カバヤ group", kabaya["template_group"], "上位5社")


def test_ai_koumuten_system_kitchen_case_uses_vendor_list_no7_fallback():
    form = make_form(
        product="システムキッチン",
        series="システムキッチン",
        manufacturer="パナソニック",
        prefecture="滋賀県",
        appliance_type="家電",
        store_name="滋賀支店",
        warranty_plan="アイ工務店_住宅設備機器【10年保証】",
        warranty_start_date="2022/03/30",
        warranty_end_date="2032/03/29",
    )
    form.update({
        "store_original": "株式会社アイ工務店",
        "genre": "(新品)住宅設備機器",
        "category": "システムキッチン",
        "model_number": "ラクシーナ2585 QSYW2585CCEL4",
        "wrt_no": "W017220010002",
        "address": "滋賀県大津市仰木の里四丁目15番21号",
    })

    decision = app.run_decision(form)
    selected = app.select_template_for_form(
        form,
        decision["repair_type"],
        form["warranty_plan"],
        app.load_template_codes(),
    )
    display = app.build_case_basic_template_display(form, decision["repair_type"])
    summary = app.build_after_call_template_vendor_summary(form, decision, selected)
    form.update({
        "template_code": selected["template_code"],
        "template_label": selected["label"],
    })
    memo = app._build_after_call_memo(
        form,
        decision["warranty_result"],
        decision["repair_type"],
        decision["vendor"],
        cost_estimate=decision["cost_estimate"],
    )
    script_reference = app.build_script_reference_info(decision)
    tags = app.build_decision_tag_items(decision, form, script_reference)
    repair_tag = next(tag for tag in tags if tag["title"] == "修理方針")
    vendor_tag = next(tag for tag in tags if tag["title"] == "拠点対応")
    script_tag = next(tag for tag in tags if tag["title"] == "スクリプト")
    teams_message = app._build_teams_chat_message(
        decision["working_form"],
        decision["vendor"],
        decision["vendor_result"].get("contact_type", ""),
    )

    check("AI工務店 appliance type inferred", decision["working_form"]["appliance_type"], "住設")
    check("AI工務店 repair type", decision["repair_type"], "出張修理")
    check("AI工務店 cost generic visit", decision["cost_estimate"], "5,000円～7,000円前後")
    check("AI工務店 cost can announce", decision["cost_result"]["can_announce_cost"], True)
    check("AI工務店 cost status", decision["cost_result"]["cost_status"], "confirmed")
    check("AI工務店 vendor", decision["vendor"], "ユナイトサービス㈱")
    check("AI工務店 vendor fallback csv", decision["vendor_result"]["matched"], True)
    check("AI工務店 vendor reason", decision["vendor_result"]["reason"], "依頼先一覧 No.7 上記以外・全国・全メーカー")
    assert "依頼先一覧 No.7" in decision["vendor_result"]["reason"]
    assert "上記以外" in decision["vendor_result"]["reason"]
    check("AI工務店 vendor escalation", decision["vendor_result"]["needs_escalation"], False)
    check("AI工務店 escalation does not mask cost", decision["cost_estimate"] != "未確定", True)
    check("AI工務店 vendor not branch name", decision["vendor"] != form["store_name"], True)
    check("AI工務店 vendor not escalation", decision["vendor"] != "担当エスカ（要確認）", True)
    check("AI工務店 template code", selected["template_code"], "0058")
    check("AI工務店 template label", selected["label"], "【出張修理】上位5社")
    check("AI工務店 after-call template reason", summary["template_reason"], "アイ工務店 上位5社テンプレート対象")
    check("AI工務店 after-call vendor reason", summary["vendor_reason"], "依頼先一覧 No.7 上記以外・全国・全メーカー")
    assert summary["template_reason"] != summary["vendor_reason"]
    assert "アイ工務店上位5社案件はユナイトサービスへ依頼" not in str(summary)
    assert "※修理キャンセル時の概算費用5,000円～7,000円前後" in memo
    check("AI工務店 repair tag primary", repair_tag["primary"], "出張修理")
    check("AI工務店 repair tag cost", repair_tag["secondary"], "5,000円～7,000円前後")
    check("AI工務店 vendor tag primary", vendor_tag["primary"], "ユナイトサービス㈱")
    check("AI工務店 vendor tag secondary", vendor_tag["secondary"], "確定")
    check("AI工務店 script tag primary", script_tag["primary"], "参照スクリプト")
    check("AI工務店 script tag matches reference", script_tag["secondary"], script_reference["display"])
    assert "ユナイトサービス㈱へFAX済み" in teams_message
    assert "担当確認依頼済み" not in teams_message
    assert "0058 【出張修理】上位5社" in display
    assert "運営会社：株式会社アイ工務店" in display
    assert "表示販売店：\n滋賀支店" in display
    assert "販売店テンプレート未登録：滋賀支店" not in display


def test_ai_koumuten_vendor_does_not_depend_on_direct_store_rule():
    rules = app.load_vendor_rules()
    enabled = rules[rules["enabled"].astype(str).str.strip().isin(["1", "True", "true"])]
    direct = enabled[
        enabled["store_keyword"].astype(str).str.contains("アイ工務店", na=False)
        & enabled["vendor_name"].astype(str).str.contains("ユナイトサービス", na=False)
    ]
    assert direct.empty


def test_ai_koumuten_extracted_residential_equipment_infers_jusetsu_and_store_template():
    form = app.apply_extracted_fields_to_form(
        {
            "operating_company": "株式会社アイ工務店",
            "store_name": "滋賀支店",
            "plan": "アイ工務店_住宅設備機器【10年保証】",
            "genre": "(新品)住宅設備機器",
            "category": "システムキッチン",
            "series": "システムキッチン",
            "manufacturer": "パナソニック",
        },
        app.empty_form(),
    )
    decision = app.run_decision(form)
    display = app.build_case_basic_template_display(form, decision["repair_type"])

    assert form["appliance_type"] == "住設"
    assert decision["working_form"]["appliance_type"] == "住設"
    assert "0058 【出張修理】上位5社" in display
    assert "運営会社：株式会社アイ工務店" in display
    assert "販売店テンプレート未登録：滋賀支店" not in display


def test_unregistered_jusetsu_script_shows_manual_reference_message():
    decision = {
        "repair_type": "出張修理",
        "cost_estimate": "5,000円～7,000円前後",
        "cost_result": {"cost_status": "confirmed", "can_announce_cost": True},
        "vendor_result": {"needs_escalation": False},
        "warranty_result": {"warranty_status": "active", "title": "保証期間内"},
        "working_form": {"appliance_type": "住設", "warranty_plan": ""},
        "repair_result": {},
        "normalized_product": "システムキッチン",
        "script_result": {
            "sheet_name": "未登録住設",
            "part": "未登録住設",
            "script_type": "通常",
            "display_name": "住設・出張修理",
            "price_guidance_allowed": True,
        },
    }

    info = app.build_script_reference_info(decision)

    assert info["matched"] is False
    assert info["display"] == "住設・出張修理"
    assert "住設スクリプト未登録" in info["message"]
    assert "家電・出張修理" not in info["label"]


def test_visit_vendor_list_no7_fallback_applies_to_generic_store():
    d = app.run_decision(make_form(
        store_name="通常販売店",
        product="システムキッチン",
        series="システムキッチン",
        manufacturer="パナソニック",
        prefecture="滋賀県",
        appliance_type="住設",
    ))

    assert d["repair_type"] == "出張修理"
    assert d["vendor"] == "ユナイトサービス㈱"
    assert d["vendor_result"]["needs_escalation"] is False
    assert d["vendor_result"]["reason"] == "依頼先一覧 No.7 上記以外・全国・全メーカー"


def test_visit_vendor_list_no7_fallback_does_not_override_priority_rules():
    bic = app.run_decision(make_form(call_line="ビックカメラ", product="冷蔵庫", prefecture="東京都"))
    sofmap = app.run_decision(make_form(call_line="ソフマップ", product="冷蔵庫", prefecture="東京都"))
    okinawa = app.run_decision(make_form(product="システムキッチン", manufacturer="パナソニック", prefecture="沖縄県"))
    east = app.run_decision(make_form(product="冷蔵庫", manufacturer="パナソニック", prefecture="東京都"))
    kyushu = app.run_decision(make_form(product="システムキッチン", manufacturer="パナソニック", prefecture="福岡県"))
    rental = app.run_decision(make_form(
        call_line="住設業務",
        product="システムキッチン",
        manufacturer="パナソニック",
        prefecture="東京都",
        appliance_type="住設",
        is_over_10years=False,
    ))

    assert bic["vendor"] == "ソフマップ修理センター"
    assert sofmap["vendor"] == "ソフマップ修理センター"
    assert okinawa["vendor"] == "宗建リノベーション"
    assert east["vendor"] == "WRT修理センター"
    assert "CER" in kyushu["vendor"]
    assert rental["vendor"] == "ユナイトサービス㈱"
    assert rental["vendor_result"]["reason"] == "賃貸東日本10年未満"


def test_tc_template_store_group_priority_over_normal_template():
    df_tpl = app.pd.DataFrame([
        {
            "priority": 10,
            "enabled": 1,
            "template_code": "0009",
            "category": "家電保証対応業務（24時間）",
            "label": "【出張修理】自然故障",
            "data_erase_required": "不要",
            "cost_guidance_allowed": "可",
            "notes": "",
        },
        {
            "priority": 10,
            "enabled": 1,
            "template_code": "0058",
            "category": "家電保証対応業務（24時間）",
            "label": "【出張修理】上位5社",
            "data_erase_required": "不要",
            "cost_guidance_allowed": "可",
            "notes": "上位5社テンプレート",
        },
    ])
    df_store = app.pd.DataFrame([
        {
            "priority": 10,
            "enabled": 1,
            "store_keyword": "アイ工務店",
            "normalized_store": "アイ工務店",
            "template_code": "",
            "template_label": "",
            "template_group": "上位5社",
            "notes": "上位5社テンプレート対象",
        },
        {
            "priority": 999,
            "enabled": 1,
            "store_keyword": "",
            "normalized_store": "",
            "template_code": "",
            "template_label": "",
            "template_group": "",
            "notes": "通常テンプレート",
        },
    ])
    form = make_form(call_line="家電保証対応業務（24時間）", store_name="アイ工務店")

    selected = app.select_template_for_form(form, "出張修理", "自然故障", df_tpl, df_store)

    check("store group selects 上位5社", selected["label"], "【出張修理】上位5社")
    check("store group selects code", selected["template_code"], "0058")
    check("store group source", selected["source"], "store_group")


def test_tc_template_no_store_rule_falls_back_to_legacy_auto_select():
    df_tpl = app.pd.DataFrame([
        {
            "priority": 10,
            "enabled": 1,
            "template_code": "0009",
            "category": "家電保証対応業務（24時間）",
            "label": "【出張修理】自然故障",
            "data_erase_required": "不要",
            "cost_guidance_allowed": "可",
            "notes": "",
        },
        {
            "priority": 10,
            "enabled": 1,
            "template_code": "0010",
            "category": "家電保証対応業務（24時間）",
            "label": "【出張修理】ダブルプロテクト",
            "data_erase_required": "不要",
            "cost_guidance_allowed": "可",
            "notes": "",
        },
    ])
    df_store = app.pd.DataFrame([
        {
            "priority": 999,
            "enabled": 1,
            "store_keyword": "",
            "normalized_store": "",
            "template_code": "",
            "template_label": "",
            "template_group": "",
            "notes": "通常テンプレート",
        },
    ])
    form = make_form(call_line="家電保証対応業務（24時間）", store_name="通常店舗")

    selected = app.select_template_for_form(form, "出張修理", "DP", df_tpl, df_store)

    check("store fallback uses legacy DP", selected["label"], "【出張修理】ダブルプロテクト")
    check("store fallback source", selected["source"], "fallback")
    check("store fallback not matched", selected["store_rule"]["matched"], False)


def test_tc_call_type_is_hidden_in_call_form_but_internal_key_remains():
    form = app.empty_form()
    check("call_type internal key remains", "call_type" in form, True)
    check("call_type UI hidden flag", app.SHOW_CALL_TYPE_IN_CALL_FORM, False)


def test_tc_call_line_options_from_csv():
    options = app.get_call_line_options()
    assert "ビックカメラ" in options
    assert "住設" in options
    assert "GIGA案件" not in options


def test_tc_call_line_options_loaded():
    options = app.get_call_line_options()
    assert "ビックカメラ" in options
    assert "住設" in options
    assert "京阪不動産" in options


def test_call_line_display_name_uses_home_appliance_business_and_alias_is_accepted():
    options = app.get_call_line_options()

    assert "家電" in options
    assert "家電保証対応業務（24時間）" not in options
    assert app.normalize_call_line_for_display("家電保証対応業務（24時間）") == "家電"
    assert app.normalize_call_line("家電業務") == "家電"
    assert app.get_call_line_display_name("家電保証対応業務（24時間）") == "家電"
    assert app.get_rakutel_line_name("家電保証対応業務（24時間）") == "家電"
    assert app.get_line_group("家電保証対応業務（24時間）") == "家電"


def test_auto_template_selection_accepts_old_call_line_alias():
    df_sample = app.pd.DataFrame([
        {
            "template_code": "0009",
            "category": "家電保証対応業務（24時間）",
            "label": "【出張修理】自然故障",
            "data_erase_required": "不要",
            "cost_guidance_allowed": "可",
            "notes": "",
        }
    ])

    assert app._auto_select_template("家電", "出張修理", "自然故障", df_sample) == "【出張修理】自然故障"


def test_call_line_rakutel_header_uses_rakutel_line_name_not_display_sentence():
    assert app.build_rakutel_call_header("家電保証対応業務（24時間）", "受電") == "【家電回線に入電】"
    assert app.build_rakutel_call_header("家電業務", "受電") == "【家電回線に入電】"
    assert app.build_rakutel_call_header("住設業務", "受電") == "【住設回線に入電】"
    assert app.build_rakutel_call_header("家電保証対応業務（24時間）", "架電") == "【家電回線から架電】"
    assert app.build_rakutel_call_header("コーナン商事（家電）", "受電") == "【コーナン（家電）回線に入電】"


def test_mach_yukako_aliases_normalize_to_correct_display_name():
    assert app.normalize_call_line("マッハのユカコ") == "マッハユカコ"
    assert app.normalize_call_line("マッハ・YUCACO") == "マッハユカコ"
    assert app.normalize_call_line("YUCACO") == "マッハユカコ"
    assert app.get_rakutel_line_name("YUCACO") == "マッハユカコ"


def test_call_line_home_appliance_does_not_confuse_appliance_type():
    form = make_form(
        call_line="家電保証対応業務（24時間）",
        appliance_type="家電",
        product="洗濯機",
        prefecture="東京都",
    )

    decision = app.run_decision(form)

    assert app.normalize_call_line(form["call_line"]) == "家電"
    assert form["appliance_type"] == "家電"
    assert decision["working_form"]["call_line"] == "家電"
    assert decision["working_form"]["appliance_type"] == "家電"


def test_tc_bic_camera_call_line_vendor():
    d = app.run_decision(make_form(call_line="ビックカメラ", product="洗濯機"))
    assert d["vendor"] == "ソフマップ修理センター"


def test_life_design_kabaya_dishwasher_visit_vendor_is_unite():
    d = app.run_decision(make_form(
        store_name="ライフデザイン・カバヤ株式会社 岡山中央展示場",
        prefecture="岡山県",
        product="食器洗い乾燥機",
        manufacturer="三菱電機",
        model_number="EW-45RD1SM",
        appliance_type="住設",
        warranty_plan="住宅設備機器保証パッケージ【10年保証】",
    ))

    assert d["repair_type"] == "出張修理"
    assert d["vendor"] == "ユナイトサービス㈱"
    assert d["vendor"] != "担当エスカ（要確認）"
    assert d["vendor_result"]["matched"] is True
    assert d["vendor_result"]["reason"] == "ライフデザイン・カバヤ通常出張"
    assert d["vendor_result"]["needs_escalation"] is False


def test_east_japan_fridge_aqua_visit_vendor_is_wrt():
    d = app.run_decision(make_form(
        product="冷蔵庫",
        manufacturer="アクア",
        prefecture="埼玉県",
        store_name="アート引越センター（浦和支店）",
    ))

    assert d["area_group"] == "NTT東日本"
    assert d["repair_type"] == "出張修理"
    assert d["vendor"] == "WRT修理センター"
    assert d["vendor_result"]["matched"] is True
    assert d["vendor_result"]["reason"] == "東日本×対象製品"
    assert d["vendor_result"]["needs_escalation"] is False
    assert app.resolve_teams_request_action(d["working_form"], d["vendor"]) == "依頼書PDF格納済み"


def test_east_japan_visit_vendor_list_no2_products_are_wrt():
    cases = [
        ("東京都", "冷蔵庫", "任意メーカー"),
        ("神奈川県", "洗濯機", "任意メーカー"),
        ("埼玉県", "電子レンジ", "任意メーカー"),
        ("千葉県", "マッサージチェア", "任意メーカー"),
    ]
    for prefecture, product, manufacturer in cases:
        d = app.run_decision(make_form(
            product=product,
            manufacturer=manufacturer,
            prefecture=prefecture,
            appliance_type="家電",
        ))
        assert d["area_group"] == "NTT東日本"
        assert d["repair_type"] == "出張修理"
        assert d["vendor"] == "WRT修理センター", (prefecture, product, d)
        assert d["vendor_result"]["matched"] is True
        assert d["vendor_result"]["reason"] in ("東日本×対象製品", "東京×洗濯機", "神奈川×洗濯機")


def test_visit_vendor_special_rules_still_win_over_east_japan_no2():
    kyushu = app.run_decision(make_form(product="冷蔵庫", manufacturer="アクア", prefecture="福岡県"))
    okinawa = app.run_decision(make_form(product="冷蔵庫", manufacturer="アクア", prefecture="沖縄県"))
    bic = app.run_decision(make_form(call_line="ビックカメラ", product="冷蔵庫", prefecture="東京都"))
    kabaya = app.run_decision(make_form(
        product="冷蔵庫",
        manufacturer="アクア",
        prefecture="岡山県",
        store_name="ライフデザイン・カバヤ株式会社 岡山中央展示場",
        appliance_type="家電",
    ))

    assert "CER" in kyushu["vendor"]
    assert kyushu["vendor_result"]["needs_escalation"] is True
    assert okinawa["vendor"] == "宗建リノベーション"
    assert bic["vendor"] == "ソフマップ修理センター"
    assert kabaya["vendor"] == "ユナイトサービス㈱"


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


def test_tc_dp_plan_detection_helper():
    check("DP helper 物損付", app.is_double_protect_plan("一般家電延長保証（物損付）【5年】"), True)
    check("DP helper DP5", app.is_double_protect_plan("一般家電延長保証（物損付）【5年】DP5"), True)
    check("DP helper normal", app.is_double_protect_plan("一般家電延長保証【5年】"), False)


def test_tc_dp_carry_in_script_display_uses_double_protect():
    d = app.run_decision(make_form(
        series="ドライヤー・ヘアアイロン",
        manufacturer="パナソニック",
        model_number="EH-NA0J-W",
        appliance_type="家電",
        warranty_plan="一般家電延長保証（物損付）【5年】DP5",
    ))
    script = d["script_result"]
    summary = app.build_summary_card_display(d)

    check("DP carry-in repair_type", d["repair_type"], "持込修理")
    check("DP carry-in script_type", script["script_type"], "ダブルプロテクト")
    check("DP carry-in display", script["display_name"], "ダブルプロテクト / 持込修理")
    check("DP carry-in card display", "ダブルプロテクト" in summary["script_display"], True)


def test_tc_dp_required_questions_include_amount_confirmation_once():
    form = make_form(
        product="ドライヤー",
        manufacturer="パナソニック",
        model_number="EH-NA0J-W",
        warranty_plan="DP5",
    )
    qs = app.build_required_questions(form, "持込修理", False)

    check("DP amount question exists", app.DOUBLE_PROTECT_AMOUNT_CONFIRMATION in qs, True)
    check("DP amount question once", qs.count(app.DOUBLE_PROTECT_AMOUNT_CONFIRMATION), 1)


def test_tc_dp_summary_separates_cost_and_damage_amount():
    d = app.run_decision(make_form(
        series="ドライヤー・ヘアアイロン",
        manufacturer="パナソニック",
        model_number="EH-NA0J-W",
        appliance_type="家電",
        warranty_plan="DP5",
    ))
    summary = app.build_summary_card_display(d)

    check("DP summary cost card keeps estimate", summary["cost"]["value"], d["cost_estimate"])
    check("DP summary amount status separate", summary["warranty"]["amount_status"], "システム確認")
    check("DP summary warranty mentions amount", "物損保証金額" in summary["warranty"]["status"], True)


def test_tc_dp_after_call_texts_include_dp_notes():
    form = make_form(
        product="ドライヤー",
        manufacturer="パナソニック",
        model_number="EH-NA0J-W",
        warranty_plan="DP5",
    )
    form.update(rakuteru_no="RT-1", call_line="家電保証対応業務（24時間）")
    texts = app._build_after_call_texts(
        form,
        app.determine_warranty_status(form),
        "持込修理",
        "WRT修理センター",
        "加入者",
        "",
    )

    check("DP attention memo note", "物損付 / DP案件" in texts["attention_memo"], True)
    check("DP rakutel note", "物損時の保証金額はシステムにて確認要" in texts["rakutel_text"], True)
    check("DP teams short note", "DP案件・保証金額確認要" in texts["teams_chat_message"], True)


def test_call_time_warning_product_missing_is_separate():
    d = app.run_decision(make_form(appliance_type="家電"))
    steps = app.build_next_action_steps(d["diagnostics"])

    assert "製品を入力してください" in steps
    assert not any("製品・案件分類を入力してSV確認" in step for step in steps)


def test_call_time_warning_product_missing_disappears_after_product_input():
    d = app.run_decision(make_form(product="ドライヤー", appliance_type="家電"))
    steps = app.build_next_action_steps(d["diagnostics"])

    assert "製品を入力してください" not in steps


def test_call_time_warning_appliance_type_missing_is_separate():
    d = app.run_decision(make_form(product="ドライヤー"))
    steps = app.build_next_action_steps(d["diagnostics"])

    assert "案件分類を入力してください" in steps
    assert not any("製品・案件分類を入力してSV確認" in step for step in steps)


def test_call_time_warning_appliance_type_missing_disappears_after_input():
    d = app.run_decision(make_form(product="ドライヤー", appliance_type="家電"))
    steps = app.build_next_action_steps(d["diagnostics"])

    assert "案件分類を入力してください" not in steps


def test_cer_escalation_remains_separate_from_missing_field_warnings():
    d = app.run_decision(make_form(
        product="エアコン",
        manufacturer="シャープ",
        appliance_type="家電",
        prefecture="福岡県",
        warranty_start_date="2026/01/01",
        warranty_end_date="2027/01/01",
    ))
    call_steps = app.build_next_action_steps(d["diagnostics"])
    after_steps = app.build_after_call_steps(d["diagnostics"])
    vendor_item = _diag_area(d["diagnostics"], "修理拠点判定")

    assert "製品を入力してください" not in call_steps
    assert "案件分類を入力してください" not in call_steps
    assert any("終話後に担当へエスカレーション" in step for step in after_steps)
    assert "CER" in d["vendor"]
    assert vendor_item["status"] == "warning"


def test_now_action_plan_shows_call_required_questions():
    form = make_form(
        product="エアコン",
        manufacturer="シャープ",
        model_number="AY-R22DM",
        appliance_type="家電",
        prefecture="東京都",
        warranty_start_date="2026/01/01",
        warranty_end_date="2027/01/01",
    )
    d = app.run_decision(form)
    plan = app.build_now_action_plan(
        form,
        d["repair_type"],
        d["needs_data_erase"],
        d["diagnostics"],
        d["warranty_result"],
        d["cost_result"],
    )

    labels = [item["label"] for item in plan["call_required"]]
    assert "具体的な症状" in labels
    assert "発生時期" in labels
    assert "発生頻度" in labels


def test_now_action_plan_removes_symptom_after_input():
    form = make_form(
        product="エアコン",
        manufacturer="シャープ",
        appliance_type="家電",
        warranty_start_date="2026/01/01",
        warranty_end_date="2027/01/01",
    )
    form["symptom_detail"] = "冷えない"
    d = app.run_decision(form)
    plan = app.build_now_action_plan(
        form, d["repair_type"], d["needs_data_erase"],
        d["diagnostics"], d["warranty_result"], d["cost_result"],
    )

    assert "具体的な症状" not in [item["label"] for item in plan["call_required"]]
    assert "具体的な症状" in [item["label"] for item in plan["completed"]]


def test_now_action_plan_removes_occurrence_time_after_input():
    form = make_form(
        product="エアコン",
        manufacturer="シャープ",
        appliance_type="家電",
        warranty_start_date="2026/01/01",
        warranty_end_date="2027/01/01",
    )
    form["occurrence_time"] = "昨日から"
    d = app.run_decision(form)
    plan = app.build_now_action_plan(
        form, d["repair_type"], d["needs_data_erase"],
        d["diagnostics"], d["warranty_result"], d["cost_result"],
    )

    assert "発生時期" not in [item["label"] for item in plan["call_required"]]
    assert "発生時期" in [item["label"] for item in plan["completed"]]


def test_now_action_plan_removes_occurrence_frequency_after_input():
    form = make_form(
        product="エアコン",
        manufacturer="シャープ",
        appliance_type="家電",
        warranty_start_date="2026/01/01",
        warranty_end_date="2027/01/01",
    )
    form["occurrence_frequency"] = "毎回"
    d = app.run_decision(form)
    plan = app.build_now_action_plan(
        form, d["repair_type"], d["needs_data_erase"],
        d["diagnostics"], d["warranty_result"], d["cost_result"],
    )

    assert "発生頻度" not in [item["label"] for item in plan["call_required"]]
    assert "発生頻度" in [item["label"] for item in plan["completed"]]


def test_manual_checked_item_moves_to_completed():
    form = make_form(
        product="エアコン",
        manufacturer="シャープ",
        appliance_type="家電",
        warranty_start_date="2026/01/01",
        warranty_end_date="2027/01/01",
    )
    d = app.run_decision(form)
    plan = app.build_now_action_plan(
        form, d["repair_type"], d["needs_data_erase"],
        d["diagnostics"], d["warranty_result"], d["cost_result"],
        {"occurrence_time": True},
    )

    assert "発生時期" not in [item["label"] for item in plan["call_required"]]
    assert "発生時期" in [item["label"] for item in plan["completed"]]


def test_manual_fallback_item_ids_include_stable_hash():
    item1 = app.build_check_item("補足確認", {}, None)
    item2 = app.build_check_item("追加確認", {}, None)

    assert item1["id"].startswith("manual_manual_item_")
    assert item2["id"].startswith("manual_manual_item_")
    assert item1["id"] != item2["id"]


def test_other_repair_requested_unknown_stays_in_now_action():
    form = make_form(
        product="エアコン",
        manufacturer="シャープ",
        appliance_type="家電",
        warranty_start_date="2026/01/01",
        warranty_end_date="2027/01/01",
    )
    form["other_repair_requested"] = "未確認"
    d = app.run_decision(form)
    plan = app.build_now_action_plan(
        form, d["repair_type"], d["needs_data_erase"],
        d["diagnostics"], d["warranty_result"], d["cost_result"],
    )

    assert "他窓口へ修理依頼済みか" in [item["label"] for item in plan["call_required"]]


def test_other_repair_requested_none_moves_to_completed():
    form = make_form(
        product="エアコン",
        manufacturer="シャープ",
        appliance_type="家電",
        warranty_start_date="2026/01/01",
        warranty_end_date="2027/01/01",
    )
    form["other_repair_requested"] = "なし"
    d = app.run_decision(form)
    plan = app.build_now_action_plan(
        form, d["repair_type"], d["needs_data_erase"],
        d["diagnostics"], d["warranty_result"], d["cost_result"],
    )

    assert "他窓口へ修理依頼済みか" not in [item["label"] for item in plan["call_required"]]
    assert "他窓口へ修理依頼済みか" in [item["label"] for item in plan["completed"]]


def test_other_repair_requested_yes_builds_warning():
    form = make_form()
    form["other_repair_requested"] = "あり"

    warning = app.build_other_repair_requested_warning(form)

    assert warning["title"] == "⚠️ 他窓口へ修理依頼済み"
    assert warning["reason"] == "重複受付・重複手配の可能性があります"
    assert "SV/担当" in warning["next_action"]


def test_question_categories_put_escalation_after_call():
    form = make_form(
        product="エアコン",
        manufacturer="シャープ",
        appliance_type="家電",
        prefecture="福岡県",
        warranty_start_date="2026/01/01",
        warranty_end_date="2027/01/01",
    )
    d = app.run_decision(form)
    categories = app.build_question_categories(
        form,
        d["repair_type"],
        d["needs_data_erase"],
        d["diagnostics"],
        d["warranty_result"],
        d["cost_result"],
    )

    assert any("終話後に担当へエスカレーションして拠点確定" in item
               for item in categories["after_call"])
    assert not any("終話後に担当へエスカレーションして拠点確定" in item["label"]
                   for item in categories["call_required"])


def test_missing_core_fields_are_call_required():
    form = make_form()
    d = app.run_decision(form)
    categories = app.build_question_categories(
        form,
        d["repair_type"],
        d["needs_data_erase"],
        d["diagnostics"],
        d["warranty_result"],
        d["cost_result"],
    )

    call_required = "\n".join(item["label"] for item in categories["call_required"])
    assert "製品" in call_required
    assert "メーカー" in call_required
    assert "案件分類" in call_required


def test_script_reference_info_for_independent_display():
    form = make_form(
        product="ドライヤー",
        manufacturer="パナソニック",
        appliance_type="家電",
        warranty_start_date="2026/01/01",
        warranty_end_date="2027/01/01",
    )
    d = app.run_decision(form)
    info = app.build_script_reference_info(d)

    assert info["title"] == "📘 参照スクリプト"
    assert info["script_type"]
    assert info["display"]
    assert " / " in info["label"]


def test_script_reference_info_unregistered_url_message():
    d = app.run_decision(make_form(
        product="腕時計",
        manufacturer="カシオ",
        appliance_type="家電",
        warranty_start_date="2026/01/01",
        warranty_end_date="2027/01/01",
    ))
    info = app.build_script_reference_info(d)

    assert info["matched"] is True
    assert info["script_type"] == "通常"
    assert info["url"]


def test_script_guidance_for_appliance_visit_repair():
    form = make_form(
        product="エアコン",
        manufacturer="シャープ",
        appliance_type="家電",
        warranty_start_date="2026/01/01",
        warranty_end_date="2027/01/01",
    )
    d = app.run_decision(form)
    reference = app.build_script_reference_info(d)
    guidance = app.build_script_guidance_panel_info(form, d, reference)

    assert guidance["matched"] is True
    assert guidance["official_script_label"] == "家電出張修理 該当箇所"
    assert "症状の詳細" in guidance["hearing_items"]
    assert "訪問先住所" in guidance["hearing_items"]


def test_script_guidance_hearing_items_feed_now_action_candidates():
    form = make_form(
        product="エアコン",
        manufacturer="シャープ",
        appliance_type="家電",
        warranty_start_date="2026/01/01",
        warranty_end_date="2027/01/01",
    )
    d = app.run_decision(form)
    guidance = app.build_script_guidance_panel_info(form, d)
    plan = app.build_now_action_plan(
        form, d["repair_type"], d["needs_data_erase"],
        d["diagnostics"], d["warranty_result"], d["cost_result"],
        {}, guidance["hearing_items"],
    )

    symptom_items = [item for item in plan["call_required"] if item["label"] == "具体的な症状"]
    assert symptom_items
    assert symptom_items[0]["source"] == "スクリプト補助"


def test_official_script_body_is_not_stored_in_guidance_master():
    df = app.load_script_guidance_csv()
    joined = "\n".join(
        " ".join(str(row.get(col, "")) for col in ["title", "hearing_items", "notes"])
        for _, row in df.iterrows()
    )

    assert "この度は" not in joined
    assert "お電話ありがとうございます" not in joined
    assert all(len(str(row.get("notes", ""))) < 120 for _, row in df.iterrows())


def test_script_reference_moved_into_decision_tags_panel():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert 'st.markdown("##### 📘 参照スクリプト")' not in source

    tags_panel_start = source.index("def render_decision_tags_panel")
    tags_panel_end = source.index("\ndef render_global_top_panels", tags_panel_start)
    tags_panel_source = source[tags_panel_start:tags_panel_end]

    assert '"url"' in tags_panel_source or "link" in tags_panel_source


def test_call_result_area_is_named_call_navigation():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    call_tab_start = source.index("def render_tab_call")
    call_tab_source = source[call_tab_start:]

    assert 'st.subheader("⚡ 通話中判定結果")' not in call_tab_source
    assert 'st.subheader("⚡ 通話中ナビ")' in call_tab_source


def test_decision_tags_are_split_structured_items():
    form = make_form(
        product="エアコン",
        manufacturer="シャープ",
        appliance_type="家電",
        warranty_start_date="2026/01/01",
        warranty_end_date="2027/01/01",
    )
    d = app.run_decision(form)
    tags = app.build_decision_tag_items(d, form)

    assert [tag["title"] for tag in tags] == ["受付可否", "修理方針", "拠点対応", "スクリプト"]
    assert all(" / " not in tag["title"] for tag in tags)
    assert all(tag["primary"] for tag in tags)
    assert all(tag["secondary"] for tag in tags)


def test_aircon_sharp_does_not_leave_manufacturer_confirmation():
    d = app.run_decision(make_form(
        product="エアコン",
        manufacturer="シャープ",
        manufacturer_original="",
        appliance_type="家電",
    ))
    rq = d["cost_result"].get("required_questions", "")
    steps = app.build_next_action_steps(d["diagnostics"])

    assert "メーカーを確認してください" not in rq
    assert "メーカーを確認してください" not in steps
    assert d["cost_result"]["cost_status"] == "confirmed"


def test_aircon_other_manufacturer_keeps_manufacturer_confirmation():
    d = app.run_decision(make_form(
        product="エアコン",
        manufacturer="その他・要確認",
        appliance_type="家電",
    ))

    assert "メーカーを確認してください" in d["cost_result"].get("required_questions", "")


def test_aircon_blank_manufacturer_keeps_manufacturer_confirmation():
    d = app.run_decision(make_form(product="エアコン", appliance_type="家電"))

    assert "メーカーを確認してください" in d["cost_result"].get("required_questions", "")


def test_empty_form_includes_call_memo():
    form = app.empty_form()

    assert "call_memo" in form
    assert form["call_memo"] == ""


def test_call_memo_does_not_affect_run_decision():
    base = make_form(
        product="ドライヤー",
        manufacturer="パナソニック",
        appliance_type="家電",
        prefecture="東京都",
        warranty_start_date="2026/01/01",
        warranty_end_date="2027/01/01",
    )
    with_memo = dict(base)
    with_memo["call_memo"] = "お客様が追加で話していた一時メモ"

    d1 = app.run_decision(base)
    d2 = app.run_decision(with_memo)

    for key in [
        "repair_type",
        "cost_estimate",
        "vendor",
        "normalized_product",
        "needs_data_erase",
        "overall_status",
    ]:
        assert d1[key] == d2[key]
    assert d1["cost_result"] == d2["cost_result"]
    assert d1["script_result"] == d2["script_result"]
    assert d1["diagnostics"] == d2["diagnostics"]


def test_tc_script_tag_includes_url_and_link_text():
    decision = {
        "warranty_result": {"warranty_status": "active"},
        "repair_type": "出張修理",
        "vendor": "WRT修理センター",
        "vendor_result": {"needs_escalation": False},
        "script_result": {"sheet_name": "家電・出張修理", "part": "該当箇所", "script_type": "通常",
                          "display_name": "家電出張修理", "price_guidance_allowed": True},
        "cost_result": {"cost_status": "confirmed"},
        "warranty_plan": "",
    }
    script_reference = app.build_script_reference_info(decision)
    script_reference.update({
        "matched": True,
        "url": "https://example.com/script",
        "confidence": "high",
        "display": "家電出張修理",
    })
    tags = app.build_decision_tag_items(decision, {}, script_reference)

    script_tag = tags[3]
    assert script_tag["title"] == "スクリプト"
    assert "url" in script_tag
    assert "link_text" in script_tag
    assert "matched" in script_tag


def test_tc_script_tag_matched_url_builds_open_link():
    decision = {
        "warranty_result": {"warranty_status": "active"},
        "repair_type": "出張修理",
        "vendor": "WRT修理センター",
        "vendor_result": {"needs_escalation": False},
        "script_result": {"sheet_name": "家電・出張修理", "part": "該当箇所", "script_type": "通常",
                          "display_name": "家電出張修理", "price_guidance_allowed": True},
        "cost_result": {"cost_status": "confirmed"},
        "warranty_plan": "",
    }
    script_reference = app.build_script_reference_info(decision)
    script_reference["matched"] = True
    script_reference["url"] = "https://example.com/script"
    script_reference["link_text"] = "家電出張修理"
    script_reference["confidence"] = "high"

    from unittest.mock import patch
    with patch("app.build_script_reference_info", return_value=script_reference):
        tags = app.build_decision_tag_items(decision, {}, script_reference)

    script_tag = tags[3]
    assert script_tag["matched"] is True
    assert script_tag["url"] == "https://example.com/script"
    assert "該当箇所を開く" in script_tag["link_text"]


def test_tc_script_tag_unmatched_shows_url_unregistered():
    decision = {
        "warranty_result": {"warranty_status": "active"},
        "repair_type": "出張修理",
        "vendor": "WRT修理センター",
        "vendor_result": {"needs_escalation": False},
        "script_result": {},
        "cost_result": {"cost_status": "confirmed"},
        "warranty_plan": "",
    }
    script_reference = app.build_script_reference_info(decision)
    script_reference["matched"] = False
    script_reference["url"] = ""

    tags = app.build_decision_tag_items(decision, {}, script_reference)

    script_tag = tags[3]
    assert script_tag["primary"] == "未判定"
    assert script_tag["color"] == app.TAG_COLOR_MISSING


def _make_acceptance_tag(product="洗濯機", warranty_plan="A3_E2_一般家電延長保証【5年】",
                          product_price="337,154円", warranty_status="active"):
    form = app.empty_form()
    form.update({"product": product, "warranty_plan": warranty_plan,
                 "product_price": product_price,
                 "warranty_start_date": "2026/01/01",
                 "warranty_end_date": "2031/12/31"})
    decision = {
        "warranty_result": {"warranty_status": warranty_status, "title": {
            "active": "保証期間内", "expired": "保証期間終了",
            "before_start": "保証開始日前", "unknown": "保証期間未確認",
        }.get(warranty_status, "保証期間未確認")},
        "repair_type": "",
        "vendor": "",
        "vendor_result": {},
        "script_result": {},
        "cost_result": {"cost_status": "confirmed"},
        "working_form": form,
    }
    tags = app.build_decision_tag_items(decision, form)
    return tags[0]


def test_tc_acceptance_tag_primary_is_warranty_status():
    tag = _make_acceptance_tag(warranty_status="active")
    assert tag["primary"] == "保証期間内"


def test_tc_acceptance_tag_primary_does_not_include_product():
    tag = _make_acceptance_tag(product="洗濯機", warranty_status="active")
    assert "洗濯機" not in tag["primary"]


def test_tc_acceptance_tag_secondary_is_product():
    tag = _make_acceptance_tag(product="洗濯機")
    assert tag["secondary"] == "洗濯機"


def test_tc_acceptance_tag_tertiary_is_warranty_plan():
    tag = _make_acceptance_tag(warranty_plan="A3_E2_一般家電延長保証【5年】")
    assert tag["tertiary"] == "A3_E2_一般家電延長保証【5年】"


def test_tc_acceptance_tag_quaternary_shows_product_price():
    tag = _make_acceptance_tag(product_price="337,154円")
    assert "337,154円" in tag["quaternary"]
    assert "商品価格" in tag["quaternary"]


def test_tc_acceptance_tag_no_combined_product_status_line():
    tag = _make_acceptance_tag(product="洗濯機", warranty_status="active")
    combined = tag.get("primary", "") + tag.get("secondary", "") + tag.get("tertiary", "") + tag.get("quaternary", "")
    assert "洗濯機　保証期間内" not in combined
    assert "保証期間内　洗濯機" not in combined


def test_tc_acceptance_tag_no_acceptance_label():
    tag = _make_acceptance_tag(warranty_status="active")
    combined = tag.get("primary", "") + tag.get("secondary", "") + tag.get("tertiary", "") + tag.get("quaternary", "")
    assert "受付判定へ進む" not in combined


def test_tc_acceptance_tag_empty_product_shows_unselected():
    tag = _make_acceptance_tag(product="")
    assert tag["secondary"] == "未選択"


def test_tc_acceptance_tag_empty_warranty_plan_shows_placeholder():
    tag = _make_acceptance_tag(warranty_plan="")
    assert tag["primary"] == "未判定"
    assert "保証プラン" in tag["secondary"]


def test_tc_acceptance_tag_empty_price_shows_placeholder():
    tag = _make_acceptance_tag(product_price="")
    assert tag["quaternary"] == "商品価格　未入力"


def test_tc_acceptance_tag_compact_flag_is_set():
    tag = _make_acceptance_tag()
    assert tag.get("compact") is True


def test_tc_acceptance_tag_compact_primary_uses_shared_css():
    """compact=True でも primary 行は共通CSSで太字かつ見切れない"""
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    compact_block_start = source.index("if compact and i == 0:")
    compact_block_end = source.index("elif i == 1:", compact_block_start)
    compact_primary_block = source[compact_block_start:compact_block_end]
    primary_css = source[source.index(".wrt-decision-tag-primary {"):source.index(".wrt-decision-tag-secondary {")]

    assert 'class="wrt-decision-tag-primary"' in compact_primary_block
    assert "font-weight: 800" in primary_css
    assert "font-size: 1.1rem" in primary_css
    assert "white-space: nowrap" in primary_css
    assert "-webkit-line-clamp" not in primary_css


# ── 今聞くことの根拠表示テスト ──

def test_now_action_source_not_rendered_in_ui():
    """render_now_action_item は source を UI に表示しない"""
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    func_start = source.index("def render_now_action_item(")
    # 次の def まで切り取る
    func_end = source.index("\ndef ", func_start + 1)
    func_source = source[func_start:func_end]
    assert '根拠：' not in func_source
    assert 'st.caption(f"根拠：' not in func_source


def test_now_action_source_field_exists_internally():
    """now_action_plan アイテムの source フィールドは内部データとして保持されてよい（文字列型）"""
    import app
    form = app.empty_form()
    form["product"] = "洗濯機"
    form["warranty_plan"] = "A3_E2_一般家電延長保証【5年】"
    now_actions = app.build_now_action_plan(
        form, "out_of_warranty", False
    )
    for item in now_actions.get("pending", []) + now_actions.get("done", []):
        if "source" in item:
            assert isinstance(item["source"], str)


# ── 色定数テスト ──

def test_tag_color_constants_defined():
    import app
    assert hasattr(app, "TAG_COLOR_OK")
    assert hasattr(app, "TAG_COLOR_WARNING")
    assert hasattr(app, "TAG_COLOR_ACTION")
    assert hasattr(app, "TAG_COLOR_DP")
    assert hasattr(app, "TAG_COLOR_ERROR")
    assert hasattr(app, "TAG_COLOR_NEUTRAL")


def test_tag_color_constants_used_in_build_decision_tag_items():
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    func_start = source.index("def build_decision_tag_items(")
    func_end = source.index("\ndef ", func_start + 1)
    func_source = source[func_start:func_end]
    # 少なくとも TAG_COLOR_ 系定数が使われていること
    assert "TAG_COLOR_" in func_source


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
    test_tc_template_store_rules_loaded_and_match_required_stores,
    test_tc_template_store_group_priority_over_normal_template,
    test_tc_template_no_store_rule_falls_back_to_legacy_auto_select,
    test_tc_call_type_is_hidden_in_call_form_but_internal_key_remains,
    test_tc_call_line_options_from_csv,
    test_tc_call_line_options_loaded,
    test_tc_bic_camera_call_line_vendor,
    test_life_design_kabaya_dishwasher_visit_vendor_is_unite,
    test_east_japan_fridge_aqua_visit_vendor_is_wrt,
    test_east_japan_visit_vendor_list_no2_products_are_wrt,
    test_visit_vendor_special_rules_still_win_over_east_japan_no2,
    test_tc_is_over_10years_rentals_tokyo,
    test_tc_is_under_10years_rentals_tokyo,
    test_tc_dp_plan_detection_helper,
    test_tc_dp_carry_in_script_display_uses_double_protect,
    test_tc_dp_required_questions_include_amount_confirmation_once,
    test_tc_dp_summary_separates_cost_and_damage_amount,
    test_tc_dp_after_call_texts_include_dp_notes,
    test_tc_script_tag_includes_url_and_link_text,
    test_tc_script_tag_matched_url_builds_open_link,
    test_tc_script_tag_unmatched_shows_url_unregistered,
    test_tc_acceptance_tag_primary_is_warranty_status,
    test_tc_acceptance_tag_primary_does_not_include_product,
    test_tc_acceptance_tag_secondary_is_product,
    test_tc_acceptance_tag_tertiary_is_warranty_plan,
    test_tc_acceptance_tag_quaternary_shows_product_price,
    test_tc_acceptance_tag_no_combined_product_status_line,
    test_tc_acceptance_tag_no_acceptance_label,
    test_tc_acceptance_tag_empty_product_shows_unselected,
    test_tc_acceptance_tag_empty_warranty_plan_shows_placeholder,
    test_tc_acceptance_tag_empty_price_shows_placeholder,
    test_tc_acceptance_tag_compact_flag_is_set,
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
