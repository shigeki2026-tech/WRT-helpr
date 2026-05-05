# -*- coding: utf-8 -*-
import json
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
        "teams_chat_message": "send this short Teams message",
    }

    assert app._get_teams_send_body(form) == "send this short Teams message"


def test_empty_teams_chat_message_is_not_sendable():
    form = {
        "rakutel_text": "detailed text exists",
        "teams_chat_message": "   ",
    }

    assert app._get_teams_send_body(form) == ""
    assert app._can_send_teams_chat_message(True, True, form) is False


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
        "家電保証対応業務（24時間）",
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


def test_teams_message_without_rakuteru_does_not_emit_empty_bold_line():
    form = app.empty_form()
    form.update({
        "call_line": "家電保証対応業務（24時間）",
        "product": "ドライヤー",
    })

    message = app._build_teams_chat_message(form, "担当エスカ（要確認）")
    lines = message.splitlines()

    assert lines[0] == "家電保証対応業務（24時間）"
    assert not message.startswith("<b>")
    assert "<b>" not in lines[0]


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


def test_teams_send_html_without_rakuteru_does_not_bold_first_line():
    form = {
        "rakuteru_no": "",
        "teams_chat_message": "家電保証対応業務（24時間）\nドライヤー",
    }

    html = app._get_teams_send_body(form)

    assert html == "家電保証対応業務（24時間）<br>\nドライヤー"
    assert "<b>" not in html


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
        "teams_send_confirmed": True,
        "request_pdf_storage_confirmed": True,
        "copy_panel_open": False,
    })

    form = app.reset_case_session_state(state, {"default_operator_name": "大濱"})

    assert form["operator_name"] == "大濱"
    assert state["pasted_text"] == ""
    assert state["extracted"] == {}
    assert state["form"]["teams_chat_message"] == ""
    assert state["form"]["rakutel_text"] == ""
    assert state["form"]["call_memo"] == ""
    assert state["copy_panel_open"] is True
    assert "teams_send_confirmed" not in state
    assert "request_pdf_storage_confirmed" not in state
    assert "call_memo_input" not in state
    assert "after_call_memo_display" not in state


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
    assert "<b>" not in texts["teams_chat_message"]
    assert "ユナイトへFAX済み" in texts["teams_chat_message"]
    assert "ご確認お願いします。大濱" in texts["teams_chat_message"]
    assert "MPG大濱" not in texts["teams_chat_message"]


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

    assert "【家電回線から架電】" in text
    assert "MPG大濱→加入者" in text


def test_call_direction_ui_is_near_rakutel_section():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    settings_index = source.index("ラクテル用テキスト設定")
    direction_index = source.index('"通話方向"', settings_index)
    counterparty_index = source.index('"相手区分"', settings_index)
    old_label = 'st.selectbox(\n            "発信者区分"'

    assert settings_index < direction_index < counterparty_index
    assert old_label not in source


def test_escalation_info_includes_reason_and_next_action():
    info = app.build_vendor_escalation_info(
        "CER候補（担当確認）",
        {"reason": "九州エリア", "needs_escalation": True},
    )

    assert "九州エリア" in info["reason"]
    assert "CER" in info["next_action"]


def test_cer_drive_link_info_is_available_on_vendor_card():
    card = app.build_vendor_candidate_card_info(
        "CER候補（担当確認）",
        {"reason": "九州エリア", "needs_escalation": True},
    )

    assert card["request_folder"]["required"] is True
    assert card["request_folder"]["name"] == "CER"
    assert "drive.google.com" in card["request_folder"]["url"]
    assert card["arrangement_method"] == "依頼書PDF格納"


def test_teams_area_source_does_not_render_drive_link():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    teams_index = source.index("##### 💬 Teams 報告文")
    send_button_index = source.index('st.button("Teamsチャットへ送信"', teams_index)
    teams_area = source[teams_index:send_button_index]

    assert "Google Drive を開く" not in teams_area
    assert "依頼書PDF格納先" not in teams_area


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
