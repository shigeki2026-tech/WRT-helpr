# WATER_FIXTURE_IMPLEMENTATION_TESTS
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8-sig")


def csv_lines_containing(relative_path: str, keywords: tuple[str, ...]) -> list[str]:
    text = read_text(relative_path)
    return [
        line
        for line in text.splitlines()
        if any(keyword in line for keyword in keywords)
    ]


def test_water_fixture_master_csv_rows_exist_after_implementation():
    repair_lines = csv_lines_containing("data/master_repair_type_rules.csv", ("水栓",))
    cost_lines = csv_lines_containing("data/master_cost_rules.csv", ("水栓",))
    vendor_lines = csv_lines_containing("data/master_vendor_rules.csv", ("水栓",))

    assert any("水栓" in line and "出張修理" in line for line in repair_lines)
    assert any("水栓" in line and "5,000円～13,000円前後" in line for line in cost_lines)
    assert any("水栓" in line and "クリンスイ" in line and "未確定" in line for line in cost_lines)
    assert any("水栓" in line and "ユナイトサービス㈱" in line and "10年以内・年数不明" in line for line in vendor_lines)
    assert any("水栓" in line and "クラシアン（交換）" in line and "10年以上" in line for line in vendor_lines)


def test_water_fixture_repair_type_rule_csv_contract():
    lines = csv_lines_containing("data/master_repair_type_rules.csv", ("水栓",))

    assert any("水栓" in line and "出張修理" in line for line in lines)


def test_water_fixture_cost_rule_csv_contract():
    lines = csv_lines_containing("data/master_cost_rules.csv", ("水栓", "クリンスイ"))

    assert any(
        "水栓" in line
        and "出張修理" in line
        and "5,000円～13,000円前後" in line
        and "confirmed" in line
        for line in lines
    )
    assert any(
        "水栓" in line
        and "クリンスイ" in line
        and "出張修理" in line
        and "不可" in line
        for line in lines
    )


def test_water_fixture_vendor_rule_csv_contract():
    lines = csv_lines_containing("data/master_vendor_rules.csv", ("水栓",))

    assert any(
        "水栓" in line
        and "0" in line
        and "ユナイトサービス㈱" in line
        and "既築／中古 水栓 10年以内・年数不明" in line
        for line in lines
    )
    assert any(
        "水栓" in line
        and "1" in line
        and "クラシアン（交換）" in line
        and "既築／中古 水栓 10年以上" in line
        for line in lines
    )


def test_water_fixture_spec_memo_records_implementation_section():
    text = read_text("docs/WATER_FIXTURE_MASTER_SPEC_CHECK.md")

    assert "## 10. 水栓系マスタ採用実装" in text
    assert "水栓系は住設 / 出張修理" in text
    assert "クリンスイ水栓は概算費用も事前提示不可" in text
    assert "10年以内・年数不明はユナイトサービス㈱" in text
    assert "10年以上はクラシアン（交換）" in text


def test_water_fixture_product_item_behavior_remains_covered_by_existing_regression_tests():
    product_items_tests = read_text("tests/test_product_items.py")

    assert "トイレ水栓" in product_items_tests
    assert "システムバス混合水栓" in product_items_tests
    assert "selected[\"product\"] == \"水栓\"" in product_items_tests
    assert "selected[\"manufacturer_original\"] == \"国内メーカー\"" in product_items_tests
    assert "synced[\"appliance_category\"] == \"住設（既築）\"" in product_items_tests
    assert "synced[\"product_price\"] == \"0円\"" in product_items_tests
