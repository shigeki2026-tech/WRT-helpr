# -*- coding: utf-8 -*-

import csv
import os
import sys
import unittest.mock as mock
import uuid
from pathlib import Path


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_st_mock = mock.MagicMock()


class _CacheData:
    def __call__(self, f):
        return f

    def clear(self):
        return None


_st_mock.cache_data = _CacheData()
sys.modules["streamlit"] = _st_mock

import app  # noqa: E402


def _write_master_csv(data_dir, filename, columns, rows=None):
    path = data_dir / filename
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows or [])
    return path


def _read_rows(path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _make_data_dir():
    data_dir = Path(__file__).resolve().parents[1] / ".codex_unit_tmp" / uuid.uuid4().hex / "data"
    data_dir.mkdir(parents=True)
    return data_dir


def test_product_alias_append_adds_one_row_and_backup():
    data_dir = _make_data_dir()
    path = _write_master_csv(data_dir, "master_product_alias.csv", app._ALIAS_COLS)

    result = app.append_master_product_alias(
        {
            "keyword": "電気調理器・調理圧力鍋",
            "normalized_product": "電気調理器",
            "product_group": "キッチン家電",
            "notes": "テスト",
        },
        data_dir=str(data_dir),
    )

    rows = _read_rows(path)
    assert result["ok"] is True
    assert len(rows) == 1
    assert rows[0]["priority"] == "10"
    assert rows[0]["enabled"] == "1"
    assert rows[0]["keyword"] == "電気調理器・調理圧力鍋"
    assert os.path.exists(result["backup_path"])


def test_product_alias_duplicate_keyword_is_detected():
    data_dir = _make_data_dir()
    path = _write_master_csv(
        data_dir,
        "master_product_alias.csv",
        app._ALIAS_COLS,
        [{"priority": "10", "enabled": "1", "keyword": "調理圧力鍋", "normalized_product": "電気調理器", "product_group": "", "notes": ""}],
    )

    result = app.append_master_product_alias(
        {"keyword": "調理圧力鍋", "normalized_product": "電気調理器"},
        data_dir=str(data_dir),
    )

    assert result["ok"] is False
    assert result["reason"] == "duplicate"
    assert len(_read_rows(path)) == 1


def test_repair_type_rule_append_adds_one_row():
    data_dir = _make_data_dir()
    path = _write_master_csv(data_dir, "master_repair_type_rules.csv", app._REPAIR_TYPE_COLS)

    result = app.append_master_repair_type_rule(
        {
            "product_keyword": "電気調理器",
            "manufacturer_keyword": "パナソニック",
            "model_keyword": "",
            "condition_keyword": "",
            "repair_type": "持込修理",
            "needs_confirmation": "0",
            "notes": "テスト",
        },
        data_dir=str(data_dir),
    )

    rows = _read_rows(path)
    assert result["ok"] is True
    assert len(rows) == 1
    assert rows[0]["repair_type"] == "持込修理"
    assert os.path.exists(result["backup_path"])


def test_store_rule_append_adds_one_row():
    data_dir = _make_data_dir()
    path = _write_master_csv(data_dir, "master_store_rules.csv", app._STORE_RULE_COLS)

    result = app.append_master_store_rule(
        {
            "store_keyword": "マサニ電気",
            "normalized_store": "マサニ電気",
            "template_code": "",
            "template_label": "",
            "template_group": "",
            "notes": "テスト",
        },
        data_dir=str(data_dir),
    )

    rows = _read_rows(path)
    assert result["ok"] is True
    assert len(rows) == 1
    assert rows[0]["store_keyword"] == "マサニ電気"
    assert os.path.exists(result["backup_path"])


def test_inline_manufacturer_candidate_for_other_with_original():
    form = app.empty_form()
    form.update({"manufacturer": app.MANUFACTURER_OTHER, "manufacturer_original": "アクア"})

    candidate = app.build_inline_manufacturer_candidate(form)

    assert candidate["manufacturer_original"] == "アクア"
    assert candidate["normalized_manufacturer"] == "アクア"
    assert candidate["group_name"] == "国内家電メーカー"
    assert "customer_name" not in str(candidate)


def test_inline_manufacturer_candidate_includes_aqua_alias():
    form = app.empty_form()
    form.update({"manufacturer": app.MANUFACTURER_OTHER, "manufacturer_original": "繧｢繧ｯ繧｢"})

    candidate = app.build_inline_manufacturer_candidate(form)

    assert candidate["manufacturers"] == "繧｢繧ｯ繧｢;AQUA"


def test_inline_manufacturer_candidate_includes_readable_aqua_alias():
    form = app.empty_form()
    form.update({"manufacturer": app.MANUFACTURER_OTHER, "manufacturer_original": "アクア"})

    candidate = app.build_inline_manufacturer_candidate(form)

    assert candidate["manufacturers"] == "アクア;AQUA"


def test_inline_manufacturer_registration_ui_has_open_and_save_flow():
    source = Path(app.__file__).read_text(encoding="utf-8")
    start = source.rindex("def render_inline_manufacturer_registration")
    end = source.index("def render_inline_product_alias_registration", start)
    function_source = source[start:end]

    assert "INLINE_MANUFACTURER_OPEN_LABEL" in function_source
    assert "INLINE_SAVE_AND_REDECIDE_LABEL" in function_source
    helper_start = source.rindex("def _send_inline_candidate_to_master")
    helper_end = source.index("def render_inline_manufacturer_registration", helper_start)
    helper_source = source[helper_start:helper_end]
    assert "INLINE_SEND_TO_MASTER_LABEL" in helper_source
    assert "メーカー未登録" in function_source
    assert "原文：" in function_source
    assert 'form["manufacturer"] = normalized.strip()' in function_source
    assert "st.cache_data.clear()" in function_source
    assert "bump_case_basic_revision(st.session_state)" in function_source


def test_manufacturer_group_append_adds_aqua_and_aqua_alias_without_duplicate():
    data_dir = _make_data_dir()
    path = _write_master_csv(
        data_dir,
        "master_manufacturer_groups.csv",
        app._MFR_GROUP_COLS,
        [{"group_name": "国内家電メーカー", "manufacturers": "パナソニック", "notes": ""}],
    )

    result = app.append_master_manufacturer_group(
        {"group_name": "国内家電メーカー", "manufacturers": "アクア;AQUA", "notes": "test"},
        data_dir=str(data_dir),
    )
    duplicate = app.append_master_manufacturer_group(
        {"group_name": "国内家電メーカー", "manufacturers": "AQUA", "notes": "test"},
        data_dir=str(data_dir),
    )

    rows = _read_rows(path)
    assert result["ok"] is True
    assert os.path.exists(result["backup_path"])
    assert "アクア" in rows[0]["manufacturers"]
    assert "AQUA" in rows[0]["manufacturers"]
    assert duplicate["ok"] is False
    assert duplicate["reason"] == "duplicate"
    assert rows[0]["manufacturers"].count("AQUA") == 1


def test_product_alias_candidate_for_unknown_product():
    form = app.empty_form()
    form.update({"product": app.PRODUCT_OTHER, "product_original": "冷蔵庫"})

    candidate = app.build_inline_product_alias_candidate(form)

    assert candidate["keyword"] == "冷蔵庫"
    assert candidate["normalized_product"] == "冷蔵庫"
    assert "customer_name" not in str(candidate)


def test_vendor_rule_candidate_for_unconfirmed_vendor():
    form = app.empty_form()
    form.update({
        "call_line": "住設業務",
        "prefecture": "東京都",
        "product": "冷蔵庫",
        "manufacturer": "アクア",
        "store_name": "テスト販売店",
    })
    decision = {
        "vendor": "担当エスカ（要確認）",
        "vendor_result": {"needs_escalation": True},
        "repair_type": "出張修理",
        "area_group": "関東",
    }

    candidate = app.build_inline_vendor_rule_candidate(form, decision)

    assert candidate["call_line"] == "住設業務"
    assert candidate["prefecture"] == "東京都"
    assert candidate["product_keyword"] == "冷蔵庫"
    assert candidate["vendor_name"] == "担当エスカ（要確認）"
    assert candidate["needs_escalation"] == "1"


def test_vendor_missing_reason_includes_current_conditions():
    form = app.empty_form()
    form.update({
        "product": "冷蔵庫",
        "manufacturer": "アクア",
        "prefecture": "埼玉県",
    })

    reason = app.build_vendor_missing_reason(form, "出張修理")

    assert "冷蔵庫 × アクア × 埼玉県 × 出張修理" in reason
    assert "修理拠点ルールが未登録" in reason


def test_vendor_rule_candidate_uses_missing_reason_and_excludes_personal_fields():
    form = app.empty_form()
    form.update({
        "call_line": "住設業務",
        "prefecture": "埼玉県",
        "product": "冷蔵庫",
        "manufacturer": "アクア",
        "store_name": "アート引越センター（浦和支店）",
        "customer_name": "山田太郎",
        "phone_number": "090-0000-0000",
        "address": "埼玉県さいたま市1-1-1",
    })
    missing_reason = app.build_vendor_missing_reason(form, "出張修理")
    decision = {
        "vendor": "担当エスカ（要確認）",
        "vendor_result": {"needs_escalation": True, "vendor_missing_reason": missing_reason},
        "repair_type": "出張修理",
        "area_group": "関東",
    }

    candidate = app.build_inline_vendor_rule_candidate(form, decision)
    candidate_text = str(candidate)

    assert candidate["prefecture"] == "埼玉県"
    assert candidate["product_keyword"] == "冷蔵庫"
    assert candidate["manufacturer_keyword"] == "アクア"
    assert candidate["repair_type"] == "出張修理"
    assert candidate["reason"] == missing_reason
    for blocked_value in ("山田太郎", "090-0000-0000", "埼玉県さいたま市1-1-1"):
        assert blocked_value not in candidate_text


def test_vendor_rule_append_creates_backup():
    data_dir = _make_data_dir()
    path = _write_master_csv(data_dir, "master_vendor_rules.csv", app._VENDOR_COLS)

    result = app.append_master_vendor_rule(
        {
            "call_line": "住設業務",
            "prefecture": "東京都",
            "product_keyword": "冷蔵庫",
            "store_keyword": "テスト販売店",
            "repair_type": "出張修理",
            "vendor_name": "ユナイトサービス㈱",
            "reason": "test",
            "needs_escalation": "0",
        },
        data_dir=str(data_dir),
    )

    rows = _read_rows(path)
    assert result["ok"] is True
    assert os.path.exists(result["backup_path"])
    assert rows[0]["vendor_name"] == "ユナイトサービス㈱"


def test_store_rule_candidate_for_fallback_template():
    form = app.empty_form()
    form["store_name"] = "アート引越センター"
    template_selection = {
        "source": "fallback",
        "label": "通常テンプレート",
        "template_code": "TPL-1",
        "store_rule": {"matched": False},
    }

    candidate = app.build_inline_store_rule_candidate(form, template_selection)

    assert candidate["store_keyword"] == "アート引越センター"
    assert candidate["template_code"] == "TPL-1"
    assert candidate["template_label"] == "通常テンプレート"


def test_master_append_clears_streamlit_cache(monkeypatch):
    data_dir = _make_data_dir()
    _write_master_csv(data_dir, "master_product_alias.csv", app._ALIAS_COLS)
    clear_mock = mock.MagicMock()
    monkeypatch.setattr(app, "_clear_streamlit_cache", clear_mock)

    app.append_master_product_alias(
        {"keyword": "冷蔵庫", "normalized_product": "冷蔵庫"},
        data_dir=str(data_dir),
    )

    clear_mock.assert_called_once()


def test_call_line_master_upsert_updates_row_and_creates_backup(monkeypatch):
    data_dir = _make_data_dir()
    path = _write_master_csv(
        data_dir,
        "master_call_lines.csv",
        app._CALL_LINE_COLS,
        [{
            "priority": "10",
            "enabled": "1",
            "call_line": "家電保証対応業務（24時間）",
            "line_group": "家電",
            "notes": "",
            "call_line_code": "home_appliance",
            "display_name": "家電保証対応業務（24時間）",
            "rakutel_line_name": "家電保証対応業務（24時間）",
            "aliases": "",
        }],
    )
    clear_mock = mock.MagicMock()
    monkeypatch.setattr(app, "_clear_streamlit_cache", clear_mock)

    result = app.upsert_master_call_line(
        {
            "priority": "10",
            "enabled": "1",
            "call_line": "家電保証対応業務（24時間）",
            "line_group": "家電",
            "notes": "旧表示名から変更",
            "call_line_code": "home_appliance",
            "display_name": "家電",
            "rakutel_line_name": "家電",
            "aliases": "家電保証対応業務（24時間）;家電保証対応業務",
        },
        data_dir=str(data_dir),
    )

    rows = _read_rows(path)
    assert result["ok"] is True
    assert rows[0]["display_name"] == "家電"
    assert rows[0]["rakutel_line_name"] == "家電"
    assert "家電保証対応業務（24時間）" in rows[0]["aliases"]
    assert os.path.exists(result["backup_path"])
    clear_mock.assert_called_once()


def test_vendor_send_template_upsert_creates_backup_and_clears_cache(monkeypatch):
    data_dir = _make_data_dir()
    path = _write_master_csv(data_dir, "master_vendor_send_templates.csv", app._VENDOR_SEND_TEMPLATE_COLS)
    clear_mock = mock.MagicMock()
    monkeypatch.setattr(app, "_clear_streamlit_cache", clear_mock)

    result = app.upsert_vendor_send_template(
        {
            "template_code": "0009",
            "template_label": "【出張修理】自然故障",
            "repair_type": "出張修理",
            "warranty_type": "自然故障",
            "attention_memo_template": "※修理キャンセル時の概算費用{{estimated_fee}}",
        },
        data_dir=str(data_dir),
    )

    rows = _read_rows(path)
    assert result["ok"] is True
    assert rows[0]["template_code"] == "0009"
    assert "{{estimated_fee}}" in rows[0]["attention_memo_template"]
    assert os.path.exists(result["backup_path"])
    clear_mock.assert_called_once()


def test_master_ui_has_call_line_and_vendor_template_editors():
    source = Path(app.__file__).read_text(encoding="utf-8")

    assert "回線名マスタ編集" in source
    assert "rakutel_line_name" in source
    assert "テンプレート編集" in source
    assert "業者送付コードテンプレートを編集" in source


def test_master_registration_candidate_excludes_personal_fields():
    form = app.empty_form()
    form.update(
        {
            "product_original": "電気調理器・調理圧力鍋",
            "product": "その他・要確認",
            "series": "電気調理器・調理圧力鍋",
            "manufacturer": "パナソニック",
            "manufacturer_original": "Panasonic",
            "store_name": "マサニ電気 株式会社",
            "customer_name": "山田太郎",
            "phone_number": "090-0000-0000",
            "contact_phone": "03-0000-0000",
            "address": "東京都千代田区1-1-1",
            "wrt_no": "WRT-123",
        }
    )

    candidate = app.build_master_registration_candidate(form)
    candidate_text = str(candidate)

    assert candidate["product_alias"]["keyword"] == "電気調理器・調理圧力鍋"
    assert candidate["product_alias"]["normalized_product"] == "電気調理器"
    assert candidate["product_alias"]["product_group"] == "キッチン家電"
    assert candidate["repair_type_rule"]["repair_type"] == "持込修理"
    assert candidate["store_rule"]["store_keyword"] == "マサニ電気"
    for blocked_value in ["山田太郎", "090-0000-0000", "03-0000-0000", "東京都千代田区1-1-1", "WRT-123"]:
        assert blocked_value not in candidate_text
