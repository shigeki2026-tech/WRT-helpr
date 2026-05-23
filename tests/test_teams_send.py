# -*- coding: utf-8 -*-
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import app


ROOT = Path(__file__).resolve().parents[1]


def test_append_attention_memo_snippets_only_updates_repair_request_memo():
    form = app.empty_form()
    form.update({
        "attention_memo": "既存本文",
        "rakutel_text": "既存ラクテル",
        "teams_chat_message": "既存Teams",
        "product": "プリンター",
        "call_line": "家電保証対応業務（24時間）",
        "operator_name": "MPG担当",
        "rakuteru_no": "2026_05_0001",
    })

    added = app.append_attention_memo_snippets(form, ["manufacturer_warranty"])

    assert len(added) == 1
    assert "既存本文" in form["attention_memo"]
    assert "【メーカー保証期間中の為、メーカー保証に準じる】" in form["attention_memo"]
    assert form["rakutel_text"] == "既存ラクテル"
    assert form["teams_chat_message"] == "既存Teams"


def test_memo_snippet_master_has_ui_columns_and_sorted_active_rows():
    df = app.load_memo_snippets()

    assert {"condition_text", "ui_group", "default_checked"}.issubset(df.columns)
    assert all(str(value).strip() != "0" for value in df["active"].tolist())
    assert df["sort_order"].tolist() == sorted(df["sort_order"].tolist())
    assert "基本案内" in set(df["ui_group"])
    assert "販売店連絡" in set(df["ui_group"])


def test_memo_snippet_condition_text_is_not_part_of_body():
    df = app.load_memo_snippets()
    row = df[df["snippet_id"] == "data_erase_backup"].iloc[0]

    assert row["condition_text"]
    assert "PC・プリンター" in row["condition_text"]
    assert "PC・プリンター" not in row["body"]


def test_append_attention_memo_snippets_does_not_duplicate():
    form = app.empty_form()
    app.append_attention_memo_snippets(form, ["store_request"])
    once = form["attention_memo"]
    app.append_attention_memo_snippets(form, ["store_request"])

    assert form["attention_memo"] == once
    assert form["attention_memo"].count("【○○店/○○様より修理依頼】") == 1


def test_append_attention_memo_snippets_adds_body_only_not_condition_text():
    form = app.empty_form()
    form["attention_memo"] = "既存本文"

    added = app.append_attention_memo_snippets(form, ["data_erase_backup"])

    assert len(added) == 1
    assert "既存本文" in form["attention_memo"]
    assert "【初期化・部品交換の可能性があり、データ消去・バックアップのご案内同意済み】" in form["attention_memo"]
    assert "PC・プリンター" not in form["attention_memo"]


def test_appended_attention_memo_snippet_stays_out_of_generated_texts():
    form = app.empty_form()
    form.update({
        "call_line": "家電保証対応業務（24時間）",
        "product": "プリンター",
        "manufacturer": "キヤノン",
        "operator_name": "MPG担当",
        "rakuteru_no": "2026_05_0002",
    })
    app.append_attention_memo_snippets(form, ["out_of_scope_store_contact"])
    snippet_text = "保証対象外時：販売店へ連絡要"

    rakutel_text = app._build_rakutel_text(form, "加入者", "")
    teams_text = app._build_teams_chat_message(form, "WRT修理受付センター")

    assert snippet_text in form["attention_memo"]
    assert snippet_text not in rakutel_text
    assert snippet_text not in teams_text


def test_appended_attention_memo_snippet_stays_out_of_warranty_report():
    form = app.empty_form()
    form.update({
        "rakuteru_no": "2026_05_1073",
        "call_line": "家電",
        "warranty_report_content": "ユナイトへFAX送信済",
        "store_name": "ヤマダホームズ",
    })
    app.append_attention_memo_snippets(form, ["out_of_scope_store_contact"])
    decision = {
        "vendor": "ユナイトサービス㈱",
        "vendor_result": {"vendor_name": "ユナイトサービス㈱", "send_method": "FAX"},
    }

    message = app.build_warranty_report_message(form, decision)

    assert "保証対象外時：販売店へ連絡要" not in message
    assert message == "2026_05_1073　家電　ユナイトへFAX送信済　ご確認お願いします"


def test_memo_snippet_ui_uses_single_selectbox_not_multiselect_or_checkboxes():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]
    snippet_source = after_source[
        after_source.index("###### 追記候補"):
        after_source.index("##### 📝 ラクテル用テキスト")
    ]
    memo_text_area_index = after_source.index('memo_display = st.text_area(')
    memo_copy_index = after_source.index("copy_attention_memo")
    snippet_index = after_source.index("###### 追記候補")
    pending_index = after_source.index('pending_snippet_id = str(st.session_state.pop("_pending_append_memo_snippet_id"')
    action_panel_index = after_source.index("修理依頼書メモ 操作")

    assert "Choose options" not in source
    assert "Select all" not in source
    assert "st.multiselect" not in snippet_source
    assert "st.checkbox" not in snippet_source
    assert "st.selectbox" in snippet_source
    assert "memo_col, memo_action_col = st.columns([2, 3], gap=\"large\")" in after_source
    assert "with memo_col:" in after_source
    assert "with memo_action_col:" in after_source
    assert "修理依頼書メモ 操作" in after_source
    assert "追記候補" in snippet_source
    assert "追記する定型文を選択" in snippet_source
    assert "追記条件" in snippet_source
    assert "追記内容" in snippet_source
    assert '"\\n" in body' in snippet_source
    assert "本文プレビュー" not in snippet_source
    assert "追加候補に入れる" not in source
    assert "選択中の定型文" not in source
    assert "選択中リストをクリア" not in source
    assert "選択中の文言を修理依頼書メモへ追記" not in source
    assert "memo_snippet_selectbox" in snippet_source
    assert "この文言を追記" in snippet_source
    assert "memo_snippet_append_current_button" in snippet_source
    assert "memo_snippet_selected_ids" not in source
    assert "memo_snippet_add_to_selection_button" not in source
    assert "memo_snippet_append_selected_button" not in source
    assert "memo_snippet_clear_selected_button" not in source
    assert "_pending_append_memo_snippet_id" in snippet_source
    assert "_memo_snippet_append_message" in snippet_source
    assert "st.rerun()" in snippet_source
    assert "append_attention_memo_snippets(form, [selected_snippet_id])" not in snippet_source
    assert "append_attention_memo_snippets(form, [pending_snippet_id])" in after_source
    assert pending_index < memo_text_area_index < action_panel_index < memo_copy_index < snippet_index


def test_after_call_operator_name_input_is_compact_with_save_button():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]
    operator_area = after_source[
        after_source.index("name_col, save_col, spacer_col"):
        after_source.index("st.session_state.form = form", after_source.index("name_col, save_col, spacer_col"))
    ]

    assert "name_col, save_col, spacer_col = st.columns([2, 1.6, 2.4])" in operator_area
    assert "with name_col:" in operator_area
    assert "with save_col:" in operator_area
    assert 'key="operator_name_input"' in operator_area
    assert 'key="save_default_operator_name"' in operator_area
    assert "既定値に保存" in operator_area
    assert "この名前を既定値として保存" not in operator_area
    assert "use_container_width=True" not in operator_area


def test_after_call_major_text_sections_use_matching_two_column_layout():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]

    assert "memo_col, memo_action_col = st.columns([2, 3], gap=\"large\")" in after_source
    assert "rakutel_text_col, rakutel_action_col = st.columns([2, 3], gap=\"large\")" in after_source
    assert "teams_text_col, teams_action_col = st.columns([2, 3], gap=\"large\")" in after_source
    assert "with memo_col:" in after_source
    assert "with memo_action_col:" in after_source
    assert "with rakutel_text_col:" in after_source
    assert "with rakutel_action_col:" in after_source
    assert "with teams_text_col:" in after_source
    assert "with teams_action_col:" in after_source
    assert "修理依頼書メモ 操作" in after_source
    assert "ラクテル用テキスト 操作" in after_source
    assert "Teams報告文 操作" in after_source
    assert "st.columns([5, 2], gap=\"large\")" not in after_source

    rakutel_section = after_source[
        after_source.index("##### 📝 ラクテル用テキスト"):
        after_source.index("##### 💬 Teams報告文")
    ]
    assert rakutel_section.index("with rakutel_action_col:") < rakutel_section.index('"通話方向"')
    assert rakutel_section.index("with rakutel_action_col:") < rakutel_section.index('"相手区分"')
    assert rakutel_section.index("with rakutel_action_col:") < rakutel_section.index('"日程調整時の連絡先"')

    teams_section = after_source[
        after_source.index("##### 💬 Teams報告文"):
        after_source.index('render_handover_requirement_panel(decision.get("handover_requirement"))')
    ]
    assert teams_section.index("with teams_action_col:") < teams_section.index('"Teams報告文に入れる対応内容"')
    assert teams_section.index("with teams_action_col:") < teams_section.index('"送信内容と送信先を確認しました"')
    assert teams_section.index("with teams_action_col:") < teams_section.index('"Teamsチャットへ送信"')
    assert "追加候補に入れる" not in after_source
    assert "選択中リスト" not in after_source


def test_after_call_record_area_is_full_width_below_top_columns():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]

    top_left_index = after_source.index("##### 案件サマリー")
    top_right_index = after_source.index("##### 補助情報")
    record_heading_index = after_source.index("##### 📝 記録文")
    memo_heading_index = after_source.index("##### 📝 修理依頼書メモ")
    record_area = after_source[record_heading_index:memo_heading_index]

    assert top_left_index < record_heading_index
    assert top_right_index < record_heading_index
    assert "with col2:" not in record_area
    assert "\n    st.markdown(\"##### 📝 記録文\")" in after_source
    assert after_source.index("memo_col, memo_action_col = st.columns([2, 3], gap=\"large\")") > record_heading_index
    assert after_source.index("rakutel_text_col, rakutel_action_col = st.columns([2, 3], gap=\"large\")") > record_heading_index
    assert after_source.index("teams_text_col, teams_action_col = st.columns([2, 3], gap=\"large\")") > record_heading_index


def test_after_call_top_summary_keeps_details_collapsed():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]
    record_heading_index = after_source.index("##### 📝 記録文")

    assert "##### 案件サマリー" in after_source
    assert 'st.expander("送付テンプレート・拠点の詳細を開く", expanded=False)' in after_source
    assert 'st.expander("修理拠点・手配詳細を開く", expanded=False)' in after_source
    assert 'st.expander("候補テンプレートの詳細を見る", expanded=False)' in after_source
    assert 'st.expander("手配方法・連絡先の詳細", expanded=False)' in after_source
    assert after_source.index("##### 案件サマリー") < record_heading_index
    assert after_source.index("送付テンプレート・拠点の詳細を開く") < record_heading_index
    assert after_source.index("修理拠点・手配詳細を開く") < record_heading_index


def test_repair_request_template_is_shown_before_memo_regeneration_button():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]
    memo_action = after_source[
        after_source.index("修理依頼書メモ 操作"):
        after_source.index("###### 追記候補")
    ]

    assert "修理依頼文テンプレ" in memo_action
    assert "テンプレート未確定" in memo_action
    assert "memo_template_code" in memo_action
    assert "memo_template_label" in memo_action
    assert "build_template_selection_reason(template_selection)" in memo_action
    assert memo_action.index("修理依頼文テンプレ") < memo_action.index('key="regenerate_attention_memo"')


def test_after_call_history_template_is_collapsed_as_legacy_format():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]
    history_index = after_source.index("対応履歴テンプレ（旧形式・必要時のみ）")

    assert "##### 📄 対応履歴テンプレ（コピー用）" not in after_source
    assert 'st.expander("対応履歴テンプレ（旧形式・必要時のみ）", expanded=False)' in after_source
    assert "通常はラクテル用テキストまたはTeams報告文を使用してください。" in after_source
    assert "旧形式の履歴貼付が必要な場合のみ使用します。" in after_source
    assert after_source.index('render_copy_button("📋 コピー", history_tmpl, "copy_history_after_template")') > history_index


def test_after_call_contact_method_table_is_collapsed_by_default():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]

    assert "###### 手配方法・連絡先" not in after_source
    assert 'st.expander("手配方法・連絡先の詳細", expanded=False)' in after_source


def test_after_call_uses_shared_status_card_css_classes():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert "wrt-status-card" in source
    assert "wrt-pill" in source
    assert "wrt-memo-snippet-row" in source
    assert ".wrt-text-section" in source
    assert ".wrt-action-panel" in source
    assert "width: 100%;" in source
    assert "box-sizing: border-box;" in source
    assert "wrt-snippet-group-label" in source


def test_decision_tags_have_fixed_height_and_secondary_tertiary_overflow_css():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    primary_css = source[source.index(".wrt-decision-tag-primary {"):source.index(".wrt-decision-tag-secondary {")]
    secondary_css = source[source.index(".wrt-decision-tag-secondary {"):source.index(".wrt-decision-tag-tertiary {")]
    tertiary_css = source[source.index(".wrt-decision-tag-tertiary {"):source.index(".wrt-snippet-group-label {")]
    tag_css = source[source.index(".wrt-decision-tag {"):source.index(".wrt-decision-tag-title {")]
    tag_height = int(re.search(r"height:\s*(\d+)px", tag_css).group(1))

    assert "wrt-decision-tag" in source
    assert tag_height >= 120
    assert "height: 96px" not in tag_css
    assert "box-sizing: border-box" in source
    assert "gap: 4px" in source
    assert "white-space: nowrap" in primary_css
    assert "-webkit-line-clamp" not in primary_css
    assert "overflow: hidden" in secondary_css
    assert "max-height: 3.0em" in secondary_css
    assert "font-size: 0.76rem" in secondary_css
    assert "overflow: hidden" in tertiary_css
    assert "max-height: 2.6em" in tertiary_css
    assert "wrt-decision-tag-secondary" in source
    assert "wrt-decision-tag-tertiary" in source
    assert "_decision_tag_short_note" in source


def test_decision_tag_long_reason_is_summarized():
    text = "CSVに明確な出張/持込ルールがないため要確認"

    assert app._decision_tag_short_note("確認：", text) == "確認：要確認"


def test_handover_and_warranty_panels_use_cards_for_status_display():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    handover_start = source.index("def render_handover_requirement_panel")
    warranty_start = source.index("def render_warranty_report_send_panel")
    handover_source = source[handover_start:warranty_start]
    warranty_end = source.index("\ndef render_decision_tags_panel", warranty_start)
    warranty_source = source[warranty_start:warranty_end]

    assert "_status_card_html" in handover_source
    assert "st.error(" not in handover_source
    assert "st.warning(" not in handover_source
    assert "_status_card_html" in warranty_source
    assert warranty_source.index("_status_card_html") < warranty_source.index("st.text_area(")
    assert "送信不可理由をすべて表示" in warranty_source


def test_memo_snippet_selectbox_labels_are_template_text_only():
    df = app.load_memo_snippets()
    row = app.memo_snippet_row_by_id(df, "manufacturer_warranty")
    visit_row = app.memo_snippet_row_by_id(df, "visit_complete_share")

    assert app.memo_snippet_option_label(row) == "【メーカー保証期間中の為、メーカー保証に準じる】"
    assert app.memo_snippet_option_label(visit_row) == "※訪問日・完了内容は弊社へ共有をお願いいたします。"
    assert "｜" not in app.memo_snippet_option_label(row)


def test_memo_snippet_csv_labels_are_body_based_templates():
    csv_text = (ROOT / "data" / "master_memo_snippets.csv").read_text(encoding="utf-8")
    app_text = (ROOT / "app.py").read_text(encoding="utf-8")
    df = app.load_memo_snippets()
    manufacturer = app.memo_snippet_row_by_id(df, "manufacturer_warranty")
    store_request = app.memo_snippet_row_by_id(df, "store_request")
    out_of_scope = app.memo_snippet_row_by_id(df, "out_of_scope_store_contact")

    assert "保証関連｜メーカー保証期間中" not in csv_text
    assert "販売店連絡｜訪問日・完了内容の共有希望" not in csv_text
    assert "保証関連｜" not in app_text
    assert "販売店連絡｜" not in app_text
    assert "依頼元変更｜" not in app_text
    assert manufacturer["label"] == "【メーカー保証期間中の為、メーカー保証に準じる】"
    assert manufacturer["body"] == "【メーカー保証期間中の為、メーカー保証に準じる】"
    assert manufacturer["condition_text"] == "メーカー保証期間中の受付"
    assert store_request["label"] == "【○○店/○○様より修理依頼】"
    assert out_of_scope["label"] == "保証対象外時：販売店へ連絡要"
    assert out_of_scope["body"].startswith("保証対象外時：販売店へ連絡要")


class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


def write_config(path: Path, enabled=True, chat_id="chat-123", send_mode="powershell_graph",
                 warranty_enabled=False, warranty_chat_id=""):
    path.write_text(
        json.dumps({
            "enabled": enabled,
            "chat_id": chat_id,
            "chat_name": "WRT報告用チャット",
            "send_mode": send_mode,
            "warranty_enabled": warranty_enabled,
            "warranty_chat_id": warranty_chat_id,
            "warranty_chat_name": "Teamsワランティ送信先チャット",
        }, ensure_ascii=False),
        encoding="utf-8",
    )


def test_teams_config_example_exists():
    example_path = ROOT / "config" / "teams_config.example.json"
    assert example_path.is_file()
    example = json.loads(example_path.read_text(encoding="utf-8"))
    assert example == {
        "enabled": False,
        "chat_id": "REPLACE_WITH_TEAMS_CHAT_ID",
        "chat_name": "WRT報告用チャット",
        "send_mode": "powershell_graph",
        "warranty_enabled": True,
        "warranty_chat_id": "",
        "warranty_chat_name": "Teamsワランティ送信先チャット",
    }


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


def test_teams_config_enabled_false_is_disabled(monkeypatch, tmp_path):
    config_path = tmp_path / "teams_config.json"
    write_config(config_path, enabled=False, chat_id="chat-123")
    monkeypatch.setattr(app, "TEAMS_CONFIG_PATH", str(config_path))
    monkeypatch.delenv("WRT_TEAMS_CHAT_ID", raising=False)

    assert app.is_teams_send_enabled() is False


def test_teams_send_disabled_without_chat_id(monkeypatch, tmp_path):
    config_path = tmp_path / "teams_config.json"
    write_config(config_path, enabled=True, chat_id="")
    monkeypatch.setattr(app, "TEAMS_CONFIG_PATH", str(config_path))
    monkeypatch.delenv("WRT_TEAMS_CHAT_ID", raising=False)

    assert app.is_teams_send_enabled() is False


def test_teams_send_disabled_for_unsupported_send_mode(monkeypatch, tmp_path):
    config_path = tmp_path / "teams_config.json"
    write_config(config_path, enabled=True, chat_id="chat-123", send_mode="unsupported")
    monkeypatch.setattr(app, "TEAMS_CONFIG_PATH", str(config_path))
    monkeypatch.delenv("WRT_TEAMS_CHAT_ID", raising=False)

    config = app.load_teams_config()

    assert app.is_teams_send_enabled() is False
    assert "send_mode は powershell_graph を指定してください" in app.teams_config_unavailable_reasons(config)


def test_empty_message_does_not_call_subprocess(monkeypatch):
    def fail_run(*args, **kwargs):
        raise AssertionError("subprocess.run should not be called")

    monkeypatch.setattr(app.subprocess, "run", fail_run)

    result = app.send_teams_message_via_powershell("   ")

    assert result["ok"] is False
    assert "本文が空" in result["message"]


def warranty_decision(vendor_name="ユナイトサービス㈱", send_method="", contact_type=""):
    return {
        "vendor": vendor_name,
        "vendor_result": {
            "vendor_name": vendor_name,
            "send_method": send_method,
            "contact_type": contact_type,
            "needs_escalation": "担当エスカ" in vendor_name or "要確認" in vendor_name,
        },
    }


def warranty_form(**overrides):
    form = app.empty_form()
    form.update({
        "rakuteru_no": "2026_05_1073",
        "call_line": "家電",
        "warranty_report_content": "ユナイトへFAX送信済",
        "store_name": "ヤマダホームズ",
        "rakutel_text": "既存ラクテル",
        "attention_memo": "既存依頼書メモ",
        "teams_chat_message": "既存Teams報告文",
    })
    form.update(overrides)
    return form


def warranty_config(enabled=True, chat_id="warranty-chat"):
    config = app.DEFAULT_TEAMS_CONFIG.copy()
    config.update({
        "warranty_enabled": enabled,
        "warranty_chat_id": chat_id,
        "send_mode": "powershell_graph",
    })
    return config


def test_warranty_report_message_uses_expected_full_width_space_format():
    message = app.build_warranty_report_message(
        warranty_form(rakuteru_no="2026_05_1758"),
        warranty_decision(send_method="FAX"),
    )

    assert message == "2026_05_1758　家電　ユナイトへFAX送信済　ご確認お願いします"
    assert " " not in message
    assert message.count("　") == 3
    assert "ご確認お願い致します。" not in message


def test_warranty_report_message_uses_form_fields_not_vendor_store_or_method():
    message = app.build_warranty_report_message(
        warranty_form(store_name="", warranty_report_content="担当確認お願いします"),
        warranty_decision(vendor_name="担当エスカ（要確認）", send_method=""),
    )

    assert message == "2026_05_1073　家電　担当確認お願いします　ご確認お願いします"
    assert "修理受付済" not in message


def test_warranty_report_validation_blocks_missing_required_fields():
    base_form = warranty_form()
    base_decision = warranty_decision(send_method="FAX")
    config = warranty_config()

    assert app.validate_warranty_report_send_request(
        {**base_form, "rakuteru_no": "", "call_line": "", "warranty_report_content": ""},
        base_decision,
        config,
    ) == []
    assert app.get_warranty_report_missing_items(
        {**base_form, "rakuteru_no": "", "call_line": "", "warranty_report_content": ""}
    ) == [
        "楽テルNOが未入力です",
        "回線名が未選択です",
        "確認内容が未入力です",
    ]
    assert "楽テルNOが未入力です" not in app.validate_warranty_report_send_request(
        {**base_form, "rakuteru_no": ""}, base_decision, config
    )
    assert "回線名が未選択です" not in app.validate_warranty_report_send_request(
        {**base_form, "call_line": ""}, base_decision, config
    )
    assert "確認内容が未入力です" not in app.validate_warranty_report_send_request(
        {**base_form, "warranty_report_content": ""}, base_decision, config
    )
    assert "販売店/運営会社名が未取得です" not in app.validate_warranty_report_send_request(
        {**base_form, "store_name": "", "store_original": ""}, base_decision, config
    )
    assert "修理拠点が未確定です" not in app.validate_warranty_report_send_request(
        base_form, warranty_decision("担当エスカ（要確認）", send_method="FAX"), config
    )
    assert "送信方法が未確定です" not in app.validate_warranty_report_send_request(
        base_form, warranty_decision("WRT修理センター"), config
    )


def test_warranty_report_validation_blocks_config_and_duplicate():
    form = warranty_form()
    decision = warranty_decision(send_method="FAX")

    disabled = app.validate_warranty_report_send_request(form, decision, warranty_config(enabled=False))
    no_chat = app.validate_warranty_report_send_request(form, decision, warranty_config(chat_id=""))
    implicit_enabled_config = warranty_config()
    implicit_enabled_config.pop("warranty_enabled")
    implicit_enabled = app.validate_warranty_report_send_request(form, decision, implicit_enabled_config)
    duplicate = app.validate_warranty_report_send_request(
        form,
        decision,
        warranty_config(),
        app.build_warranty_report_message(form, decision),
        already_sent=True,
    )

    assert "ワランティ送信設定が無効です" in disabled
    assert "ワランティ送信先 chat_id が未設定です" in no_chat
    assert "ワランティ送信設定が無効です" not in implicit_enabled
    assert "同じ内容は送信済みです" in duplicate


def test_warranty_report_send_is_independent_from_handover_requirement():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    panel_start = source.index("def render_warranty_report_send_panel")
    panel_end = source.index("\ndef render_decision_tags_panel", panel_start)
    panel_source = source[panel_start:panel_end]
    form = warranty_form()
    decision = {
        **warranty_decision(send_method="FAX"),
        "handover_requirement": {
            "required": False,
            "matched": False,
            "reason": "引き継ぎ対象ルールに一致なし",
        },
    }
    errors = app.validate_warranty_report_send_request(form, decision, warranty_config())

    assert errors == []
    assert "引き継ぎ対象ルールに一致していません" not in source
    assert "全案件、ワランティ報告チャットへ送信してください。" in panel_source
    assert "handover_requirement" not in panel_source


def test_warranty_report_message_uses_placeholders_for_missing_fields():
    message = app.build_warranty_report_message(
        warranty_form(rakuteru_no="", call_line="", warranty_report_content=""),
        warranty_decision(send_method="FAX"),
    )
    partial = app.build_warranty_report_message(
        warranty_form(rakuteru_no="2026_05_1758", call_line="家電", warranty_report_content=""),
        warranty_decision(send_method="FAX"),
    )

    assert message == "楽テルNO未入力　●●　○○○○○○　ご確認お願いします"
    assert partial == "2026_05_1758　家電　○○○○○○　ご確認お願いします"


def test_warranty_report_message_stays_out_of_rakutel_memo_and_existing_teams():
    form = warranty_form()
    decision = warranty_decision(send_method="FAX")
    message = app.build_warranty_report_message(form, decision)

    assert message
    assert form["rakutel_text"] == "既存ラクテル"
    assert form["attention_memo"] == "既存依頼書メモ"
    assert form["teams_chat_message"] == "既存Teams報告文"


def test_warranty_report_send_uses_warranty_chat_id(monkeypatch, tmp_path):
    config_path = tmp_path / "teams_config.json"
    write_config(
        config_path,
        enabled=False,
        chat_id="",
        warranty_enabled=True,
        warranty_chat_id="warranty-chat-id",
    )
    script_path = tmp_path / "send_teams_message.ps1"
    script_path.write_text("# test", encoding="utf-8")
    monkeypatch.setattr(app, "TEAMS_CONFIG_PATH", str(config_path))
    monkeypatch.setattr(app, "TEAMS_SEND_SCRIPT_PATH", str(script_path))

    calls = {}

    def fake_run(args, **kwargs):
        calls["args"] = args
        return SimpleNamespace(returncode=0, stdout="SUCCESS message-1", stderr="")

    monkeypatch.setattr(app.subprocess, "run", fake_run)

    result = app.send_teams_message_via_powershell("hello", chat_id_override="warranty-chat-id")

    assert result["ok"] is True
    assert "warranty-chat-id" in calls["args"]


def test_warranty_report_panel_buttons_have_unique_keys():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    panel_start = source.index("def render_warranty_report_send_panel")
    panel_end = source.index("\ndef render_decision_tags_panel", panel_start)
    panel_source = source[panel_start:panel_end]

    assert "Teamsワランティ送信" in panel_source
    assert "ワランティ報告送信" not in panel_source
    assert '"確認内容"' in panel_source
    assert 'key="warranty_report_content_input"' in panel_source
    assert "例：ユナイトへFAX送信済 / 担当確認お願いします" in panel_source
    assert "注意：未入力項目があります。内容を確認してから送信してください。" in panel_source
    assert '"Teamsワランティへ送信"' in panel_source
    assert '"未完了項目があります"' not in panel_source
    for key in [
        'key="warranty_report_sending_button"',
        'key="warranty_report_sent_button"',
        'key="warranty_report_resend_button"',
        'key="warranty_report_send_incomplete_button"',
        'key="warranty_report_send_button"',
        'key="warranty_report_message_display"',
    ]:
        assert key in panel_source


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


def test_attention_memo_009_is_normalized_to_0009_template():
    form = app.empty_form()
    form.update({
        "template_code": "009",
        "template_label": "【出張修理】自然故障",
        "symptom_detail": "電源が入らない",
        "occurrence_time": "昨日から",
        "occurrence_frequency": "毎回",
    })

    memo = app._build_after_call_memo(
        form,
        {"title": "保証期間内"},
        "出張修理",
        "WRT修理センター",
        cost_estimate="確認中",
    )

    assert "具体的な症状：電源が入らない" in memo
    assert "発生時期：昨日から" in memo
    assert "発生頻度：毎回" in memo


def test_residential_0009_attention_memo_uses_0009_template():
    form = app.empty_form()
    form.update({
        "call_line": "住設",
        "appliance_type": "住設",
        "genre": "(新品)住宅設備機器",
        "template_code": "0009",
        "template_label": "【出張修理】自然故障",
        "product": "IHクッキングヒーター",
        "manufacturer": "三菱電機",
        "symptom_detail": "加熱しない",
        "occurrence_time": "数日前から",
        "occurrence_frequency": "毎回",
    })

    memo = app._build_after_call_memo(
        form,
        {"title": "保証期間内"},
        "出張修理",
        "WRT修理センター",
        cost_estimate="確認中",
    )

    assert "具体的な症状：加熱しない" in memo
    assert "発生時期：数日前から" in memo
    assert "発生頻度：毎回" in memo
    assert "テンプレート:" not in memo


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
    assert app.build_rakutel_call_header("", "受電") == "【●●回線に入電】"
    assert app.build_rakutel_call_header("", "架電") == "【●●回線から架電】"
    assert "未選択回線" not in app.build_rakutel_call_header("", "受電")
    assert app.build_rakutel_call_header("家電保証対応業務（24時間）", "受電") == "【家電回線に入電】"
    assert app.build_rakutel_call_header("住設業務", "受電") == "【住設回線に入電】"
    assert app.build_rakutel_call_header("家電保証対応業務（24時間）", "架電") == "【家電回線から架電】"
    assert app.build_rakutel_call_header("住設業務", "架電") == "【住設回線から架電】"
    assert app.build_rakutel_call_header("家電保証対応業務（24時間）", "架電") != "【家電回線に架電】"


def test_rakutel_text_does_not_generate_blank_line_header():
    form = app.empty_form()

    text = app._build_rakutel_text(form, "加入者", "")

    assert "【回線に入電】" not in text


def test_residential_case_keeps_manual_home_line_and_only_infers_appliance_type():
    form = app.empty_form()
    form.update({
        "call_line": "家電保証対応業務（24時間）",
        "appliance_type": "家電",
        "warranty_plan": "アイ工務店_住宅設備機器【10年保証】",
        "genre": "(新品)住宅設備機器",
        "category": "システムキッチン",
        "series": "システムキッチン",
        "product": "システムキッチン",
        "manufacturer": "パナソニック",
        "prefecture": "滋賀県",
    })

    decision = app.run_decision(form)
    rakutel_text = app._build_rakutel_text(decision["working_form"], "加入者", "")
    teams_message = app._build_teams_chat_message(decision["working_form"], "ユナイトサービス㈱")

    assert decision["working_form"]["appliance_type"] == "住設"
    assert decision["working_form"]["call_line"] == "家電"
    assert "【家電回線に入電】" in rakutel_text
    assert "【住設回線に入電】" not in rakutel_text
    assert teams_message.splitlines()[0] == "家電"


def test_manual_call_line_prevents_residential_auto_call_line_override():
    form = app.empty_form()
    form.update({
        "call_line": "家電",
        "manual_call_line": True,
        "appliance_type": "家電",
        "warranty_plan": "アイ工務店_住宅設備機器【10年保証】",
        "product": "システムキッチン",
    })

    assert app.effective_call_line_for_form(form) == "家電"
    assert "【家電回線に入電】" in app._build_rakutel_text(form, "加入者", "")


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


def test_teams_send_validation_allows_when_all_required_conditions_are_ready():
    form = {
        "rakuteru_no": "2026_05_0174",
        "teams_action": "FAX済み",
        "teams_chat_message": "2026_05_0174\n家電回線\nドライヤー\nユナイトサービス㈱へFAX済み",
    }

    errors = app.validate_teams_send_request(
        form,
        teams_enabled=True,
        send_confirmed=True,
        action_confirmed=True,
        pdf_storage_confirmed=True,
        vendor="ユナイトサービス㈱",
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
    assert app.teams_send_status_label([], already_sent=False, send_failed=True) == "送信失敗"
    assert app.teams_send_status_label([], already_sent=False, in_progress=True) == "送信処理中"
    assert app.teams_send_status_label(["楽テルNO未入力"], already_sent=False, send_failed=True) == "送信不可"


def test_teams_send_panel_reasons_include_duplicate_send_state():
    form = {
        "rakuteru_no": "2026_05_0174",
        "teams_action": "FAX済み",
        "teams_chat_message": "2026_05_0174\n家電回線\nドライヤー\nユナイトサービス㈱へFAX済み",
    }
    config = {"enabled": True, "chat_id": "chat-123", "send_mode": "powershell_graph"}

    reasons = app.build_teams_send_incomplete_reasons(
        form,
        config,
        send_confirmed=True,
        action_confirmed=True,
        pdf_storage_confirmed=True,
        vendor="ユナイトサービス㈱",
        already_sent=True,
    )

    assert "送信済み（二重送信防止）" in reasons


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
    app._mark_teams_send_requested(state, form, now=datetime(2026, 5, 8, 12, 34, 50))

    app._mark_teams_message_sent(
        state,
        form,
        datetime(2026, 5, 8, 12, 34, 56),
        result={"stdout": "SUCCESS message-001\n"},
    )

    assert state["teams_sent"] is True
    assert state["teams_sent_message"] == form["teams_chat_message"]
    assert state["teams_sent_at"] == "2026/05/08 12:34:56"
    assert state["teams_sent_body_hash"]
    assert state["teams_sent_message_id"] == "message-001"
    assert state["teams_send_failed"] is False
    assert state["teams_send_requested"] is False
    assert state["teams_send_requested_body_hash"] == ""
    assert state["teams_send_in_progress"] is False
    assert state["teams_send_in_progress_body_hash"] == ""
    assert app._teams_case_already_sent(state, form) is True


def test_teams_sent_state_only_matches_same_body_hash():
    state = SessionState()
    form = {"teams_chat_message": "2026_05_0174\n家電回線"}
    changed_form = {"teams_chat_message": "2026_05_0174\n住設"}

    app._mark_teams_message_sent(state, form, datetime(2026, 5, 8, 12, 34, 56))

    assert app._teams_case_already_sent(state, form) is True
    assert app._teams_case_already_sent(state, changed_form) is False


def test_teams_send_in_progress_only_matches_same_body_hash():
    state = SessionState()
    form = {"teams_chat_message": "2026_05_0174\n家電回線"}
    changed_form = {"teams_chat_message": "2026_05_0174\n住設"}

    app._mark_teams_send_in_progress(state, form, datetime(2026, 5, 8, 12, 34, 50))

    assert state["teams_send_in_progress"] is True
    assert state["teams_send_started_at"] == "2026/05/08 12:34:50"
    assert state["teams_send_in_progress_body_hash"]
    assert app._teams_send_in_progress(state, form) is True
    assert app._teams_send_in_progress(state, changed_form) is False


def test_mark_teams_send_requested_sets_requested_and_in_progress_state():
    state = SessionState()
    form = {"teams_chat_message": "2026_05_0174\n家電回線"}

    app._mark_teams_send_requested(
        state,
        form,
        allow_resend=True,
        now=datetime(2026, 5, 8, 12, 34, 50),
    )

    assert state["teams_send_requested"] is True
    assert state["teams_send_requested_body_hash"]
    assert state["teams_send_requested_allow_resend"] is True
    assert app._teams_send_requested(state, form) is True
    assert state["teams_send_in_progress"] is True
    assert state["teams_send_in_progress_body_hash"] == state["teams_send_requested_body_hash"]
    assert state["teams_send_started_at"] == "2026/05/08 12:34:50"


def test_stale_teams_send_request_is_cleared_when_body_hash_changes():
    state = SessionState()
    form = {"teams_chat_message": "2026_05_0174\n家電回線"}
    changed_form = {"teams_chat_message": "2026_05_0174\n住設"}
    app._mark_teams_send_requested(state, form, now=datetime(2026, 5, 8, 12, 34, 50))

    app._clear_stale_teams_send_transient_state(state, changed_form)

    assert state["teams_send_requested"] is False
    assert state["teams_send_requested_body_hash"] == ""
    assert state["teams_send_in_progress"] is False
    assert state["teams_send_in_progress_body_hash"] == ""


def test_mark_teams_send_failed_sets_current_message_error_state():
    state = SessionState()
    form = {"teams_chat_message": "2026_05_0174\n家電回線"}
    app._mark_teams_send_requested(state, form, now=datetime(2026, 5, 8, 12, 35, 0))

    app._mark_teams_message_send_failed(
        state,
        form,
        {"message": "送信失敗: denied"},
        datetime(2026, 5, 8, 12, 35, 10),
    )

    assert state["teams_send_failed"] is True
    assert state["teams_send_failed_message"] == form["teams_chat_message"]
    assert state["teams_send_failed_body_hash"]
    assert state["teams_send_failed_at"] == "2026/05/08 12:35:10"
    assert state["teams_send_error_message"] == "送信失敗: denied"
    assert state["teams_send_requested"] is False
    assert state["teams_send_requested_body_hash"] == ""
    assert state["teams_send_in_progress"] is False
    assert state["teams_send_in_progress_body_hash"] == ""
    assert app._teams_last_send_failed(state, form) is True


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
        "memo_after_widget": "old memo",
        "_memo_after_widget_synced": "old memo",
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
    assert "memo_after_widget" not in state
    assert "_memo_after_widget_synced" not in state
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
    assert 'value=form.get("product_price", "")' in panel_source
    assert 'current_manufacturer = form.get("manufacturer", "")' in panel_source
    assert 'value=form.get("store_name", "")' in panel_source


def test_case_basic_fields_do_not_show_required_optional_badges():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    panel_index = source.index("def render_shared_case_basic_editor")
    panel_end = source.index("def render_global_case_basic_panel", panel_index)
    panel_source = source[panel_index:panel_end]

    assert "required-badge" not in panel_source
    assert "optional-badge" not in panel_source
    assert "conditional-badge" not in panel_source
    assert "render_field_label(" not in panel_source
    assert 'st.selectbox(\n            "回線名"' in panel_source
    assert 'st.text_input(\n            "商品価格"' in panel_source


def test_hearing_choice_text_uses_supplemental_input_labels():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    helper_index = source.index("def _choice_text_hearing_value")
    helper_end = source.index("def render_call_hearing_inputs", helper_index)
    helper_source = source[helper_index:helper_end]
    hearing_index = source.index("def render_call_hearing_inputs")
    hearing_end = source.index("def render_now_action_item", hearing_index)
    hearing_source = source[hearing_index:hearing_end]

    assert "発生時期（任意入力）" not in source
    assert "発生頻度（任意入力）" not in source
    assert "wrt-sub-input-label" in source
    assert "wrt-sub-input-help" in source
    assert '"補足入力"' in helper_source
    assert "選択肢で表せない場合のみ入力してください。" in helper_source
    assert 'label_visibility="collapsed"' in helper_source
    assert 'placeholder="例：2〜3日前から"' in hearing_source
    assert 'placeholder="例：朝だけ、使用中だけ"' in hearing_source


def test_case_basic_product_price_is_editable_in_common_basic_panel():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    panel_index = source.index("def render_shared_case_basic_editor")
    panel_end = source.index("def render_global_case_basic_panel", panel_index)
    panel_source = source[panel_index:panel_end]
    aux_index = source.index("with st.expander(\"補助情報を開く\"")
    aux_source = source[aux_index:source.index("sync_hearing_widget_state_to_form(form)", aux_index)]

    assert 'form["product_price"] = st.text_input(' in panel_source
    assert 'case_basic_widget_key("product_price", revision)' in panel_source
    assert '"product_price": "case_basic_product_price"' in source
    assert "商品価格は「案件基本（共通）」で編集します。" in aux_source


def test_global_case_basic_stale_blank_widget_does_not_overwrite_form():
    form = app.empty_form()
    form.update({
        "product": "食器洗い乾燥機",
        "manufacturer": "三菱電機",
        "store_name": "ライフデザイン・カバヤ株式会社",
        "product_price": "36,300円",
    })
    revision = 0
    state = SessionState({
        "case_basic_revision": revision,
        app.case_basic_widget_key("product", revision): "",
        app.case_basic_widget_key("manufacturer", revision): "",
        app.case_basic_widget_key("store_name", revision): "",
        app.case_basic_widget_key("product_price", revision): "",
    })

    synced = app.sync_global_case_basic_widget_state(form, state)

    assert synced["product"] == "食器洗い乾燥機"
    assert synced["manufacturer"] == "三菱電機"
    assert synced["store_name"] == "ライフデザイン・カバヤ株式会社"
    assert synced["product_price"] == "36,300円"
    assert state[app.case_basic_widget_key("product", revision)] == "食器洗い乾燥機"
    assert state[app.case_basic_widget_key("manufacturer", revision)] == "三菱電機"
    assert state[app.case_basic_widget_key("store_name", revision)] == "ライフデザイン・カバヤ株式会社"
    assert state[app.case_basic_widget_key("product_price", revision)] == "36,300円"


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
    assert "【修理受付済み】" in texts["rakutel_text"]
    assert "【修理受付】" not in texts["rakutel_text"]
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
    assert "加入者⇒MPG大濱" in text


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
    assert "【家電回線に架電】" not in text
    assert "MPG大濱⇒加入者" in text


def test_rakutel_text_reflects_store_counterparty_detail_contact_and_missing_time():
    form = app.empty_form()
    form.update({
        "operator_name": "大濱",
        "call_line": "家電",
        "extracted_time": "2026/5/23",
        "call_direction": "受電",
        "counterparty_type": "販売店",
        "counterparty_detail": "あかりと空調の専門店 山田様",
        "contact_phone": "072-950-0880　5/26 12時以降",
    })

    text = app._build_rakutel_text(form, "販売店", "")

    assert "【家電回線に入電】" in text
    assert "2026/5/23 ●●：●●　販売店（あかりと空調の専門店 山田様）⇒MPG大濱" in text
    assert "日程調整時の連絡先：072-950-0880　5/26 12時以降" in text
    assert "販売店⇒MPG大濱" not in text


def test_rakutel_text_prefers_form_counterparty_over_legacy_caller_type_argument():
    form = app.empty_form()
    form.update({
        "operator_name": "大濱",
        "call_line": "家電",
        "call_direction": "受電",
        "counterparty_type": "販売店",
        "caller_type": "販売店",
    })

    text = app._build_rakutel_text(form, "加入者", "")

    assert "販売店⇒MPG大濱" in text
    assert "加入者⇒MPG大濱" not in text


def test_rakutel_action_input_sync_updates_form_before_generation():
    form = app.empty_form()
    state = SessionState({
        "case_basic_revision": 0,
        app.case_basic_widget_key("call_line", 0): "家電",
        "call_direction_select": "架電",
        "counterparty_type_select": "販売店",
        "counterparty_detail_input": "あかりと空調の専門店 山田様",
        "contact_phone_input": "072-950-0880　5/26 12時以降",
        "operator_name_input": "大濱",
    })

    synced = app.sync_after_call_rakutel_action_inputs(form, state)
    text = app._build_rakutel_text(synced, "加入者", "")

    assert synced["call_line"] == "家電"
    assert synced["call_direction"] == "架電"
    assert synced["counterparty_type"] == "販売店"
    assert "【家電回線から架電】" in text
    assert "MPG大濱⇒販売店（あかりと空調の専門店 山田様）" in text
    assert "日程調整時の連絡先：072-950-0880　5/26 12時以降" in text


def test_rakutel_text_missing_datetime_uses_placeholder_time_without_current_time():
    form = app.empty_form()
    form.update({
        "operator_name": "大濱",
        "call_line": "家電",
        "call_direction": "受電",
        "counterparty_type": "販売店",
    })

    text = app._build_rakutel_text(form, "販売店", "")

    assert "●●：●●　販売店⇒MPG大濱" in text


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
    teams_index = source.index("##### 💬 Teams報告文")
    send_button_index = source.index('st.button("Teamsチャットへ送信"', teams_index)
    teams_area = source[teams_index:send_button_index]

    assert "Google Drive を開く" not in teams_area
    assert "依頼書PDF格納先" not in teams_area


def test_teams_auto_send_panel_heading_exists():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert "###### Teams送信" in source
    assert "送信前チェックと送信状態" in source


def test_teams_report_and_send_have_separate_headings():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    report_index = source.index("##### 💬 Teams報告文")
    send_index = source.index("###### Teams送信")

    assert report_index < send_index


def test_teams_auto_send_heading_is_not_duplicated():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]

    assert after_source.count("Teams自動送信") == 1  # validation warning text only
    assert "##### 💬 Teams自動送信" not in after_source
    assert "##### 🚀 Teams送信" not in after_source
    assert "##### 🚀 Teams自動送信" not in after_source


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
    assert 'st.caption(f"自動判定：{auto_teams_action_display}")' in source
    assert "自動判定と異なる場合のみ変更" in source
    assert '"Teams報告アクション（手入力優先）"' not in source


def test_teams_send_panel_status_labels_exist():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert "送信不可" in source
    assert "送信可能" in source
    assert "送信済み" in source
    assert "送信失敗" in source


def test_teams_send_success_ui_hides_normal_primary_send_button():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]

    already_sent_index = after_source.index("if already_sent:")
    sent_button_index = after_source.index('st.button("送信済み"', already_sent_index)
    resend_button_index = after_source.index('st.button("同じ内容を再送する"', sent_button_index)
    normal_button_index = after_source.index('st.button("Teamsチャットへ送信"', resend_button_index)

    assert "Teamsへ送信しました。" in after_source
    assert "送信済み本文（確認用）" in after_source
    assert sent_button_index < resend_button_index < normal_button_index
    assert 'type="primary"' not in after_source[sent_button_index:resend_button_index]


def test_teams_send_in_progress_ui_hides_normal_primary_send_button():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]

    status_index = after_source.index('send_status == "送信処理中"')
    in_progress_index = after_source.index("if in_progress:", status_index)
    message_index = after_source.index("Teamsへ送信しています。完了まで画面を閉じないでください。", in_progress_index)
    disabled_button_index = after_source.index('st.button("送信処理中..."', message_index)
    normal_button_index = after_source.index('st.button("Teamsチャットへ送信"', disabled_button_index)

    assert "teams_send_in_progress_body_hash" in source
    assert "teams_send_requested_body_hash" in source
    assert "Teamsへ送信中です... Microsoft Graph / PowerShell の応答待ちです。" in after_source
    assert disabled_button_index < normal_button_index
    assert 'type="primary"' not in after_source[disabled_button_index:normal_button_index]


def test_teams_send_incomplete_ui_hides_normal_primary_send_button():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]

    sent_branch_index = after_source.index("elif already_sent:")
    incomplete_branch_index = after_source.index("elif incomplete_reasons:", sent_branch_index)
    disabled_button_index = after_source.index('st.button("未完了項目があります"', incomplete_branch_index)
    normal_button_index = after_source.index('st.button("Teamsチャットへ送信"', disabled_button_index)

    assert incomplete_branch_index < disabled_button_index < normal_button_index
    assert 'type="primary"' not in after_source[disabled_button_index:normal_button_index]


def test_teams_send_failure_ui_keeps_error_and_normal_send_button():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]

    failure_index = after_source.index('send_status == "送信失敗"')
    error_index = after_source.index("Teams送信に失敗しました：", failure_index)
    normal_button_index = after_source.index('st.button("Teamsチャットへ送信"', error_index)

    assert failure_index < error_index < normal_button_index
    assert "_mark_teams_message_send_failed" in after_source


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
    assert result["message_id"] == "message-001"


def test_send_teams_message_uses_chat_id_and_message_file_arguments(monkeypatch, tmp_path):
    config_path = tmp_path / "teams_config.json"
    script_path = tmp_path / "send_teams_message.ps1"
    write_config(config_path, chat_id="chat-456")
    script_path.write_text("# test script", encoding="utf-8")
    monkeypatch.setattr(app, "TEAMS_CONFIG_PATH", str(config_path))
    monkeypatch.setattr(app, "TEAMS_SEND_SCRIPT_PATH", str(script_path))

    def fake_run(args, capture_output, text, timeout):
        assert args[:5] == ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
        assert args[5] == str(script_path)
        assert args[6:9] == ["-ChatId", "chat-456", "-MessageFile"]
        assert Path(args[9]).read_text(encoding="utf-8") == "hello teams"
        return SimpleNamespace(returncode=0, stdout="SUCCESS message-001\n", stderr="")

    monkeypatch.setattr(app.subprocess, "run", fake_run)

    result = app.send_teams_message_via_powershell("hello teams")

    assert result["ok"] is True


def test_send_teams_message_blocks_unsupported_send_mode(monkeypatch, tmp_path):
    config_path = tmp_path / "teams_config.json"
    script_path = tmp_path / "send_teams_message.ps1"
    write_config(config_path, send_mode="unsupported")
    script_path.write_text("# test script", encoding="utf-8")
    monkeypatch.setattr(app, "TEAMS_CONFIG_PATH", str(config_path))
    monkeypatch.setattr(app, "TEAMS_SEND_SCRIPT_PATH", str(script_path))

    def fail_run(*args, **kwargs):
        raise AssertionError("subprocess.run should not be called")

    monkeypatch.setattr(app.subprocess, "run", fail_run)

    result = app.send_teams_message_via_powershell("hello teams")

    assert result["ok"] is False
    assert "send_mode は powershell_graph" in result["message"]


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


def test_send_teams_message_script_documents_graph_contract():
    source = (ROOT / "scripts" / "send_teams_message.ps1").read_text(encoding="utf-8")

    assert "[string]$ChatId" in source
    assert "[string]$MessageFile" in source
    assert "Get-Content -LiteralPath $MessageFile -Raw -Encoding UTF8" in source
    assert "Import-Module Microsoft.Graph.Authentication" in source
    assert "Import-Module Microsoft.Graph.Teams" in source
    assert 'Connect-MgGraph -Scopes "ChatMessage.Send"' in source
    assert "New-MgChatMessage -ChatId $ChatId -BodyParameter $bodyParameter" in source
    assert 'Write-Output ("SUCCESS " + $message.Id)' in source
    assert "exit 0" in source
    assert 'Write-Output ("ERROR " + $_.Exception.Message)' in source
    assert "exit 1" in source


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
    teams_heading_index = source.index("##### 💬 Teams報告文", rakutel_heading_index)

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
        'case_basic_widget_key("product_price", revision)',
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

    for field in ["call_line", "appliance_type", "product", "manufacturer", "store_name", "product_price"]:
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


def test_after_call_template_auto_and_candidate_display_exists():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]

    assert "**テンプレート：**" in after_source
    assert "**修理拠点：**" in after_source
    assert after_source.index("**テンプレート：**") < after_source.index("**修理拠点：**")
    assert "summary[\"template_reason\"]" in after_source
    assert "summary[\"vendor_reason\"]" in after_source
    assert after_source.index("summary[\"template_reason\"]") < after_source.index("summary[\"vendor_reason\"]")
    assert "理由：" in after_source
    assert '"テンプレートを選択"' in after_source
    assert "selected_option_val = st.selectbox(" in after_source
    assert "候補テンプレートの詳細を見る" in after_source
    assert "選択可能テンプレート：" in after_source
    assert after_source.index("候補テンプレートの詳細を見る") < after_source.index("選択可能テンプレート：")
    assert "修理依頼書メモは 0009 【出張修理】自然故障テンプレートから生成されます。" in after_source


def test_after_call_template_selection_is_not_blocked_by_unconfirmed_vendor():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]
    detail_source = after_source[
        after_source.index("送付テンプレート・拠点の詳細を開く"):
        after_source.index("修理拠点・手配詳細を開く")
    ]

    assert "テンプレートは選択可能です。修理拠点は別途確認してください。" in after_source
    assert "テンプレート候補がありません。回線名・製品・保証種別を確認してください。" in after_source
    assert "if not df_tpl.empty:" in detail_source
    assert 'if (call_line_val or template_selection.get("label"))' not in detail_source
    assert "disabled=True" not in detail_source


def test_after_call_template_and_vendor_reasons_are_separated_for_ai_koumuten():
    form = app.empty_form()
    form.update({
        "product": "システムキッチン",
        "series": "システムキッチン",
        "manufacturer": "パナソニック",
        "prefecture": "滋賀県",
        "appliance_type": "家電",
        "store_name": "滋賀支店",
        "store_original": "株式会社アイ工務店",
        "warranty_plan": "アイ工務店_住宅設備機器【10年保証】",
        "genre": "(新品)住宅設備機器",
        "category": "システムキッチン",
    })
    decision = app.run_decision(form)
    selected = app.select_template_for_form(
        form,
        decision["repair_type"],
        form["warranty_plan"],
        app.load_template_codes(),
    )
    summary = app.build_after_call_template_vendor_summary(form, decision, selected)

    assert summary["template"] == "0058 【出張修理】上位5社"
    assert summary["template_reason"] == "アイ工務店 上位5社テンプレート対象"
    assert summary["template_source_label"] == "運営会社"
    assert summary["template_source_value"] == "株式会社アイ工務店"
    assert summary["display_store"] == "滋賀支店"
    assert summary["vendor"] == "ユナイトサービス㈱"
    assert summary["vendor_reason"] == "依頼先一覧 No.7 上記以外・全国・全メーカー"
    assert "アイ工務店上位5社案件はユナイトサービスへ依頼" not in str(summary)


def test_ai_koumuten_teams_regeneration_uses_current_unite_vendor_not_stale_escalation():
    form = app.empty_form()
    form.update({
        "product": "システムキッチン",
        "series": "システムキッチン",
        "manufacturer": "パナソニック",
        "prefecture": "滋賀県",
        "appliance_type": "家電",
        "store_name": "滋賀支店",
        "store_original": "株式会社アイ工務店",
        "warranty_plan": "アイ工務店_住宅設備機器【10年保証】",
        "genre": "(新品)住宅設備機器",
        "category": "システムキッチン",
        "operator_name": "大濱",
        "rakuteru_no": "2026_05_0490",
        "teams_action": "担当確認依頼済み",
        "teams_chat_message": "担当エスカ（要確認）へ担当確認依頼済み\nご確認お願いします。大濱",
    })
    decision = app.run_decision(form)
    generation_form = app.form_for_current_teams_generation(
        form,
        decision["vendor"],
        decision["vendor_result"].get("contact_type", ""),
    )
    message = app._build_teams_chat_message(
        generation_form,
        decision["vendor"],
        decision["vendor_result"].get("contact_type", ""),
    )

    assert "ユナイトサービス㈱" in message
    assert "ユナイトサービス㈱へFAX済み" in message
    assert message == "\n".join([
        "2026_05_0490",
        "システムキッチン",
        "ユナイトサービス㈱へFAX済み",
        "ご確認お願いします。大濱",
    ])
    assert "担当エスカ（要確認）" not in message
    assert "担当確認依頼済み" not in message


def test_teams_send_preview_uses_current_teams_chat_message():
    message = "\n".join([
        "2026_05_0490",
        "住設",
        "システムキッチン",
        "ユナイトサービス㈱へFAX済み",
        "ご確認お願いします。大濱",
    ])

    preview = app.build_teams_send_preview_lines(message, "2026_05_0490")

    assert preview == [
        "楽テルNO：2026_05_0490",
        "回線：住設",
        "製品：システムキッチン",
        "対応：ユナイトサービス㈱へFAX済み",
        "確認文：ご確認お願いします。大濱",
    ]


def test_teams_send_preview_does_not_shift_when_rakuteru_no_is_blank():
    message = "\n".join([
        "住設",
        "エコキュート",
        "ユナイトサービス㈱へFAX済み",
        "ご確認お願いします。大濱",
    ])

    preview = app.build_teams_send_preview_lines(message, "")

    assert preview == [
        "楽テルNO：未入力",
        "回線：住設",
        "製品：エコキュート",
        "対応：ユナイトサービス㈱へFAX済み",
        "確認文：ご確認お願いします。大濱",
    ]


def test_teams_send_preview_keeps_rakuteru_no_from_field_even_if_message_has_no_rakuteru_line():
    message = "\n".join([
        "住設",
        "エコキュート",
        "ユナイトサービス㈱へFAX済み",
        "ご確認お願いします。大濱",
    ])

    preview = app.build_teams_send_preview_lines(message, "2026_05_0664")

    assert preview == [
        "楽テルNO：2026_05_0664",
        "回線：住設",
        "製品：エコキュート",
        "対応：ユナイトサービス㈱へFAX済み",
        "確認文：ご確認お願いします。大濱",
    ]


def test_ai_koumuten_0058_memo_estimated_fee_has_no_body_emoji():
    form = app.empty_form()
    form.update({
        "template_code": "0058",
        "template_label": "【出張修理】上位5社",
        "product": "システムキッチン",
        "manufacturer": "パナソニック",
        "warranty_plan": "アイ工務店_住宅設備機器【10年保証】",
    })
    memo = app._build_after_call_memo(
        form,
        {"title": "保証期間内"},
        "出張修理",
        "ユナイトサービス㈱",
        cost_estimate="5,000円～7,000円前後",
    )

    assert "※修理キャンセル時の概算費用5,000円～7,000円前後" in memo
    assert "※📋修理キャンセル時" not in memo


def test_repair_request_memo_sanitizes_stale_body_emoji_for_display_and_copy():
    dirty_memo = "具体的な症状：\n※📋修理キャンセル時の概算費用5,000円～7,000円前後"
    clean_memo = app.sanitize_generated_body_text(dirty_memo)

    assert clean_memo == "具体的な症状：\n※修理キャンセル時の概算費用5,000円～7,000円前後"

    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]
    memo_area = after_source[
        after_source.index('memo_display = st.text_area('):
        after_source.index("###### 追記候補")
    ]

    assert 'key=memo_widget_key' in memo_area
    assert '"memo_after_widget"' in after_source
    assert 'form["attention_memo"] = sanitize_generated_body_text(memo_display)' in memo_area
    assert 'render_copy_button("📋 コピー", sanitize_generated_body_text(form["attention_memo"]), "copy_attention_memo")' in memo_area


def test_unite_vendor_summary_uses_handoff_table_mail_and_contact():
    card = app.build_vendor_candidate_card_info(
        "ユナイトサービス㈱",
        {"reason": "依頼先一覧 No.7 上記以外・全国・全メーカー", "needs_escalation": False},
    )
    unknown = app.build_vendor_candidate_card_info(
        "未登録業者",
        {"reason": "", "needs_escalation": False},
    )

    assert card["arrangement_method"] == "メール依頼"
    assert card["contact"] == "担当確認"
    assert unknown["arrangement_method"] == ""


def test_confirmed_vendor_block_does_not_show_stale_escalation_candidate():
    card = app.build_vendor_candidate_card_info(
        "ユナイトサービス㈱",
        {"reason": "依頼先一覧 No.7 上記以外・全国・全メーカー", "needs_escalation": False},
    )
    block = app.format_confirmed_vendor_block("ユナイトサービス㈱", card)

    assert "修理拠点：" in block
    assert "ユナイトサービス㈱" in block
    assert "状態：確定" in block
    assert "手配方法：メール依頼" in block
    assert "連絡先：担当確認" in block
    assert "担当エスカ（要確認）" not in block
    assert "拠点候補：担当エスカ（要確認）" not in block


def test_after_call_history_template_keys_include_content_hash_to_avoid_stale_empty_display():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]

    assert 'key=f"history_after_{stable_hash_text(history_tmpl, 12)}"' in after_source
    assert 'key=f"history_display_{stable_hash_text(history_tmpl, 12)}"' in source


def test_after_call_display_uses_repair_request_memo_not_attention_memo():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]

    assert "注意内容メモ" not in after_source
    assert "##### 📝 修理依頼書メモ" in after_source
    assert "修理依頼書メモ 操作" in after_source
    assert 'st.button("再生成", key="regenerate_attention_memo")' in after_source
    assert 'render_copy_button("📋 コピー", sanitize_generated_body_text(form["attention_memo"]), "copy_attention_memo")' in after_source


def test_contact_phone_input_is_inside_rakutel_section_only():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]
    rakutel_heading = after_source.index("##### 📝 ラクテル用テキスト")
    teams_heading = after_source.index("##### 💬 Teams報告文")
    contact_index = after_source.index('"日程調整時の連絡先"')

    assert rakutel_heading < contact_index < teams_heading
    assert '"例：072-950-0880\u30005/26 12時以降"' in after_source
    assert '"相手名・担当者名（任意）"' in after_source


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
    assert 'key="regenerate_attention_memo"' in after_source
    assert 'key="regenerate_rakutel_text"' in after_source
    assert 'key="regenerate_teams_chat_message"' in after_source


def test_after_call_regeneration_buttons_are_independent():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]

    assert "ラクテル用・Teams用テキストを再生成" not in after_source
    attention_button = after_source.index('key="regenerate_attention_memo"')
    rakutel_button = after_source.index('key="regenerate_rakutel_text"')
    teams_button = after_source.index('key="regenerate_teams_chat_message"')
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
        after_source.index("###### 追記候補")
    ]
    memo_and_snippet_area = after_source[
        after_source.index('memo_display = st.text_area('):
        after_source.index("##### 📝 ラクテル用テキスト")
    ]
    rakutel_area = after_source[
        after_source.index('rakutel_text_display = st.text_area('):
        after_source.index("##### 💬 Teams報告文")
    ]
    teams_area = after_source[
        after_source.index('teams_chat_message = st.text_area('):
        after_source.index("###### Teams送信")
    ]

    assert "st.code(" not in memo_area
    assert "コピー用：修理依頼書メモ" not in memo_area
    assert 'render_copy_button("📋 コピー", sanitize_generated_body_text(form["attention_memo"]), "copy_attention_memo")' in memo_area
    assert memo_area.index('form["attention_memo"] = sanitize_generated_body_text(memo_display)') < memo_area.index("copy_attention_memo")
    assert memo_and_snippet_area.index("copy_attention_memo") < memo_and_snippet_area.index("###### 追記候補")

    assert "st.code(" not in rakutel_area
    assert "コピー用：ラクテル用テキスト" not in rakutel_area
    assert 'render_copy_button("📋 コピー", form["rakutel_text"], "copy_rakutel_text")' in rakutel_area
    assert rakutel_area.index('form["rakutel_text"] = rakutel_text_display') < rakutel_area.index("copy_rakutel_text")

    assert "st.code(" not in teams_area
    assert "コピー用：Teams報告文" not in teams_area
    assert "height=160" in teams_area
    assert "送信内容プレビュー：" in teams_area
    assert 'build_teams_send_preview_lines(teams_chat_message, form.get("rakuteru_no", ""))' in teams_area
    assert 'render_copy_button("📋 コピー", teams_chat_message, "copy_teams_chat_message")' in teams_area
    assert teams_area.index('form["teams_chat_message"] = teams_chat_message') < teams_area.index("copy_teams_chat_message")


def test_teams_copy_button_uses_plain_text_without_drive_url_source():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    teams_index = source.index("##### 💬 Teams報告文")
    teams_copy_index = source.index("render_copy_button", teams_index)
    copy_end_index = source.index("st.session_state.form = form", teams_copy_index)
    teams_copy_area = source[teams_copy_index:copy_end_index]

    assert 'render_copy_button("📋 コピー", teams_chat_message, "copy_teams_chat_message")' in teams_copy_area
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

    attention_regen = after_source.index('st.session_state[memo_widget_key] = form["attention_memo"]')
    attention_copy = after_source.index("copy_attention_memo")
    rakutel_regen = after_source.index('st.session_state["rakutel_text_display"] = form["rakutel_text"]')
    rakutel_copy = after_source.index("copy_rakutel_text")
    teams_regen = after_source.index('st.session_state["teams_chat_message_display"] = form["teams_chat_message"]')
    teams_copy = after_source.index("copy_teams_chat_message")

    assert attention_regen < attention_copy
    assert rakutel_regen < rakutel_copy
    assert teams_regen < teams_copy


def test_after_call_memo_widget_key_is_not_modified_after_text_area_instantiation():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    after_index = source.index("def render_tab_after_call")
    master_index = source.index("def render_tab_master", after_index)
    after_source = source[after_index:master_index]
    memo_area = after_source[
        after_source.index('memo_display = st.text_area('):
        after_source.index("##### 📝 ラクテル用テキスト")
    ]
    after_widget = memo_area[memo_area.index('memo_display = st.text_area('):]

    assert 'key="memo_after"' not in memo_area
    assert 'key=memo_widget_key' in memo_area
    assert 'st.session_state[memo_widget_key] =' not in after_widget
    assert 'st.session_state["memo_after_widget"] =' not in after_widget
    assert 'st.session_state["memo_after"] =' not in after_source


def test_push_bat_does_not_use_git_add_dot_and_pushes_origin_main():
    source = (ROOT / "Push.bat").read_text(encoding="utf-8")
    lines = [line.strip() for line in source.splitlines()]

    assert "git add ." not in lines
    assert "git add Push.bat" in lines
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


def test_teams_config_json_is_gitignored_and_not_tracked():
    gitignore_lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    tracked = subprocess.run(
        ["git", "ls-files", "--", "config/teams_config.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "config/teams_config.json" in gitignore_lines
    assert tracked.stdout.strip() == ""


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

    teams_heading_index = source.index("##### 💬 Teams報告文")
    # Search for the widget by its unique key, which only exists at the widget definition
    rakuteru_no_index = source.index('key="rakuteru_no_input"', teams_heading_index)
    text_area_index = source.index('teams_chat_message = st.text_area(', teams_heading_index)

    assert teams_heading_index < rakuteru_no_index < text_area_index


def test_teams_action_input_before_teams_regeneration_button():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    teams_heading_index = source.index("##### 💬 Teams報告文")
    teams_action_index = source.index('key="teams_action_input"', teams_heading_index)
    text_area_index = source.index('teams_chat_message = st.text_area(', teams_heading_index)

    assert teams_heading_index < teams_action_index < text_area_index


def test_rakuteru_no_not_in_template_col1():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    vendor_section_index = source.index("##### 🏭 修理拠点候補")
    teams_heading_index = source.index("##### 💬 Teams報告文")
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
