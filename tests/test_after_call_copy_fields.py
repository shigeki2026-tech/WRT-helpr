# -*- coding: utf-8 -*-

import os
import sys
import types
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_st_mock = mock.MagicMock()
_st_mock.cache_data = lambda f: f
sys.modules["streamlit"] = _st_mock

import app  # noqa: E402


def test_residential_without_phase_stays_unselected():
    assert app.normalize_appliance_category("", "住設", "") == ""
    assert app.normalize_appliance_category("住設", "", "") == ""


def test_residential_existing_requires_explicit_existing_evidence():
    assert app.normalize_appliance_category("", "住設", "既築") == "住設（既築）"
    assert app.normalize_appliance_category("住設（既築）", "", "") == "住設（既築）"


def test_after_call_copy_values_are_independent_and_price_is_digits_only():
    form = {
        "model_number": " ABC-123 ",
        "manufacturer": " パナソニック ",
        "product": "電子レンジ",
        "product_price": "50,000円（税込）",
    }
    values = app.build_after_call_field_copy_values(form, {"normalized_product": "オーブンレンジ"})

    assert values == {
        "model_number": "ABC-123",
        "manufacturer": "パナソニック",
        "product": "オーブンレンジ",
        "product_price": "50000",
    }


def test_product_price_copy_normalizes_full_width_digits():
    assert app.digits_only("１２３，４５６ 円") == "123456"


def test_clipboard_history_items_are_separate_and_keep_external_field_order():
    form = {
        "model_number": "ABC-123",
        "manufacturer": "パナソニック",
        "product": "電子レンジ",
        "product_price": "50,000円",
    }

    items = app.build_after_call_clipboard_history_items(form)

    assert items == [
        ("型番", "ABC-123"),
        ("メーカー", "パナソニック"),
        ("製品", "電子レンジ"),
        ("商品金額", "50000"),
    ]


def test_clipboard_history_copy_writes_reverse_so_win_v_shows_field_order(monkeypatch):
    copied_values = []
    monkeypatch.setattr(app, "_PYPERCLIP_AVAILABLE", True)
    monkeypatch.setattr(
        app,
        "pyperclip",
        types.SimpleNamespace(copy=copied_values.append),
        raising=False,
    )
    monkeypatch.setattr(app.time, "sleep", lambda _seconds: None)

    copied_labels = app.copy_after_call_fields_to_clipboard_history(
        {
            "model_number": "ABC-123",
            "manufacturer": "パナソニック",
            "product": "電子レンジ",
            "product_price": "50,000円",
        },
        delay_seconds=0,
    )

    assert copied_values == ["50000", "電子レンジ", "パナソニック", "ABC-123"]
    assert copied_labels == ["型番", "メーカー", "製品", "商品金額"]
