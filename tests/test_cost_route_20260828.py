# -*- coding: utf-8 -*-
import os
import sys
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_st_mock = mock.MagicMock()
_st_mock.cache_data = lambda f: f
sys.modules["streamlit"] = _st_mock

import app  # noqa: E402


def selected_form(*, line="住設", product="", manufacturer="", aircon_type=""):
    form = app.empty_form()
    form.update(
        call_line=line,
        manual_call_line=True,
        appliance_type="住設" if line != "家電" else "家電",
        product=product,
        manufacturer=manufacturer,
        aircon_type=aircon_type,
    )
    return form


def test_selected_jusetsu_line_uses_housing_generic_cost():
    result = app.determine_cost_from_rules(
        selected_form(product="システムキッチン", manufacturer="パナソニック"),
        "出張修理",
    )
    assert result["cost_estimate"] == "5,000円～13,000円前後"
    assert result["cost_status"] == "confirmed"


def test_selected_jusetsu_line_updates_included_water_heater_costs():
    for product in (
        "ガス給湯器",
        "石油給湯器",
        "ハイブリッド給湯器",
        "エネファーム",
        "電気温水器",
        "電気暖房温水ボイラー",
    ):
        result = app.determine_cost_from_rules(selected_form(product=product), "出張修理")
        assert result["cost_estimate"] == "5,000円～13,000円前後", product


def test_selected_jusetsu_line_uses_latest_daikin_ecocute_cost():
    result = app.determine_cost_from_rules(
        selected_form(product="エコキュート", manufacturer="ダイキン"),
        "出張修理",
    )
    assert result["cost_estimate"] == "20,000円～25,000円前後"


def test_selected_line_uses_latest_daikin_home_aircon_cost():
    result = app.determine_cost_from_rules(
        selected_form(
            line="家電",
            product="エアコン",
            manufacturer="ダイキン",
            aircon_type=app.AIRCON_TYPE_HOME,
        ),
        "出張修理",
    )
    assert result["cost_estimate"] == "7,000円～19,000円前後"


def test_selected_line_sk_japan_carry_in_is_not_generic_price():
    result = app.determine_cost_from_rules(
        selected_form(line="家電", product="ドライヤー", manufacturer="エスケイジャパン"),
        "持込修理",
    )
    assert result["cost_estimate"] == "-"
    assert result["cost_status"] == "unavailable"
    assert result["can_announce_cost"] is False


def test_selected_jusetsu_fallback_never_returns_household_generic_cost():
    form = selected_form(product="住宅設備機器")
    assert app.determine_cost_estimate(form, "出張修理") == "5,000円～13,000円前後"


def test_nonmanual_legacy_path_is_unchanged_for_regression_compatibility():
    form = app.empty_form()
    form.update(product="ガス給湯器", manual_call_line=False)
    result = app.determine_cost_from_rules(form, "出張修理")
    assert result["cost_estimate"] == "5,000円～7,000円前後"
