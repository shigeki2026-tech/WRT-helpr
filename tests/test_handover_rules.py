# -*- coding: utf-8 -*-
from pathlib import Path

import app
import pytest


ROOT = Path(__file__).resolve().parents[1]


NEW_WRS_HANDOVER_CASES = (
    ("ニッテイライフ", "ニッテイライフ"),
    ("トレス", "トレス"),
    ("MED Communications", "MED Communications"),
    ("MEDコミュニケーションズ", "MED Communications"),
    ("キューハウ", "キューハウ / Comfo home"),
    ("Comfo home", "キューハウ / Comfo home"),
    ("住宅資材センター", "住宅資材センター"),
    ("大成有楽", "大成有楽"),
    ("相鉄不動産", "相鉄不動産"),
    ("オンレイ", "オンレイ"),
    ("フュディアル", "フュディアル"),
    ("株式会社ミツウロコヴェッセル", "株式会社ミツウロコヴェッセル"),
    ("ミツウロコヴェッセル", "株式会社ミツウロコヴェッセル"),
    ("クリーンリバー", "クリーンリバー"),
    ("ケィ・マックインダストリー", "ケィ・マックインダストリー"),
    ("ケイマックインダストリー", "ケィ・マックインダストリー"),
    ("株式会社三建", "株式会社三建"),
    ("三建", "株式会社三建"),
    ("FUTAEDA", "FUTAEDA"),
    ("フタエダ", "FUTAEDA"),
    ("木場(こば)家電住宅設備", "木場家電住宅設備"),
    ("こば家電住宅設備", "木場家電住宅設備"),
    ("ぽちる", "ぽちる"),
    ("SKY", "SKY"),
    ("電算システム", "電算システム案件"),
    ("三城", "三城案件（メガネ）"),
    ("コジマ", "コジマ（CHIKYUJIN）"),
    ("CHIKYUJIN", "コジマ（CHIKYUJIN）"),
    ("チャオ", "チャオ"),
    ("WM案件", "WM案件（M停止）"),
    ("M停止", "WM案件（M停止）"),
    ("松﨑電機", "松﨑電機 / エアコンのマツ"),
    ("松崎電機", "松﨑電機 / エアコンのマツ"),
    ("エアコンのマツ", "松﨑電機 / エアコンのマツ"),
)


SELF_REPAIR_VENDOR_CASES = (
    ("株式会社三建", "", "株式会社三建"),
    ("三建", "", "株式会社三建"),
    ("住宅資材センター", "", "住宅資材センター"),
    ("キューハウ", "", "株式会社キューハウ"),
    ("フュディアル", "住設業務", "㈱リファテック"),
)


UNCLEAR_SELF_REPAIR_VENDOR_CANDIDATES = (
    "ニッテイライフ",
    "トレス",
    "MED Communications",
    "Comfo home",
    "大成有楽（TOKAI/リファテック/ユナイト条件分岐あり）",
    "相鉄不動産",
    "オンレイ",
    "株式会社ミツウロコヴェッセル",
    "クリーンリバー",
    "ケィ・マックインダストリー",
    "FUTAEDA",
    "木場(こば)家電住宅設備",
    "ぽちる",
    "SKY",
    "電算システム案件",
    "三城案件（メガネ）",
    "コジマ（CHIKYUJIN）",
    "チャオ",
    "WM案件（M停止）",
)


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


@pytest.mark.parametrize(("keyword", "expected_rule_name"), NEW_WRS_HANDOVER_CASES)
def test_added_wrs_handover_targets_are_matched(keyword, expected_rule_name):
    form_values = {"operating_company": keyword}
    if expected_rule_name == "フュディアル":
        form_values["appliance_type"] = "住設"
    if expected_rule_name == "電算システム案件":
        form_values["appliance_type"] = "住設"
    result = wrs_handover(make_form(**form_values))

    assert result["needs_wrs_handover"] is True
    assert result["rule_name"] == expected_rule_name
    assert result["action_type"] == "受付報告"
    assert result["handover_request_content"] == "【BKK】WRS（福岡）へ対応依頼"


def test_fudial_wrs_handover_is_limited_to_jusetsu_cases():
    result = wrs_handover(make_form(operating_company="フュディアル", appliance_type="家電"))

    assert result["needs_wrs_handover"] is False


def test_densan_wrs_handover_is_limited_to_jusetsu_cases():
    residential = wrs_handover(make_form(store_name="電算システム", appliance_type="住設"))
    appliance = wrs_handover(make_form(store_name="電算システム", appliance_type="家電"))

    assert residential["needs_wrs_handover"] is True
    assert residential["rule_name"] == "電算システム案件"
    assert appliance["needs_wrs_handover"] is False


def test_bosch_wrs_handover_matches_manufacturer_without_changing_vendor():
    form = make_form(
        manufacturer="Bosch",
        product="食器洗い乾燥機",
        appliance_type="住設",
        prefecture="東京都",
    )
    decision = app.run_decision(form)

    assert decision["wrs_handover_action"]["needs_wrs_handover"] is True
    assert decision["wrs_handover_action"]["rule_name"] == "Bosch"
    assert decision["wrs_handover_action"]["handover_request_content"] == "【BKK】WRS（福岡）へ対応依頼"
    assert decision["vendor"] != decision["wrs_handover_action"]["handover_request_content"]


@pytest.mark.parametrize(
    "form_values",
    [
        {"operating_company": "株式会社日新"},
        {"store_name": "株式会社日新"},
        {"appliance_type": "住設"},
        {"warranty_plan": "賃貸"},
        {"warranty_plan": "中古"},
        {"appliance_type": "住設", "warranty_plan": "賃貸"},
        {"appliance_type": "住設", "warranty_plan": "中古"},
    ],
)
def test_pending_wrs_handover_targets_do_not_match_broad_conditions(form_values):
    result = wrs_handover(make_form(**form_values))

    assert result["needs_wrs_handover"] is False


def test_pending_wrs_handover_guard_keeps_clear_targets_matching():
    result = wrs_handover(make_form(operating_company="株式会社アイ工務店"))

    assert result["needs_wrs_handover"] is True
    assert result["rule_name"] == "アイ工務店"


@pytest.mark.parametrize(
    "form_values",
    [
        {"product": "メガネ"},
        {"manufacturer": "SKY"},
        {"product": "SKY"},
        {"product": "コジマ製品"},
        {"manufacturer": "チャオ"},
        {"memo": "M停止という語を含む通常メモ"},
        {"symptom_detail": "電算という語だけを含む問い合わせ"},
        {"warranty_plan": "中古住宅向け通常保証"},
    ],
)
def test_wrs_handover_broad_keywords_do_not_match_outside_identity_fields(form_values):
    result = wrs_handover(make_form(**form_values))

    assert result["needs_wrs_handover"] is False


def test_wrs_handover_megane_product_alone_does_not_match_sanjyo_rule():
    result = wrs_handover(make_form(product="メガネ", manufacturer="一般メーカー"))

    assert result["needs_wrs_handover"] is False


def test_wrs_handover_m_teishi_identity_keyword_currently_matches_wm_rule():
    result = wrs_handover(make_form(call_line="M停止"))

    assert result["needs_wrs_handover"] is True
    assert result["rule_name"] == "WM案件（M停止）"


def test_kohnan_and_beavertozan_wrs_handover_are_limited_to_jusetsu_cases():
    kohnan_jusetsu = wrs_handover(make_form(store_name="コーナン", appliance_type="住設"))
    beavertozan_jusetsu = wrs_handover(make_form(store_name="ビーバートザン", appliance_type="住設"))
    kohnan_appliance = wrs_handover(make_form(store_name="コーナン", appliance_type="家電"))
    beavertozan_appliance = wrs_handover(make_form(store_name="ビーバートザン", appliance_type="家電"))

    assert kohnan_jusetsu["needs_wrs_handover"] is True
    assert kohnan_jusetsu["rule_name"] == "コーナン住設"
    assert beavertozan_jusetsu["needs_wrs_handover"] is True
    assert beavertozan_jusetsu["rule_name"] == "コーナン住設"
    assert kohnan_appliance["needs_wrs_handover"] is False
    assert beavertozan_appliance["needs_wrs_handover"] is False


@pytest.mark.parametrize(("store_name", "call_line", "expected_vendor"), SELF_REPAIR_VENDOR_CASES)
def test_clear_self_repair_vendor_rules_take_priority_over_no7(store_name, call_line, expected_vendor):
    result = app.determine_vendor_from_rules(
        make_form(store_name=store_name, call_line=call_line),
        "出張修理",
    )

    assert result["matched"] is True
    assert result["vendor_name"] == expected_vendor
    assert result["priority"] < 900


def test_unclear_self_repair_vendor_candidates_are_left_as_test_memo():
    assert "大成有楽（TOKAI/リファテック/ユナイト条件分岐あり）" in UNCLEAR_SELF_REPAIR_VENDOR_CANDIDATES
    assert "Comfo home" in UNCLEAR_SELF_REPAIR_VENDOR_CANDIDATES
    assert "株式会社ミツウロコヴェッセル" in UNCLEAR_SELF_REPAIR_VENDOR_CANDIDATES
    assert "SKY" in UNCLEAR_SELF_REPAIR_VENDOR_CANDIDATES
    assert "電算システム案件" in UNCLEAR_SELF_REPAIR_VENDOR_CANDIDATES
    assert "WM案件（M停止）" in UNCLEAR_SELF_REPAIR_VENDOR_CANDIDATES


def test_wrs_handover_panel_renders_basis_text():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    panel_start = source.index("def render_wrs_handover_action_panel")
    panel_end = source.index("\ndef build_wrs_handover_transfer_text", panel_start)
    panel_source = source[panel_start:panel_end]

    assert "basis_text" in panel_source
    assert "WRS引き継ぎ" in panel_source
    assert "render_wrs_handover_action_panel(decision.get(\"wrs_handover_action\"))" in source


def test_call_area_renders_wrs_handover_summary():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    call_start = source.index("def render_tab_call")
    call_end = source.index("\ndef render_tab_after_call", call_start)
    call_source = source[call_start:call_end]

    assert "render_call_wrs_handover_summary(decision.get(\"wrs_handover_action\"))" in call_source
    assert call_source.index("render_call_hearing_inputs(st.session_state.form)") < call_source.index("render_call_wrs_handover_summary")
    assert call_source.index("render_call_wrs_handover_summary") < call_source.index('with st.expander("📘 スクリプト補助の詳細", expanded=False):')


def test_wrs_call_summary_lines_show_present_and_absent_states():
    present = wrs_handover(make_form(operating_company="株式会社アイ工務店"))
    present_lines = app.wrs_handover_call_summary_lines(present)
    absent_lines = app.wrs_handover_call_summary_lines(app.determine_wrs_handover_action(make_form(store_name="対象外販売店")))

    assert "WRS引き継ぎ：あり" in present_lines
    assert "依頼内容：受付報告" in present_lines
    assert any(line.startswith("根拠：WRS引き継ぎ対象 No.") for line in present_lines)
    assert absent_lines == ["WRS引き継ぎ：なし"]


def test_wrs_call_summary_keeps_ai_koumuten_vendor_unite():
    form = make_form(
        operating_company="株式会社アイ工務店",
        store_name="滋賀支店",
        prefecture="滋賀県",
        product="システムキッチン",
        appliance_type="住設",
        warranty_plan="住宅設備機器保証パッケージ 10年保証",
    )
    decision = app.run_decision(form)
    lines = app.wrs_handover_call_summary_lines(decision["wrs_handover_action"])

    assert "ユナイト" in decision["vendor"]
    assert "WRS" not in decision["vendor"]
    assert "WRS引き継ぎ：あり" in lines


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


def test_handover_panel_is_rendered_after_unified_teams_send_block():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_source = source[source.index("def render_tab_after_call"):source.index("def _candidate_field")]

    assert "render_handover_requirement_panel(decision.get(\"handover_requirement\"))" not in after_source
    assert after_source.index("teams_send_cols = st.columns([1.0, 3.0], gap=\"small\")") < after_source.index("render_wrs_handover_transfer_text")
    assert "render_warranty_report_send_panel" not in after_source


def test_wrs_transfer_text_for_ai_koumuten_includes_request_and_note():
    form = make_form(
        operating_company="株式会社アイ工務店",
        store_name="滋賀支店",
        prefecture="滋賀県",
        product="システムキッチン",
        manufacturer="パナソニック",
        appliance_type="住設",
        warranty_plan="住宅設備機器保証パッケージ 10年保証",
        rakuteru_no="2026_05_1073",
        symptom_detail="水漏れ",
    )
    decision = app.run_decision(form)
    text = app.build_wrs_handover_transfer_text(decision["working_form"], decision["wrs_handover_action"])

    assert "依頼内容：受付報告" in text
    assert "対象：アイ工務店" in text
    assert "根拠：WRS引き継ぎ対象 No." in text
    assert "アイ工務店" in text
    assert "備考：間違い電話は不要" in text
    assert "楽テルNO：2026_05_1073" in text
    assert "製品：システムキッチン" in text
    assert "メーカー：パナソニック" in text
    assert "症状：水漏れ" in text


def test_wrs_transfer_text_for_keihan_includes_alsok_note():
    form = make_form(call_line="京阪不動産", rakuteru_no="R-001")
    wrs = wrs_handover(form)
    text = app.build_wrs_handover_transfer_text(form, wrs)

    assert "依頼内容：受付報告" in text
    assert "対象：京阪" in text
    assert "ALSOK入力有無" in text
    assert "楽テルNO：R-001" in text


def test_wrs_transfer_text_is_empty_for_non_wrs_case():
    form = make_form(store_name="対象外販売店")
    wrs = wrs_handover(form)

    assert app.build_wrs_handover_transfer_text(form, wrs) == ""


def test_after_call_renders_wrs_transfer_after_detail_card():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_source = source[source.index("def render_tab_after_call"):source.index("def _candidate_field")]

    assert "render_wrs_handover_transfer_text(form, decision.get(\"wrs_handover_action\"))" in after_source
    assert after_source.index("render_wrs_handover_action_panel") < after_source.index("render_wrs_handover_transfer_text")
    assert after_source.index("render_wrs_handover_transfer_text") < after_source.index("対応履歴テンプレ")
    assert "render_warranty_report_send_panel" not in after_source


def test_wrs_transfer_text_stays_out_of_rakutel_teams_and_repair_request_memo():
    form = make_form(
        operator_name="大浦",
        operating_company="株式会社アイ工務店",
        store_name="滋賀支店",
        prefecture="滋賀県",
        product="システムキッチン",
        manufacturer="パナソニック",
        appliance_type="住設",
        warranty_plan="住宅設備機器保証パッケージ 10年保証",
        rakuteru_no="2026_05_1073",
        teams_action="FAX送信済",
    )
    decision = app.run_decision(form)
    warranty_result = {"title": "保証中", "warranty_status": "active", "can_accept": True}
    memo = app._build_after_call_memo(
        decision["working_form"],
        warranty_result,
        decision["repair_type"],
        decision["vendor"],
        "",
        decision["cost_estimate"],
    )
    rakutel = app._build_rakutel_text(decision["working_form"], "加入者", "")
    teams = app._build_teams_chat_message(decision["working_form"], decision["vendor"], decision["vendor_result"].get("contact_type", ""))

    forbidden = [
        "WRS引き継ぎ対象",
        "依頼内容：受付報告",
        "備考：間違い電話は不要",
    ]
    for generated in (memo, rakutel, teams):
        for value in forbidden:
            assert value not in generated
