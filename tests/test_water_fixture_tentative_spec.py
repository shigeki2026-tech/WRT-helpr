# WATER_FIXTURE_TENTATIVE_SPEC_TESTS
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

WATER_FIXTURE_PRODUCTS = (
    "水栓",
    "混合水栓",
    "トイレ水栓",
    "システムバス混合水栓",
)


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8-sig")


def csv_lines_containing(relative_path: str, keywords: tuple[str, ...]) -> list[str]:
    text = read_text(relative_path)
    return [
        line
        for line in text.splitlines()
        if any(keyword in line for keyword in keywords)
    ]


def test_water_fixture_specific_repair_type_rules_are_not_registered_yet():
    lines = csv_lines_containing(
        "data/master_repair_type_rules.csv",
        WATER_FIXTURE_PRODUCTS,
    )

    assert lines == []


def test_water_fixture_specific_cost_rules_are_not_registered_yet():
    lines = csv_lines_containing(
        "data/master_cost_rules.csv",
        WATER_FIXTURE_PRODUCTS,
    )

    assert lines == []


def test_water_fixture_specific_vendor_rules_are_not_registered_yet():
    lines = csv_lines_containing(
        "data/master_vendor_rules.csv",
        WATER_FIXTURE_PRODUCTS,
    )

    assert lines == []


def test_water_fixture_spec_memo_marks_section_8_as_tentative_not_current_implementation():
    text = read_text("docs/WATER_FIXTURE_MASTER_SPEC_CHECK.md")

    assert "## 8. 水栓系の仮仕様案" in text
    assert "現時点では、CSVマスタへの確定登録はまだ行わない。" in text
    assert "この仮仕様で進める場合でも、先にテスト追加を行い、CSV変更はその後にする。" in text


def test_water_fixture_spec_memo_records_focused_test_correction():
    text = read_text("docs/WATER_FIXTURE_MASTER_SPEC_CHECK.md")

    assert "## 9. focused test結果による補正" in text
    assert "Section 8 は、現行仕様ではなく「採用するならこうする」という仮仕様案である。" in text
    assert "CSVマスタは変更しない" in text


def test_water_fixture_product_item_behavior_is_covered_by_existing_regression_tests():
    product_items_tests = read_text("tests/test_product_items.py")

    assert "test_extract_labeled_residential_phase_restores_appliance_category" in product_items_tests
    assert "トイレ水栓" in product_items_tests
    assert "システムバス混合水栓" in product_items_tests
    assert "selected[\"product\"] == \"水栓\"" in product_items_tests
    assert "selected[\"manufacturer_original\"] == \"国内メーカー\"" in product_items_tests
    assert "synced[\"appliance_category\"] == \"住設（既築）\"" in product_items_tests
    assert "synced[\"product_price\"] == \"0円\"" in product_items_tests
