# -*- coding: utf-8 -*-
"""
tests/test_symptom_fields.py

通話中判定タブの symptom_detail / occurrence_time / occurrence_frequency フィールドと
0009テンプレートへの差し込みに関するテスト。
"""

import sys
import os
from datetime import date
from pathlib import Path
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_st_mock = mock.MagicMock()
_st_mock.cache_data = lambda f: f
sys.modules["streamlit"] = _st_mock

import app  # noqa: E402


# ============================================================
# フィールド定義
# ============================================================

def test_symptom_detail_in_field_labels():
    """FIELD_LABELS に symptom_detail が存在する。"""
    assert "symptom_detail" in app.FIELD_LABELS


def test_occurrence_time_in_field_labels():
    """FIELD_LABELS に occurrence_time が存在する。"""
    assert "occurrence_time" in app.FIELD_LABELS


def test_occurrence_frequency_in_field_labels():
    """FIELD_LABELS に occurrence_frequency が存在する。"""
    assert "occurrence_frequency" in app.FIELD_LABELS


def test_symptom_detail_in_empty_form():
    """empty_form() に symptom_detail が含まれ、初期値は空文字。"""
    form = app.empty_form()
    assert "symptom_detail" in form
    assert form["symptom_detail"] == ""


def test_occurrence_time_in_empty_form():
    """empty_form() に occurrence_time が含まれ、初期値は空文字。"""
    form = app.empty_form()
    assert "occurrence_time" in form
    assert form["occurrence_time"] == ""


def test_occurrence_frequency_in_empty_form():
    """empty_form() に occurrence_frequency が含まれ、初期値は空文字。"""
    form = app.empty_form()
    assert "occurrence_frequency" in form
    assert form["occurrence_frequency"] == ""


# ============================================================
# CHECK_ITEM_DEFINITIONS（症状の詳細は symptom_detail に統一）
# ============================================================

def test_check_item_definition_symptom_detail_uses_symptom_detail_field():
    """症状の詳細 のチェック項目は form["symptom_detail"] を参照する（二重管理しない）。"""
    defn = app.CHECK_ITEM_DEFINITIONS.get("症状の詳細", {})
    assert "symptom_detail" in defn.get("fields", ())
    assert "symptom" not in defn.get("fields", ()), \
        "form['symptom'] と form['symptom_detail'] が二重管理されている"


# ============================================================
# build_vendor_send_template_context
# ============================================================

def test_template_context_includes_symptom_detail():
    """テンプレートコンテキストに symptom_detail が含まれる。"""
    form = app.empty_form()
    form["symptom_detail"] = "冷蔵庫が冷えない"
    ctx = app.build_vendor_send_template_context(form)
    assert ctx["symptom_detail"] == "冷蔵庫が冷えない"


def test_template_context_includes_occurrence_time():
    """テンプレートコンテキストに occurrence_time が含まれる。"""
    form = app.empty_form()
    form["occurrence_time"] = "昨日から"
    ctx = app.build_vendor_send_template_context(form)
    assert ctx["occurrence_time"] == "昨日から"


def test_template_context_includes_occurrence_frequency():
    """テンプレートコンテキストに occurrence_frequency が含まれる。"""
    form = app.empty_form()
    form["occurrence_frequency"] = "常時"
    ctx = app.build_vendor_send_template_context(form)
    assert ctx["occurrence_frequency"] == "常時"


# ============================================================
# 0009テンプレートへの差し込み
# ============================================================

def _build_memo_0009(symptom_detail="", occurrence_time="", occurrence_frequency="",
                     cost_estimate="5,000円～7,000円前後"):
    form = app.empty_form()
    form.update({
        "template_code": "0009",
        "template_label": "【出張修理】自然故障",
        "symptom_detail": symptom_detail,
        "occurrence_time": occurrence_time,
        "occurrence_frequency": occurrence_frequency,
    })
    return app._build_after_call_memo(
        form,
        {"title": "保証期間内"},
        "出張修理",
        "WRT修理センター",
        cost_estimate=cost_estimate,
    )


def test_0009_memo_inserts_symptom_detail():
    """symptom_detail の値が注意内容メモに差し込まれる。"""
    memo = _build_memo_0009(symptom_detail="冷蔵庫が冷えない")
    assert "具体的な症状：冷蔵庫が冷えない" in memo


def test_0009_memo_inserts_occurrence_time():
    """occurrence_time の値が注意内容メモに差し込まれる。"""
    memo = _build_memo_0009(occurrence_time="昨日から")
    assert "発生時期：昨日から" in memo


def test_0009_memo_inserts_occurrence_frequency():
    """occurrence_frequency の値が注意内容メモに差し込まれる。"""
    memo = _build_memo_0009(occurrence_frequency="常時")
    assert "発生頻度：常時" in memo


def test_0009_memo_all_three_filled():
    """3項目すべて入力済みの場合、正しく差し込まれる。"""
    memo = _build_memo_0009(
        symptom_detail="冷蔵庫が冷えない",
        occurrence_time="昨日から",
        occurrence_frequency="常時",
    )
    assert "具体的な症状：冷蔵庫が冷えない" in memo
    assert "発生時期：昨日から" in memo
    assert "発生頻度：常時" in memo
    assert "※保証対象外時の案内済み" in memo
    assert "※修理キャンセル時の概算費用5,000円～7,000円前後" in memo


def test_0009_memo_empty_fields_produce_blank_lines():
    """未入力の場合、各行は空欄のまま生成される。"""
    memo = _build_memo_0009()
    assert "具体的な症状：\n" in memo + "\n"
    assert "発生時期：\n" in memo + "\n"
    assert "発生頻度：\n" in memo + "\n"


def test_0009_memo_with_estimated_fee():
    """estimated_fee がある場合、概算費用に差し込まれる。"""
    memo = _build_memo_0009(cost_estimate="5,000円～7,000円前後")
    assert "※修理キャンセル時の概算費用5,000円～7,000円前後" in memo


def test_0009_memo_without_estimated_fee_shows_confirming():
    """estimated_fee が未確定の場合、「確認中」になる。"""
    memo = _build_memo_0009(cost_estimate="")
    assert "※修理キャンセル時の概算費用確認中" in memo


# ============================================================
# 注意内容メモ再生成でラクテル・Teams を上書きしない
# ============================================================

def test_0009_memo_regen_does_not_overwrite_rakutel():
    """注意内容メモ再生成でラクテル用テキストを上書きしない。"""
    form = app.empty_form()
    form.update({
        "template_code": "0009",
        "rakutel_text": "既存ラクテルテキスト",
    })
    app._build_after_call_memo(form, {}, "出張修理", "WRT修理センター")
    assert form["rakutel_text"] == "既存ラクテルテキスト"


def test_0009_memo_regen_does_not_overwrite_teams():
    """注意内容メモ再生成でTeams報告文を上書きしない。"""
    form = app.empty_form()
    form.update({
        "template_code": "0009",
        "teams_chat_message": "既存Teams報告文",
    })
    app._build_after_call_memo(form, {}, "出張修理", "WRT修理センター")
    assert form["teams_chat_message"] == "既存Teams報告文"


# ============================================================
# 案件クリア時のフィールドリセット
# ============================================================

def test_reset_clears_symptom_detail():
    """案件クリア時に symptom_detail が空になる。"""
    session = {
        "form": app.empty_form(),
        "case_basic_revision": 0,
        "case_memo_global": "old",
    }
    session["form"]["symptom_detail"] = "冷蔵庫が冷えない"
    new_form = app.reset_case_session_state(session)
    assert new_form["symptom_detail"] == ""


def test_reset_clears_occurrence_time():
    """案件クリア時に occurrence_time が空になる。"""
    session = {
        "form": app.empty_form(),
        "case_basic_revision": 0,
        "case_memo_global": "old",
    }
    session["form"]["occurrence_time"] = "昨日から"
    new_form = app.reset_case_session_state(session)
    assert new_form["occurrence_time"] == ""


def test_reset_clears_occurrence_frequency():
    """案件クリア時に occurrence_frequency が空になる。"""
    session = {
        "form": app.empty_form(),
        "case_basic_revision": 0,
        "case_memo_global": "old",
    }
    session["form"]["occurrence_frequency"] = "常時"
    new_form = app.reset_case_session_state(session)
    assert new_form["occurrence_frequency"] == ""


def test_reset_clears_now_input_widget_keys():
    """案件クリア時に now_input_ で始まる widget state が削除される。"""
    session = {
        "form": app.empty_form(),
        "case_basic_revision": 0,
        "case_memo_global": "old",
        "now_input_symptom_detail_0_abc12345": "冷蔵庫が冷えない",
        "now_input_occurrence_time_1_def67890": "昨日から",
    }
    app.reset_case_session_state(session)
    for key in list(session.keys()):
        assert not key.startswith("now_input_"), f"now_input_ キーが残っている: {key}"


# ============================================================
# 通話中判定画面（今聞くこと）への表示確認
# ============================================================

def _make_call_plan(product="エアコン", manufacturer="シャープ",
                    warranty_start="2026/01/01", warranty_end="2027/01/01"):
    form = app.empty_form()
    form.update({
        "product": product,
        "manufacturer": manufacturer,
        "appliance_type": "家電",
        "warranty_start_date": warranty_start,
        "warranty_end_date": warranty_end,
    })
    d = app.run_decision(form)
    plan = app.build_now_action_plan(
        form, d["repair_type"], d.get("needs_data_erase", False),
        d.get("diagnostics"), d.get("warranty_result"), d.get("cost_result"),
    )
    return plan


def test_now_action_shows_occurrence_time():
    """通話中判定画面の「今聞くこと」に「発生時期」が表示される。"""
    plan = _make_call_plan()
    all_items = plan["call_required"] + plan["completed"]
    labels = [item["label"] for item in all_items]
    assert "発生時期" in labels, f"発生時期が今聞くことに見当たらない: {labels}"


def test_now_action_shows_occurrence_frequency():
    """通話中判定画面の「今聞くこと」に「発生頻度」が表示される。"""
    plan = _make_call_plan()
    all_items = plan["call_required"] + plan["completed"]
    labels = [item["label"] for item in all_items]
    assert "発生頻度" in labels, f"発生頻度が今聞くことに見当たらない: {labels}"


def test_occurrence_time_moves_to_completed_after_input():
    """occurrence_time を入力すると「発生時期」が完了済みに移動する。"""
    form = app.empty_form()
    form.update({
        "product": "エアコン",
        "manufacturer": "シャープ",
        "appliance_type": "家電",
        "warranty_start_date": "2026/01/01",
        "warranty_end_date": "2027/01/01",
        "occurrence_time": "昨日から",
    })
    d = app.run_decision(form)
    plan = app.build_now_action_plan(
        form, d["repair_type"], d.get("needs_data_erase", False),
        d.get("diagnostics"), d.get("warranty_result"), d.get("cost_result"),
    )
    call_labels = [item["label"] for item in plan["call_required"]]
    done_labels = [item["label"] for item in plan["completed"]]
    assert "発生時期" not in call_labels
    assert "発生時期" in done_labels


def test_occurrence_frequency_moves_to_completed_after_input():
    """occurrence_frequency を入力すると「発生頻度」が完了済みに移動する。"""
    form = app.empty_form()
    form.update({
        "product": "エアコン",
        "manufacturer": "シャープ",
        "appliance_type": "家電",
        "warranty_start_date": "2026/01/01",
        "warranty_end_date": "2027/01/01",
        "occurrence_frequency": "常時",
    })
    d = app.run_decision(form)
    plan = app.build_now_action_plan(
        form, d["repair_type"], d.get("needs_data_erase", False),
        d.get("diagnostics"), d.get("warranty_result"), d.get("cost_result"),
    )
    call_labels = [item["label"] for item in plan["call_required"]]
    done_labels = [item["label"] for item in plan["completed"]]
    assert "発生頻度" not in call_labels
    assert "発生頻度" in done_labels


def test_occurrence_time_in_memo_when_filled():
    """occurrence_time の入力値が注意内容メモに反映される。"""
    memo = _build_memo_0009(occurrence_time="昨日から")
    assert "発生時期：昨日から" in memo


def test_occurrence_frequency_in_memo_when_filled():
    """occurrence_frequency の入力値が注意内容メモに反映される。"""
    memo = _build_memo_0009(occurrence_frequency="常時")
    assert "発生頻度：常時" in memo


def test_occurrence_time_blank_when_not_filled():
    """occurrence_time が未入力のとき、発生時期欄は空欄で生成される。"""
    memo = _build_memo_0009(occurrence_time="")
    assert "発生時期：\n" in memo + "\n"


def test_occurrence_frequency_blank_when_not_filled():
    """occurrence_frequency が未入力のとき、発生頻度欄は空欄で生成される。"""
    memo = _build_memo_0009(occurrence_frequency="")
    assert "発生頻度：\n" in memo + "\n"


# ============================================================
# 選択肢定数・select_with_other
# ============================================================

def test_occurrence_time_options_constant_exists():
    """OCCURRENCE_TIME_OPTIONS 定数が存在する。"""
    assert hasattr(app, "OCCURRENCE_TIME_OPTIONS")
    assert isinstance(app.OCCURRENCE_TIME_OPTIONS, list)


def test_occurrence_frequency_options_constant_exists():
    """OCCURRENCE_FREQUENCY_OPTIONS 定数が存在する。"""
    assert hasattr(app, "OCCURRENCE_FREQUENCY_OPTIONS")
    assert isinstance(app.OCCURRENCE_FREQUENCY_OPTIONS, list)


def test_occurrence_time_options_do_not_include_sono_ta():
    """発生時期は常時任意入力欄があるため「その他」を使わない。"""
    assert "その他" not in app.OCCURRENCE_TIME_OPTIONS
    assert app.OCCURRENCE_TIME_OPTIONS[0] == "未選択"


def test_occurrence_frequency_options_do_not_include_sono_ta():
    """発生頻度は常時任意入力欄があるため「その他」を使わない。"""
    assert "その他" not in app.OCCURRENCE_FREQUENCY_OPTIONS
    assert app.OCCURRENCE_FREQUENCY_OPTIONS[0] == "未選択"


def test_occurrence_time_options_include_predefined():
    """発生時期の選択肢に主要な候補が含まれる。"""
    for expected in [app.occurrence_today_option(), app.occurrence_yesterday_option(), "数日前から", "不明"]:
        assert expected in app.OCCURRENCE_TIME_OPTIONS, f"'{expected}' が OCCURRENCE_TIME_OPTIONS にない"
    assert "以前から" not in app.OCCURRENCE_TIME_OPTIONS
    assert "昨日から" not in app.OCCURRENCE_TIME_OPTIONS
    assert "本日（6/15）から" not in app.occurrence_time_options(date(2026, 6, 15))


def test_occurrence_today_option_uses_month_day_without_zero_padding():
    assert app.occurrence_today_option(date(2026, 6, 4)) == "本日（6/4）"
    assert app.occurrence_yesterday_option(date(2026, 6, 15)) == "昨日（6/14）"


def test_occurrence_frequency_options_include_predefined():
    """発生頻度の選択肢に主要な候補が含まれる。"""
    for expected in ["継続中", "時々", "たまに", "1回のみ", "不明"]:
        assert expected in app.OCCURRENCE_FREQUENCY_OPTIONS, f"'{expected}' が OCCURRENCE_FREQUENCY_OPTIONS にない"
    for removed in ["常時", "初回のみ", "再発"]:
        assert removed not in app.OCCURRENCE_FREQUENCY_OPTIONS


def test_occurrence_frequency_keizokuchu_is_after_unselected():
    """発生頻度の「継続中」は未選択の次に置く。"""
    assert app.OCCURRENCE_FREQUENCY_OPTIONS[:2] == ["未選択", "継続中"]


def test_occurrence_time_check_item_uses_hearing_choice_text():
    """CHECK_ITEM_DEFINITIONS の発生時期が選択肢+任意入力型を使う。"""
    defn = app.CHECK_ITEM_DEFINITIONS.get("発生時期", {})
    assert defn.get("input") == "hearing_choice_text", \
        f"expected 'hearing_choice_text', got {defn.get('input')!r}"


def test_occurrence_frequency_check_item_uses_hearing_choice_text():
    """CHECK_ITEM_DEFINITIONS の発生頻度が選択肢+任意入力型を使う。"""
    defn = app.CHECK_ITEM_DEFINITIONS.get("発生頻度", {})
    assert defn.get("input") == "hearing_choice_text", \
        f"expected 'hearing_choice_text', got {defn.get('input')!r}"


def test_select_with_other_options_lookup_for_occurrence_time():
    """_SELECT_WITH_OTHER_OPTIONS に occurrence_time が含まれる。"""
    opts = app._SELECT_WITH_OTHER_OPTIONS.get("occurrence_time", [])
    assert opts, "occurrence_time の選択肢が未定義"
    assert "未選択" in opts
    assert "その他" not in opts


def test_select_with_other_options_lookup_for_occurrence_frequency():
    """_SELECT_WITH_OTHER_OPTIONS に occurrence_frequency が含まれる。"""
    opts = app._SELECT_WITH_OTHER_OPTIONS.get("occurrence_frequency", [])
    assert opts, "occurrence_frequency の選択肢が未定義"
    assert "未選択" in opts
    assert "その他" not in opts


# ============================================================
# 注意内容メモ反映予定プレビュー（build_vendor_send_template_context 経由）
# ============================================================

def test_occurrence_time_free_text_takes_priority_over_choice():
    form = {"occurrence_time_choice": "昨日", "occurrence_time_text": "2〜3日前から"}

    assert app.resolve_occurrence_time(form) == "2〜3日前から"


def test_occurrence_frequency_free_text_takes_priority_over_choice():
    form = {"occurrence_frequency_choice": "常時", "occurrence_frequency_text": "朝だけ"}

    assert app.resolve_occurrence_frequency(form) == "朝だけ"


def test_occurrence_time_choice_used_when_free_text_is_blank():
    form = {"occurrence_time_choice": "購入直後", "occurrence_time_text": ""}

    assert app.resolve_occurrence_time(form) == "購入直後"


def test_occurrence_frequency_choice_used_when_free_text_is_blank():
    form = {"occurrence_frequency_choice": "再発", "occurrence_frequency_text": ""}

    assert app.resolve_occurrence_frequency(form) == "再発"


def test_occurrence_unselected_and_blank_text_resolve_to_blank():
    assert app.resolve_occurrence_time({"occurrence_time_choice": "未選択", "occurrence_time_text": ""}) == ""
    assert app.resolve_occurrence_frequency({"occurrence_frequency_choice": "未選択", "occurrence_frequency_text": ""}) == ""


def test_occurrence_choice_text_values_remove_now_action_missing_items():
    form = app.empty_form()
    form.update({
        "occurrence_time_choice": "本日",
        "occurrence_time_text": "前回修理後から",
        "occurrence_frequency_choice": "常時",
        "occurrence_frequency_text": "使用中だけ",
    })

    plan = app.build_now_action_plan(
        form,
        repair_type="持込修理",
        needs_data_erase=False,
        guidance_items=["発生時期", "発生頻度"],
    )

    assert "発生時期" not in [item["label"] for item in plan["call_required"]]
    assert "発生頻度" not in [item["label"] for item in plan["call_required"]]
    assert "発生時期：前回修理後から" in [app.format_completed_check_item(item, form) for item in plan["completed"]]
    assert "発生頻度：使用中だけ" in [app.format_completed_check_item(item, form) for item in plan["completed"]]


def test_occurrence_frequency_choice_value_removed_from_required_checklist():
    form = app.empty_form()
    form.update({
        "occurrence_frequency_choice": "再発",
        "occurrence_frequency_text": "",
    })

    categories = app.build_question_categories(
        form,
        repair_type="持込修理",
        needs_data_erase=False,
        guidance_items=["発生頻度"],
    )

    assert "発生頻度" not in [item["label"] for item in categories["call_required"]]


def test_attention_memo_preview_uses_occurrence_free_text_values():
    form = app.empty_form()
    form.update({
        "symptom_detail": "電源が付かない",
        "occurrence_time_choice": "購入直後",
        "occurrence_time_text": "",
        "occurrence_frequency_choice": "常時",
        "occurrence_frequency_text": "継続中",
    })

    assert app.build_attention_memo_preview_lines(form) == [
        "具体的な症状：電源が付かない",
        "発生時期：購入直後",
        "発生頻度：継続中",
    ]


def test_attention_memo_preview_lines_remove_body_clipboard_icon():
    form = app.empty_form()
    form.update({
        "symptom_detail": "📋電源が付かない",
        "occurrence_time_choice": "購入直後",
        "occurrence_frequency_choice": "常時",
    })

    lines = app.build_attention_memo_preview_lines(form)

    assert lines[0] == "具体的な症状：電源が付かない"
    assert all("📋" not in line for line in lines)


def test_attention_memo_regeneration_uses_occurrence_free_text_values():
    form = app.empty_form()
    form.update({
        "template_code": "0009",
        "template_label": "【出張修理】自然故障",
        "symptom_detail": "電源が付かない",
        "occurrence_time_choice": "昨日",
        "occurrence_time_text": "2〜3日前から",
        "occurrence_frequency_choice": "時々",
        "occurrence_frequency_text": "朝だけ",
    })

    memo = app._build_after_call_memo(
        form,
        {"title": "保証期間内"},
        "出張修理",
        "WRT修理センター",
    )

    assert "発生時期：2〜3日前から" in memo
    assert "発生頻度：朝だけ" in memo


def test_preview_all_three_appear_in_template_context():
    """3項目がテンプレートコンテキストに含まれ、プレビューとして利用できる。"""
    form = app.empty_form()
    form["symptom_detail"] = "電源が付かない"
    form["occurrence_time"] = "昨日から"
    form["occurrence_frequency"] = "常時"
    ctx = app.build_vendor_send_template_context(form)
    assert ctx["symptom_detail"] == "電源が付かない"
    assert ctx["occurrence_time"] == "昨日から"
    assert ctx["occurrence_frequency"] == "常時"


def test_preview_empty_when_no_input():
    """未入力のとき、コンテキスト値は空文字。"""
    form = app.empty_form()
    ctx = app.build_vendor_send_template_context(form)
    assert ctx["symptom_detail"] == ""
    assert ctx["occurrence_time"] == ""
    assert ctx["occurrence_frequency"] == ""


# ============================================================
# 注意内容メモ再生成でラクテル/Teams を上書きしない（改善6）
# ============================================================

def test_attention_memo_regen_does_not_touch_rakutel_or_teams():
    """注意内容メモ再生成でラクテル用テキストとTeams報告文を上書きしない。"""
    form = app.empty_form()
    form.update({
        "template_code": "0009",
        "rakutel_text": "既存ラクテル",
        "teams_chat_message": "既存Teams",
        "symptom_detail": "故障",
        "occurrence_time": "昨日",
        "occurrence_frequency": "常時",
    })
    app._build_after_call_memo(form, {"title": "保証期間内"}, "出張修理", "WRT修理センター",
                               cost_estimate="5,000円～7,000円前後")
    assert form["rakutel_text"] == "既存ラクテル"
    assert form["teams_chat_message"] == "既存Teams"


def test_completed_display_includes_symptom_detail_value():
    form = app.empty_form()
    form["symptom_detail"] = "電源が付かない"
    item = app.build_check_item("症状の詳細", form)

    assert app.format_completed_check_item(item, form) == "具体的な症状：電源が付かない"


def test_completed_display_includes_occurrence_time_value():
    form = app.empty_form()
    form["occurrence_time"] = "昨日"
    item = app.build_check_item("発生時期", form)

    assert app.format_completed_check_item(item, form) == "発生時期：昨日"


def test_completed_display_includes_occurrence_frequency_value():
    form = app.empty_form()
    form["occurrence_frequency"] = "常時"
    item = app.build_check_item("発生頻度", form)

    assert app.format_completed_check_item(item, form) == "発生頻度：常時"


def test_completed_manual_check_without_value_shows_confirmed():
    form = app.empty_form()
    item = app.build_check_item("発生時期", form, {"occurrence_time": True})

    assert app.format_completed_check_item(item, form) == "発生時期：確認済み"


def test_hearing_summary_lines_include_call_inputs():
    form = app.empty_form()
    form.update({
        "symptom_detail": "電源が付かない",
        "occurrence_time": "昨日",
        "occurrence_frequency": "常時",
        "install_location": "キッチン",
        "address": "埼玉県朝霞市幸町２－１８－２７",
    })

    assert app.build_hearing_summary_lines(form) == [
        "具体的な症状：電源が付かない",
        "発生時期：昨日",
        "発生頻度：常時",
        "設置場所：キッチン",
        "訪問先住所：埼玉県朝霞市幸町２－１８－２７",
    ]


def test_hearing_summary_lines_use_occurrence_frequency_choice_value():
    form = app.empty_form()
    form.update({
        "symptom_detail": "電源が付かない",
        "occurrence_time_choice": "本日",
        "occurrence_time_text": "",
        "occurrence_frequency_choice": "再発",
        "occurrence_frequency_text": "",
        "address": "兵庫県宝塚市逆瀬川2丁目9-8",
    })

    assert "発生頻度：再発" in app.build_hearing_summary_lines(form)


def test_hearing_summary_lines_use_occurrence_frequency_keizokuchu_choice_value():
    form = app.empty_form()
    form.update({
        "occurrence_frequency_choice": "継続中",
        "occurrence_frequency_text": "",
    })

    assert "発生頻度：継続中" in app.build_hearing_summary_lines(form)


def test_hearing_summary_lines_use_occurrence_frequency_free_text_value():
    form = app.empty_form()
    form.update({
        "occurrence_frequency_choice": "再発",
        "occurrence_frequency_text": "朝だけ",
    })

    assert "発生頻度：朝だけ" in app.build_hearing_summary_lines(form)


def test_attention_preview_and_hearing_summary_share_resolved_frequency_value():
    form = app.empty_form()
    form.update({
        "symptom_detail": "電源が付かない",
        "occurrence_time_choice": "本日",
        "occurrence_time_text": "",
        "occurrence_frequency_choice": "再発",
        "occurrence_frequency_text": "",
    })

    assert "発生頻度：再発" in app.build_attention_memo_preview_lines(form)
    assert "発生頻度：再発" in app.build_hearing_summary_lines(form)


def test_sync_hearing_widget_state_updates_summary_before_inputs_render():
    form = app.empty_form()
    today_option = app.occurrence_today_option()
    state = {
        "call_hearing_symptom_detail": "電源が付かない",
        "call_hearing_occurrence_time_choice": today_option,
        "call_hearing_occurrence_time_text": "",
        "call_hearing_occurrence_frequency_choice": "継続中",
        "call_hearing_occurrence_frequency_text": "",
    }

    app.sync_hearing_widget_state_to_form(form, state)

    assert app.build_hearing_summary_lines(form)[:3] == [
        "具体的な症状：電源が付かない",
        f"発生時期：{today_option}",
        "発生頻度：継続中",
    ]


def test_hearing_summary_lines_keep_required_blank_rows():
    form = app.empty_form()
    form["address"] = "兵庫県宝塚市逆瀬川2丁目9-8"

    assert app.build_hearing_summary_lines(form) == [
        "具体的な症状：",
        "発生時期：",
        "発生頻度：",
        "設置場所：",
        "訪問先住所：兵庫県宝塚市逆瀬川2丁目9-8",
    ]


def test_support_info_hearing_summary_renders_one_item_per_markdown_line():
    source = Path(app.__file__).read_text(encoding="utf-8")
    start = source.index("hearing_summary_lines = build_hearing_summary_lines(form)")
    end = source.index('form["maker_warranty_period"]', start)
    support_source = source[start:end]

    assert "for line in hearing_summary_lines:" in support_source
    assert "st.markdown(line)" in support_source
    assert '"\\n".join(hearing_summary_lines)' not in support_source


def test_attention_memo_preview_lines_include_three_values():
    form = app.empty_form()
    form.update({
        "symptom_detail": "電源が付かない",
        "occurrence_time": "昨日",
        "occurrence_frequency": "常時",
        "install_location": "キッチン",
    })

    assert app.build_attention_memo_preview_lines(form) == [
        "具体的な症状：電源が付かない",
        "発生時期：昨日",
        "発生頻度：常時",
    ]


def test_support_info_expander_is_open_and_has_hearing_summary():
    source = Path(app.__file__).read_text(encoding="utf-8")

    assert 'with st.expander("補助情報を開く", expanded=True)' in source
    assert "聴取内容まとめ" in source


def test_support_info_does_not_duplicate_symptom_input_widgets():
    source = Path(app.__file__).read_text(encoding="utf-8")
    start = source.index('with st.expander("補助情報を開く", expanded=True)')
    end = source.index("st.session_state.form = form", start)
    support_source = source[start:end]

    assert 'key="now_input_symptom_detail' not in support_source
    assert 'key="now_input_occurrence_time' not in support_source
    assert 'key="now_input_occurrence_frequency' not in support_source
    assert 'form["symptom_detail"] = st.' not in support_source
    assert 'form["occurrence_time"] = st.' not in support_source
    assert 'form["occurrence_frequency"] = st.' not in support_source
    assert "今聞くこと」で入力してください" not in support_source
    assert "今聞くことで入力してください" not in support_source


def test_call_hearing_block_exists():
    source = Path(app.__file__).read_text(encoding="utf-8")

    assert "📋 聴取内容（修理依頼書メモ反映）" in source
    assert "def render_call_hearing_inputs" in source


def test_call_hearing_block_owns_stable_widget_keys():
    source = Path(app.__file__).read_text(encoding="utf-8")
    start = source.index("def render_call_hearing_inputs")
    end = source.index("def render_now_action_item", start)
    hearing_source = source[start:end]

    assert '"call_hearing_symptom_detail"' in hearing_source
    assert 'choice_key="call_hearing_occurrence_time_choice"' in hearing_source
    assert 'text_key="call_hearing_occurrence_time_text"' in hearing_source
    assert 'choice_key="call_hearing_occurrence_frequency_choice"' in hearing_source
    assert 'text_key="call_hearing_occurrence_frequency_text"' in hearing_source
    assert 'key="call_hearing_occurrence_time_text"' in hearing_source
    assert 'key="call_hearing_occurrence_frequency_text"' in hearing_source


def test_call_hearing_block_renders_before_script_support_details():
    source = Path(app.__file__).read_text(encoding="utf-8")
    call_tab_start = source.index("def render_tab_call")
    hearing_index = source.index("render_call_hearing_inputs(st.session_state.form)", call_tab_start)
    support_detail_index = source.index('with st.expander("📘 スクリプト補助の詳細", expanded=False):', call_tab_start)

    assert hearing_index < support_detail_index


def test_call_hearing_block_renders_after_script_support_area():
    source = Path(app.__file__).read_text(encoding="utf-8")
    call_tab_start = source.index("def render_tab_call")
    script_support_index = source.index("script_guidance = build_script_guidance_panel_info", call_tab_start)
    hearing_index = source.index("render_call_hearing_inputs(st.session_state.form)", call_tab_start)

    assert script_support_index < hearing_index


def test_old_support_info_guidance_text_removed():
    source = Path(app.__file__).read_text(encoding="utf-8")

    assert "具体的な症状 / 発生時期 / 発生頻度は「今聞くこと」で入力してください" not in source


def test_now_action_does_not_render_hearing_input_widgets():
    source = Path(app.__file__).read_text(encoding="utf-8")
    start = source.index("def render_now_action_item")
    end = source.index("def render_warranty_date_input", start)
    now_source = source[start:end]

    assert "HEARING_INPUT_FIELD_IDS" in now_source
    assert 'key="call_hearing_symptom_detail"' not in now_source
    assert 'call_hearing_occurrence_time_choice' not in now_source
    assert 'call_hearing_occurrence_frequency_choice' not in now_source


def test_now_action_does_not_show_large_hearing_info_boxes():
    source = Path(app.__file__).read_text(encoding="utf-8")
    start = source.index("def render_now_action_item")
    end = source.index("def render_warranty_date_input", start)
    now_source = source[start:end]

    assert "HEARING_INPUT_PROMPTS.get" not in now_source
    assert "具体的な症状を入力してください" not in now_source
    assert "発生時期を選択してください" not in now_source
    assert "発生頻度を選択してください" not in now_source


def test_right_column_does_not_render_inline_next_confirmation_list():
    source = Path(app.__file__).read_text(encoding="utf-8")
    call_tab_start = source.index("def render_tab_call")
    summary_index = source.index("summary_display = build_summary_card_display", call_tab_start)
    right_column_source = source[call_tab_start:summary_index]

    assert 'st.markdown("### ✅ 次に確認すること")' not in right_column_source
    assert "now_action_plan" not in right_column_source
    assert "render_now_action_item(item, st.session_state.form, idx)" not in right_column_source


def test_script_support_details_are_below_hearing_block():
    source = Path(app.__file__).read_text(encoding="utf-8")
    call_tab_start = source.index("def render_tab_call")
    hearing_index = source.index("render_call_hearing_inputs(st.session_state.form)", call_tab_start)
    support_detail_index = source.index('with st.expander("📘 スクリプト補助の詳細", expanded=False):', call_tab_start)

    assert hearing_index < support_detail_index


def test_attention_memo_preview_is_in_hearing_block_only():
    source = Path(app.__file__).read_text(encoding="utf-8")
    hearing_start = source.index("def render_call_hearing_inputs")
    hearing_end = source.index("def render_now_action_item", hearing_start)
    hearing_source = source[hearing_start:hearing_end]
    call_tab_start = source.index("def render_tab_call")
    hearing_render_index = source.index("render_call_hearing_inputs(st.session_state.form)", call_tab_start)
    summary_index = source.index("summary_display = build_summary_card_display", hearing_render_index)
    right_column_after_hearing_source = source[hearing_render_index:summary_index]

    assert "修理依頼書メモ反映予定" in hearing_source
    assert "📋 修理依頼書メモ反映予定" not in hearing_source
    assert "attention_preview_lines = build_attention_memo_preview_lines" not in right_column_after_hearing_source


def test_now_action_has_missing_guidance_only_for_hearing_fields():
    form = app.empty_form()
    symptom_item = app.build_check_item("症状の詳細", form)

    assert symptom_item["id"] in app.HEARING_INPUT_FIELD_IDS
    assert app.HEARING_INPUT_PROMPTS[symptom_item["id"]] == "具体的な症状を入力してください"


def test_call_hearing_widgets_do_not_depend_on_completed_state():
    source = Path(app.__file__).read_text(encoding="utf-8")
    start = source.index("def render_call_hearing_inputs")
    end = source.index("def render_now_action_item", start)
    hearing_source = source[start:end]

    assert "now_action_plan" not in hearing_source
    assert "completed" not in hearing_source
    assert "item_id" not in hearing_source


def test_case_clear_removes_call_hearing_widget_state():
    state = {
        "form": app.empty_form(),
        "call_hearing_symptom_detail": "故障",
        "call_hearing_occurrence_time_choice": "本日",
        "call_hearing_occurrence_time_text": "昨日の夜",
        "call_hearing_occurrence_frequency_choice": "常時",
        "call_hearing_occurrence_frequency_text": "",
    }

    app.reset_case_session_state(state)

    assert not any(str(key).startswith("call_hearing_") for key in state)
