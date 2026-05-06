# -*- coding: utf-8 -*-
"""
tests/test_symptom_fields.py

通話中判定タブの symptom_detail / occurrence_time / occurrence_frequency フィールドと
0009テンプレートへの差し込みに関するテスト。
"""

import sys
import os
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
