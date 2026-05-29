# -*- coding: utf-8 -*-
"""実ケース寄りの重要判定回帰テスト。"""

from pathlib import Path

import pytest

import app


ROOT = Path(__file__).resolve().parents[1]


def make_form(**overrides):
    form = app.empty_form()
    form.update(overrides)
    return form


def selected_template(form, decision):
    return app.select_template_for_form(
        decision["working_form"],
        decision["repair_type"],
        decision["working_form"].get("warranty_plan", ""),
        app.load_template_codes(),
    )


def assert_wrs(decision, rule_name):
    wrs = decision["wrs_handover_action"]
    assert wrs["needs_wrs_handover"] is True
    assert wrs["rule_name"] == rule_name
    assert wrs["action_type"] == "受付報告"
    assert wrs["handover_request_content"] == "【BKK】WRS（福岡）へ対応依頼"


def test_ai_koumuten_jusetsu_system_kitchen_uses_no7_unite_and_wrs():
    form = make_form(
        product="システムキッチン",
        series="システムキッチン",
        manufacturer="パナソニック",
        prefecture="滋賀県",
        appliance_type="家電",
        store_name="滋賀支店",
        store_original="株式会社アイ工務店",
        operating_company="株式会社アイ工務店",
        warranty_plan="アイ工務店_住宅設備機器【10年保証】",
        genre="(新品)住宅設備機器",
        category="システムキッチン",
    )

    decision = app.run_decision(form)
    template = selected_template(form, decision)

    assert decision["working_form"]["appliance_type"] == "住設"
    assert decision["repair_type"] == "出張修理"
    assert template["template_code"] == "0058"
    assert template["label"] == "【出張修理】上位5社"
    assert decision["vendor"] == "ユナイトサービス㈱"
    assert decision["vendor_result"]["reason"] == "依頼先一覧 No.7 上記以外・全国・全メーカー"
    assert_wrs(decision, "アイ工務店")


def test_yamada_homes_jusetsu_uses_generic_script_and_wrs():
    form = make_form(
        call_line="ヤマダホームズ修理受付業務",
        store_name="ヤマダホームズ",
        appliance_category="住設（新築）",
        appliance_type="住設",
        product="システムキッチン",
        manufacturer="パナソニック",
        prefecture="滋賀県",
    )

    decision = app.run_decision(form)
    route = app.judge_script_route(decision["working_form"])

    assert route["display_name"] == "0099回線（住設新築）"
    assert route["script_key"] != "yamada_homes"
    assert_wrs(decision, "ヤマダホームズ")


def test_life_design_kabaya_is_not_treated_as_normal_non_wrs_case():
    form = make_form(
        store_name="ライフデザイン・カバヤ株式会社 岡山中央展示場",
        operating_company="ライフデザインカバヤ",
        prefecture="岡山県",
        product="食器洗い乾燥機",
        manufacturer="三菱電機",
        appliance_type="住設",
        warranty_plan="住宅設備機器保証パッケージ【10年保証】",
    )

    decision = app.run_decision(form)

    assert decision["repair_type"] == "出張修理"
    assert decision["vendor"] == "ユナイトサービス㈱"
    assert decision["vendor_result"]["reason"] == "ライフデザイン・カバヤ通常出張"
    assert_wrs(decision, "ライフデザインカバヤ")


def test_keihan_wrs_keeps_alsok_note():
    form = make_form(
        call_line="京阪不動産",
        store_name="京阪",
        appliance_type="住設",
        product="システムキッチン",
        manufacturer="パナソニック",
        prefecture="滋賀県",
    )

    decision = app.run_decision(form)

    assert_wrs(decision, "京阪")
    assert "ALSOK入力有無" in decision["wrs_handover_action"]["note_template"]


def test_kohnan_jusetsu_keeps_dedicated_script_and_wrs():
    form = make_form(
        call_line="コーナン（住設）",
        store_name="コーナン住設",
        appliance_type="住設",
        product="システムキッチン",
        manufacturer="パナソニック",
        prefecture="大阪府",
    )

    decision = app.run_decision(form)
    route = app.judge_script_route(decision["working_form"])

    assert route["display_name"] == "コーナン住設"
    assert_wrs(decision, "コーナン住設")


def test_mach_yucaco_keeps_dedicated_script_and_wrs():
    form = make_form(
        call_line="マッハユカコ",
        store_name="マッハシステム",
        appliance_type="住設",
        product="システムキッチン",
        manufacturer="パナソニック",
        prefecture="東京都",
    )

    decision = app.run_decision(form)
    route = app.judge_script_route(decision["working_form"])

    assert route["display_name"] == "マッハ・YUCACO"
    assert_wrs(decision, "マッハシステム・YUCACOシステム")


def test_normal_visit_case_has_no_wrs_and_uses_no7_unite_fallback():
    form = make_form(
        store_name="通常販売店",
        appliance_type="住設",
        product="システムキッチン",
        series="システムキッチン",
        manufacturer="パナソニック",
        prefecture="滋賀県",
    )

    decision = app.run_decision(form)

    assert decision["repair_type"] == "出張修理"
    assert decision["vendor"] == "ユナイトサービス㈱"
    assert decision["vendor_result"]["reason"] == "依頼先一覧 No.7 上記以外・全国・全メーカー"
    assert decision["wrs_handover_action"]["needs_wrs_handover"] is False


@pytest.mark.parametrize(
    ("store_name", "expected_vendor", "expected_wrs_rule"),
    [
        ("株式会社三建", "株式会社三建", "株式会社三建"),
        ("住宅資材センター", "住宅資材センター", "住宅資材センター"),
        ("キューハウ", "株式会社キューハウ", "キューハウ / Comfo home"),
    ],
)
def test_self_repair_vendor_rules_win_over_no7_fallback(store_name, expected_vendor, expected_wrs_rule):
    form = make_form(
        store_name=store_name,
        appliance_type="住設",
        product="システムキッチン",
        manufacturer="パナソニック",
        prefecture="滋賀県",
    )

    decision = app.run_decision(form)

    assert decision["repair_type"] == "出張修理"
    assert decision["vendor"] == expected_vendor
    assert decision["vendor_result"]["reason"] != "依頼先一覧 No.7 上記以外・全国・全メーカー"
    assert "自店修理" in decision["vendor_result"]["reason"]
    assert_wrs(decision, expected_wrs_rule)


def test_wrs_only_target_does_not_overwrite_repair_vendor():
    form = make_form(
        store_name="Comfo home",
        appliance_type="住設",
        product="食器洗い乾燥機",
        manufacturer="Bosch",
        prefecture="東京都",
    )

    decision = app.run_decision(form)

    assert_wrs(decision, "キューハウ / Comfo home")
    assert decision["vendor"] != decision["wrs_handover_action"]["handover_request_content"]
    assert "WRS" not in decision["vendor"]


@pytest.mark.parametrize(
    ("store_name", "appliance_type", "expected_wrs_rule"),
    [
        ("SKY", "住設", "SKY"),
        ("電算システム", "住設", "電算システム案件"),
        ("三城メガネ", "家電", "三城案件（メガネ）"),
        ("コジマ CHIKYUJIN", "家電", "コジマ（CHIKYUJIN）"),
        ("チャオ", "家電", "チャオ"),
        ("WM案件 M停止", "家電", "WM案件（M停止）"),
    ],
)
def test_added_wrs_only_targets_do_not_overwrite_repair_vendor(store_name, appliance_type, expected_wrs_rule):
    form = make_form(
        store_name=store_name,
        appliance_type=appliance_type,
        product="システムキッチン" if appliance_type == "住設" else "ドライヤー",
        manufacturer="パナソニック",
        prefecture="滋賀県",
    )

    decision = app.run_decision(form)

    assert_wrs(decision, expected_wrs_rule)
    assert decision["vendor"] != decision["wrs_handover_action"]["handover_request_content"]
    assert "WRS" not in decision["vendor"]


def test_real_case_regression_source_has_no_unwanted_chinese_button_text():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert "按钮" not in source
