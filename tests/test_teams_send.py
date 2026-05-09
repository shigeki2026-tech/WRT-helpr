# -*- coding: utf-8 -*-
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import app


ROOT = Path(__file__).resolve().parents[1]


class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


def write_config(path: Path, enabled=True, chat_id="chat-123"):
    path.write_text(
        json.dumps({
            "enabled": enabled,
            "chat_id": chat_id,
            "chat_name": "WRT報告用チャット",
            "send_mode": "powershell_graph",
        }, ensure_ascii=False),
        encoding="utf-8",
    )


def test_teams_config_example_exists():
    assert (ROOT / "config" / "teams_config.example.json").is_file()


def test_teams_config_missing_is_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "TEAMS_CONFIG_PATH", str(tmp_path / "teams_config.json"))
    monkeypatch.delenv("WRT_TEAMS_CHAT_ID", raising=False)

    config = app.load_teams_config()

    assert config["enabled"] is False
    assert config["chat_id"] == ""


def test_teams_config_reads_chat_id_from_env(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "TEAMS_CONFIG_PATH", str(tmp_path / "teams_config.json"))
    monkeypatch.setenv("WRT_TEAMS_CHAT_ID", "env-chat-id")

    config = app.load_teams_config()

    assert config["enabled"] is True
    assert config["chat_id"] == "env-chat-id"


def test_teams_send_disabled_without_chat_id(monkeypatch, tmp_path):
    config_path = tmp_path / "teams_config.json"
    write_config(config_path, enabled=True, chat_id="")
    monkeypatch.setattr(app, "TEAMS_CONFIG_PATH", str(config_path))
    monkeypatch.delenv("WRT_TEAMS_CHAT_ID", raising=False)

    assert app.is_teams_send_enabled() is False


def test_empty_message_does_not_call_subprocess(monkeypatch):
    def fail_run(*args, **kwargs):
        raise AssertionError("subprocess.run should not be called")

    monkeypatch.setattr(app.subprocess, "run", fail_run)

    result = app.send_teams_message_via_powershell("   ")

    assert result["ok"] is False
    assert "本文が空" in result["message"]


def test_teams_send_body_uses_teams_chat_message_not_rakutel_text():
    form = {
        "rakutel_text": "do not send this detailed text",
        "attention_memo": "do not send this memo either",
        "teams_chat_message": "send this short Teams message",
    }

    assert app._get_teams_send_body(form) == "send this short Teams message"
    assert "do not send this detailed text" not in app._get_teams_send_body(form)
    assert "do not send this memo either" not in app._get_teams_send_body(form)


def test_empty_teams_chat_message_is_not_sendable():
    form = {
        "rakutel_text": "detailed text exists",
        "teams_chat_message": "   ",
    }

    assert app._get_teams_send_body(form) == ""
    assert app._can_send_teams_chat_message(True, True, form) is False


def test_teams_uses_call_line_display_name_and_rakutel_uses_line_name_for_old_alias():
    form = app.empty_form()
    form.update({
        "call_line": "家電保証対応業務（24時間）",
        "product": "ドライヤー",
        "rakuteru_no": "2026_05_0162",
    })

    teams_message = app._build_teams_chat_message(form, "WRT修理センター")
    rakutel_text = app._build_rakutel_text(form, "加入者")

    assert "家電" in teams_message
    assert "【家電回線に入電】" in rakutel_text
    assert "【家電業務に入電】" not in rakutel_text


def test_attention_memo_0009_uses_vendor_send_template_with_estimated_fee():
    form = app.empty_form()
    form.update({
        "template_code": "0009",
        "template_label": "【出張修理】自然故障",
        "product": "冷蔵庫",
        "manufacturer": "アクア",
    })

    memo = app._build_after_call_memo(
        form,
        {"title": "保証期間内"},
        "出張修理",
        "WRT修理センター",
        cost_estimate="5,000円～7,000円前後",
    )

    assert memo == "\n".join([
        "具体的な症状：",
        "発生時期：",
        "発生頻度：",
        "※保証対象外時の案内済み",
        "※修理キャンセル時の概算費用5,000円～7,000円前後",
    ])


def test_attention_memo_0009_uses_confirming_when_estimated_fee_is_blank():
    form = app.empty_form()
    form.update({
        "template_code": "0009",
        "template_label": "【出張修理】自然故障",
    })

    memo = app._build_after_call_memo(
        form,
        {"title": "保証期間内"},
        "出張修理",
        "WRT修理センター",
        cost_estimate="",
    )

    assert "※修理キャンセル時の概算費用確認中" in memo


def test_teams_action_wrt_repair_center_uses_pdf_storage():
    form = app.empty_form()
    form.update({"rakuteru_no": "2026_05_0162", "call_line": "家電保証対応業務（24時間）", "product": "ドライヤー"})

    message = app._build_teams_chat_message(form, "WRT修理センター")

    assert "WRT修理センターへ依頼書PDF格納済み" in message
    assert "FAX済み" not in message
    assert "<br>" not in message
    assert "<b>" not in message
    assert message.splitlines()[0] == "2026_05_0162"


def test_teams_action_wrt_repair_reception_center_uses_pdf_storage():
    form = app.empty_form()

    assert app.resolve_teams_request_action(form, "WRT修理受付センター") == "依頼書PDF格納済み"


def test_teams_action_cer_uses_pdf_storage():
    form = app.empty_form()

    assert app.resolve_teams_request_action(form, "CER") == "依頼書PDF格納済み"
    assert app.resolve_teams_request_action(form, "CER候補（担当確認）") == "依頼書PDF格納済み"


def test_teams_action_unite_uses_fax():
    form = app.empty_form()

    assert app.resolve_teams_request_action(form, "ユナイトサービス㈱") == "FAX済み"


def test_teams_action_escalation_uses_confirmation_request():
    form = app.empty_form()

    assert app.resolve_teams_request_action(form, "担当エスカ（要確認）") == "担当確認依頼済み"


def test_teams_action_callback_uses_callback_request():
    form = app.empty_form()

    assert app.resolve_teams_request_action(form, "WRT修理センター", "callback") == "折り返し対応依頼済み"
    assert app.resolve_teams_request_action(form, "翌営業日折り返し（担当確認）") == "折り返し対応依頼済み"


def test_teams_action_manual_input_takes_priority():
    form = app.empty_form()
    form["teams_action"] = "手入力アクション済み"

    assert app.resolve_teams_request_action(form, "WRT修理センター", "callback") == "手入力アクション済み"


def test_pdf_storage_confirmation_required_for_sendable_wrt_cer():
    form = {"teams_chat_message": "send this short Teams message"}

    assert app._can_send_teams_chat_message(True, True, form, False) is False
    assert app._can_send_teams_chat_message(True, True, form, True) is True


def test_request_pdf_folder_info_returns_drive_links():
    wrt = app.get_request_pdf_folder_info("WRT修理センター")
    cer = app.get_request_pdf_folder_info("CER候補（担当確認）")

    assert wrt["required"] is True
    assert wrt["name"] == "WRT修理受付センター"
    assert wrt["url"] == "https://drive.google.com/drive/folders/14EgcYq4JfgPRH4XA6rVUULSow8uyrGI7"
    assert cer["required"] is True
    assert cer["name"] == "CER"
    assert cer["url"] == "https://drive.google.com/drive/u/0/folders/1zatFuNMucZWxwGQkketgjicfngo_9wEP"


def test_drive_url_is_not_in_teams_message_or_send_body():
    form = app.empty_form()
    form.update({
        "rakuteru_no": "2026_05_0174",
        "call_line": "家電保証対応業務（24時間）",
        "product": "エアコン",
    })

    message = app._build_teams_chat_message(form, "CER候補（担当確認）")
    form["teams_chat_message"] = message
    send_body = app._get_teams_send_body(form)

    assert "drive.google.com" not in message
    assert "drive.google.com" not in send_body
    assert "CER候補（担当確認）へ依頼書PDF格納済み" in message


def test_dp_short_note_is_preserved_with_auto_action():
    form = app.empty_form()
    form.update({"warranty_plan": "DP5"})

    message = app._build_teams_chat_message(form, "WRT修理センター")

    assert "依頼書PDF格納済み" in message
    assert "DP案件・保証金額確認要" in message


def test_teams_message_uses_expected_multiline_format():
    form = app.empty_form()
    form.update({
        "operator_name": "大濱",
        "rakuteru_no": "2026_05_0162",
        "call_line": "家電保証対応業務（24時間）",
        "product": "ドライヤー",
        "warranty_plan": "一般家電延長保証（物損付）【5年】DP5",
    })

    message = app._build_teams_chat_message(form, "WRT修理センター")

    assert message == "\n".join([
        "2026_05_0162",
        "家電",
        "ドライヤー",
        "WRT修理センターへ依頼書PDF格納済み",
        "DP案件・保証金額確認要",
        "ご確認お願いします。大濱",
    ])
    assert "MPG大濱" not in message


def test_teams_message_without_dp_omits_dp_line():
    form = app.empty_form()
    form.update({
        "rakuteru_no": "2026_05_0162",
        "call_line": "家電保証対応業務（24時間）",
        "product": "ドライヤー",
        "warranty_plan": "一般家電延長保証【5年】",
    })

    message = app._build_teams_chat_message(form, "ユナイトサービス㈱")

    assert "DP案件・保証金額確認要" not in message
    assert "ユナイトサービス㈱へFAX済み" in message


def test_life_design_kabaya_unite_teams_action_is_fax():
    form = app.empty_form()
    form.update({
        "rakuteru_no": "2026_05_0170",
        "store_name": "ライフデザイン・カバヤ株式会社 岡山中央展示場",
        "product": "食器洗い乾燥機",
    })

    message = app._build_teams_chat_message(form, "ユナイトサービス㈱")

    assert "ユナイトサービス㈱へFAX済み" in message


def test_life_design_kabaya_attention_notes_stay_out_of_teams_message():
    form = app.empty_form()
    form.update({
        "rakuteru_no": "2026_05_0171",
        "store_name": "ライフデザイン・カバヤ株式会社 岡山中央展示場",
        "product": "食器洗い乾燥機",
    })

    notes = app.build_store_attention_notes(form)
    texts = app._build_after_call_texts(
        form,
        {"title": "保証中"},
        "出張修理",
        "ユナイトサービス㈱",
        "加入者",
        "",
    )

    assert "施工側起因" in "\n".join(notes)
    assert "施工側起因" in texts["attention_memo"]
    assert "施工側起因" not in texts["teams_chat_message"]


def test_teams_message_without_rakuteru_does_not_emit_empty_bold_line():
    form = app.empty_form()
    form.update({
        "call_line": "家電保証対応業務（24時間）",
        "product": "ドライヤー",
    })

    message = app._build_teams_chat_message(form, "担当エスカ（要確認）")
    lines = message.splitlines()

    assert lines[0] == "家電"
    assert not message.startswith("<b>")
    assert "<b>" not in lines[0]


def test_rakutel_header_never_generates_blank_line_name():
    assert app.build_rakutel_call_header("", "受電") != "【回線に入電】"
    assert app.build_rakutel_call_header("", "受電") == "【未選択回線に入電】"
    assert app.build_rakutel_call_header("家電保証対応業務（24時間）", "受電") == "【家電回線に入電】"
    assert app.build_rakutel_call_header("住設業務", "受電") == "【住設回線に入電】"


def test_rakutel_text_does_not_generate_blank_line_header():
    form = app.empty_form()

    text = app._build_rakutel_text(form, "加入者", "")

    assert "【回線に入電】" not in text


def test_teams_chat_message_is_plain_text_before_send():
    form = app.empty_form()
    form.update({
        "rakuteru_no": '2026<&"0162',
        "call_line": "家電 & 住設",
        "product": "ドライヤー<白>",
        "operator_name": '大"濱',
    })

    message = app._build_teams_chat_message(form, "WRT修理センター")

    assert '2026<&"0162' in message
    assert "家電 & 住設" in message
    assert "ドライヤー<白>" in message
    assert 'ご確認お願いします。大"濱' in message
    assert "<b>" not in message
    assert "<br>" not in message


def test_teams_send_html_bolds_first_line_and_escapes_special_chars():
    form = {
        "rakuteru_no": '2026<&"0162',
        "teams_chat_message": '2026<&"0162\n家電 & 住設\nドライヤー<白>\nご確認お願いします。大"濱',
    }

    html = app._get_teams_send_body(form)

    assert html.startswith("<b>2026&lt;&amp;&quot;0162</b>")
    assert "<br>" in html
    assert "家電 &amp; 住設" in html
    assert "ドライヤー&lt;白&gt;" in html
    assert "ご確認お願いします。大&quot;濱" in html


def test_teams_send_html_keeps_display_message_plain_and_excludes_drive_url():
    form = {
        "rakuteru_no": "2026_05_0174",
        "teams_chat_message": "\n".join([
            "2026_05_0174",
            "家電回線",
            "ドライヤー",
            "WRT修理センターへ依頼書PDF格納済み",
            "ご確認お願いします。大濱",
        ]),
    }

    display_message = form["teams_chat_message"]
    html = app._get_teams_send_body(form)

    assert "<b>" not in display_message
    assert "<br>" not in display_message
    assert html == "\n".join([
        "<b>2026_05_0174</b><br>",
        "家電回線<br>",
        "ドライヤー<br>",
        "WRT修理センターへ依頼書PDF格納済み<br>",
        "ご確認お願いします。大濱",
    ])
    assert "drive.google.com" not in html


def test_teams_send_html_without_rakuteru_does_not_bold_first_line():
    form = {
        "rakuteru_no": "",
        "teams_chat_message": "家電保証対応業務（24時間）\nドライヤー",
    }

    html = app._get_teams_send_body(form)

    assert html == "家電保証対応業務（24時間）<br>\nドライヤー"
    assert "<b>" not in html


def test_teams_send_validation_requires_rakuteru_no_and_action_confirmation():
    form = {
        "rakuteru_no": "",
        "teams_chat_message": "家電回線\nドライヤー\nWRT修理センターへ依頼書PDF格納済み",
    }

    errors = app.validate_teams_send_request(
        form,
        teams_enabled=True,
        send_confirmed=True,
        action_confirmed=False,
        pdf_storage_confirmed=True,
        vendor="WRT修理センター",
    )

    assert any("楽テルNO" in error for error in errors)
    assert any("Teams報告アクション" in error for error in errors)


def test_teams_send_validation_blocks_wrt_cer_when_pdf_storage_is_unchecked():
    form = {
        "rakuteru_no": "2026_05_0174",
        "teams_chat_message": "2026_05_0174\n家電回線\nドライヤー\nWRT修理センターへ依頼書PDF格納済み",
    }

    errors = app.validate_teams_send_request(
        form,
        teams_enabled=True,
        send_confirmed=True,
        action_confirmed=True,
        pdf_storage_confirmed=False,
        vendor="WRT修理センター",
    )

    assert any("依頼書PDF" in error for error in errors)


def test_teams_send_validation_allows_wrt_cer_when_pdf_storage_is_checked():
    form = {
        "rakuteru_no": "2026_05_0174",
        "teams_chat_message": "2026_05_0174\n家電回線\nドライヤー\nWRT修理センターへ依頼書PDF格納済み",
    }

    errors = app.validate_teams_send_request(
        form,
        teams_enabled=True,
        send_confirmed=True,
        action_confirmed=True,
        pdf_storage_confirmed=True,
        vendor="WRT修理センター",
    )

    assert errors == []


def test_teams_send_validation_blocks_drive_url_in_body():
    form = {
        "rakuteru_no": "2026_05_0174",
        "teams_chat_message": "2026_05_0174\nhttps://drive.google.com/drive/folders/example",
    }

    errors = app.validate_teams_send_request(
        form,
        teams_enabled=True,
        send_confirmed=True,
        action_confirmed=True,
        pdf_storage_confirmed=True,
        vendor="WRT修理センター",
    )

    assert any("Drive URL" in error for error in errors)


def test_teams_send_panel_reasons_collect_config_rakuteru_and_pdf():
    form = {
        "rakuteru_no": "",
        "teams_chat_message": "2026_05_0174\n家電回線\nドライヤー",
    }
    config = {"enabled": False, "chat_id": ""}

    reasons = app.build_teams_send_incomplete_reasons(
        form,
        config,
        send_confirmed=True,
        action_confirmed=True,
        pdf_storage_confirmed=False,
        vendor="WRT修理センター",
    )

    assert "Teams設定が未完了" in reasons
    assert "楽テルNO未入力" in reasons
    assert "PDF格納チェック未完了" in reasons
    assert app.teams_send_status_label(reasons, already_sent=False) == "送信不可"


def test_teams_send_panel_status_sendable_and_sent():
    assert app.teams_send_status_label([], already_sent=False) == "送信可能"
    assert app.teams_send_status_label(["楽テルNO未入力"], already_sent=True) == "送信済み"


def test_escalation_teams_message_uses_confirmation_request_not_pdf_storage():
    form = app.empty_form()
    form.update({
        "rakuteru_no": "2026_05_0174",
        "call_line": "家電保証対応業務（24時間）",
        "product": "ドライヤー",
    })

    message = app._build_teams_chat_message(form, "担当エスカ（要確認）")

    assert "担当確認依頼済み" in message
    assert "依頼書PDF格納済み" not in message


def test_teams_send_validation_blocks_escalation_pdf_storage_text():
    form = {
        "rakuteru_no": "2026_05_0174",
        "teams_chat_message": "2026_05_0174\n家電回線\n担当エスカ（要確認）へ依頼書PDF格納済み",
    }

    errors = app.validate_teams_send_request(
        form,
        teams_enabled=True,
        send_confirmed=True,
        action_confirmed=True,
        pdf_storage_confirmed=True,
        vendor="担当エスカ（要確認）",
    )

    assert any("依頼書PDF格納済み" in error for error in errors)


def test_mark_teams_sent_sets_duplicate_send_state():
    state = SessionState()
    form = {"teams_chat_message": "2026_05_0174\n家電回線"}

    app._mark_teams_message_sent(state, form, datetime(2026, 5, 8, 12, 34, 56))

    assert state["teams_sent"] is True
    assert state["teams_sent_message"] == form["teams_chat_message"]
    assert state["teams_sent_at"] == "2026/05/08 12:34:56"
    assert app._teams_case_already_sent(state, form) is True


def test_local_user_settings_loads_default_operator_name(tmp_path):
    settings_path = tmp_path / "local_user_settings.json"
    settings_path.write_text('{"default_operator_name": "大濱"}', encoding="utf-8")

    settings = app.load_local_user_settings(str(settings_path))

    assert settings["default_operator_name"] == "大濱"


def test_default_operator_name_applies_to_blank_form():
    form = app.empty_form()

    app.apply_default_operator_name(form, {"default_operator_name": "大濱"})

    assert form["operator_name"] == "大濱"


def test_reset_case_preserves_default_operator_and_clears_case_state():
    state = SessionState({
        "form": {
            "operator_name": "別名",
            "call_memo": "old call memo",
            "teams_chat_message": "old teams",
            "rakutel_text": "old rakutel",
            "attention_memo": "old memo",
        },
        "pasted_text": "old pasted",
        "extracted": {"product": "ドライヤー"},
        "memo_after": "old memo",
        "rakutel_text_display": "old rakutel",
        "teams_chat_message_display": "old teams",
        "call_memo_input": "old call memo",
        "after_call_memo_display": "old call memo",
        "call_memo_common_call": "old call memo",
        "call_memo_common_after": "old call memo",
        "case_memo_common": "old call memo",
        "case_memo_global": "old call memo",
        "call_check_manual": {"occurrence_time": True},
        "manual_check_occurrence_time": True,
        "teams_send_confirmed": True,
        "request_pdf_storage_confirmed": True,
        "copy_panel_open": False,
        "copy_import_expanded": True,
        "show_copy_import": False,
    })

    form = app.reset_case_session_state(state, {"default_operator_name": "大濱"})

    assert form["operator_name"] == "大濱"
    assert state["pasted_text"] == ""
    assert state["extracted"] == {}
    assert state["form"]["teams_chat_message"] == ""
    assert state["form"]["rakutel_text"] == ""
    assert state["form"]["call_memo"] == ""
    assert state["show_copy_import"] is True
    assert state["copy_panel_open"] is True
    assert state["copy_import_expanded"] is True
    assert "teams_send_confirmed" not in state
    assert "request_pdf_storage_confirmed" not in state
    assert "call_memo_input" not in state
    assert "after_call_memo_display" not in state
    assert "call_memo_common_call" not in state
    assert "call_memo_common_after" not in state
    assert "case_memo_common" not in state
    assert state["case_memo_global"] == ""
    assert state["call_check_manual"] == {}
    assert "manual_check_occurrence_time" not in state


def test_copy_import_panel_state_helpers_close_new_and_legacy_keys():
    state = SessionState({"show_copy_import": True, "copy_import_expanded": True, "copy_panel_open": True})

    app.close_copy_import_panel(state)

    assert state["show_copy_import"] is False
    assert state["copy_import_expanded"] is False
    assert state["copy_panel_open"] is False
    assert app.copy_import_expanded(state) is False


def test_clear_case_reopens_copy_import_panel():
    state = SessionState({"show_copy_import": False, "copy_import_expanded": False, "copy_panel_open": False})

    app.reset_case_session_state(state, {"default_operator_name": ""})

    assert state["show_copy_import"] is True


def test_copy_import_expanded_falls_back_to_legacy_key():
    state = SessionState({"copy_panel_open": True})

    assert app.copy_import_expanded(state) is True


def test_copy_import_success_paths_close_only_after_form_reflection_or_clipboard_direct():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    clipboard_index = source.index('if st.button("📋 クリップボードから直接抽出"')
    manual_index = source.index('if st.button("🔍 抽出する"', clipboard_index)
    reflect_index = source.index('if st.button("📥 フォームへ反映"', manual_index)
    clipboard_area = source[clipboard_index:manual_index]
    manual_area = source[manual_index:reflect_index]
    reflect_area = source[reflect_index:source.index("form = st.session_state.form", reflect_index)]

    assert "close_copy_import_panel(st.session_state)" in clipboard_area
    assert "st.rerun()" in clipboard_area
    assert "request_case_basic_widget_refresh(st.session_state)" in clipboard_area
    assert "close_copy_import_panel(st.session_state)" not in manual_area
    assert "st.rerun()" not in manual_area
    assert "抽出しました。内容を確認してからフォームへ反映してください。" in manual_area
    assert "close_copy_import_panel(st.session_state)" in reflect_area
    assert "st.rerun()" in reflect_area
    assert "request_case_basic_widget_refresh(st.session_state)" in reflect_area


def test_copy_import_uses_self_managed_ui_not_expander():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    copy_section = source[source.index("toggle_copy_import"):source.index("form = st.session_state.form")]

    assert "show_copy_import(st.session_state)" in copy_section
    assert "st.expander" not in copy_section


def test_copy_import_failure_paths_do_not_close_panel():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    clipboard_fail_index = source.index("クリップボードが空です")
    clipboard_fail_area = source[clipboard_fail_index:source.index("else:", clipboard_fail_index)]
    manual_fail_index = source.index("テキストを貼り付けてください。")
    manual_fail_area = source[manual_fail_index:source.index("if st.session_state.extracted", manual_fail_index)]

    assert "close_copy_import_panel" not in clipboard_fail_area
    assert "close_copy_import_panel" not in manual_fail_area


def test_case_memo_global_sync_preserves_widget_state_on_rerun():
    state = SessionState({"case_memo_global": "入力中メモ"})
    form = {"call_memo": ""}

    synced = app.sync_case_memo_global(form, state)

    assert synced["call_memo"] == "入力中メモ"
    assert state["form"]["call_memo"] == "入力中メモ"


def test_case_memo_global_initializes_from_form_only_once():
    state = SessionState({})
    form = {"call_memo": "既存メモ"}

    app.sync_case_memo_global(form, state)
    state["case_memo_global"] = "編集後メモ"
    app.sync_case_memo_global(form, state)

    assert form["call_memo"] == "編集後メモ"


def test_case_memo_header_is_short_and_without_description():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    memo_start = source.index("def render_common_case_memo")
    memo_end = source.index("def render_common_call_memo", memo_start)
    memo_source = source[memo_start:memo_end]

    assert "##### 📝 案件メモ" in memo_source
    assert "案件メモ（通話中・終話後共通）" not in source
    assert "判定には使いません。通話中の一時メモ・終話後の転記メモ用です。" not in source
    assert 'label_visibility="collapsed"' in memo_source


def test_call_memo_tabs_use_same_form_field_source():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    main_index = source.index("def main():")
    tabs_index = source.index("st.tabs(", main_index)
    top_panels_index = source.index("render_global_top_panels(st.session_state.form)", main_index)
    memo_render_index = source.index("def render_global_top_panels")
    assert main_index < top_panels_index < tabs_index
    assert 'render_common_case_memo(form, "case_memo_global"' in source[memo_render_index:tabs_index]
    assert 'key="case_memo_global"' in source or '"case_memo_global"' in source
    assert 'label_visibility="collapsed"' in source
    assert "render_tab_local_call_memo_enabled() -> bool" in source
    assert 'render_common_call_memo(form, "call_memo_common_call"' not in source
    assert 'render_common_call_memo(form, "call_memo_common_after"' not in source


def test_case_clear_uses_pending_reset_before_case_memo_widget():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    controls_start = source.index("def render_case_clear_controls")
    controls_end = source.index("def _set_manual_check", controls_start)
    controls_source = source[controls_start:controls_end]
    main_index = source.index("def main():")
    pending_index = source.index("process_pending_case_clear(st.session_state)", main_index)
    top_panels_index = source.index("render_global_top_panels(st.session_state.form)", main_index)

    assert "request_case_clear(st.session_state)" in controls_source
    assert "reset_case_session_state(st.session_state)" not in controls_source
    assert 'session_state["case_memo_global"]' not in controls_source
    assert pending_index < top_panels_index


def test_pending_case_clear_clears_memo_and_preserves_default_operator():
    state = SessionState({
        "_pending_case_clear": True,
        "clear_case_pending_call": True,
        "clear_case_done_call": True,
        "form": {
            "operator_name": "",
            "call_memo": "old memo",
            "teams_chat_message": "old teams",
            "rakutel_text": "old rakutel",
        },
        "case_memo_global": "old memo",
        "show_copy_import": False,
    })

    processed = app.process_pending_case_clear(state, {"default_operator_name": "大濱"})

    assert processed is True
    assert "_pending_case_clear" not in state
    assert "clear_case_pending_call" not in state
    assert "clear_case_done_call" not in state
    assert state["form"]["operator_name"] == "大濱"
    assert state["form"]["call_memo"] == ""
    assert state["case_memo_global"] == ""
    assert state["show_copy_import"] is True


def test_manual_check_widget_keys_include_index_and_hash():
    item = {"id": "manual_manual_item", "label": "同じ確認項目"}

    key1 = app.manual_check_widget_key(item, 0)
    key2 = app.manual_check_widget_key(item, 1)

    assert key1 != key2
    assert key1.startswith("manual_check_manual_manual_item_0_")
    assert key2.startswith("manual_check_manual_manual_item_1_")


def test_pending_case_clear_clears_manual_and_now_input_widget_state():
    state = SessionState({
        "_pending_case_clear": True,
        "form": {"call_memo": "old memo", "operator_name": ""},
        "case_memo_global": "old memo",
        "call_check_manual": {"manual_manual_item": True},
        "manual_check_manual_manual_item_0_abcd1234": True,
        "now_input_manual_manual_item_0_abcd1234": "old input",
        "call_line_input_global": "old line",
        "product_input_global": "old product",
    })

    app.process_pending_case_clear(state, {"default_operator_name": ""})

    assert state["call_check_manual"] == {}
    assert not any(str(key).startswith("manual_check_") for key in state)
    assert not any(str(key).startswith("now_input_") for key in state)
    assert not any(str(key).startswith("call_line_input_") for key in state)
    assert not any(str(key).startswith("product_input_") for key in state)


def test_global_top_panels_render_case_memo_and_decision_tags_before_tabs():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    panels_start = source.index("def render_global_top_panels")
    panels_end = source.index("def render_common_call_memo", panels_start)
    panels_source = source[panels_start:panels_end]
    main_index = source.index("def main():")
    top_index = source.index("render_global_top_panels(st.session_state.form)", main_index)
    tabs_index = source.index("st.tabs(", main_index)

    assert "render_common_case_memo" in panels_source
    assert "render_decision_tags_panel" in panels_source
    assert top_index < tabs_index


def test_global_case_basic_widget_state_syncs_to_shared_form_before_render():
    form = app.empty_form()
    revision = 0
    state = SessionState({
        "case_basic_revision": revision,
        app.case_basic_widget_key("call_line", revision): "家電保証対応業務（24時間）",
        app.case_basic_widget_key("appliance_type", revision): "家電",
        app.case_basic_widget_key("product", revision): "食器洗い乾燥機",
        app.case_basic_widget_key("manufacturer", revision): "三菱電機",
        app.case_basic_widget_key("store_name", revision): "ライフデザイン・カバヤ",
    })

    synced = app.sync_global_case_basic_widget_state(form, state)

    assert synced["call_line"] == "家電保証対応業務（24時間）"
    assert synced["product"] == "食器洗い乾燥機"
    assert state["form"]["manufacturer"] == "三菱電機"


def test_case_basic_revision_initializes_and_bumps_on_refresh_and_clear():
    state = SessionState()

    assert app.get_case_basic_revision(state) == 0

    app.request_case_basic_widget_refresh(state)
    assert state["case_basic_revision"] == 1
    assert state["_pending_case_basic_widget_refresh"] is True

    app.reset_case_session_state(state, {"default_operator_name": ""})
    assert state["case_basic_revision"] == 2


def test_case_basic_widget_keys_include_revision():
    assert app.case_basic_widget_key("call_line", 7) == "case_basic_call_line_7"
    assert app.case_basic_widget_key("appliance_type", 7) == "case_basic_appliance_type_7"
    assert app.case_basic_widget_key("product", 7) == "case_basic_product_7"
    assert app.case_basic_widget_key("manufacturer", 7) == "case_basic_manufacturer_7"
    assert app.case_basic_widget_key("store_name", 7) == "case_basic_store_name_7"


def test_case_basic_refresh_success_paths_bump_revision():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    refresh_index = source.index("def request_case_basic_widget_refresh")
    refresh_source = source[refresh_index:source.index("def process_pending_case_basic_widget_refresh", refresh_index)]
    clipboard_index = source.index('if st.button("📋 クリップボードから直接抽出"')
    manual_index = source.index('if st.button("🔍 抽出する"', clipboard_index)
    reflect_index = source.index('if st.button("📥 フォームへ反映"', manual_index)
    clipboard_area = source[clipboard_index:manual_index]
    reflect_area = source[reflect_index:reflect_index + 500]

    assert "bump_case_basic_revision(session_state)" in refresh_source
    assert "request_case_basic_widget_refresh(st.session_state)" in clipboard_area
    assert "request_case_basic_widget_refresh(st.session_state)" in reflect_area


def test_case_basic_widget_initial_values_use_current_form_values():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    panel_index = source.index("def render_shared_case_basic_editor")
    panel_end = source.index("def render_global_case_basic_panel", panel_index)
    panel_source = source[panel_index:panel_end]

    assert 'value=form.get("product", "")' in panel_source
    assert 'current_manufacturer = form.get("manufacturer", "")' in panel_source
    assert 'value=form.get("store_name", "")' in panel_source


def test_global_case_basic_stale_blank_widget_does_not_overwrite_form():
    form = app.empty_form()
    form.update({
        "product": "食器洗い乾燥機",
        "manufacturer": "三菱電機",
        "store_name": "ライフデザイン・カバヤ株式会社",
    })
    revision = 0
    state = SessionState({
        "case_basic_revision": revision,
        app.case_basic_widget_key("product", revision): "",
        app.case_basic_widget_key("manufacturer", revision): "",
        app.case_basic_widget_key("store_name", revision): "",
    })

    synced = app.sync_global_case_basic_widget_state(form, state)

    assert synced["product"] == "食器洗い乾燥機"
    assert synced["manufacturer"] == "三菱電機"
    assert synced["store_name"] == "ライフデザイン・カバヤ株式会社"
    assert state[app.case_basic_widget_key("product", revision)] == "食器洗い乾燥機"
    assert state[app.case_basic_widget_key("manufacturer", revision)] == "三菱電機"
    assert state[app.case_basic_widget_key("store_name", revision)] == "ライフデザイン・カバヤ株式会社"


def test_global_case_basic_manual_widget_edit_updates_form():
    form = app.empty_form()
    form["product"] = "洗濯機"
    revision = 0
    product_key = app.case_basic_widget_key("product", revision)
    state = SessionState({
        "case_basic_revision": revision,
        product_key: "食器洗い乾燥機",
        "_case_basic_widget_synced_values": {
            product_key: "洗濯機",
        },
    })

    synced = app.sync_global_case_basic_widget_state(form, state)

    assert synced["product"] == "食器洗い乾燥機"


def test_pending_case_basic_widget_refresh_clears_stale_widget_keys():
    state = SessionState({
        "_pending_case_basic_widget_refresh": True,
        "case_basic_revision": 1,
        "case_basic_call_line_0": "old line",
        "case_basic_product_0": "old product",
        "case_basic_manufacturer_0": "old manufacturer",
        "case_basic_store_name_0": "old store",
        "unrelated": "keep",
    })

    processed = app.process_pending_case_basic_widget_refresh(state)

    assert processed is True
    assert "case_basic_call_line_0" not in state
    assert "case_basic_product_0" not in state
    assert "case_basic_manufacturer_0" not in state
    assert "case_basic_store_name_0" not in state
    assert state["unrelated"] == "keep"


def test_regenerated_teams_message_reflects_late_operator_name():
    form = app.empty_form()
    form.update({
        "operator_name": "大濱",
        "rakuteru_no": "2026_05_0143",
        "call_line": "カバヤ案件",
        "product": "多機能便座",
    })

    texts = app._build_after_call_texts(
        form,
        {"title": "保証中"},
        "出張修理",
        "ユナイト",
        "加入者",
        "",
    )

    assert "大濱" in texts["teams_chat_message"]
    assert "2026_05_0143" in texts["teams_chat_message"]


def test_regenerated_teams_message_reflects_rakuteru_and_manual_action():
    form = app.empty_form()
    form.update({
        "operator_name": "大濱",
        "rakuteru_no": "2026_05_0470",
        "call_line": "家電保証対応業務（24時間）",
        "product": "食器洗い乾燥機",
        "teams_action": "FAX済み",
    })

    message = app._build_teams_chat_message(form, "ユナイトサービス㈱")

    assert message.splitlines()[0] == "2026_05_0470"
    assert "FAX済み" in message
    assert "<b>" not in message
    assert "<br>" not in message


def test_regenerated_rakutel_text_reflects_late_operator_name():
    form = app.empty_form()
    form.update({
        "operator_name": "大濱",
        "extracted_time": "2026/5/4 09:30",
        "call_line": "家電保証対応業務（24時間）",
        "contact_phone": "090-1111-2222",
        "product": "多機能便座",
    })

    texts = app._build_after_call_texts(
        form,
        {"title": "保証中"},
        "出張修理",
        "ユナイト",
        "販売店",
        "",
    )

    assert "MPG大濱" in texts["rakutel_text"]
    assert "【家電回線に入電】" in texts["rakutel_text"]
    assert "【家電業務に入電】" not in texts["rakutel_text"]
    assert "【修理受付】" in texts["rakutel_text"]
    assert "2026/5/4 09:30　販売店" in texts["rakutel_text"]


def test_rakutel_text_inbound_subscriber_arrow():
    form = app.empty_form()
    form.update({
        "operator_name": "大濱",
        "call_line": "家電保証対応業務（24時間）",
        "extracted_time": "2026/05/05　13：05",
        "call_direction": "受電",
        "counterparty_type": "加入者",
    })

    text = app._build_rakutel_text(form, "加入者", "")

    assert "【家電回線に入電】" in text
    assert "加入者→MPG大濱" in text


def test_rakutel_text_outbound_subscriber_arrow():
    form = app.empty_form()
    form.update({
        "operator_name": "大濱",
        "call_line": "家電保証対応業務（24時間）",
        "extracted_time": "2026/05/05　13：05",
        "call_direction": "架電",
        "counterparty_type": "加入者",
    })

    text = app._build_rakutel_text(form, "加入者", "")

    assert "【家電回線に架電】" in text
    assert "MPG大濱→加入者" in text


def test_call_direction_ui_is_near_rakutel_section():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    rakutel_heading_index = source.index('##### 📝 ラクテル用テキスト")')
    direction_index = source.index('"通話方向"', rakutel_heading_index)
    counterparty_index = source.index('"相手区分"', rakutel_heading_index)
    old_label = 'st.selectbox(\n            "発信者区分"'

    assert rakutel_heading_index < direction_index < counterparty_index
    assert old_label not in source


def test_escalation_info_includes_reason_and_next_action():
    info = app.build_vendor_escalation_info(
        "CER候補（担当確認）",
        {"reason": "九州エリア", "needs_escalation": True},
    )

    assert "九州エリア" in info["reason"]
    assert "CER" in info["next_action"]


def test_generic_vendor_escalation_uses_meaningful_fallback_reason():
    info = app.build_vendor_escalation_info(
        "担当エスカ（要確認）",
        {"reason": "", "needs_escalation": True},
    )

    assert info["title"] == "⚠️ 拠点未確定：担当確認が必要"
    assert info["reason"] == "現在の条件では修理拠点を自動確定できません"
    assert "担当エスカについて担当確認が必要" not in info["reason"]
    assert info["next_action"] == "終話後に担当へ確認し、拠点を確定"


def test_generic_vendor_escalation_does_not_repeat_vendor_as_reason():
    info = app.build_vendor_escalation_info(
        "担当エスカ（要確認）",
        {"reason": "担当エスカ（要確認）", "needs_escalation": True},
    )

    assert info["reason"] == "現在の条件では修理拠点を自動確定できません"


def test_cer_escalation_uses_cer_reason_and_action():
    info = app.build_vendor_escalation_info(
        "CER候補（担当確認）",
        {"reason": "九州エリア", "needs_escalation": True},
    )

    assert info["title"] == "⚠️ 拠点候補：CER候補"
    assert info["reason"] == "九州エリアのためCER候補。手配可否は担当確認が必要"
    assert info["next_action"] == "終話後に担当へCER手配可否を確認"


def test_cer_drive_link_info_is_available_on_vendor_card():
    card = app.build_vendor_candidate_card_info(
        "CER候補（担当確認）",
        {"reason": "九州エリア", "needs_escalation": True},
    )

    assert card["request_folder"]["required"] is True
    assert card["request_folder"]["name"] == "CER"
    assert "drive.google.com" in card["request_folder"]["url"]
    assert card["arrangement_method"] == "依頼書PDF格納"


def test_cer_escalation_block_source_groups_drive_link_with_action():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    block_index = source.index("drive_line =")
    block_end = source.index("拠点確定：{vendor}", block_index)
    block_source = source[block_index:block_end]

    assert 'esc["title"]' in block_source
    assert "理由：" in block_source
    assert "次アクション：" in block_source
    assert 'esc["next_action"]' in block_source
    assert "依頼書PDF格納先：" in block_source
    assert "Google Drive を開く" in block_source


def test_teams_chat_message_never_includes_drive_url_for_cer():
    form = app.empty_form()
    form.update({
        "rakuteru_no": "2026_05_0300",
        "call_line": "家電保証対応業務（24時間）",
        "product": "エアコン",
    })
    message = app._build_teams_chat_message(form, "CER候補（担当確認）")

    assert "drive.google.com" not in message
    assert "folders/" not in message


def test_teams_area_source_does_not_render_drive_link():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    teams_index = source.index("##### 💬 Teams 報告文")
    send_button_index = source.index('st.button("Teamsチャットへ送信"', teams_index)
    teams_area = source[teams_index:send_button_index]

    assert "Google Drive を開く" not in teams_area
    assert "依頼書PDF格納先" not in teams_area


def test_teams_auto_send_panel_heading_exists():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert "##### 🚀 Teams自動送信" in source


def test_teams_report_and_send_have_separate_headings():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    report_index = source.index("##### 💬 Teams 報告文")
    send_index = source.index("##### 🚀 Teams自動送信")

    assert report_index < send_index


def test_teams_auto_send_heading_is_not_duplicated():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]

    assert after_source.count("Teams自動送信") == 2  # heading + validation warning text
    assert "##### 💬 Teams自動送信" not in after_source
    assert "##### 🚀 Teams送信" not in after_source


def test_teams_send_unavailable_reasons_are_rendered_in_one_place():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]

    assert after_source.count('st.markdown("**未完了：**")') == 1
    assert "build_teams_send_incomplete_reasons" in after_source
    assert "楽テルNOが未入力です。" not in after_source
    assert "設定未完了のため送信できません" not in after_source


def test_teams_send_disabled_message_is_specific():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert "**Teams送信：{'有効' if teams_enabled else '無効'}**" in source
    assert "config/teams_config.json が未作成、または enabled=false" in source
    assert "chat_id が未設定" in source
    assert "送信スクリプトが利用できない" in source


def test_teams_action_input_label_is_teams_report_content():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert '"Teams報告文に入れる対応内容"' in source
    assert "自動判定と異なる場合のみ変更" in source
    assert '"Teams報告アクション（手入力優先）"' not in source


def test_teams_send_panel_status_labels_exist():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert "送信不可" in source
    assert "送信可能" in source
    assert "送信済み" in source


def test_dp_rakutel_text_includes_guarantee_amount_confirmation():
    form = app.empty_form()
    form.update({
        "operator_name": "大濱",
        "extracted_time": "2026/05/05　13：05",
        "warranty_plan": "一般家電延長保証（物損付）【5年】DP5",
        "contact_phone": "043-309-6828",
        "product": "エアコン",
        "manufacturer": "シャープ",
        "model_number": "AY-R22DM",
    })

    text = app._build_rakutel_text(form, "加入者", "")

    assert "物損付 / DP案件" in text
    assert "物損時の保証金額はシステムにて確認要" in text
    assert "日程調整時の連絡先：043-309-6828" in text


def test_call_memo_is_not_auto_mixed_into_rakutel_or_teams_texts():
    form = app.empty_form()
    form.update({
        "operator_name": "大濱",
        "call_memo": "これは通話中メモだけに残す内容",
        "rakuteru_no": "2026_05_0200",
        "call_line": "家電保証対応業務（24時間）",
        "product": "ドライヤー",
    })

    texts = app._build_after_call_texts(
        form,
        {"title": "保証中"},
        "持込修理",
        "WRT修理センター",
        "加入者",
        "",
    )

    assert "これは通話中メモだけに残す内容" not in texts["rakutel_text"]
    assert "これは通話中メモだけに残す内容" not in texts["teams_chat_message"]


def test_send_teams_message_success(monkeypatch, tmp_path):
    config_path = tmp_path / "teams_config.json"
    script_path = tmp_path / "send_teams_message.ps1"
    write_config(config_path)
    script_path.write_text("# test script", encoding="utf-8")
    monkeypatch.setattr(app, "TEAMS_CONFIG_PATH", str(config_path))
    monkeypatch.setattr(app, "TEAMS_SEND_SCRIPT_PATH", str(script_path))

    def fake_run(args, capture_output, text, timeout):
        message_file = Path(args[-1])
        assert message_file.read_text(encoding="utf-8") == "hello teams"
        return SimpleNamespace(returncode=0, stdout="SUCCESS message-001\n", stderr="")

    monkeypatch.setattr(app.subprocess, "run", fake_run)

    result = app.send_teams_message_via_powershell("hello teams")

    assert result["ok"] is True
    assert result["message"] == "送信成功"


def test_send_teams_message_failure(monkeypatch, tmp_path):
    config_path = tmp_path / "teams_config.json"
    script_path = tmp_path / "send_teams_message.ps1"
    write_config(config_path)
    script_path.write_text("# test script", encoding="utf-8")
    monkeypatch.setattr(app, "TEAMS_CONFIG_PATH", str(config_path))
    monkeypatch.setattr(app, "TEAMS_SEND_SCRIPT_PATH", str(script_path))

    def fake_run(args, capture_output, text, timeout):
        return SimpleNamespace(returncode=1, stdout="ERROR denied\n", stderr="denied")

    monkeypatch.setattr(app.subprocess, "run", fake_run)

    result = app.send_teams_message_via_powershell("hello teams")

    assert result["ok"] is False
    assert "送信失敗" in result["message"]
    assert result["stderr"] == "denied"


def test_teams_send_log_includes_preview(monkeypatch):
    original_session_state = app.st.session_state
    try:
        app.st.session_state = SessionState()
        logs = app.append_teams_send_log(
            {"ok": False, "message": "送信失敗: denied"},
            "0123456789" * 12,
            "WRT報告用チャット",
        )
    finally:
        app.st.session_state = original_session_state

    assert logs[0]["ok"] is False
    assert logs[0]["chat_name"] == "WRT報告用チャット"
    assert logs[0]["message_preview"] == "0123456789" * 10
    assert logs[0]["error_message"] == "送信失敗: denied"


def test_no_standalone_script_reference_block():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert "##### 📘 参照スクリプト" not in source


def test_clear_button_not_full_width():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert 'render_case_clear_controls("call", use_container_width=True)' not in source


def test_rakutel_settings_ui_inside_rakutel_section():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    rakutel_heading_index = source.index('##### 📝 ラクテル用テキスト")')
    direction_index = source.index('"通話方向"', rakutel_heading_index)
    counterparty_index = source.index('"相手区分"', rakutel_heading_index)
    teams_heading_index = source.index("##### 💬 Teams 報告文", rakutel_heading_index)

    assert rakutel_heading_index < direction_index < counterparty_index < teams_heading_index


def test_rakutel_settings_no_separate_heading():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert 'st.markdown("##### 📝 ラクテル用テキスト設定")' not in source


def test_rakutel_text_generation_uses_stored_counterparty_type():
    form = app.empty_form()
    form.update({
        "operator_name": "大濱",
        "call_line": "家電保証対応業務（24時間）",
        "extracted_time": "2026/05/05　13：05",
        "counterparty_type": "販売店",
        "call_direction": "受電",
    })

    text = app._build_rakutel_text(form, "販売店", "")

    assert "販売店" in text
    assert "MPG大濱" in text


def test_global_case_basic_common_section_exists_before_tabs():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    main_index = source.index("def main():")
    top_index = source.index("render_global_top_panels(st.session_state.form)", main_index)
    basic_index = source.index("render_global_case_basic_panel(st.session_state.form)", main_index)
    tabs_index = source.index("st.tabs(", main_index)
    after_index = source.index("def render_tab_after_call")
    after_source = source[after_index:source.index("def render_tab_master", after_index)]

    assert top_index < basic_index < tabs_index
    assert "##### 🧾 案件基本（共通）" in source
    assert "render_global_case_basic_panel" in source
    assert "案件基本（共通）" not in after_source


def test_global_case_basic_widget_keys_are_single_global_set():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    panel_index = source.index("def render_shared_case_basic_editor")
    panel_end = source.index("def render_global_case_basic_panel", panel_index)
    panel_source = source[panel_index:panel_end]

    for key in [
        'case_basic_widget_key("call_line", revision)',
        'case_basic_widget_key("appliance_type", revision)',
        'case_basic_widget_key("product", revision)',
        'case_basic_widget_key("manufacturer", revision)',
        'case_basic_widget_key("store_name", revision)',
    ]:
        assert key in panel_source
    assert 'render_shared_case_basic_editor(form, "global"' in source
    assert "call_line_input_after" not in source
    assert "product_input_after" not in source
    assert "manufacturer_input_after" not in source


def test_global_case_basic_panel_updates_shared_form_fields():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    panel_index = source.index("def render_shared_case_basic_editor")
    panel_end = source.index("def render_global_case_basic_panel", panel_index)
    panel_source = source[panel_index:panel_end]

    for field in ["call_line", "appliance_type", "product", "manufacturer", "store_name"]:
        assert f'form["{field}"]' in panel_source
    assert "st.session_state.form = form" in panel_source


def test_call_tab_does_not_render_duplicate_case_basic_fields():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    call_index = source.index("def render_tab_call")
    call_end = source.index("def render_tab_after_call", call_index)
    call_source = source[call_index:call_end]

    assert "受付補足情報" in call_source
    assert 'st.selectbox("回線名"' not in call_source
    assert 'st.selectbox("家電/住設"' not in call_source
    assert 'st.selectbox(\n            "製品"' not in call_source
    assert 'st.selectbox(\n            "メーカー"' not in call_source


def test_case_basic_template_display_for_life_design_kabaya():
    form = app.empty_form()
    form.update({
        "store_name": "ライフデザイン・カバヤ株式会社 岡山中央展示場",
        "call_line": "家電保証対応業務（24時間）",
        "appliance_type": "住設",
        "product": "食器洗い乾燥機",
        "manufacturer": "三菱電機",
    })

    display = app.build_case_basic_template_display(form, "出張修理")

    assert "ライフデザイン・カバヤ" in display
    assert "上位5社テンプレート対象" in display


def test_after_call_template_caption_replaced():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert "回線名を選択するとテンプレートが表示されます" not in source
    assert "販売店テンプレート判定：" not in source
    assert "基本項目を変更すると、テンプレート判定・ラクテル文・Teams報告文に反映されます。" in source


def test_case_basic_template_result_rendered_only_in_basic_panel():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert source.count("テンプレート判定結果") == 1
    main_index = source.index("def main():")
    basic_call_index = source.index("render_global_case_basic_panel(st.session_state.form)", main_index)
    tabs_index = source.index("st.tabs(", main_index)
    basic_panel_index = source.index("def render_shared_case_basic_editor")
    result_index = source.index("テンプレート判定結果")

    assert basic_panel_index < result_index
    assert basic_call_index < tabs_index


def test_after_call_regeneration_uses_current_global_form_after_basic_panel():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    main_index = source.index("def main():")
    basic_index = source.index("render_global_case_basic_panel(st.session_state.form)", main_index)
    tabs_index = source.index("st.tabs(", main_index)
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]

    assert basic_index < tabs_index
    assert "form = st.session_state.form" in after_source
    assert "注意内容メモを再生成" in after_source
    assert "ラクテル用テキストを再生成" in after_source
    assert "Teams報告文を再生成" in after_source


def test_after_call_regeneration_buttons_are_independent():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]

    assert "ラクテル用・Teams用テキストを再生成" not in after_source
    attention_button = after_source.index("注意内容メモを再生成")
    rakutel_button = after_source.index("ラクテル用テキストを再生成")
    teams_button = after_source.index("Teams報告文を再生成")
    rakutel_area = after_source[rakutel_button:teams_button]
    teams_area = after_source[teams_button:]

    assert attention_button < rakutel_button < teams_button
    assert 'form["teams_chat_message"] = generated_teams_message' not in rakutel_area
    assert 'form["rakutel_text"] = generated_rakutel_text' not in teams_area


def test_render_copy_button_helper_exists():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    helper_index = source.index("def render_copy_button")
    helper_source = source[helper_index:source.index("def sort_diagnostic_items", helper_index)]

    assert "st.components.v1.html" in helper_source
    assert "json.dumps(text or \"\", ensure_ascii=False)" in helper_source
    assert "navigator.clipboard.writeText(copyText)" in helper_source
    assert 'document.createElement("textarea")' in helper_source
    assert "document.execCommand(\"copy\")" in helper_source
    assert "コピーしました" in helper_source
    assert "コピー対象がありません" in helper_source


def test_after_call_copy_buttons_exist_under_each_text_area():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]

    memo_area = after_source[
        after_source.index('memo_display = st.text_area('):
        after_source.index("##### 📝 ラクテル用テキスト")
    ]
    rakutel_area = after_source[
        after_source.index('rakutel_text_display = st.text_area('):
        after_source.index("##### 💬 Teams 報告文")
    ]
    teams_area = after_source[
        after_source.index('teams_chat_message = st.text_area('):
        after_source.index("teams_config = load_teams_config()")
    ]

    assert "st.code(" not in memo_area
    assert "コピー用：注意内容メモ" not in memo_area
    assert 'render_copy_button("📋 注意内容メモをコピー", form["attention_memo"], "copy_attention_memo")' in memo_area
    assert memo_area.index('form["attention_memo"] = memo_display') < memo_area.index("copy_attention_memo")

    assert "st.code(" not in rakutel_area
    assert "コピー用：ラクテル用テキスト" not in rakutel_area
    assert 'render_copy_button("📋 ラクテル用テキストをコピー", form["rakutel_text"], "copy_rakutel_text")' in rakutel_area
    assert rakutel_area.index('form["rakutel_text"] = rakutel_text_display') < rakutel_area.index("copy_rakutel_text")

    assert "st.code(" not in teams_area
    assert "コピー用：Teams報告文" not in teams_area
    assert 'render_copy_button("📋 Teams報告文をコピー", teams_chat_message, "copy_teams_chat_message")' in teams_area
    assert teams_area.index('form["teams_chat_message"] = teams_chat_message') < teams_area.index("copy_teams_chat_message")


def test_teams_copy_button_uses_plain_text_without_drive_url_source():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    teams_index = source.index("##### 💬 Teams 報告文")
    teams_copy_index = source.index("render_copy_button", teams_index)
    copy_end_index = source.index("st.session_state.form = form", teams_copy_index)
    teams_copy_area = source[teams_copy_index:copy_end_index]

    assert 'render_copy_button("📋 Teams報告文をコピー", teams_chat_message, "copy_teams_chat_message")' in teams_copy_area
    assert "_get_teams_send_body" not in teams_copy_area
    assert "teams_plain_text_to_html" not in teams_copy_area
    assert "<b>" not in teams_copy_area
    assert "<br>" not in teams_copy_area
    assert "request_folder" not in teams_copy_area
    assert "drive.google.com" not in teams_copy_area


def test_after_call_copy_buttons_reference_regenerated_session_values():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]

    attention_regen = after_source.index('st.session_state["memo_after"] = form["attention_memo"]')
    attention_copy = after_source.index("copy_attention_memo")
    rakutel_regen = after_source.index('st.session_state["rakutel_text_display"] = form["rakutel_text"]')
    rakutel_copy = after_source.index("copy_rakutel_text")
    teams_regen = after_source.index('st.session_state["teams_chat_message_display"] = form["teams_chat_message"]')
    teams_copy = after_source.index("copy_teams_chat_message")

    assert attention_regen < attention_copy
    assert rakutel_regen < rakutel_copy
    assert teams_regen < teams_copy


def test_push_bat_does_not_use_git_add_dot_and_pushes_origin_main():
    source = (ROOT / "Push.bat").read_text(encoding="utf-8")
    lines = [line.strip() for line in source.splitlines()]

    assert "git add ." not in lines
    assert "git status --short" in source
    assert "git diff --cached --quiet" in source
    assert "No staged changes." in source
    assert "git push origin main" in source


def test_gitignore_excludes_codex_temp_folders():
    source = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert ".codex_pytest_tmp/" in source
    assert ".codex_run_tmp/" in source
    assert ".codex_unit_tmp/" in source
    assert "__pycache__/" in source
    assert ".pytest_cache/" in source


def test_after_call_regeneration_dirty_state_helpers():
    form = app.empty_form()
    form.update({"call_line": "A", "product": "洗濯機", "rakuteru_no": "RT-1"})
    state = SessionState()
    first_hash = app.get_after_call_regeneration_hash(form, "teams_chat_message", vendor="V")

    app.mark_after_call_section_regenerated(state, "teams_chat_message", first_hash)
    assert app.after_call_section_needs_regeneration(state, "teams_chat_message", first_hash) is False

    form["rakuteru_no"] = "RT-2"
    second_hash = app.get_after_call_regeneration_hash(form, "teams_chat_message", vendor="V")
    assert app.after_call_section_needs_regeneration(state, "teams_chat_message", second_hash) is True


def test_tab_css_uses_blue_selected_state_not_red():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    css = source[source.index("div[data-baseweb=\"tab-list\"]"):source.index("</style>", source.index("div[data-baseweb=\"tab-list\"]"))]

    assert "#2563EB" in css
    assert "#EFF6FF" in css
    assert "#667085" in css
    assert "#d6336c" not in css
    assert "#fff5f7" not in css
    for red_token in ("#ff", "#f43", "#ef4444", "#d6336c"):
        assert red_token.lower() not in css.lower()
    assert 'div[data-baseweb="tab-highlight"]' in css
    assert "background-color: #2563EB !important;" in css


def test_master_csv_cache_clear_is_secondary_not_danger():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    master_index = source.index("def render_tab_master")
    master_source = source[master_index:]
    cache_index = master_source.index("CSVキャッシュをクリア")
    cache_area = master_source[cache_index:cache_index + 220]

    assert 'type="secondary"' in cache_area
    assert 'type="primary"' not in cache_area


# ── ナビゲーション構造テスト ──

def test_nav_uses_tabs_not_radio():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    main_index = source.index("def main():")
    main_source = source[main_index:]
    assert "st.tabs(" in main_source
    assert 'key="main_nav_tab"' not in main_source


def test_nav_tabs_has_three_labels():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    main_index = source.index("def main():")
    main_source = source[main_index:]
    assert '"通話中判定"' in main_source
    assert '"終話後処理"' in main_source
    assert '"マスタ管理"' in main_source


def test_nav_tabs_do_not_use_red_tinted_emoji_labels():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    main_index = source.index("def main():")
    main_source = source[main_index:]
    tabs_index = main_source.index("st.tabs(")
    tabs_source = main_source[tabs_index:main_source.index("])", tabs_index)]

    for emoji in ("📞", "📋", "⚙️"):
        assert emoji not in tabs_source


def test_nav_no_pill_radio_css():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert "border-radius: 20px" not in source
    assert 'key="main_nav_tab"' not in source


# ── 楽テルNO 移動テスト (Session 4) ──

def test_rakuteru_no_input_before_teams_regeneration_button():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    teams_heading_index = source.index("##### 💬 Teams 報告文")
    # Search for the widget by its unique key, which only exists at the widget definition
    rakuteru_no_index = source.index('key="rakuteru_no_input"', teams_heading_index)
    regenerate_index = source.index('key="regenerate_teams_chat_message"', teams_heading_index)

    assert teams_heading_index < rakuteru_no_index < regenerate_index


def test_teams_action_input_before_teams_regeneration_button():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    teams_heading_index = source.index("##### 💬 Teams 報告文")
    teams_action_index = source.index('key="teams_action_input"', teams_heading_index)
    regenerate_index = source.index('key="regenerate_teams_chat_message"', teams_heading_index)

    assert teams_heading_index < teams_action_index < regenerate_index


def test_rakuteru_no_not_in_template_col1():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    vendor_section_index = source.index("##### 🏭 修理拠点候補")
    teams_heading_index = source.index("##### 💬 Teams 報告文")
    # vendor section (col1) must come before Teams heading (col2)
    assert vendor_section_index < teams_heading_index
    # The widget must only appear after the Teams heading
    rakuteru_widget_index = source.index('key="rakuteru_no_input"')
    assert rakuteru_widget_index > teams_heading_index


# ── タブ CSS テスト ──

def test_tab_css_uses_baseweb_not_pill():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    # data-baseweb セレクタが使われている
    assert 'data-baseweb="tab' in source
    # pill/radio 風の丸いボタンスタイルではない
    assert "border-radius: 20px" not in source
    assert 'key="main_nav_tab"' not in source


def test_tab_css_selected_tab_is_emphasized():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    # 選択中タブに font-weight:700 相当の強調がある
    assert "font-weight: 700" in source
    # 選択中タブに border-bottom が設定されている
    assert "border-bottom: 3px solid" in source
