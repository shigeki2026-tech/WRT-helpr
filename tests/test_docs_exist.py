# -*- coding: utf-8 -*-
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_manual_checklist_exists():
    assert (ROOT / "docs" / "manual_checklist.md").is_file()


def test_demo_cases_exists():
    assert (ROOT / "docs" / "demo_cases.md").is_file()


def test_demo_cases_include_required_case_ids():
    text = (ROOT / "docs" / "demo_cases.md").read_text(encoding="utf-8")
    for case_id in [
        "expired_washer",
        "before_start_aircon",
        "aircon_missing_maker",
        "generic_water_heater",
        "normal_dryer",
    ]:
        assert case_id in text
