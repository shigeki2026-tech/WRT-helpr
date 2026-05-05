# -*- coding: utf-8 -*-

import csv
import os
import sys
import unittest.mock as mock


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


def test_product_alias_append_adds_one_row_and_backup(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
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


def test_product_alias_duplicate_keyword_is_detected(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
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


def test_repair_type_rule_append_adds_one_row(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
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


def test_store_rule_append_adds_one_row(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
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
