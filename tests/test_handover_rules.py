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


def wrs_handover(form, vendor_result=None):
    return app.determine_wrs_handover_action(form, vendor_result)


def test_handover_master_loads_and_sorts_by_priority():
    df = app.load_handover_rules()

    assert not df.empty
    assert list(df.columns) == app._HANDOVER_RULE_COLS
    assert df["priority"].tolist() == sorted(df["priority"].tolist())


def test_wrs_handover_master_loads_and_sorts_by_priority():
    df = app.load_wrs_handover_rules()

    assert not df.empty
    assert list(df.columns) == app._WRS_HANDOVER_RULE_COLS
    assert df["priority"].tolist() == sorted(df["priority"].tolist())


def test_ai_koumuten_vendor_stays_unite_and_wrs_handover_is_separate():
    form = make_form(
        operating_company="株式会社アイ工務店",
        store_name="滋賀支店",
        prefecture="滋賀県",
        product="システムキッチン",
        appliance_type="住設",
        warranty_plan="住宅設備機器保証パッケージ 10年保証",
    )
    decision = app.run_decision(form)
    wrs = decision["wrs_handover_action"]

    assert "ユナイト" in decision["vendor"]
    assert "WRS" not in decision["vendor"]
    assert decision["vendor_result"]["reason"] == "依頼先一覧 No.7 上記以外・全国・全メーカー"
    assert wrs["needs_wrs_handover"] is True
    assert wrs["rule_name"] == "アイ工務店"
    assert wrs["action_type"] == "受付報告"
    assert "根拠：" in wrs["basis_text"]


def test_keihan_wrs_handover_keeps_alsok_note():
    result = wrs_handover(make_form(call_line="京阪不動産"))

    assert result["needs_wrs_handover"] is True
    assert result["rule_name"] == "京阪"
    assert "ALSOK入力有無" in result["note_template"]
    assert "根拠：" in result["basis_text"]


def test_yamada_homes_keeps_generic_jusetsu_script_and_gets_wrs_handover():
    form = make_form(call_line="ヤマダホームズ修理受付業務", appliance_category="住設（新築）")
    route = app.judge_script_route(form)
    wrs = wrs_handover(form)

    assert route["display_name"] == "0099回線（住設新築）"
    assert route["script_key"] != "yamada_homes"
    assert wrs["needs_wrs_handover"] is True
    assert wrs["rule_name"] == "ヤマダホームズ"


def test_jusetsu_kaketsuke_wrs_handover_does_not_overwrite_vendor():
    form = make_form(
        call_line="駆けつけサブスク",
        appliance_type="住設",
        warranty_plan="駆けつけ 24h",
        prefecture="東京都",
        product="トイレ",
    )
    decision = app.run_decision(form)
    wrs = decision["wrs_handover_action"]

    assert wrs["needs_wrs_handover"] is True
    assert wrs["rule_name"] == "住設駆けつけ"
    assert "WRS" not in decision["vendor"]
    assert decision["vendor"] != wrs["handover_request_content"]


def test_normal_case_has_no_wrs_handover_and_keeps_no7_unite_fallback():
    form = make_form(
        prefecture="滋賀県",
        product="システムキッチン",
        appliance_type="住設",
        warranty_plan="住宅設備機器保証パッケージ",
    )
    decision = app.run_decision(form)
    wrs = decision["wrs_handover_action"]

    assert "ユナイト" in decision["vendor"]
    assert decision["vendor_result"]["reason"] == "依頼先一覧 No.7 上記以外・全国・全メーカー"
    assert wrs["needs_wrs_handover"] is False


def test_wrs_handover_panel_renders_basis_text():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    panel_start = source.index("def render_wrs_handover_action_panel")
    panel_end = source.index("\ndef render_warranty_report_send_panel", panel_start)
    panel_source = source[panel_start:panel_end]

    assert "basis_text" in panel_source
    assert "WRS引き継ぎ" in panel_source
    assert "render_wrs_handover_action_panel(decision.get(\"wrs_handover_action\"))" in source


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
        call_line="家電",
        store_name="ヤマダホームズ",
        warranty_report_content="ユナイトへFAX送信済",
    )
    decision = {
        "vendor": "ユナイトサービス㈱",
        "vendor_result": {"vendor_name": "ユナイトサービス㈱", "send_method": "FAX"},
        "handover_requirement": handover(form),
    }

    message = app.build_warranty_report_message(form, decision)

    assert message == "2026_05_1073　家電　ユナイトへFAX送信済　ご確認お願いします"


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
