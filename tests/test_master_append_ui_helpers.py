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
