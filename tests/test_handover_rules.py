# -*- coding: utf-8 -*-
from pathlib import Path

import app


ROOT = Path(__file__).resolve().parents[1]


def make_form(**overrides):
    form = app.empty_form()
    form.update(overrides)
    return form


def handover(form, call_kind="repair", decision=None):
    decision = decision or {"repair_type": form.get("repair_type", "出張修理"), "vendor_result": {}}
    return app.determine_handover_requirement(form, decision, call_kind)


def test_handover_master_loads_and_sorts_by_priority():
    df = app.load_handover_rules()

    assert not df.empty
    assert list(df.columns) == app._HANDOVER_RULE_COLS
    assert df["priority"].tolist() == sorted(df["priority"].tolist())


def test_yamada_homes_repair_requires_handover():
    result = handover(make_form(store_name="ヤマダホームズ"))

    assert result["required"] is True
    assert result["rule_name"] == "ヤマダホームズ"
    assert result["rakutel_status"] == "【BKK】WRS（福岡）へ対応依頼"
    assert result["handover_request_content"] == "受付報告"
    assert "間違い電話は不要" in result["notes"]
    assert result["exclude_wrong_number"] is True


def test_yamada_homes_operating_company_repair_requires_handover():
    result = handover(make_form(operating_company="株式会社ヤマダホームズ"))

    assert result["required"] is True
    assert result["rule_name"] == "ヤマダホームズ"


def test_ai_koumuten_repair_requires_handover():
    result = handover(make_form(operating_company="株式会社アイ工務店"))

    assert result["required"] is True
    assert result["rule_name"] == "アイ工務店"
    assert result["handover_request_content"] == "受付報告"


def test_life_design_kabaya_repair_requires_handover():
    result = handover(make_form(store_name="ライフデザインカバヤ"))

    assert result["required"] is True
    assert result["rule_name"] == "ライフデザインカバヤ"
    assert result["handover_request_content"] == "受付報告"


def test_keihan_repair_keeps_alsok_note():
    result = handover(make_form(store_company="京阪"))

    assert result["required"] is True
    assert result["rule_name"] == "京阪"
    assert "ALSOK入力有無まで引き継ぎ" in result["notes"]


def test_appliance_warranty_resend_inquiry_uses_mail_request():
    result = handover(
        make_form(symptom="保証書再送希望", appliance_type="家電"),
        call_kind="inquiry",
    )

    assert result["required"] is True
    assert result["rule_name"] == "保証書再送希望（家電製品）"
    assert result["handover_request_content"] == "メール対応依頼"


def test_residential_warranty_resend_inquiry_uses_handling_request():
    result = handover(
        make_form(symptom="保証書再送希望", appliance_type="住設"),
        call_kind="inquiry",
    )

    assert result["required"] is True
    assert result["rule_name"] == "保証書再送希望（住宅設備）"
    assert result["handover_request_content"] == "対応依頼"
    assert "メール送信不可" in result["notes"]


def test_before_request_cancel_uses_cancel_status_and_content():
    result = handover(make_form(memo="依頼前_修理キャンセル"))

    assert result["required"] is True
    assert result["rule_name"] == "依頼前_修理キャンセル"
    assert result["rakutel_status"] == "依頼前キャンセル"
    assert result["handover_request_content"] == "キャンセル"


def test_claim_priority_wins_over_store_rule():
    result = handover(make_form(store_name="ヤマダホームズ", symptom="クレーム案件"))

    assert result["required"] is True
    assert result["rule_name"] == "クレーム案件"
    assert result["priority"] < 18


def test_no_matching_store_is_not_required():
    result = handover(make_form(store_name="対象外販売店"))

    assert result == {
        "required": False,
        "matched": False,
        "reason": "引き継ぎ対象ルールに一致なし",
    }


def test_run_decision_includes_handover_without_auto_filling_call_line():
    form = make_form(store_name="ヤマダホームズ", product="エアコン")
    decision = app.run_decision(form)

    assert decision["handover_requirement"]["required"] is True
    assert decision["handover_requirement"]["rule_name"] == "ヤマダホームズ"
    assert decision["working_form"]["call_line"] == ""


def test_handover_does_not_change_existing_warranty_report_format():
    form = make_form(
        rakuteru_no="2026_05_1073",
        store_name="ヤマダホームズ",
    )
    decision = {
        "vendor": "ユナイトサービス㈱",
        "vendor_result": {"vendor_name": "ユナイトサービス㈱", "send_method": "FAX"},
        "handover_requirement": handover(form),
    }

    message = app.build_warranty_report_message(form, decision)

    assert message == "2026_05_1073　ヤマダホームズ　修理受付済　ユナイトへFAX送信済　ご確認お願い致します。"


def test_handover_text_stays_out_of_rakutel_teams_and_repair_request_memo():
    form = make_form(
        operator_name="大濱",
        call_line="家電保証対応業務（24時間）",
        appliance_type="家電",
        product="エアコン",
        manufacturer="ダイキン",
        store_name="ヤマダホームズ",
        rakuteru_no="2026_05_1073",
        teams_action="FAX送信済",
    )
    warranty_result = {"title": "保証中", "warranty_status": "active", "can_accept": True}
    handover_result = handover(form)
    memo = app._build_after_call_memo(form, warranty_result, "出張修理", "ユナイトサービス㈱", "", "5,000円～7,000円前後")
    rakutel = app._build_rakutel_text(form, "加入者", "")
    teams = app._build_teams_chat_message(form, "ユナイトサービス㈱")

    forbidden = [
        handover_result["rakutel_status"],
        handover_result["handover_request_content"],
        handover_result["notes"],
    ]
    for text in (memo, rakutel, teams):
        for value in forbidden:
            assert value not in text


def test_handover_panel_is_rendered_before_warranty_report_panel():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_source = source[source.index("def render_tab_after_call"):source.index("def _candidate_field")]

    assert "render_handover_requirement_panel(decision.get(\"handover_requirement\"))" in after_source
    assert after_source.index("render_handover_requirement_panel") < after_source.index("render_warranty_report_send_panel")
