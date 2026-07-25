# -*- coding: utf-8 -*-

import os
import sys
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
