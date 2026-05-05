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


def test_copy_import_success_paths_close_panel_and_rerun():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    clipboard_index = source.index('if st.button("📋 クリップボードから直接抽出"')
    manual_index = source.index('if st.button("🔍 抽出する"', clipboard_index)
    reflect_index = source.index('if st.button("📥 フォームへ反映"', manual_index)
    clipboard_area = source[clipboard_index:manual_index]
    manual_area = source[manual_index:reflect_index]
    reflect_area = source[reflect_index:source.index("form = st.session_state.form", reflect_index)]

    assert "close_copy_import_panel(st.session_state)" in clipboard_area
    assert "st.rerun()" in clipboard_area
    assert "close_copy_import_panel(st.session_state)" in manual_area
    assert "st.rerun()" in manual_area
    assert "close_copy_import_panel(st.session_state)" in reflect_area
    assert "st.rerun()" in reflect_area


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
    tabs_index = source.index("st.tabs", main_index)
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
    })

    app.process_pending_case_clear(state, {"default_operator_name": ""})

    assert state["call_check_manual"] == {}
    assert not any(str(key).startswith("manual_check_") for key in state)
    assert not any(str(key).startswith("now_input_") for key in state)


def test_global_top_panels_render_case_memo_and_decision_tags_before_tabs():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    panels_start = source.index("def render_global_top_panels")
    panels_end = source.index("def render_common_call_memo", panels_start)
    panels_source = source[panels_start:panels_end]
    main_index = source.index("def main():")
    top_index = source.index("render_global_top_panels(st.session_state.form)", main_index)
    tabs_index = source.index("st.tabs", main_index)

    assert "render_common_case_memo" in panels_source
    assert "render_decision_tags_panel" in panels_source
    assert top_index < tabs_index


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
