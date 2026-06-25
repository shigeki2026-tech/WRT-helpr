# -*- coding: utf-8 -*-

import os
import sys
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_st_mock = mock.MagicMock()
_st_mock.cache_data = lambda f: f
sys.modules["streamlit"] = _st_mock

import app  # noqa: E402


class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


AI_KOUMUTEN_MULTI_PRODUCT_TEXT = """■プラン詳細
販売店情報
運営会社	株式会社アイ工務店	販売店	阪神支店
顧客情報
お名前（漢字）	山田太郎	お電話番号	090-1111-2222	ご住所	大阪府大阪市北区梅田1-1-1
製品情報
WRT-NO	W026700099999
支払金額	0円
プラン
システムキッチン【10年保証】
商品価格	0円
ジャンル	住宅設備	分類	システムキッチン
シリーズ	ラクシーナ アイランド型 2596	メーカー	パナソニック
型番		製造番号	
プラン
24時間換気システム【10年保証】
商品価格	0円
ジャンル	住宅設備	分類	24時間換気システム
シリーズ	24時間換気システム	メーカー	協立エアテック
型番	24HEA-TVA6D-K	製造番号	
プラン
24時間換気システム【10年保証】(2)
商品価格	0円
ジャンル	住宅設備	分類	24時間換気システム
シリーズ	24時間換気システム	メーカー	協立エアテック
型番	24HEA-TVA6D-K	製造番号	
プラン
インターホン【10年保証】
商品価格	0円
ジャンル	住宅設備	分類	ドアホン
シリーズ	インターホン	メーカー	アイホン
型番	JQ-12E	製造番号	
プラン
システムバス【10年保証】
商品価格	0円
ジャンル	住宅設備	分類	システムバス
シリーズ	オフローラ 1616AL	メーカー	パナソニック
型番		製造番号	
プラン
多機能便座【10年保証】
商品価格	0円
ジャンル	住宅設備	分類	多機能便座
シリーズ	多機能便座	メーカー	LIXIL
型番	BC-BL10S/BW1 DT-BL113G/BW1	製造番号	
プラン
多機能便座【10年保証】(2)
商品価格	0円
ジャンル	住宅設備	分類	多機能便座
シリーズ	多機能便座	メーカー	LIXIL
型番	BC-BA20S/BW1 DT-BA283G/BW1	製造番号	
プラン
洗面化粧台【10年保証】
商品価格	0円
ジャンル	住宅設備	分類	洗面化粧台
シリーズ	シーライン W=1200	メーカー	パナソニック
型番		製造番号	
プラン
給湯器【10年保証】
商品価格	0円
ジャンル	住宅設備	分類	エコキュート
シリーズ	エコキュート	メーカー	コロナ
型番	CHP-46AY1	製造番号	
プラン
食器洗い機【10年保証】
商品価格	0円
ジャンル	住宅設備	分類	食器洗い乾燥機
シリーズ	食器洗い乾燥機	メーカー	パナソニック
型番	QSS45RD7SD	製造番号	
"""


def test_extract_product_items_from_ai_koumuten_clipboard_extracts_ten_blocks():
    items = app.extract_product_items_from_pasted_text(AI_KOUMUTEN_MULTI_PRODUCT_TEXT)

    assert len(items) == 10
    labels = [item["attached_plan_name"] for item in items]
    assert "システムキッチン【10年保証】" in labels
    assert "24時間換気システム【10年保証】" in labels
    assert "24時間換気システム【10年保証】(2)" in labels
    assert "インターホン【10年保証】" in labels
    assert "システムバス【10年保証】" in labels
    assert "多機能便座【10年保証】" in labels
    assert "多機能便座【10年保証】(2)" in labels
    assert "洗面化粧台【10年保証】" in labels
    assert "給湯器【10年保証】" in labels
    assert "食器洗い機【10年保証】" in labels
    assert items[1]["model_number"] == "24HEA-TVA6D-K"
    assert items[2]["model_number"] == "24HEA-TVA6D-K"


def test_product_item_selection_reflects_selected_product_and_preserves_case_fields():
    extracted = app.extract_fields_from_pasted_text(AI_KOUMUTEN_MULTI_PRODUCT_TEXT)
    form = app.empty_form()
    form.update({
        "call_memo": "既存聴取内容",
        "attention_memo": "既存メモ",
    })
    form = app.apply_extracted_fields_to_form(extracted, form)

    assert len(form["product_items"]) == 10
    assert form["wrt_no"] == "W026700099999"
    assert form["store_name"] == "阪神支店"
    assert form["model_number"] == ""

    ecocute = app.apply_product_item_to_form(form["product_items"][8], form)
    assert ecocute["product"] == "エコキュート"
    assert ecocute["series"] == "エコキュート"
    assert ecocute["manufacturer"] == "コロナ"
    assert ecocute["model_number"] == "CHP-46AY1"
    assert ecocute["wrt_no"] == "W026700099999"
    assert ecocute["store_name"] == "阪神支店"
    assert ecocute["call_memo"] == "既存聴取内容"
    assert ecocute["attention_memo"] == "既存メモ"

    dishwasher = app.apply_product_item_to_form(form["product_items"][9], ecocute)
    assert dishwasher["product"] == "食器洗い乾燥機"
    assert dishwasher["manufacturer"] == "パナソニック"
    assert dishwasher["model_number"] == "QSS45RD7SD"
    assert dishwasher["wrt_no"] == "W026700099999"
    assert dishwasher["call_memo"] == "既存聴取内容"


def test_apply_product_item_clears_previous_product_scoped_values():
    form = app.empty_form()
    form.update({
        "call_line": "なかやしき",
        "manual_call_line": True,
        "store_name": "阪神支店",
        "wrt_no": "W026700099999",
        "customer_name": "山田太郎",
        "phone_number": "090-1111-2222",
        "address": "大阪府大阪市北区梅田1-1-1",
        "prefecture": "大阪府",
        "warranty_start_date": "2026/06/01",
        "warranty_end_date": "2036/05/31",
        "product": "エコキュート",
        "product_original": "エコキュート",
        "product_price": "100,000円",
        "genre": "住宅設備",
        "category": "エコキュート",
        "series": "エコキュート",
        "manufacturer": "コロナ",
        "manufacturer_original": "コロナ",
        "model_number": "CHP-46AY1",
        "serial_number": "SERIAL-1",
        "attached_plan_name": "給湯器【10年保証】",
        "appliance_type": "住設",
        "appliance_category": "住設（既築）",
        "housing_phase": "既築",
    })
    next_item = {
        "attached_plan_name": "システムキッチン【10年保証】",
        "product_price": "0円",
        "genre": "住宅設備",
        "category": "システムキッチン",
        "series": "ラクシーナ",
        "manufacturer": "パナソニック",
        "model_number": "",
        "serial_number": "",
        "product_original": "ラクシーナ",
        "product": "システムキッチン",
    }

    merged = app.apply_product_item_to_form(next_item, form)

    assert merged["product"] == "システムキッチン"
    assert merged["product_original"] == "ラクシーナ"
    assert merged["product_price"] == "0円"
    assert merged["manufacturer"] == "パナソニック"
    assert merged["manufacturer_original"] == "パナソニック"
    assert merged["model_number"] == ""
    assert merged["serial_number"] == ""
    assert merged["attached_plan_name"] == "システムキッチン【10年保証】"
    assert merged["appliance_type"] == "住設"
    assert merged["call_line"] == "なかやしき"
    assert merged["manual_call_line"] is True
    assert merged["store_name"] == "阪神支店"
    assert merged["wrt_no"] == "W026700099999"
    assert merged["customer_name"] == "山田太郎"
    assert merged["phone_number"] == "090-1111-2222"
    assert merged["address"] == "大阪府大阪市北区梅田1-1-1"
    assert merged["prefecture"] == "大阪府"
    assert merged["warranty_start_date"] == "2026/06/01"
    assert merged["warranty_end_date"] == "2036/05/31"


def test_selecting_toilet_faucet_product_item_does_not_keep_toilet_seat_widget_value():
    form = app.empty_form()
    form.update({
        "product": "多機能便座",
        "product_original": "多機能便座",
        "manufacturer": "その他・要確認",
        "manufacturer_original": "LIXIL",
        "warranty_start_date": "2026/01/01",
        "warranty_end_date": "2036/12/31",
        "product_items": [
            {
                "attached_plan_name": "多機能便座【10年保証】",
                "product_price": "0円",
                "genre": "住宅設備",
                "category": "多機能便座",
                "series": "多機能便座",
                "manufacturer": "LIXIL",
                "model_number": "",
                "serial_number": "",
                "product_original": "多機能便座",
                "product": "多機能便座",
            },
            {
                "attached_plan_name": "トイレ水栓【10年保証】",
                "product_price": "0円",
                "genre": "住宅設備",
                "category": "トイレ水栓",
                "series": "トイレ水栓",
                "manufacturer": "国内メーカー",
                "model_number": "",
                "serial_number": "",
                "product_original": "トイレ水栓",
                "product": "その他・要確認",
            },
        ],
        "selected_product_item_index": 0,
    })
    revision = 0
    product_key = app.case_basic_widget_key("product", revision)
    manufacturer_key = app.case_basic_widget_key("manufacturer", revision)
    price_key = app.case_basic_widget_key("product_price", revision)
    state = SessionState({
        "case_basic_revision": revision,
        product_key: "多機能便座",
        manufacturer_key: "その他・要確認",
        price_key: "0",
        "_case_basic_widget_synced_values": {
            product_key: "多機能便座",
            manufacturer_key: "その他・要確認",
            price_key: "0",
        },
    })

    selected = app.apply_product_item_to_form(form["product_items"][1], form)
    selected["selected_product_item_index"] = 1
    app.sync_case_basic_product_item_widgets(state, selected)
    synced = app.sync_global_case_basic_widget_state(selected, state)
    decision = app.run_decision(synced)

    assert selected["product_original"] == "トイレ水栓"
    assert selected["product"] != "多機能便座"
    assert selected["manufacturer_original"] == "国内メーカー"
    assert synced["product"] != "多機能便座"
    assert state[product_key] == synced["product"]
    assert decision["normalized_product"] == "トイレ水栓"
    assert "ビルトイン" not in decision["repair_result"].get("reason", "")


def test_selecting_system_bath_faucet_keeps_product_and_manufacturer_originals_separate():
    form = app.empty_form()
    form.update({
        "product": "多機能便座",
        "product_original": "多機能便座",
        "manufacturer": "その他・要確認",
        "manufacturer_original": "LIXIL",
        "product_items": [
            {
                "attached_plan_name": "多機能便座【10年保証】",
                "product_price": "0円",
                "genre": "住宅設備",
                "category": "多機能便座",
                "series": "多機能便座",
                "manufacturer": "LIXIL",
                "model_number": "",
                "serial_number": "",
                "product_original": "多機能便座",
                "product": "多機能便座",
            },
            {
                "attached_plan_name": "システムバス混合水栓",
                "product_price": "0円",
                "genre": "住宅設備",
                "category": "システムバス混合水栓",
                "series": "水栓",
                "manufacturer": "国内メーカー",
                "model_number": "",
                "serial_number": "",
                "product_original": "国内メーカー",
                "product": "その他・要確認",
            },
        ],
        "selected_product_item_index": 0,
    })

    assert app.product_item_option_label(form["product_items"][1], 10) == "製品10: システムバス混合水栓 / 国内メーカー / 水栓"

    selected = app.apply_product_item_to_form(form["product_items"][1], form)
    selected["selected_product_item_index"] = 1
    decision = app.run_decision(selected)
    candidate = app.build_master_registration_candidate(selected, decision)

    assert selected["product_original"] in ("システムバス混合水栓", "水栓")
    assert selected["manufacturer_original"] == "国内メーカー"
    assert selected["product"] != "多機能便座"
    assert selected["product_original"] != "国内メーカー"
    assert "水栓" in candidate["product_alias"]["keyword"]


def test_appliance_category_normalization_recovers_residential_phase():
    assert app.normalize_appliance_category("", "住設", "既築") == "住設（既築）"
    assert app.normalize_appliance_category("", "住設", "新築") == "住設（新築）"
    assert app.normalize_appliance_category("", "住設", "賃貸") == "住設（賃貸）"
    assert app.normalize_appliance_category("住設", "", "既築") == "住設（既築）"


def test_extract_labeled_residential_phase_restores_appliance_category():
    text = """回線名\tコーナン住設
案件分類\t住設
住設区分\t既築
製品\t水栓
メーカー\t国内メーカー
商品価格\t0円
"""
    extracted = app.extract_fields_from_pasted_text(text)
    form = app.apply_extracted_fields_to_form(extracted, app.empty_form())

    assert extracted["appliance_category"] == "住設"
    assert extracted["housing_phase"] == "既築"
    assert form["appliance_category"] == "住設（既築）"
    assert form["appliance_type"] == "住設"
    assert form["housing_phase"] == "既築"


def test_selecting_faucet_product_item_preserves_residential_category_and_price():
    form = app.empty_form()
    form.update({
        "call_line": "コーナン住設",
        "appliance_type": "住設",
        "appliance_category": "住設（既築）",
        "housing_phase": "既築",
        "product": "多機能便座",
        "product_original": "多機能便座",
        "manufacturer": "その他・要確認",
        "manufacturer_original": "LIXIL",
        "product_price": "120,000円",
        "product_items": [
            {
                "attached_plan_name": "多機能便座【10年保証】",
                "product_price": "120,000円",
                "genre": "住宅設備",
                "category": "多機能便座",
                "series": "多機能便座",
                "manufacturer": "LIXIL",
                "model_number": "",
                "serial_number": "",
                "product_original": "多機能便座",
                "product": "多機能便座",
                "appliance_type": "",
                "appliance_category": "",
                "housing_phase": "",
            },
            {
                "attached_plan_name": "システムバス混合水栓",
                "product_price": "0円",
                "genre": "住宅設備",
                "category": "システムバス混合水栓",
                "series": "水栓",
                "manufacturer": "国内メーカー",
                "model_number": "",
                "serial_number": "",
                "product_original": "システムバス混合水栓",
                "product": "その他・要確認",
                "appliance_type": "",
                "appliance_category": "",
                "housing_phase": "",
            },
        ],
        "selected_product_item_index": 0,
    })
    revision = 0
    state = SessionState({
        "case_basic_revision": revision,
        app.case_basic_widget_key("appliance_category", revision): "住設（既築）",
        app.case_basic_widget_key("product", revision): "多機能便座",
        app.case_basic_widget_key("manufacturer", revision): "その他・要確認",
        app.case_basic_widget_key("product_price", revision): "120,000",
        "_case_basic_widget_synced_values": {
            app.case_basic_widget_key("appliance_category", revision): "住設（既築）",
            app.case_basic_widget_key("product", revision): "多機能便座",
            app.case_basic_widget_key("manufacturer", revision): "その他・要確認",
            app.case_basic_widget_key("product_price", revision): "120,000",
        },
    })

    selected = app.apply_product_item_to_form(form["product_items"][1], form)
    selected["selected_product_item_index"] = 1
    app.sync_case_basic_product_item_widgets(state, selected)
    synced = app.sync_global_case_basic_widget_state(selected, state)

    assert selected["appliance_category"] == "住設（既築）"
    assert selected["appliance_type"] == "住設"
    assert selected["housing_phase"] == "既築"
    assert selected["product"] == "水栓"
    assert selected["manufacturer_original"] == "国内メーカー"
    assert selected["product_price"] == "0円"
    assert synced["appliance_category"] == "住設（既築）"
    assert synced["product"] == "水栓"
    assert synced["manufacturer_original"] == "国内メーカー"
    assert synced["product_price"] == "0円"


def test_vendor_request_memo_appends_once_and_ignores_blank_store():
    form = {"store_name": "阪神支店", "attention_memo": "既存メモ"}

    assert app.append_vendor_request_to_attention_memo(form) is True
    assert form["attention_memo"] == "既存メモ\n【阪神支店より修理依頼】"
    assert app.append_vendor_request_to_attention_memo(form) is False
    assert form["attention_memo"].count("【阪神支店より修理依頼】") == 1

    blank = {"store_name": "", "attention_memo": "既存メモ"}
    assert app.append_vendor_request_to_attention_memo(blank) is False
    assert blank["attention_memo"] == "既存メモ"


def test_vendor_request_memo_uses_counterparty_detail_fallback():
    form = {"store_name": "", "counterparty_detail": "あかりと空調の専門店 山田様", "attention_memo": ""}

    assert app.vendor_request_source_name(form) == "あかりと空調の専門店 山田様"
    assert app.append_vendor_request_to_attention_memo(form) is True
    assert form["attention_memo"] == "【あかりと空調の専門店 山田様より修理依頼】"


def test_apply_extracted_fields_preserves_existing_values_when_parsed_values_are_empty():
    existing = app.empty_form()
    existing.update({
        "call_line": "なかやしき",
        "manual_call_line": True,
        "appliance_type": "住設",
        "appliance_category": "住設（既築）",
        "housing_phase": "既築",
        "case_category": "手動分類",
        "warranty_plan": "既存保証",
        "warranty_start_date": "2026/06/01",
        "warranty_end_date": "2036/05/31",
        "product": "食器洗い乾燥機",
        "series": "既存シリーズ",
        "manufacturer": "パナソニック",
        "model_number": "ABC-123",
        "store_name": "阪神支店",
        "operating_company": "既存運営",
        "product_items": [{"attached_plan_name": "既存製品", "product": "食器洗い乾燥機"}],
        "selected_product_item_index": 0,
    })
    extracted = {
        "plan": "",
        "warranty_start_date": "",
        "warranty_end_date": None,
        "product_price": "",
        "manufacturer": "",
        "model_number": "",
        "series": "",
        "store_name": "",
        "operating_company": "",
        "genre": "",
        "category": "",
        "prefecture": "不正な都道府県",
        "product_items": [],
    }

    merged = app.apply_extracted_fields_to_form(extracted, existing)

    for field in (
        "call_line", "manual_call_line", "appliance_type", "appliance_category", "housing_phase",
        "case_category", "warranty_plan", "warranty_start_date", "warranty_end_date",
        "product", "series", "manufacturer", "model_number", "store_name",
        "operating_company", "product_items", "selected_product_item_index",
    ):
        assert merged[field] == existing[field]


def test_apply_extracted_fields_updates_clear_non_empty_values_and_keeps_manual_call_line():
    existing = app.empty_form()
    existing.update({
        "call_line": "なかやしき",
        "manual_call_line": True,
        "warranty_plan": "古い保証",
        "product": "古い製品",
        "manufacturer": "古いメーカー",
        "store_name": "古い販売店",
    })

    merged = app.apply_extracted_fields_to_form(
        {
            "plan": "新保証",
            "series": "エコキュート",
            "manufacturer": "コロナ",
            "store_name": "新販売店",
            "model_number": "CHP-46AY1",
        },
        existing,
    )

    assert merged["call_line"] == "なかやしき"
    assert merged["manual_call_line"] is True
    assert merged["warranty_plan"] == "新保証"
    assert merged["product"] == "エコキュート"
    assert merged["manufacturer"] == "コロナ"
    assert merged["store_name"] == "新販売店"
    assert merged["model_number"] == "CHP-46AY1"
