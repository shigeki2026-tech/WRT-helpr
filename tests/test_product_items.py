# -*- coding: utf-8 -*-

import os
import sys
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_st_mock = mock.MagicMock()
_st_mock.cache_data = lambda f: f
sys.modules["streamlit"] = _st_mock

import app  # noqa: E402


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


def test_vendor_request_memo_appends_once_and_ignores_blank_store():
    form = {"store_name": "阪神支店", "attention_memo": "既存メモ"}

    assert app.append_vendor_request_to_attention_memo(form) is True
    assert form["attention_memo"] == "既存メモ\n【阪神支店より修理依頼】"
    assert app.append_vendor_request_to_attention_memo(form) is False
    assert form["attention_memo"].count("【阪神支店より修理依頼】") == 1

    blank = {"store_name": "", "attention_memo": "既存メモ"}
    assert app.append_vendor_request_to_attention_memo(blank) is False
    assert blank["attention_memo"] == "既存メモ"
