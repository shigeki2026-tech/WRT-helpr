# -*- coding: utf-8 -*-
"""Fixture-based integration tests for copied warranty screen text."""

import os
import sys
from pathlib import Path
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_st_mock = mock.MagicMock()
_st_mock.cache_data = lambda f: f
sys.modules["streamlit"] = _st_mock

import app  # noqa: E402


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def run_fixture(name: str):
    text = load_fixture(name)
    extracted = app.extract_fields_from_pasted_text(text)
    form = app.apply_extracted_fields_to_form(extracted, app.empty_form())
    decision = app.run_decision(form)
    return extracted, form, decision


def debug_payload(extracted: dict, form: dict, decision: dict) -> str:
    keys = [
        "warranty_start_date", "warranty_end_date", "customer_name",
        "phone_number", "address", "prefecture", "wrt_no", "product_price",
        "series", "manufacturer", "model_number", "store_name",
    ]
    extracted_part = {k: extracted.get(k) for k in keys if extracted.get(k)}
    form_part = {
        "product": form.get("product"),
        "manufacturer": form.get("manufacturer"),
        "manufacturer_original": form.get("manufacturer_original"),
        "prefecture": form.get("prefecture"),
        "model_number": form.get("model_number"),
    }
    decision_part = {
        "warranty_status": decision.get("warranty_status"),
        "can_accept": decision.get("can_accept"),
        "area_group": decision.get("area_group"),
        "repair_type": decision.get("repair_type"),
        "cost_estimate": decision.get("cost_estimate"),
        "vendor": decision.get("vendor"),
    }
    return f"extracted={extracted_part}\nform={form_part}\ndecision={decision_part}"


def test_case_dryer_active():
    extracted, form, decision = run_fixture("case_dryer_active.txt")

    assert extracted["series"] == "ドライヤー・ヘアアイロン"
    assert extracted["manufacturer"] == "Panasonic"
    assert form["product"] == "ドライヤー"
    assert form["manufacturer"] == "パナソニック"
    assert form["manufacturer_original"] == "Panasonic"
    assert form["prefecture"] == "滋賀県"
    assert decision["area_group"] == "NTT西日本"
    assert decision["warranty_status"] == "active"
    assert decision["repair_type"] == "持込修理"
    assert decision["cost_estimate"] == "2,000円～5,000円前後"


def test_case_aircon_before_start():
    extracted, form, decision = run_fixture("case_aircon_before_start.txt")

    assert extracted["warranty_start_date"] == "2028/05/01"
    assert form["product"] == "エアコン"
    assert form["manufacturer"] == "ダイキン"
    assert form["manufacturer_original"] == "DAIKIN"
    assert form["extra_condition"] == ""
    assert form["prefecture"] == "東京都"
    assert decision["area_group"] == "NTT東日本"
    assert decision["warranty_status"] == "before_start"
    assert decision["can_accept"] is False
    assert app.build_warranty_guidance(decision["warranty_result"]) == "メーカー保証または販売店・メーカー窓口へ誘導"
    assert decision["cost_estimate"] == "未確定"
    assert decision["cost_result"]["cost_status"] == "pending"


def test_case_pc_expired():
    extracted, form, decision = run_fixture("case_pc_expired.txt")

    assert extracted["warranty_start_date"] == "2020/01/01"
    assert extracted["warranty_end_date"] == "2026/04/26"
    assert form["product"] == "パソコン"
    assert form["manufacturer"] == "Dell"
    assert form["prefecture"] == "神奈川県"
    assert decision["warranty_status"] == "expired"
    assert decision["can_accept"] is False
    assert decision["repair_type"] == "持込修理"
    assert decision["cost_estimate"] == "12,000円前後"
    assert app.build_warranty_guidance(decision["warranty_result"]) == "保証期間終了のため受付不可"


def test_case_bic_camera_active():
    extracted, form, decision = run_fixture("case_bic_camera_active.txt")

    assert extracted["store_name"] == "ビックカメラ新宿店"
    assert form["product"] == "洗濯機"
    assert form["manufacturer"] == "パナソニック"
    assert decision["inferred_call_line_attrs"]["call_line"] == "ビックカメラ"
    assert decision["vendor"] == "ソフマップ修理センター"
    assert decision["script_result"]["price_guidance_allowed"] is False
    assert decision["warranty_status"] == "active"


def test_case_unknown_missing_dates():
    extracted, form, decision = run_fixture("case_unknown_missing_dates.txt")

    assert "warranty_start_date" not in extracted
    assert "warranty_end_date" not in extracted
    assert form["product"] == "洗濯機"
    assert form["manufacturer"] == "パナソニック"
    assert decision["warranty_status"] == "unknown"
    assert decision["can_accept"] is False
    assert "保証開始日・保証終了日" in decision["warranty_result"]["required_questions"]


def test_case_variation_colon_labels():
    extracted, form, decision = run_fixture("case_variation_colon_labels.txt")
    dbg = debug_payload(extracted, form, decision)

    assert extracted["warranty_start_date"] == "2026/01/01", dbg
    assert form["product"] == "エアコン", dbg
    assert form["manufacturer"] == "ダイキン", dbg
    assert form["prefecture"] == "滋賀県", dbg
    assert decision["area_group"] == "NTT西日本", dbg
    assert decision["warranty_status"] == "active", dbg


def test_case_variation_space_labels():
    extracted, form, decision = run_fixture("case_variation_space_labels.txt")
    dbg = debug_payload(extracted, form, decision)

    assert extracted["warranty_start_date"] == "2026/01/01", dbg
    assert form["product"] == "ドライヤー", dbg
    assert form["manufacturer"] == "パナソニック", dbg
    assert form["manufacturer_original"] == "Panasonic", dbg
    assert decision["warranty_status"] == "active", dbg
    assert decision["repair_type"] == "持込修理", dbg


def test_case_variation_alt_labels():
    extracted, form, decision = run_fixture("case_variation_alt_labels.txt")
    dbg = debug_payload(extracted, form, decision)

    assert extracted["phone_number"] == "03-1234-5678", dbg
    assert extracted["address"] == "東京都新宿区西新宿1-1-1", dbg
    assert form["prefecture"] == "東京都", dbg
    assert extracted["warranty_end_date"] == "2030/12/31", dbg
    assert form["product"] == "パソコン", dbg
    assert form["manufacturer"] == "Dell", dbg
    assert form["model_number"] == "XPS13", dbg
    assert decision["warranty_status"] == "active", dbg


def test_case_ecocute_daikin_active():
    extracted, form, decision = run_fixture("case_ecocute_daikin_active.txt")
    dbg = debug_payload(extracted, form, decision)

    assert form["product"] == "エコキュート", dbg
    assert form["manufacturer"] == "ダイキン", dbg
    assert decision["repair_type"] == "出張修理", dbg
    assert decision["cost_estimate"] == "15,000円～20,000円前後", dbg
    assert decision["area_group"] == "NTT西日本", dbg
    assert decision["warranty_status"] == "active", dbg


def test_case_airdog_active():
    extracted, form, decision = run_fixture("case_airdog_active.txt")
    dbg = debug_payload(extracted, form, decision)

    assert form["product"] == "Airdog", dbg
    assert decision["repair_type"] == "持込修理", dbg
    assert decision["cost_estimate"] == "7,000円～10,000円前後", dbg


def test_case_pioneer_av_active():
    extracted, form, decision = run_fixture("case_pioneer_av_active.txt")
    dbg = debug_payload(extracted, form, decision)

    assert form["product"] == "AV製品", dbg
    assert form["manufacturer"] == "パイオニア", dbg
    assert decision["cost_estimate"] == "16,000円前後", dbg
    assert decision["cost_result"]["needs_escalation"] is True, dbg
