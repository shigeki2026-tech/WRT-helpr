# -*- coding: utf-8 -*-
"""修理受付 支援ツール MVP - app.py  (Phase2-2: 4-layer CSV decision)"""

import re
import os
import csv  # CSV読み込み改善
import json
import hashlib
import html
import subprocess
import tempfile
import shutil
import streamlit as st
from datetime import date, datetime
import pandas as pd

try:
    import pyperclip
    _PYPERCLIP_AVAILABLE = True
except ImportError:
    _PYPERCLIP_AVAILABLE = False

# ============================================================
# 定数
# ============================================================
APP_DIR = os.path.dirname(os.path.abspath(__file__))
TEAMS_CONFIG_PATH = os.path.join(APP_DIR, "config", "teams_config.json")
LOCAL_USER_SETTINGS_PATH = os.path.join(APP_DIR, "config", "local_user_settings.json")
TEAMS_SEND_SCRIPT_PATH = os.path.join(APP_DIR, "scripts", "send_teams_message.ps1")
TEAMS_SEND_LOG_PATH = os.path.join(APP_DIR, "logs", "teams_send_log.csv")
DEFAULT_TEAMS_CONFIG = {
    "enabled": False,
    "chat_id": "",
    "chat_name": "WRT報告用チャット",
    "send_mode": "powershell_graph",
    "warranty_enabled": True,
    "warranty_chat_id": "",
    "warranty_chat_name": "Teamsワランティ送信先チャット",
}
SUPPORTED_TEAMS_SEND_MODES = {"powershell_graph"}
REQUEST_PDF_FOLDERS = {
    "wrt": {
        "name": "WRT修理受付センター",
        "url": "https://drive.google.com/drive/folders/14EgcYq4JfgPRH4XA6rVUULSow8uyrGI7",
    },
    "cer": {
        "name": "CER",
        "url": "https://drive.google.com/drive/u/0/folders/1zatFuNMucZWxwGQkketgjicfngo_9wEP",
    },
}

PREFECTURES = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県",
    "岐阜県", "静岡県", "愛知県", "三重県",
    "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
    "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県",
    "福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]

FIELD_LABELS = {
    "operator_name": "オペレーター名",
    "call_type": "入電種別",
    "call_line": "回線名",
    "appliance_type": "案件分類",
    "appliance_category": "案件分類",
    "housing_phase": "住設区分",
    "prefecture": "都道府県",
    "address": "お客様住所",
    "product": "製品",
    "product_original": "製品メモ / 原文製品名",
    "series": "シリーズ",
    "manufacturer": "メーカー",
    "manufacturer_original": "メーカー原文 / コピー元メーカー名",
    "pc_manufacturer_type": "PCメーカー区分",
    "model_number": "型番",
    "call_memo": "通話中メモ",
    "occurrence_time": "発生時期",
    "occurrence_frequency": "発生頻度",
    "install_location": "設置場所",
    "other_repair_requested": "他窓口へ修理依頼済みか",
    "product_price": "商品価格",
    "warranty_plan": "保証プラン",
    "warranty_start_date": "保証開始日",
    "warranty_end_date": "保証終了日",
    "store_name": "販売店",
    "wrt_no": "WRT-NO",
    "customer_code": "お客様コード",
    "customer_name": "お客様名",
    "phone_number": "電話番号",
    "contact_phone": "日程調整時の連絡先",
    "caller_type": "発信者区分",
    "counterparty_detail": "相手名・担当者名",
    "warranty_report_content": "確認内容",
    "extracted_time": "入電時刻",
    "symptom": "症状",
    "symptom_detail": "具体的な症状",
    "maker_warranty_period": "メーカー保証期間",
    "install_type": "設置形態",
    "extra_condition": "補足条件",
    "is_over_10years": "製造10年以上",
    "template_code": "テンプレートコード",
    "template_label": "テンプレートラベル",
    "rakuteru_no": "楽テルNO",
}

DIAGNOSTIC_STATUS_ORDER = {"error": 0, "warning": 1, "ok": 2}
DIAGNOSTIC_IMPACT_ORDER = {
    "blocking": 0,
    "call_time_required": 1,
    "after_call_ok": 2,
    "info": 3,
}
DIAGNOSTIC_IMPACT_LABELS = {
    "blocking": "受付不可",
    "call_time_required": "通話中確認",
    "after_call_ok": "終話後確認",
    "info": "補足",
}
DIAGNOSTIC_AREA_ORDER = {
    "保証期間判定": 0,
    "概算費用判定": 1,
    "参照スクリプト判定": 2,
    "修理形態判定": 3,
    "修理拠点判定": 4,
}
DIAGNOSTIC_OVERALL_DISPLAY = {
    "ok": {
        "icon": "✅",
        "title": "判定診断：OK",
        "message": "主要判定は成立しています",
    },
    "warning": {
        "icon": "⚠️",
        "title": "判定診断：要確認あり",
        "message": "不足項目または確認事項があります",
    },
    "error": {
        "icon": "❌",
        "title": "判定診断：受付不可 / 重大確認あり",
        "message": "受付不可または重大な未確定項目があります",
    },
}


def field_label(field_name: str) -> str:
    """Internal field key -> operator-facing Japanese label."""
    return FIELD_LABELS.get(field_name, field_name)


def format_field_labels(field_names: list) -> str:
    """Join field keys after converting them to Japanese labels."""
    return "、".join(field_label(f) for f in field_names)


def field_anchor_id(field_name: str) -> str:
    return f"field-{field_name}"


def field_anchor_html(field_name: str) -> str:
    return f'<div id="{field_anchor_id(field_name)}"></div>'


def field_link(field_name: str, suffix: str = "欄へ移動") -> str:
    return f"[{field_label(field_name)}{suffix}](#{field_anchor_id(field_name)})"


def diagnostic_field_links(field_names: list) -> list:
    return [field_link(field_name) for field_name in field_names]


def render_copy_button(label: str, text: str, key: str):
    """Render a browser-side clipboard copy button for editable text."""
    text_json = json.dumps(text or "", ensure_ascii=False)
    label_json = json.dumps(label, ensure_ascii=False)
    key_json = json.dumps(key, ensure_ascii=False)
    st.components.v1.html(
        f"""
<div id="copy-root"></div>
<script>
const copyText = {text_json};
const copyLabel = {label_json};
const copyKey = {key_json};
const root = document.getElementById("copy-root");
root.innerHTML = "";

const button = document.createElement("button");
button.type = "button";
button.textContent = copyLabel;
button.disabled = !copyText;
button.setAttribute("data-copy-key", copyKey);
button.style.cssText = [
  "border:1px solid #d0d7de",
  "border-radius:6px",
  "background:#ffffff",
  "color:#24292f",
  "padding:0.42rem 0.75rem",
  "font-size:0.92rem",
  "line-height:1.2",
  "cursor:pointer"
].join(";");
if (!copyText) {{
  button.style.opacity = "0.55";
  button.style.cursor = "not-allowed";
}}

const status = document.createElement("span");
status.style.cssText = "margin-left:0.6rem;font-size:0.82rem;color:#57606a;";
status.textContent = copyText ? "" : "コピー対象がありません";

function fallbackCopy(value) {{
  const area = document.createElement("textarea");
  area.value = value;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.top = "-1000px";
  area.style.left = "-1000px";
  document.body.appendChild(area);
  area.focus();
  area.select();
  const ok = document.execCommand("copy");
  document.body.removeChild(area);
  if (!ok) {{
    throw new Error("copy command failed");
  }}
}}

button.addEventListener("click", async () => {{
  if (!copyText) {{
    status.textContent = "コピー対象がありません";
    return;
  }}
  try {{
    if (navigator.clipboard && window.isSecureContext) {{
      await navigator.clipboard.writeText(copyText);
    }} else {{
      fallbackCopy(copyText);
    }}
    status.textContent = "コピーしました";
  }} catch (error) {{
    try {{
      fallbackCopy(copyText);
      status.textContent = "コピーしました";
    }} catch (fallbackError) {{
      status.textContent = "コピーに失敗しました";
    }}
  }}
}});

root.appendChild(button);
root.appendChild(status);
</script>
        """,
        height=42,
    )


def sort_diagnostic_items(items: list) -> list:
    """Show business-impacting items first, then severity and stable area priority."""
    return sorted(
        items,
        key=lambda item: (
            DIAGNOSTIC_IMPACT_ORDER.get(item.get("impact", "info"), 99),
            DIAGNOSTIC_STATUS_ORDER.get(item.get("status", "ok"), 99),
            DIAGNOSTIC_AREA_ORDER.get(item.get("area", ""), 99),
        ),
    )


def diagnostic_history_status(item: dict) -> str:
    """Short status for the history template; details stay in the UI panel."""
    status = item.get("status")
    title = item.get("title", "")
    if status == "ok":
        return "OK"
    if status == "error":
        return "受付不可"
    if "未確定" in title:
        return "未確定"
    return "要確認"


def build_next_action_steps(diagnostics: dict) -> list[str]:
    """通話中に聞くべき next_action を impact 優先で重複なしに返す。"""
    steps: list[str] = []
    seen: set = set()
    for item in sort_diagnostic_items(diagnostics.get("items", [])):
        if item.get("impact") not in ("blocking", "call_time_required"):
            continue
        action = (item.get("next_action") or "").strip()
        if action and action not in seen:
            steps.append(action)
            seen.add(action)
    return steps


def build_after_call_steps(diagnostics: dict) -> list[str]:
    """終話後対応でよい next_action を重複なしに返す。"""
    steps: list[str] = []
    seen: set = set()
    for item in sort_diagnostic_items(diagnostics.get("items", [])):
        if item.get("impact") != "after_call_ok":
            continue
        action = (item.get("next_action") or "").strip()
        if action and action not in seen:
            steps.append(action)
            seen.add(action)
    return steps


def _append_unique_across(categories: dict, category: str, value: str, seen: set) -> None:
    value = (value or "").strip()
    if value and value not in seen:
        categories[category].append(value)
        seen.add(value)


def _split_required_question_text(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if "、" in text and not text.startswith("【"):
        return [part.strip() for part in text.split("、") if part.strip()]
    return [text]


def _split_pipe_items(text: str) -> list[str]:
    return [part.strip() for part in str(text or "").split("|") if part.strip()]


def _is_after_call_question(text: str) -> bool:
    return any(keyword in text for keyword in (
        "終話後", "担当へエスカレーション", "担当確認", "SV/担当確認",
        "拠点確定", "修理拠点確認", "Google Drive", "依頼書PDF格納",
    ))


def _is_supplemental_question(text: str) -> bool:
    if text == DOUBLE_PROTECT_AMOUNT_CONFIRMATION:
        return False
    return any(keyword in text for keyword in (
        "他窓口", "修理依頼済み", "データ消去", "事故状況", "破損状況",
    ))


HEARING_UNSELECTED = "未選択"
OCCURRENCE_TIME_OPTIONS = [HEARING_UNSELECTED, "本日", "昨日", "数日前", "1週間前", "購入直後", "不明"]
OCCURRENCE_FREQUENCY_OPTIONS = [HEARING_UNSELECTED, "継続中", "常時", "時々", "初回のみ", "再発", "特定条件で発生", "不明"]

_SELECT_WITH_OTHER_OPTIONS: dict[str, list[str]] = {
    "occurrence_time": OCCURRENCE_TIME_OPTIONS,
    "occurrence_frequency": OCCURRENCE_FREQUENCY_OPTIONS,
}

CHECK_ITEM_DEFINITIONS = {
    "症状の詳細": {
        "id": "symptom_detail",
        "fields": ("symptom_detail",),
        "input": "textarea",
        "label": "具体的な症状",
        "input_label": "具体的な症状",
    },
    "発生時期": {
        "id": "occurrence_time",
        "fields": ("occurrence_time",),
        "input": "hearing_choice_text",
        "label": "発生時期",
    },
    "発生頻度": {
        "id": "occurrence_frequency",
        "fields": ("occurrence_frequency",),
        "input": "hearing_choice_text",
        "label": "発生頻度",
    },
    "設置場所": {
        "id": "install_location",
        "fields": ("install_location", "install_type"),
        "input": "text",
        "label": "設置場所",
    },
    "訪問先住所": {
        "id": "visit_address",
        "fields": ("address",),
        "input": "address_with_check",
        "label": "訪問先住所",
    },
    "訪問先住所確認済みチェック": {
        "id": "visit_address",
        "fields": ("address",),
        "input": "address_with_check",
        "label": "訪問先住所",
    },
    "他窓口へ修理依頼済みか": {
        "id": "other_repair_requested",
        "fields": ("other_repair_requested",),
        "input": "select_other_repair_requested",
        "label": "他窓口へ修理依頼済みか",
    },
    "【物損付/DP】物損時の保証金額をシステムで確認": {
        "id": "double_protect_amount",
        "fields": (),
        "input": "manual",
        "label": "【物損付/DP】物損時の保証金額をシステムで確認",
    },
}


def stable_hash_text(text: str, length: int = 8) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:length]


def _check_item_definition(label: str) -> dict:
    clean = (label or "").strip()
    if clean in CHECK_ITEM_DEFINITIONS:
        return CHECK_ITEM_DEFINITIONS[clean]
    for key, definition in CHECK_ITEM_DEFINITIONS.items():
        if key and key in clean:
            return {**definition, "label": clean}
    item_id = re.sub(r"[^0-9A-Za-z_]+", "_", clean).strip("_") or "manual_item"
    return {"id": f"manual_{item_id}_{stable_hash_text(clean)}", "fields": (), "input": "manual", "label": clean}


def _manual_check_done(manual_check: dict | None, item_id: str) -> bool:
    return bool((manual_check or {}).get(item_id))


def _form_field_done(form: dict, field: str) -> bool:
    if field in ("occurrence_time", "occurrence_frequency"):
        return bool(get_hearing_value(form, field))
    value = form.get(field)
    if field == "other_repair_requested":
        return str(value or "").strip() in ("なし", "あり")
    if isinstance(value, bool):
        return value
    return bool(str(value or "").strip())


def build_check_item(label: str, form: dict, manual_check: dict | None = None,
                     source: str = "") -> dict:
    definition = _check_item_definition(label)
    item_id = definition["id"]
    fields = tuple(definition.get("fields") or ())
    field_done = any(_form_field_done(form, field) for field in fields)
    manual_done = _manual_check_done(manual_check, item_id)
    return {
        "id": item_id,
        "label": definition.get("label") or label,
        "input_label": definition.get("input_label") or definition.get("label") or label,
        "fields": fields,
        "input": definition.get("input", "manual"),
        "done": bool(field_done or manual_done),
        "source": source,
    }


def build_question_categories(form: dict, repair_type: str, needs_data_erase: bool,
                              diagnostics: dict | None = None,
                              warranty_result: dict | None = None,
                              cost_result: dict | None = None,
                              manual_check: dict | None = None,
                              guidance_items: list[str] | None = None) -> dict:
    """通話中の確認項目を、通話中必須 / 終話後 / 補足に重複なしで分類する。"""
    diagnostics = diagnostics or {}
    warranty_result = warranty_result or {}
    cost_result = cost_result or {}
    categories = {"call_required": [], "after_call": [], "completed": []}
    seen: set = set()
    completed_seen: set = set()

    def _add_call_item(label: str, source: str) -> None:
        item = build_check_item(label, form, manual_check, source)
        if item["label"] in seen or item["label"] in completed_seen:
            return
        target = categories["completed"] if item["done"] else categories["call_required"]
        target_seen = completed_seen if item["done"] else seen
        target.append(item)
        target_seen.add(item["label"])

    for field in ("appliance_type", "product", "manufacturer"):
        if not (form.get(field) or "").strip():
            _add_call_item(field_label(field), "未入力項目")

    for guidance_item in guidance_items or []:
        _add_call_item(guidance_item, "スクリプト補助")

    req_questions = build_required_questions(form, repair_type, needs_data_erase)
    if warranty_result.get("warranty_status") == "before_start":
        req_questions.insert(0, "メーカー保証期間を確認")
        req_questions.insert(1, "メーカーまたは販売店窓口への誘導")
    elif warranty_result.get("warranty_status") == "unknown":
        req_questions.insert(0, "保証開始日・保証終了日を確認")
    elif warranty_result.get("warranty_status") == "expired":
        req_questions.insert(0, "受付不可。保証期間終了後であることを案内")
    if cost_result.get("cost_status") == "pending":
        cost_rq = (cost_result.get("required_questions") or "").strip()
        if cost_rq:
            req_questions.insert(0, f"【費用確定のため必須】{cost_rq}")

    for question in req_questions:
        for part in _split_required_question_text(question):
            if _is_after_call_question(part):
                bucket = "after_call"
            elif _is_supplemental_question(part):
                bucket = "call_required"
            else:
                bucket = "call_required"
            if bucket == "after_call":
                _append_unique_across(categories, "after_call", part, seen)
            else:
                _add_call_item(part, "確認項目")

    for item in sort_diagnostic_items(diagnostics.get("items", [])):
        for field in item.get("missing_fields", []) or []:
            bucket = "after_call" if item.get("impact") == "after_call_ok" else "call_required"
            if bucket == "after_call":
                _append_unique_across(categories, bucket, field_label(field), seen)
            else:
                _add_call_item(field_label(field), item.get("area", "判定診断"))
        action = (item.get("next_action") or "").strip()
        if item.get("impact") == "after_call_ok":
            _append_unique_across(categories, "after_call", action, seen)
        elif item.get("impact") in ("blocking", "call_time_required"):
            _add_call_item(action, item.get("area", "判定診断"))

    return categories


def build_now_action_plan(form: dict, repair_type: str, needs_data_erase: bool,
                          diagnostics: dict | None = None,
                          warranty_result: dict | None = None,
                          cost_result: dict | None = None,
                          manual_check: dict | None = None,
                          guidance_items: list[str] | None = None) -> dict:
    """最上部の「今やること」パネルに出す内容を返す。"""
    categories = build_question_categories(
        form, repair_type, needs_data_erase, diagnostics, warranty_result, cost_result,
        manual_check, guidance_items,
    )
    return {
        "call_required": categories["call_required"],
        "after_call": categories["after_call"],
        "completed": categories["completed"],
    }


HEARING_SUMMARY_FIELDS = [
    ("symptom_detail", "具体的な症状"),
    ("occurrence_time", "発生時期"),
    ("occurrence_frequency", "発生頻度"),
    ("install_location", "設置場所"),
    ("address", "訪問先住所"),
]
HEARING_INPUT_FIELD_IDS = {"symptom_detail", "occurrence_time", "occurrence_frequency"}
HEARING_INPUT_PROMPTS = {
    "symptom_detail": "具体的な症状を入力してください",
    "occurrence_time": "発生時期を選択してください",
    "occurrence_frequency": "発生頻度を選択してください",
}


def _resolve_choice_text_value(choice: str = "", text: str = "") -> str:
    typed = str(text or "").strip()
    selected = str(choice or "").strip()
    if typed:
        return typed
    if selected and selected != HEARING_UNSELECTED:
        return selected
    return ""


def get_hearing_value(form: dict, field_name: str) -> str:
    if field_name == "symptom_detail":
        return str(form.get("symptom_detail") or "").strip()
    if field_name in ("occurrence_time", "occurrence_frequency"):
        choice = form.get(f"{field_name}_choice", "")
        text = form.get(f"{field_name}_text", "")
        resolved = _resolve_choice_text_value(choice, text)
        if resolved:
            return resolved
    return str(form.get(field_name) or "").strip()


def resolve_occurrence_time(form: dict) -> str:
    return get_hearing_value(form, "occurrence_time")


def resolve_occurrence_frequency(form: dict) -> str:
    return get_hearing_value(form, "occurrence_frequency")


def sync_hearing_widget_state_to_form(form: dict, session_state=None) -> dict:
    state = session_state if session_state is not None else st.session_state
    if "call_hearing_symptom_detail" in state:
        form["symptom_detail"] = str(state.get("call_hearing_symptom_detail") or "")
    for field_name in ("occurrence_time", "occurrence_frequency"):
        choice_key = f"call_hearing_{field_name}_choice"
        text_key = f"call_hearing_{field_name}_text"
        if choice_key in state:
            form[f"{field_name}_choice"] = str(state.get(choice_key) or "")
        if text_key in state:
            form[f"{field_name}_text"] = str(state.get(text_key) or "")
        if choice_key in state or text_key in state:
            form[field_name] = get_hearing_value(form, field_name)
    return form


def _display_value_for_fields(form: dict, fields: tuple[str, ...]) -> str:
    values = []
    for field in fields:
        value = get_hearing_value(form, field) if field in HEARING_INPUT_FIELD_IDS else str(form.get(field) or "").strip()
        if value:
            values.append(value)
    return " / ".join(values)


def format_completed_check_item(item: dict, form: dict) -> str:
    label = item.get("label") or ""
    value = _display_value_for_fields(form, tuple(item.get("fields") or ()))
    if value:
        return f"{label}：{value}"
    if item.get("done"):
        return f"{label}：確認済み"
    return label


def build_hearing_summary_lines(form: dict) -> list[str]:
    return [
        f"{label}：{get_hearing_value(form, field) if field in HEARING_INPUT_FIELD_IDS else str(form.get(field) or '').strip()}"
        for field, label in HEARING_SUMMARY_FIELDS
    ]


def build_attention_memo_preview_lines(form: dict) -> list[str]:
    return [
        sanitize_generated_body_text(
            f"{label}：{get_hearing_value(form, field) if field in HEARING_INPUT_FIELD_IDS else str(form.get(field) or '').strip()}"
        )
        for field, label in HEARING_SUMMARY_FIELDS[:3]
    ]

def build_other_repair_requested_warning(form: dict) -> dict:
    if (form.get("other_repair_requested") or "").strip() != "あり":
        return {}
    return {
        "title": "⚠️ 他窓口へ修理依頼済み",
        "reason": "重複受付・重複手配の可能性があります",
        "next_action": "受付可否または対応継続可否をSV/担当に確認",
    }


# 国内PCメーカー判定グループ
DOMESTIC_PC_MAKERS = {
    "パナソニック", "シャープ", "富士通", "東芝", "日立", "ソニー", "NEC", "VAIO",
}
PC_MANUFACTURER_TYPE_UNKNOWN = "未確認"
PC_MANUFACTURER_TYPE_DOMESTIC = "国内メーカー"
PC_MANUFACTURER_TYPE_FOREIGN = "海外メーカー"
PC_MANUFACTURER_TYPE_OPTIONS = [
    PC_MANUFACTURER_TYPE_UNKNOWN,
    PC_MANUFACTURER_TYPE_DOMESTIC,
    PC_MANUFACTURER_TYPE_FOREIGN,
]

# manufacturer_group 名 → メーカーセット のマッピング
MANUFACTURER_GROUPS: dict = {
    "国内PC": DOMESTIC_PC_MAKERS,
}

# エリアグループ → 都道府県セット のマッピング
AREA_GROUPS: dict = {
    "九州":  {"福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県"},
    "東北":  {"青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県"},
    "関東":  {"東京都", "神奈川県", "埼玉県", "千葉県", "茨城県", "栃木県", "群馬県"},
    "近畿":  {"大阪府", "兵庫県", "京都府", "滋賀県", "奈良県", "和歌山県"},
    "中国":  {"鳥取県", "島根県", "岡山県", "広島県", "山口県"},
    "四国":  {"徳島県", "香川県", "愛媛県", "高知県"},
    "北海道": {"北海道"},
    "沖縄":  {"沖縄県"},
}

# ── CSV 必須列定義 ──
_ALIAS_COLS        = ["priority", "enabled", "keyword", "normalized_product", "product_group", "notes"]
_REPAIR_TYPE_COLS  = [
    "priority", "enabled", "product_keyword", "manufacturer_keyword",
    "model_keyword", "condition_keyword", "repair_type",
    "manufacturer_required", "model_required", "manual_required",
    "needs_confirmation", "notes",
    "certainty", "reason", "memo_note", "rakutel_repair_type_override", "active",
]
_COST_COLS         = ["priority", "enabled", "product_keyword", "manufacturer_keyword",
                      "manufacturer_group", "condition_keyword", "repair_type",
                      "cost_estimate", "can_announce_cost", "needs_escalation",
                      "required_fields", "cost_status", "guidance_scope",
                      "required_questions", "customer_notice", "internal_note", "notes"]
_MFR_GROUP_COLS    = ["group_name", "manufacturers", "notes"]
_AREA_GROUP_COLS   = ["area_group", "prefectures", "notes"]
_SCRIPT_LINK_COLS   = ["script_sheet", "script_part", "display_name", "url", "notes"]
_SCRIPT_ROUTE_COLS = [
    "priority", "enabled", "script_key", "display_name", "site_section", "url",
    "match_line", "match_kaden_jusetsu", "match_plan_keywords",
    "match_store_keywords", "match_company_keywords", "match_product_keywords",
    "match_repair_type", "confidence", "memo", "source_cell",
]
_SCRIPT_GUIDANCE_COLS = [
    "priority", "enabled", "script_key", "repair_type", "appliance_type",
    "product_keyword", "manufacturer_keyword", "title", "hearing_items",
    "notes", "official_script_label", "official_script_url",
]
_VENDOR_COLS       = ["priority", "enabled", "call_line", "prefecture", "area_group",
                      "manufacturer_keyword", "product_keyword", "store_keyword",
                      "repair_type", "is_over_10years", "vendor_name", "reason",
                      "needs_escalation", "notes", "contact_type"]
_TEMPLATE_CODE_COLS = [
    "priority", "enabled", "template_code", "category",
    "label", "data_erase_required", "cost_guidance_allowed", "notes"
]
_STORE_RULE_COLS = [
    "priority", "enabled", "store_keyword", "normalized_store",
    "template_code", "template_label", "template_group", "notes"
]
_CALL_LINE_COLS = [
    "priority", "enabled", "call_line", "line_group", "notes",
    "call_line_code", "display_name", "rakutel_line_name", "aliases",
]
_VENDOR_SEND_TEMPLATE_COLS = [
    "priority", "enabled", "template_code", "template_label", "repair_type",
    "warranty_type", "attention_memo_template", "rakutel_template",
    "teams_template", "notes",
]
_HANDOVER_RULE_COLS = [
    "priority", "enabled", "rule_name", "store_keywords", "case_keywords",
    "appliance_type", "call_type_inquiry", "call_type_repair", "rakutel_status",
    "handover_request_content", "notes", "exclude_wrong_number", "active",
]
_MEMO_SNIPPET_COLS = [
    "snippet_id", "category", "ui_group", "label", "body", "condition_text",
    "default_checked", "active", "sort_order",
]
# legacy
_MASTER_REQUIRED_COLS = [
    "priority", "enabled", "match_target", "keyword",
    "normalized_product", "category", "repair_type", "cost_estimate",
    "script_sheet", "script_part", "can_announce_cost", "data_erase_required", "notes",
]

PRODUCT_OTHER = "その他・要確認"
MANUFACTURER_OTHER = "その他・要確認"
MANUFACTURER_UNKNOWN = "不明"
SHOW_CALL_TYPE_IN_CALL_FORM = False


def normalize_template_code(code) -> str:
    """業者送付テンプレートコードを4桁表記へ正規化する。"""
    text = str(code or "").strip()
    if not text:
        return ""
    return text.zfill(4) if text.isdigit() else text


# ============================================================
# Generic CSV ローダー（キャッシュなし・内部用）
# ============================================================
def _load_csv(filename: str, required_cols: list) -> pd.DataFrame:
    """
    data/<filename> を読み込む。
    - utf-8-sig / utf-8 / cp932 エンコード
    - ヘッダー列数と一致しない行を除外
    - enabled=1 の行のみ
    - priority 昇順ソート
    - 失敗時は空 DataFrame を返す（呼び出し元でフォールバック）
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", filename)
    if not os.path.exists(path):
        return pd.DataFrame(columns=required_cols)
    rows = None  # CSV読み込み改善
    for encoding in ("utf-8-sig", "utf-8", "cp932"):  # CSV読み込み改善
        try:
            with open(path, "r", encoding=encoding, errors="replace", newline="") as f:
                rows = list(csv.reader(f))
            break
        except Exception:
            rows = None
    if not rows:  # CSV読み込み改善
        return pd.DataFrame(columns=required_cols)
    header = rows[0]  # CSV読み込み改善
    header_col_count = len(header)  # CSV読み込み改善
    valid_rows = [row[:header_col_count] for row in rows[1:] if len(row) >= header_col_count]  # CSV読み込み改善
    excluded_count = len(rows[1:]) - len(valid_rows)  # CSV読み込み改善
    if excluded_count > 0:  # CSV読み込み改善
        st.warning(f"CSV列数不一致のため {filename} から {excluded_count} 行を除外しました。")  # CSV読み込み改善
    df = pd.DataFrame(valid_rows, columns=header, dtype=str)  # CSV読み込み改善
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        for col in missing:
            df[col] = ""
    df["priority"] = pd.to_numeric(df["priority"], errors="coerce").fillna(999).astype(int)
    df["enabled"]  = pd.to_numeric(df["enabled"],  errors="coerce").fillna(0).astype(int)
    df = df[df["enabled"] == 1].copy()
    if "template_code" in df.columns:
        df["template_code"] = df["template_code"].apply(normalize_template_code)
    df = df.sort_values("priority", kind="stable").reset_index(drop=True)
    df = df.fillna("")
    return df


# ============================================================
# キャッシュ付き CSV ローダー × 4 + legacy
# ============================================================
@st.cache_data
def _load_alias_csv_cached(mtime: float) -> pd.DataFrame:
    return _load_csv("master_product_alias.csv", _ALIAS_COLS)


@st.cache_data
def _load_repair_type_rules_cached(mtime: float) -> pd.DataFrame:
    return _load_csv("master_repair_type_rules.csv", _REPAIR_TYPE_COLS)


@st.cache_data
def _load_cost_rules_cached(mtime: float) -> pd.DataFrame:
    return _load_csv("master_cost_rules.csv", _COST_COLS)


@st.cache_data
def _load_vendor_rules_cached(mtime: float) -> pd.DataFrame:
    return _load_csv("master_vendor_rules.csv", _VENDOR_COLS)


@st.cache_data
def _load_template_codes_cached(mtime: float) -> pd.DataFrame:
    return _load_csv("master_template_codes.csv", _TEMPLATE_CODE_COLS)


@st.cache_data
def _load_store_rules_cached(mtime: float) -> pd.DataFrame:
    return _load_csv("master_store_rules.csv", _STORE_RULE_COLS)


@st.cache_data
def _load_call_lines_cached(mtime: float) -> pd.DataFrame:
    return _load_csv("master_call_lines.csv", _CALL_LINE_COLS)


@st.cache_data
def _load_vendor_send_templates_cached(mtime: float) -> pd.DataFrame:
    return _load_csv("master_vendor_send_templates.csv", _VENDOR_SEND_TEMPLATE_COLS)


@st.cache_data
def _load_handover_rules_cached(mtime: float) -> pd.DataFrame:
    return _load_csv("master_handover_rules.csv", _HANDOVER_RULE_COLS)


@st.cache_data
def _load_script_guidance_cached(mtime: float) -> pd.DataFrame:
    return _load_csv("master_script_guidance.csv", _SCRIPT_GUIDANCE_COLS)


@st.cache_data
def _load_script_routes_cached(mtime: float) -> pd.DataFrame:
    return _load_csv("master_script_routes.csv", _SCRIPT_ROUTE_COLS)


@st.cache_data
def _load_memo_snippets_cached(mtime: float) -> pd.DataFrame:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "master_memo_snippets.csv")
    if not os.path.exists(path):
        return pd.DataFrame(columns=_MEMO_SNIPPET_COLS)
    rows = None
    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            with open(path, "r", encoding=encoding, errors="replace", newline="") as f:
                rows = list(csv.DictReader(f))
            break
        except Exception:
            rows = None
    if not rows:
        return pd.DataFrame(columns=_MEMO_SNIPPET_COLS)
    df = pd.DataFrame(rows, dtype=str)
    for col in _MEMO_SNIPPET_COLS:
        if col not in df.columns:
            df[col] = ""
    df = df.fillna("")
    df["sort_order"] = pd.to_numeric(df["sort_order"], errors="coerce").fillna(999).astype(int)
    df = df[df["active"].astype(str).str.strip().ne("0")].copy()
    return df.sort_values(["sort_order", "snippet_id"], kind="stable").reset_index(drop=True)


def _csv_mtime(filename: str) -> float:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", filename)
    return os.path.getmtime(path) if os.path.exists(path) else 0.0


def load_alias_csv() -> pd.DataFrame:
    return _load_alias_csv_cached(_csv_mtime("master_product_alias.csv"))


def load_repair_type_rules() -> pd.DataFrame:
    return _load_repair_type_rules_cached(_csv_mtime("master_repair_type_rules.csv"))


def load_cost_rules() -> pd.DataFrame:
    return _load_cost_rules_cached(_csv_mtime("master_cost_rules.csv"))


def load_vendor_rules() -> pd.DataFrame:
    return _load_vendor_rules_cached(_csv_mtime("master_vendor_rules.csv"))


def load_template_codes() -> pd.DataFrame:
    return _load_template_codes_cached(_csv_mtime("master_template_codes.csv"))


def load_store_rules() -> pd.DataFrame:
    return _load_store_rules_cached(_csv_mtime("master_store_rules.csv"))


def load_call_lines() -> pd.DataFrame:
    return _load_call_lines_cached(_csv_mtime("master_call_lines.csv"))


def load_vendor_send_templates() -> pd.DataFrame:
    return _load_vendor_send_templates_cached(_csv_mtime("master_vendor_send_templates.csv"))


def load_handover_rules() -> pd.DataFrame:
    return _load_handover_rules_cached(_csv_mtime("master_handover_rules.csv"))


def load_script_guidance_csv() -> pd.DataFrame:
    return _load_script_guidance_cached(_csv_mtime("master_script_guidance.csv"))


def load_script_routes() -> pd.DataFrame:
    return _load_script_routes_cached(_csv_mtime("master_script_routes.csv"))


def load_memo_snippets() -> pd.DataFrame:
    return _load_memo_snippets_cached(_csv_mtime("master_memo_snippets.csv"))


MASTER_APPEND_TARGETS = {
    "master_product_alias.csv": _ALIAS_COLS,
    "master_repair_type_rules.csv": _REPAIR_TYPE_COLS,
    "master_vendor_rules.csv": _VENDOR_COLS,
    "master_store_rules.csv": _STORE_RULE_COLS,
    "master_manufacturer_groups.csv": _MFR_GROUP_COLS,
    "master_call_lines.csv": _CALL_LINE_COLS,
    "master_vendor_send_templates.csv": _VENDOR_SEND_TEMPLATE_COLS,
}
MASTER_CANDIDATE_SOURCE_FIELDS = [
    "product_original", "product", "series",
    "manufacturer", "manufacturer_original", "store_name",
]
MASTER_CANDIDATE_BLOCKED_FIELDS = {
    "customer_name", "phone_number", "contact_phone", "address",
    "wrt_no", "customer_code", "operator_name", "rakuteru_no",
}


def _master_data_dir(data_dir: str | None = None) -> str:
    return os.path.abspath(data_dir or os.path.join(APP_DIR, "data"))


def _safe_master_csv_path(filename: str, data_dir: str | None = None) -> str:
    if filename not in MASTER_APPEND_TARGETS:
        raise ValueError(f"Unsupported master CSV: {filename}")
    base_dir = _master_data_dir(data_dir)
    path = os.path.abspath(os.path.join(base_dir, filename))
    if os.path.dirname(path) != base_dir or not path.endswith(".csv"):
        raise ValueError("Master CSV writes are limited to data/*.csv")
    return path


def _master_backup_path(filename: str, data_dir: str | None = None) -> str:
    base_dir = _master_data_dir(data_dir)
    backup_dir = os.path.abspath(os.path.join(base_dir, "_backup"))
    if os.path.dirname(backup_dir) != base_dir:
        raise ValueError("Backup writes are limited to data/_backup")
    os.makedirs(backup_dir, exist_ok=True)
    stem = os.path.splitext(filename)[0]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return os.path.join(backup_dir, f"{stem}_{timestamp}.csv")


def _read_master_csv_rows(filename: str, columns: list[str], data_dir: str | None = None) -> tuple[list[str], list[dict]]:
    path = _safe_master_csv_path(filename, data_dir)
    if not os.path.exists(path):
        return columns, []
    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            with open(path, "r", encoding=encoding, errors="replace", newline="") as f:
                reader = csv.DictReader(f)
                header = reader.fieldnames or columns
                return header, [dict(row) for row in reader]
        except Exception:
            continue
    return columns, []


def _clear_streamlit_cache() -> None:
    clear = getattr(getattr(st, "cache_data", None), "clear", None)
    if callable(clear):
        clear()


def _normalize_duplicate_value(value) -> str:
    return str(value or "").strip().casefold()


def _append_master_csv_row(
    filename: str,
    row: dict,
    *,
    required_cols: list[str],
    duplicate_cols: list[str],
    data_dir: str | None = None,
) -> dict:
    columns = MASTER_APPEND_TARGETS[filename]
    clean_row = {col: str(row.get(col, "") or "").strip() for col in columns}
    clean_row["priority"] = clean_row.get("priority") or "10"
    clean_row["enabled"] = clean_row.get("enabled") or "1"

    missing = [col for col in required_cols if not clean_row.get(col)]
    if missing:
        return {"ok": False, "reason": "missing_required", "missing": missing, "row": clean_row}

    header, rows = _read_master_csv_rows(filename, columns, data_dir)
    duplicate_key = tuple(_normalize_duplicate_value(clean_row.get(col)) for col in duplicate_cols)
    for existing in rows:
        existing_key = tuple(_normalize_duplicate_value(existing.get(col)) for col in duplicate_cols)
        if existing_key == duplicate_key:
            return {
                "ok": False,
                "reason": "duplicate",
                "duplicate_cols": duplicate_cols,
                "row": clean_row,
            }

    path = _safe_master_csv_path(filename, data_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    backup_path = _master_backup_path(filename, data_dir)
    if os.path.exists(path):
        shutil.copy2(path, backup_path)
    else:
        with open(backup_path, "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerow(columns)

    output_columns = [col for col in header if col] or columns
    for col in columns:
        if col not in output_columns:
            output_columns.append(col)
    rows.append(clean_row)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=output_columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    _clear_streamlit_cache()
    return {"ok": True, "reason": "appended", "row": clean_row, "backup_path": backup_path, "path": path}


def _upsert_master_csv_row(
    filename: str,
    row: dict,
    *,
    key_cols: list[str],
    required_cols: list[str],
    data_dir: str | None = None,
) -> dict:
    columns = MASTER_APPEND_TARGETS[filename]
    clean_row = {col: str(row.get(col, "") or "").strip() for col in columns}
    clean_row["priority"] = clean_row.get("priority") or "10"
    clean_row["enabled"] = clean_row.get("enabled") or "1"

    missing = [col for col in required_cols if not clean_row.get(col)]
    if missing:
        return {"ok": False, "reason": "missing_required", "missing": missing, "row": clean_row}

    header, rows = _read_master_csv_rows(filename, columns, data_dir)
    clean_key = tuple(_normalize_duplicate_value(clean_row.get(col)) for col in key_cols)
    updated = False
    for index, existing in enumerate(rows):
        existing_key = tuple(_normalize_duplicate_value(existing.get(col)) for col in key_cols)
        if existing_key == clean_key:
            merged = dict(existing)
            merged.update(clean_row)
            rows[index] = merged
            updated = True
            break
    if not updated:
        rows.append(clean_row)

    path = _safe_master_csv_path(filename, data_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    backup_path = _master_backup_path(filename, data_dir)
    if os.path.exists(path):
        shutil.copy2(path, backup_path)
    else:
        with open(backup_path, "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerow(columns)

    output_columns = [col for col in header if col] or columns
    for col in columns:
        if col not in output_columns:
            output_columns.append(col)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=output_columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    _clear_streamlit_cache()
    return {
        "ok": True,
        "reason": "updated" if updated else "appended",
        "row": clean_row,
        "backup_path": backup_path,
        "path": path,
    }


def upsert_master_call_line(row: dict, data_dir: str | None = None) -> dict:
    display_name = str(row.get("display_name") or row.get("call_line") or "").strip()
    call_line_code = str(row.get("call_line_code") or display_name or "").strip()
    rakutel_line_name = str(row.get("rakutel_line_name") or display_name).strip()
    merged = dict(row)
    merged["call_line"] = str(row.get("call_line") or display_name).strip()
    merged["display_name"] = display_name
    merged["rakutel_line_name"] = rakutel_line_name
    merged["call_line_code"] = call_line_code
    return _upsert_master_csv_row(
        "master_call_lines.csv",
        merged,
        key_cols=["call_line_code"],
        required_cols=["display_name"],
        data_dir=data_dir,
    )


def upsert_vendor_send_template(row: dict, data_dir: str | None = None) -> dict:
    normalized_row = dict(row)
    normalized_row["template_code"] = normalize_template_code(normalized_row.get("template_code"))
    return _upsert_master_csv_row(
        "master_vendor_send_templates.csv",
        normalized_row,
        key_cols=["template_code"],
        required_cols=["template_code"],
        data_dir=data_dir,
    )


def append_master_product_alias(row: dict, data_dir: str | None = None) -> dict:
    return _append_master_csv_row(
        "master_product_alias.csv",
        row,
        required_cols=["keyword", "normalized_product"],
        duplicate_cols=["keyword"],
        data_dir=data_dir,
    )


def append_master_repair_type_rule(row: dict, data_dir: str | None = None) -> dict:
    return _append_master_csv_row(
        "master_repair_type_rules.csv",
        row,
        required_cols=["product_keyword", "repair_type"],
        duplicate_cols=["product_keyword", "manufacturer_keyword", "model_keyword", "condition_keyword"],
        data_dir=data_dir,
    )


def append_master_store_rule(row: dict, data_dir: str | None = None) -> dict:
    return _append_master_csv_row(
        "master_store_rules.csv",
        row,
        required_cols=["store_keyword"],
        duplicate_cols=["store_keyword"],
        data_dir=data_dir,
    )


def append_master_vendor_rule(row: dict, data_dir: str | None = None) -> dict:
    return _append_master_csv_row(
        "master_vendor_rules.csv",
        row,
        required_cols=["repair_type", "vendor_name"],
        duplicate_cols=["call_line", "prefecture", "area_group", "manufacturer_keyword", "product_keyword", "store_keyword", "repair_type", "is_over_10years"],
        data_dir=data_dir,
    )


def _split_master_manufacturers(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[;；]", str(value or "")) if item.strip()]


def append_master_manufacturer_group(row: dict, data_dir: str | None = None) -> dict:
    group_name = str(row.get("group_name", "") or "").strip()
    manufacturers = _split_master_manufacturers(row.get("manufacturers") or row.get("manufacturer") or "")
    notes = str(row.get("notes", "") or "").strip()
    if not group_name:
        return {"ok": False, "reason": "missing_required", "missing": ["group_name"], "row": row}
    blocked = {MANUFACTURER_OTHER, MANUFACTURER_UNKNOWN, ""}
    manufacturers = [m for m in manufacturers if m not in blocked]
    if not manufacturers:
        return {"ok": False, "reason": "missing_required", "missing": ["manufacturers"], "row": row}

    header, rows = _read_master_csv_rows("master_manufacturer_groups.csv", _MFR_GROUP_COLS, data_dir)
    target = None
    for existing in rows:
        if _normalize_duplicate_value(existing.get("group_name")) == _normalize_duplicate_value(group_name):
            target = existing
            break

    existing_names = set()
    if target:
        existing_names = {_normalize_duplicate_value(m) for m in _split_master_manufacturers(target.get("manufacturers", ""))}
    additions = [m for m in manufacturers if _normalize_duplicate_value(m) not in existing_names]
    if not additions:
        return {"ok": False, "reason": "duplicate", "row": row, "duplicate_cols": ["group_name", "manufacturers"]}

    path = _safe_master_csv_path("master_manufacturer_groups.csv", data_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    backup_path = _master_backup_path("master_manufacturer_groups.csv", data_dir)
    if os.path.exists(path):
        shutil.copy2(path, backup_path)
    else:
        with open(backup_path, "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerow(_MFR_GROUP_COLS)

    if target:
        merged = _split_master_manufacturers(target.get("manufacturers", "")) + additions
        target["manufacturers"] = ";".join(merged)
        if notes and not (target.get("notes") or "").strip():
            target["notes"] = notes
    else:
        rows.append({"group_name": group_name, "manufacturers": ";".join(additions), "notes": notes})

    output_columns = [col for col in header if col] or _MFR_GROUP_COLS
    for col in _MFR_GROUP_COLS:
        if col not in output_columns:
            output_columns.append(col)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=output_columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    _clear_streamlit_cache()
    return {"ok": True, "reason": "updated", "row": {"group_name": group_name, "manufacturers": ";".join(additions), "notes": notes}, "backup_path": backup_path, "path": path}


def master_csv_has_duplicate(filename: str, row: dict, duplicate_cols: list[str], data_dir: str | None = None) -> bool:
    columns = MASTER_APPEND_TARGETS[filename]
    _, rows = _read_master_csv_rows(filename, columns, data_dir)
    key = tuple(_normalize_duplicate_value(row.get(col)) for col in duplicate_cols)
    return any(tuple(_normalize_duplicate_value(existing.get(col)) for col in duplicate_cols) == key for existing in rows)


def _short_store_keyword(store_name: str) -> str:
    value = re.sub(r"\s+", " ", (store_name or "").strip())
    for suffix in ["株式会社", "有限会社", "合同会社", "(株)", "（株）", "㈱", " Inc.", " Co., Ltd."]:
        value = value.replace(suffix, " ")
    value = re.sub(r"\s+", " ", value).strip(" 　・,，")
    return value.split()[0] if value else ""


def _suggest_product_master_values(keyword: str, current_product: str = "") -> dict:
    text = (keyword or "").strip()
    normalized = (current_product or "").strip()
    if normalized == PRODUCT_OTHER:
        normalized = ""
    product_group = ""
    repair_type = ""
    notes = "抽出結果から作成した候補"

    kitchen_keywords = ["電気調理器", "調理圧力鍋", "電気圧力鍋", "圧力鍋", "炊飯器", "トースター"]
    if any(word in text for word in kitchen_keywords):
        normalized = "電気調理器" if any(word in text for word in ["電気調理器", "調理圧力鍋", "電気圧力鍋", "圧力鍋"]) else normalized
        product_group = "キッチン家電"
        repair_type = "持込修理"
        notes = "抽出結果から作成した候補（持込修理候補）"

    return {
        "keyword": text,
        "normalized_product": normalized,
        "product_group": product_group,
        "repair_type": repair_type,
        "notes": notes,
    }


def build_master_registration_candidate(form: dict, decision: dict | None = None) -> dict:
    safe_values = {
        field: str(form.get(field, "") or "").strip()
        for field in MASTER_CANDIDATE_SOURCE_FIELDS
        if field not in MASTER_CANDIDATE_BLOCKED_FIELDS
    }
    product_keyword = (
        safe_values.get("product_original")
        or safe_values.get("series")
        or safe_values.get("product")
        or ""
    ).strip()
    product_values = _suggest_product_master_values(product_keyword, safe_values.get("product", ""))
    manufacturer = safe_values.get("manufacturer") or safe_values.get("manufacturer_original") or ""
    store_keyword = _short_store_keyword(safe_values.get("store_name", ""))

    return {
        "source_fields": safe_values,
        "product_alias": {
            "priority": "10",
            "enabled": "1",
            "keyword": product_values["keyword"],
            "normalized_product": product_values["normalized_product"],
            "product_group": product_values["product_group"],
            "notes": product_values["notes"],
        },
        "repair_type_rule": {
            "priority": "10",
            "enabled": "1",
            "product_keyword": product_values["normalized_product"] or product_values["keyword"],
            "manufacturer_keyword": manufacturer,
            "model_keyword": "",
            "condition_keyword": "",
            "repair_type": product_values["repair_type"],
            "needs_confirmation": "0" if product_values["repair_type"] else "1",
            "notes": product_values["notes"],
        },
        "store_rule": {
            "priority": "10",
            "enabled": "1",
            "store_keyword": store_keyword,
            "normalized_store": store_keyword,
            "template_code": "",
            "template_label": "",
            "template_group": "",
            "notes": "抽出結果から作成した候補" if store_keyword else "",
        },
    }


MANUFACTURER_INLINE_GROUP_OPTIONS = [
    "国内家電メーカー",
    "国内エアコンメーカー",
    "国内給湯器メーカー",
    "海外PC",
    "国内PC",
    "時計メーカー",
    "その他",
]

VENDOR_INLINE_OPTIONS = [
    "ユナイトサービス㈱",
    "WRT修理センター",
    "CER候補（担当確認）",
    "宗建リノベーション",
    "ソフマップ修理センター",
    "担当エスカ（要確認）",
]


INLINE_MANUFACTURER_OPEN_LABEL = "メーカー登録候補を開く"
INLINE_SAVE_AND_REDECIDE_LABEL = "保存して再判定"
INLINE_SEND_TO_MASTER_LABEL = "マスタ管理で確認して登録"


def _clean_master_candidate_value(value) -> str:
    return str(value or "").strip()


def _manufacturer_inline_aliases(original: str, normalized: str) -> list[str]:
    values: list[str] = []
    for value in (normalized, original):
        value = _clean_master_candidate_value(value)
        if value and value not in values and value not in (MANUFACTURER_OTHER, MANUFACTURER_UNKNOWN):
            values.append(value)
    folded = {value.casefold() for value in values}
    aqua_ja_values = ("アクア", "繧｢繧ｯ繧｢")
    if "aqua" in folded and not any(value in aqua_ja_values for value in values):
        values.insert(0, "アクア")
    if any(value in aqua_ja_values for value in values) and "aqua" not in folded:
        values.append("AQUA")
    return values


def build_inline_manufacturer_candidate(form: dict) -> dict:
    current = _clean_master_candidate_value(form.get("manufacturer"))
    original = _clean_master_candidate_value(form.get("manufacturer_original"))
    if current not in ("", MANUFACTURER_OTHER, MANUFACTURER_UNKNOWN):
        return {}
    if not original or original in (MANUFACTURER_OTHER, MANUFACTURER_UNKNOWN):
        return {}
    normalized = normalize_manufacturer(original).strip() or original
    if normalized in (MANUFACTURER_OTHER, MANUFACTURER_UNKNOWN):
        normalized = original
    aliases = _manufacturer_inline_aliases(original, normalized)
    return {
        "manufacturer_original": original,
        "normalized_manufacturer": normalized,
        "group_name": "国内家電メーカー",
        "manufacturers": ";".join(aliases),
        "notes": "インライン登録候補",
    }


def build_inline_product_alias_candidate(form: dict) -> dict:
    current = _clean_master_candidate_value(form.get("product"))
    source = (
        _clean_master_candidate_value(form.get("product_original"))
        or _clean_master_candidate_value(form.get("series"))
    )
    if current not in ("", PRODUCT_OTHER):
        return {}
    if not source or source == PRODUCT_OTHER:
        return {}
    values = _suggest_product_master_values(source, "")
    return {
        "priority": "10",
        "enabled": "1",
        "keyword": values["keyword"],
        "normalized_product": values["normalized_product"] or source,
        "product_group": values["product_group"],
        "notes": values["notes"],
    }


def build_inline_vendor_rule_candidate(form: dict, decision: dict) -> dict:
    vendor = _clean_master_candidate_value(decision.get("vendor"))
    vendor_result = decision.get("vendor_result", {}) or {}
    repair_type = _clean_master_candidate_value(decision.get("repair_type"))
    product = _clean_master_candidate_value(form.get("product") or decision.get("normalized_product"))
    prefecture = _clean_master_candidate_value(form.get("prefecture"))
    store_name = _clean_master_candidate_value(form.get("store_name"))
    call_line = _clean_master_candidate_value(form.get("call_line"))
    if "担当エスカ" not in vendor and not vendor_result.get("needs_escalation"):
        return {}
    if not (repair_type and product and prefecture and (store_name or call_line)):
        return {}
    return {
        "priority": "10",
        "enabled": "1",
        "call_line": call_line,
        "prefecture": prefecture,
        "area_group": _clean_master_candidate_value(decision.get("area_group")),
        "manufacturer_keyword": "" if form.get("manufacturer") in (MANUFACTURER_OTHER, MANUFACTURER_UNKNOWN) else _clean_master_candidate_value(form.get("manufacturer")),
        "product_keyword": product,
        "store_keyword": _short_store_keyword(store_name) if store_name else "",
        "repair_type": repair_type,
        "is_over_10years": "1" if form.get("is_over_10years") else "",
        "vendor_name": "担当エスカ（要確認）",
        "reason": vendor_result.get("vendor_missing_reason") or vendor_result.get("reason") or "インライン登録候補",
        "needs_escalation": "1",
        "notes": "",
        "contact_type": "",
    }


def build_inline_store_rule_candidate(form: dict, template_selection: dict | None = None) -> dict:
    store_name = _clean_master_candidate_value(form.get("store_name"))
    if not store_name:
        return {}
    selection = template_selection or {}
    store_rule = selection.get("store_rule") or {}
    if store_rule.get("matched") or selection.get("source") != "fallback":
        return {}
    store_keyword = _short_store_keyword(store_name)
    if not store_keyword:
        return {}
    return {
        "priority": "10",
        "enabled": "1",
        "store_keyword": store_keyword,
        "normalized_store": store_keyword,
        "template_code": selection.get("template_code", ""),
        "template_label": selection.get("label", ""),
        "template_group": "",
        "notes": "インライン登録候補",
    }


def should_offer_master_registration_candidate(form: dict, decision: dict) -> bool:
    alias_result = decision.get("alias_result", {})
    repair_type = (decision.get("repair_type") or "").strip()
    product = (decision.get("normalized_product") or form.get("product") or "").strip()
    has_product_source = any((form.get(field) or "").strip() for field in ["product_original", "series", "product"])
    unknown_product = product in ("", PRODUCT_OTHER) or not alias_result.get("matched")
    needs_repair_master = repair_type in ("", "要確認") or not decision.get("repair_result", {}).get("matched")
    return has_product_source and (unknown_product or needs_repair_master)


DOUBLE_PROTECT_KEYWORDS = ("物損", "ダブル", "DP")
DOUBLE_PROTECT_AMOUNT_CONFIRMATION = "【物損付/DP】物損時の保証金額をシステムで確認"
DOUBLE_PROTECT_DAMAGE_CONFIRMATION = "【物損付/DP】事故状況・破損状況を確認"


def is_double_protect_plan(warranty_plan: str) -> bool:
    plan = (warranty_plan or "").strip()
    if not plan:
        return False
    plan_upper = plan.upper()
    return "物損" in plan or "ダブル" in plan or "DP" in plan_upper


def double_protect_plan_label(warranty_plan: str) -> str:
    plan = (warranty_plan or "").strip()
    if not is_double_protect_plan(plan):
        return "通常保証"
    labels = []
    if "物損" in plan:
        labels.append("物損付")
    dp_match = re.search(r"DP\s*\d*", plan, flags=re.IGNORECASE)
    if dp_match:
        labels.append(dp_match.group(0).upper().replace(" ", ""))
    elif "ダブル" in plan:
        labels.append("ダブルプロテクト")
    return " / ".join(dict.fromkeys(labels)) or "物損付 / DP"


def double_protect_amount_status(warranty_plan: str) -> str:
    return "システム確認" if is_double_protect_plan(warranty_plan) else "対象外"


def _append_unique(items: list, value: str) -> None:
    if value and value not in items:
        items.append(value)


def _dedupe_preserve_order(items: list) -> list:
    result = []
    for item in items:
        _append_unique(result, item)
    return result


RESIDENTIAL_APPLIANCE_KEYWORDS = (
    "住設", "住宅設備", "住宅設備機器", "給湯", "温水", "ビルトイン",
    "システムキッチン", "キッチン", "IHクッキングヒーター", "クッキングヒーター",
    "食器洗い乾燥機", "食洗機", "レンジフード", "浴室", "洗面", "トイレ",
)


def infer_appliance_type_from_form(form: dict, current_value: str = "") -> str:
    """保証・製品情報から家電/住設を補助判定する。強い住設根拠のみ家電を上書きする。"""
    current = (current_value or form.get("appliance_type") or "").strip()
    evidence_text = " ".join(
        str(form.get(field) or "")
        for field in ("warranty_plan", "genre", "category", "series", "product", "product_original")
    )
    if any(keyword in evidence_text for keyword in RESIDENTIAL_APPLIANCE_KEYWORDS):
        return "住設"
    return current


def normalize_appliance_category(value: str, appliance_type: str = "", housing_phase: str = "") -> str:
    category = (value or "").strip()
    if category in APPLIANCE_CATEGORY_OPTIONS:
        return category
    if category in ("住設新築", "住設 新築"):
        return "住設（新築）"
    if category in ("住設新設", "住設 新設"):
        return "住設（新築）"
    if category in ("住設既築", "住設 既築", "住設中古", "住設 中古", "住設既築/中古", "住設 既築/中古"):
        return "住設（既築）"
    if category in ("住設賃貸", "住設 賃貸") or ("住設" in category and "賃貸" in category):
        return "住設（賃貸）"
    if category == "賃貸" and (appliance_type or "").strip() == "住設":
        return "住設（賃貸）"
    base_type = (appliance_type or "").strip()
    phase = (housing_phase or "").strip()
    if base_type == "家電":
        return "家電"
    if base_type == "住設":
        if phase == "賃貸":
            return "住設（賃貸）"
        return "住設（新築）" if phase in ("新築", "新設") else "住設（既築）"
    return ""


def apply_appliance_category_to_form(form: dict) -> dict:
    """新しい案件分類を、既存の appliance_type / housing_phase へ互換反映する。"""
    category = normalize_appliance_category(
        form.get("appliance_category", ""),
        form.get("appliance_type", ""),
        form.get("housing_phase", ""),
    )
    form["appliance_category"] = category
    if category == "家電":
        form["appliance_type"] = "家電"
        form["housing_phase"] = ""
    elif category == "住設（新築）":
        form["appliance_type"] = "住設"
        form["housing_phase"] = "新築"
    elif category == "住設（既築）":
        form["appliance_type"] = "住設"
        form["housing_phase"] = "既築"
    elif category == "住設（賃貸）":
        form["appliance_type"] = "住設"
        form["housing_phase"] = "賃貸"
    return form


DEFAULT_HOME_CALL_LINE_VALUES = {
    "",
    "家電",
    "家電保証対応業務（24時間）",
    "家電業務",
}


def should_auto_use_residential_call_line(form: dict) -> bool:
    return False


def effective_call_line_for_form(form: dict) -> str:
    return normalize_call_line_for_display(form.get("call_line", ""))


def _auto_select_template_from_candidates(df_tpl: pd.DataFrame, repair_type: str, warranty_plan: str) -> str:
    """
    - warranty_plan に「物損」「ダブル」「DP」のいずれかを含む → ダブルプロテクト系を優先
    - repair_type == "出張修理" → 【出張修理】系
    - repair_type == "持込修理" → 【持込修理】系
    - マッチしなければ "" を返す
    """
    if df_tpl.empty:
        return ""
    is_dp = is_double_protect_plan(warranty_plan)
    repair_kw = (
        "出張修理" if repair_type == "出張修理"
        else "持込修理" if repair_type == "持込修理"
        else ""
    )
    if is_dp and repair_kw:
        for _, row in df_tpl.iterrows():
            label = row["label"]
            if repair_kw in label and "ダブル" in label:
                return label
    if repair_kw:
        for _, row in df_tpl.iterrows():
            label = row["label"]
            if repair_kw in label and "ダブル" not in label and "物損" not in label:
                return label
    return ""


def _auto_select_template(call_line: str, repair_type: str, warranty_plan: str, df_tpl: pd.DataFrame) -> str:
    """
    call_line + repair_type + warranty_plan からテンプレートラベルを自動選択。
    販売店別ルールがない場合のフォールバックとして使う。
    """
    if df_tpl.empty or not call_line:
        return ""
    filtered = df_tpl[df_tpl["category"].apply(lambda value: call_line_master_values_match(value, call_line))]
    if filtered.empty:
        return ""
    return _auto_select_template_from_candidates(filtered, repair_type, warranty_plan)


def match_store_template_rule(form: dict, df_store_rules: pd.DataFrame = None) -> dict:
    df = load_store_rules() if df_store_rules is None else df_store_rules
    base = {
        "matched": False,
        "store_keyword": "",
        "normalized_store": "",
        "template_code": "",
        "template_label": "",
        "template_group": "",
        "notes": "通常テンプレート",
        "priority": None,
    }
    if df.empty:
        return base

    store_targets = [
        (form.get("store_name") or "").strip(),
        (form.get("store_original") or "").strip(),
        (form.get("store_name_original") or "").strip(),
        (form.get("store_company") or "").strip(),
        (form.get("operating_company") or "").strip(),
    ]
    source_labels = [
        ("表示販売店", (form.get("store_name") or "").strip()),
        ("運営会社", (form.get("store_original") or "").strip()),
        ("販売店原文", (form.get("store_name_original") or "").strip()),
        ("運営会社", (form.get("store_company") or "").strip()),
        ("運営会社", (form.get("operating_company") or "").strip()),
    ]
    store_text = " ".join(t for t in store_targets if t)
    default_row = None

    for _, row in df.iterrows():
        keyword = (row.get("store_keyword") or "").strip()
        if not keyword:
            if default_row is None:
                default_row = row
            continue
        if keyword in store_text:
            matched_label = ""
            matched_value = ""
            for label, value in source_labels:
                if value and keyword in value:
                    matched_label = label
                    matched_value = value
                    break
            return {
                "matched": True,
                "store_keyword": keyword,
                "normalized_store": (row.get("normalized_store") or keyword).strip(),
                "template_code": normalize_template_code(row.get("template_code")),
                "template_label": (row.get("template_label") or "").strip(),
                "template_group": (row.get("template_group") or "").strip(),
                "notes": (row.get("notes") or "").strip(),
                "priority": int(row.get("priority", 999)),
                "matched_source_label": matched_label,
                "matched_source_value": matched_value,
                "display_store": (form.get("store_name") or "").strip(),
            }

    if default_row is not None:
        base.update({
            "normalized_store": (default_row.get("normalized_store") or "").strip(),
            "template_code": normalize_template_code(default_row.get("template_code")),
            "template_label": (default_row.get("template_label") or "").strip(),
            "template_group": (default_row.get("template_group") or "").strip(),
            "notes": (default_row.get("notes") or "通常テンプレート").strip(),
            "priority": int(default_row.get("priority", 999)),
        })
    return base


def _template_row_by_code_or_label(df_tpl: pd.DataFrame, template_code: str = "", template_label: str = None):
    if df_tpl.empty:
        return None
    if template_code:
        normalized_code = normalize_template_code(template_code)
        matched = df_tpl[df_tpl["template_code"].apply(normalize_template_code) == normalized_code]
        if not matched.empty:
            return matched.iloc[0]
    if template_label:
        matched = df_tpl[df_tpl["label"] == template_label]
        if not matched.empty:
            return matched.iloc[0]
    return None


def _template_candidate_from_row(row) -> dict:
    return {
        "template_code": normalize_template_code(row.get("template_code")),
        "label": (row.get("label") or "").strip(),
        "category": (row.get("category") or "").strip(),
        "data_erase_required": (row.get("data_erase_required") or "").strip(),
        "cost_guidance_allowed": (row.get("cost_guidance_allowed") or "").strip(),
        "notes": (row.get("notes") or "").strip(),
    }


def _append_template_candidate(candidates: list, row) -> None:
    if row is None:
        return
    candidate = _template_candidate_from_row(row)
    key = (candidate["template_code"], candidate["label"])
    if candidate["label"] and key not in {
        (item["template_code"], item["label"]) for item in candidates
    }:
        candidates.append(candidate)


def _template_option_label(candidate: dict) -> str:
    code = normalize_template_code(candidate.get("template_code"))
    label = (candidate.get("label") or "").strip()
    return f"{code} {label}".strip()


def build_template_selection_reason(selection: dict) -> str:
    label = (selection.get("label") or "").strip()
    source = (selection.get("source") or "").strip()
    store_rule = selection.get("store_rule") or {}
    reasons = []
    if "住宅資材センター" in label:
        reasons.append("住宅資材センター")
    if "メーカー保証期間" in label:
        reasons.append("メーカー保証期間")
    if "延長保証" in label:
        reasons.append("延長保証")
    if "ダブル" in label or "物損" in label:
        reasons.append("物損付 / DP")
    if source.startswith("store"):
        detail = format_store_template_rule_display(store_rule)
        if detail and detail not in reasons:
            reasons.append(detail)
    if not reasons and label:
        reasons.append("回線・修理形態・保証プラン")
    return " / ".join(_dedupe_preserve_order(reasons))


def build_after_call_template_vendor_summary(form: dict, decision: dict,
                                             template_selection: dict,
                                             selected_option: str = "") -> dict:
    """終話後処理のテンプレート理由と拠点理由を混ぜずに表示するための要約。"""
    store_rule = template_selection.get("store_rule") or {}
    template_label = selected_option or _template_option_label({
        "template_code": template_selection.get("template_code", ""),
        "label": template_selection.get("label", ""),
    })
    template_reason = (
        store_rule.get("notes")
        or store_rule.get("template_group")
        or store_rule.get("template_label")
        or build_template_selection_reason(template_selection)
        or "回線・修理形態・保証プラン"
    )
    vendor_result = decision.get("vendor_result", {}) or {}
    vendor = decision.get("vendor", "")
    return {
        "template": template_label,
        "template_reason": template_reason,
        "template_source_label": store_rule.get("matched_source_label") or "判定根拠",
        "template_source_value": (
            store_rule.get("matched_source_value")
            or store_rule.get("normalized_store")
            or store_rule.get("store_keyword")
            or ""
        ),
        "display_store": store_rule.get("display_store") or form.get("store_name", ""),
        "vendor": vendor,
        "vendor_reason": vendor_result.get("reason", ""),
        "vendor_status": "終話後エスカ" if vendor_result.get("needs_escalation") else "確定",
    }


def build_template_candidates_for_form(form: dict, repair_type: str, warranty_plan: str,
                                       df_tpl: pd.DataFrame, selected: dict = None) -> list[dict]:
    """
    画面のテンプレート選択候補を作る。
    特殊テンプレートを優先しつつ、通常の出張修理・自然故障 0009 は住設でも残す。
    """
    if df_tpl.empty:
        return []

    candidates = []
    selected = selected or {}
    selected_row = _template_row_by_code_or_label(
        df_tpl,
        selected.get("template_code", ""),
        selected.get("label", ""),
    )
    _append_template_candidate(candidates, selected_row)
    if selected_row is None and (selected.get("template_code") or selected.get("label")):
        _append_template_candidate(candidates, {
            "template_code": selected.get("template_code", ""),
            "label": selected.get("label", ""),
            "category": selected.get("source", ""),
            "data_erase_required": "",
            "cost_guidance_allowed": "",
            "notes": (selected.get("store_rule") or {}).get("notes", ""),
        })

    if repair_type == "出張修理" and not is_double_protect_plan(warranty_plan):
        row_0009 = _template_row_by_code_or_label(df_tpl, template_code="0009")
        _append_template_candidate(candidates, row_0009)

    call_line = form.get("call_line", "")
    if call_line:
        filtered = df_tpl[df_tpl["category"].apply(lambda value: call_line_master_values_match(value, call_line))]
        for _, row in filtered.iterrows():
            _append_template_candidate(candidates, row)

    if not candidates:
        label = _auto_select_template(call_line, repair_type, warranty_plan, df_tpl)
        _append_template_candidate(candidates, _template_row_by_code_or_label(df_tpl, template_label=label))

    return candidates


def _auto_select_template_by_group(template_group: str, repair_type: str,
                                   warranty_plan: str, df_tpl: pd.DataFrame) -> str:
    group = (template_group or "").strip()
    if df_tpl.empty or not group:
        return ""
    mask = (
        df_tpl["category"].str.contains(group, na=False) |
        df_tpl["label"].str.contains(group, na=False) |
        df_tpl["notes"].str.contains(group, na=False)
    )
    candidates = df_tpl[mask]
    return _auto_select_template_from_candidates(candidates, repair_type, warranty_plan)


def select_template_for_form(form: dict, repair_type: str, warranty_plan: str,
                             df_tpl: pd.DataFrame, df_store_rules: pd.DataFrame = None) -> dict:
    store_rule = match_store_template_rule(form, df_store_rules)
    label = ""
    code = ""
    source = "fallback"

    if store_rule.get("matched") and (store_rule.get("template_code") or store_rule.get("template_label")):
        row = _template_row_by_code_or_label(
            df_tpl, store_rule.get("template_code", ""), store_rule.get("template_label", "")
        )
        if row is not None:
            label = (row.get("label") or "").strip()
            code = normalize_template_code(row.get("template_code"))
        else:
            label = store_rule.get("template_label", "")
            code = normalize_template_code(store_rule.get("template_code"))
        source = "store_direct"
    elif store_rule.get("matched") and store_rule.get("template_group"):
        label = _auto_select_template_by_group(
            store_rule["template_group"], repair_type, warranty_plan, df_tpl
        )
        if label:
            row = _template_row_by_code_or_label(df_tpl, template_label=label)
            code = normalize_template_code(row.get("template_code")) if row is not None else ""
            source = "store_group"

    if not label:
        label = _auto_select_template(
            form.get("call_line", ""), repair_type, warranty_plan, df_tpl
        )
        row = _template_row_by_code_or_label(df_tpl, template_label=label)
        code = normalize_template_code(row.get("template_code")) if row is not None else ""
        source = "fallback"

    selected = {
        "label": label,
        "template_code": normalize_template_code(code),
        "source": source,
        "store_rule": store_rule,
    }
    selected["candidates"] = build_template_candidates_for_form(
        form, repair_type, warranty_plan, df_tpl, selected
    )
    return selected


def format_store_template_rule_display(store_rule: dict) -> str:
    if store_rule.get("matched"):
        store_name = store_rule.get("normalized_store") or store_rule.get("store_keyword") or "販売店"
        detail = (
            store_rule.get("notes")
            or store_rule.get("template_group")
            or store_rule.get("template_label")
            or store_rule.get("template_code")
            or "販売店テンプレート対象"
        )
        return f"{store_name} → {detail}"
    return store_rule.get("notes") or "通常テンプレート"


def build_store_attention_notes(form: dict) -> list[str]:
    store = (form.get("store_name") or "").strip()
    if "ライフデザイン・カバヤ" not in store:
        return []
    return [
        "施工側起因の可能性が高い場合は販売店対応",
        "住設以外、建具、内装、その他は販売店案内",
        "保証対象外箇所は販売店対応または有償案内の可能性あり",
    ]


def _format_extracted_time(now: datetime | None = None) -> str:
    now = now or datetime.now()
    return (
        f"{now.year}/{now.month}/{now.day} "
        f"{now.hour:02d}：{now.minute:02d}"
    )


def _fill_template_notes(notes: str, form: dict) -> str:
    notes_filled = notes or ""
    store = (form.get("store_name") or "").strip()
    phone = (form.get("phone_number") or "").strip()
    if store:
        notes_filled = notes_filled.replace("〇〇〇〇〇", store)
    if phone:
        notes_filled = notes_filled.replace("TEL：", f"TEL：{phone}")
    return notes_filled


def _estimated_fee_for_template(cost_estimate: str = "") -> str:
    value = (cost_estimate or "").strip()
    if not value or value in ("確認中", "未確定", "要確認"):
        return "確認中"
    return value


def build_vendor_send_template_context(
    form: dict,
    warranty_result: dict | None = None,
    repair_type: str = "",
    vendor: str = "",
    cost_estimate: str = "",
) -> dict:
    warranty_result = warranty_result or {}
    return {
        "wrt_no": form.get("wrt_no", ""),
        "template_code": form.get("template_code", ""),
        "template_label": form.get("template_label", ""),
        "product": form.get("product", ""),
        "manufacturer": form.get("manufacturer", ""),
        "model": form.get("model_number", ""),
        "warranty_status": warranty_result.get("title", ""),
        "repair_type": repair_type,
        "vendor_name": vendor,
        "estimated_fee": _estimated_fee_for_template(cost_estimate or form.get("cost_estimate", "")),
        "operator_name": form.get("operator_name", ""),
        "rakuteru_no": form.get("rakuteru_no", ""),
        "symptom_detail": get_hearing_value(form, "symptom_detail"),
        "occurrence_time": resolve_occurrence_time(form),
        "occurrence_frequency": resolve_occurrence_frequency(form),
    }


def render_vendor_send_template_text(template_text: str, context: dict) -> str:
    def replace(match):
        key = match.group(1).strip()
        return str(context.get(key, ""))

    rendered = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", replace, template_text or "")
    return sanitize_generated_body_text(rendered)


def sanitize_generated_body_text(text: str) -> str:
    """Remove UI-only icons that must not leak into generated business text."""
    return str(text or "").replace("📋", "")


def _join_text_blocks(existing: str, addition: str) -> str:
    existing = sanitize_generated_body_text(existing).rstrip()
    addition = sanitize_generated_body_text(addition).strip()
    if not existing:
        return addition
    if not addition:
        return existing
    return f"{existing}\n\n{addition}"


def append_attention_memo_snippets(form: dict, snippet_ids: list[str]) -> list[dict]:
    """CSV定型文を修理依頼書メモだけへ重複なしで追記する。"""
    df = load_memo_snippets()
    if df.empty or not snippet_ids:
        form["attention_memo"] = sanitize_generated_body_text(form.get("attention_memo", ""))
        return []

    selected = {str(snippet_id or "").strip() for snippet_id in snippet_ids if str(snippet_id or "").strip()}
    current = sanitize_generated_body_text(form.get("attention_memo", ""))
    added: list[dict] = []
    for _, row in df.iterrows():
        snippet_id = str(row.get("snippet_id") or "").strip()
        body = sanitize_generated_body_text(row.get("body") or "")
        if snippet_id not in selected or not body:
            continue
        if body in current:
            continue
        current = _join_text_blocks(current, body)
        added.append(row.to_dict())
    form["attention_memo"] = current
    return added


def memo_snippet_option_label(row) -> str:
    label = str(row.get("label") or row.get("snippet_id") or "").strip()
    return label


def memo_snippet_row_by_id(snippets_df: pd.DataFrame, snippet_id: str) -> dict:
    snippet_id = str(snippet_id or "").strip()
    if not snippet_id or snippets_df.empty:
        return {}
    matched = snippets_df[snippets_df["snippet_id"].astype(str) == snippet_id]
    if matched.empty:
        return {}
    return matched.iloc[0].to_dict()


def get_vendor_send_template_for_form(form: dict, repair_type: str = "", warranty_type: str = "") -> dict:
    df = load_vendor_send_templates()
    if df.empty:
        return {}
    code = normalize_template_code(form.get("template_code"))
    label = (form.get("template_label") or "").strip()
    if code:
        matched = df[df["template_code"].apply(normalize_template_code) == code]
        if not matched.empty:
            return matched.iloc[0].to_dict()
    if label:
        matched = df[df["template_label"] == label]
        if not matched.empty:
            return matched.iloc[0].to_dict()
    return {}


def _line_label_for_call_line(call_line: str) -> str:
    line_group = get_line_group(call_line)
    if not line_group:
        cl = (call_line or "").strip()
        if "住設" in cl or "不動産" in cl or "工務店" in cl:
            line_group = "住設"
        elif cl:
            line_group = "家電"
    return (
        "家電回線" if line_group == "家電"
        else "住設回線" if line_group == "住設"
        else "回線"
    )


def _build_after_call_memo(form: dict, warranty_result: dict, repair_type: str,
                           vendor: str, notes_filled: str = "", cost_estimate: str = "") -> str:
    template_row = get_vendor_send_template_for_form(
        form, repair_type, double_protect_plan_label(form.get("warranty_plan", ""))
    )
    attention_template = (template_row.get("attention_memo_template") or "").strip() if template_row else ""
    if attention_template:
        context = build_vendor_send_template_context(
            form, warranty_result, repair_type, vendor, cost_estimate
        )
        return sanitize_generated_body_text(render_vendor_send_template_text(attention_template, context))

    dp_note = ""
    if is_double_protect_plan(form.get("warranty_plan", "")):
        dp_note = "\n物損付 / DP案件: 物損時の保証金額はシステムにて確認要"
    memo = (
        f"WRT-NO: {form.get('wrt_no','─')}\n"
        f"テンプレート: {form.get('template_code', '─')} {form.get('template_label', '─')}\n"
        f"製品: {form.get('product','─')} / {form.get('manufacturer','─')} {form.get('model_number','─')}\n"
        f"保証期間判定: {warranty_result.get('title','─')}\n"
        f"保証種別: {double_protect_plan_label(form.get('warranty_plan', ''))}\n"
        f"修理形態: {repair_type}\n"
        f"症状: {form.get('symptom_detail') or form.get('symptom','─')}\n"
        f"拠点候補: {vendor}"
        f"{dp_note}"
    )
    store_attention_notes = build_store_attention_notes(form)
    if store_attention_notes:
        memo += "\n\n【販売店別注意】\n" + "\n".join(f"- {note}" for note in store_attention_notes)
    if notes_filled:
        memo += f"\n\n【備考】\n{notes_filled}"
    return sanitize_generated_body_text(memo)


def _rakutel_call_direction(form: dict) -> str:
    direction = (form.get("call_direction") or "").strip()
    return direction if direction in ("受電", "架電") else "受電"


def _rakutel_counterparty(form: dict, caller_type: str = "") -> str:
    counterparty = (form.get("counterparty_type") or "").strip()
    legacy_caller = (caller_type or "").strip()
    form_caller = (form.get("caller_type") or "").strip()
    if counterparty:
        return counterparty
    return (legacy_caller or form_caller or "加入者").strip() or "加入者"


def _rakutel_counterparty_display(form: dict, caller_type: str = "") -> str:
    counterparty = _rakutel_counterparty(form, caller_type)
    detail = (form.get("counterparty_detail") or form.get("counterparty_free_text") or "").strip()
    if detail:
        return f"{counterparty}（{detail}）"
    return counterparty


def _rakutel_call_arrow(form: dict, caller_type: str = "") -> str:
    operator = (form.get("operator_name") or "").strip() or "●●"
    counterparty = _rakutel_counterparty_display(form, caller_type)
    if _rakutel_call_direction(form) == "架電":
        return f"MPG{operator}⇒{counterparty}"
    return f"{counterparty}⇒MPG{operator}"


def _rakutel_call_heading(form: dict) -> str:
    return build_rakutel_call_header(effective_call_line_for_form(form), _rakutel_call_direction(form))


def _rakutel_timestamp_text(form: dict) -> str:
    text = (form.get("extracted_time") or "").strip()
    if not text:
        return "●●：●●"
    if re.search(r"\d{1,2}[：:]\d{2}", text):
        return text
    return f"{text} ●●：●●"


def _build_rakutel_text(form: dict, caller_type: str, notes_filled: str = "") -> str:
    operator = (form.get("operator_name") or "").strip() or "●●"
    extracted_time = _rakutel_timestamp_text(form)
    contact = (form.get("contact_phone") or "").strip() or (form.get("phone_number") or "").strip() or "─"
    rakuteru = (form.get("rakuteru_no") or "").strip()

    rakutel_text = (
        f"{_rakutel_call_heading(form)}\n"
        f"{extracted_time}　{_rakutel_call_arrow(form, caller_type)}\n\n"
        f"【修理受付済み】\n"
        f"※保証対象外の事例ご案内済\n"
        f"日程調整時の連絡先：{contact}\n"
        f"WRT-NO：{form.get('wrt_no','─')}\n"
        f"お客様名：{form.get('customer_name','─')}\n"
        f"製品：{form.get('product','─')}\n"
        f"メーカー：{form.get('manufacturer','─')} {form.get('model_number','─')}"
    )
    if rakuteru:
        rakutel_text += f"\n楽テルNO：{rakuteru}"
    if is_double_protect_plan(form.get("warranty_plan", "")):
        rakutel_text += "\n物損付 / DP案件\n物損時の保証金額はシステムにて確認要"
    if notes_filled:
        rakutel_text += f"\n依頼票メモ備考：{notes_filled}"
    return rakutel_text


def _build_teams_report(form: dict, caller_type: str, notes_filled: str = "") -> str:
    return _build_rakutel_text(form, caller_type, notes_filled)


def _escape_teams_html(value) -> str:
    return (str(value or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def get_request_pdf_folder_info(vendor: str) -> dict:
    vendor_text = (vendor or "").strip()
    if "WRT修理受付センター" in vendor_text or "WRT修理センター" in vendor_text:
        return {"required": True, **REQUEST_PDF_FOLDERS["wrt"]}
    if "CER候補" in vendor_text or "CER" in vendor_text:
        return {"required": True, **REQUEST_PDF_FOLDERS["cer"]}
    return {"required": False, "name": "", "url": ""}


def build_vendor_escalation_info(vendor: str, vendor_result: dict | None = None,
                                 repair_result: dict | None = None,
                                 script_result: dict | None = None,
                                 diagnostics: list | None = None) -> dict:
    vendor_result = vendor_result or {}
    reason = (vendor_result.get("reason") or "").strip()
    vendor_text = (vendor or vendor_result.get("vendor_name") or "").strip()
    is_cer = "CER" in vendor_text
    is_generic_escalation = "担当エスカ" in vendor_text or "要確認" in vendor_text
    generic_reason_tokens = ("担当エスカ", "要確認", "担当確認")

    if not reason and repair_result:
        reason = (repair_result.get("reason") or "").strip()
    if not reason and script_result:
        reason = (script_result.get("reason") or "").strip()
    if not reason and diagnostics:
        for item in diagnostics:
            if not isinstance(item, dict):
                continue
            text = (item.get("message") or item.get("detail") or "").strip()
            if text:
                reason = text
                break

    reason_is_generic = not reason or all(token in generic_reason_tokens for token in re.findall(r"[一-龥ァ-ヶーA-Za-z]+", reason))

    if is_cer:
        title = "⚠️ 拠点候補：CER候補"
        if reason and not reason_is_generic:
            if "九州" in reason:
                reason = "九州エリアのためCER候補。手配可否は担当確認が必要"
            elif "CER" not in reason:
                reason = f"{reason}のためCER候補。手配可否は担当確認が必要"
        else:
            reason = "CER候補。手配可否は担当確認が必要"
        next_action = "終話後に担当へCER手配可否を確認"
    elif is_generic_escalation:
        title = "⚠️ 拠点未確定：担当確認が必要"
        if reason_is_generic or vendor_text in reason:
            reason = "現在の条件では修理拠点を自動確定できません"
        next_action = "終話後に担当へ確認し、拠点を確定"
    else:
        title = "⚠️ 拠点確認が必要"
        if not reason:
            reason = "現在の条件では修理拠点を自動確定できません"
        next_action = "終話後に担当へ確認し、拠点を確定"

    if is_generic_escalation and vendor_result.get("vendor_missing_reason"):
        next_action = "担当へ確認するか、修理拠点ルール候補を作成してください。"

    return {
        "title": title,
        "reason": reason,
        "next_action": next_action,
    }


def build_vendor_candidate_card_info(vendor: str, vendor_result: dict | None = None) -> dict:
    vendor_result = vendor_result or {}
    folder = get_request_pdf_folder_info(vendor)
    handoff = resolve_vendor_handoff_info(vendor, vendor_result.get("contact_type", ""))
    action = "依頼書PDF格納" if folder.get("required") else handoff.get("arrangement_method", "")
    return {
        "vendor": vendor,
        "reason": (vendor_result.get("reason") or "").strip(),
        "needs_escalation": bool(vendor_result.get("needs_escalation")),
        "escalation": build_vendor_escalation_info(vendor, vendor_result) if vendor_result.get("needs_escalation") else {},
        "request_folder": folder,
        "arrangement_method": action,
        "contact": handoff.get("contact", ""),
    }


def format_confirmed_vendor_block(vendor: str, vendor_card: dict) -> str:
    arrangement = vendor_card.get("arrangement_method") or "手配方法を確認"
    contact = vendor_card.get("contact") or "連絡先を確認"
    return (
        f"修理拠点：\n{vendor or '未確定'}\n\n"
        "状態：確定\n\n"
        f"手配方法：{arrangement}\n\n"
        f"連絡先：{contact}"
    )


def resolve_vendor_handoff_info(vendor: str, contact_type: str = "") -> dict:
    vendor_text = (vendor or "").strip()
    if get_request_pdf_folder_info(vendor_text).get("required"):
        return {"arrangement_method": "依頼書PDF格納", "contact": "担当確認"}
    if "ユナイトサービス" in vendor_text or "ユナイト" in vendor_text:
        return {"arrangement_method": "メール依頼", "contact": "担当確認"}
    if "ソフマップ" in vendor_text:
        return {"arrangement_method": "所定フォーム", "contact": "担当確認"}
    if "宗建リノベーション" in vendor_text:
        return {"arrangement_method": "電話依頼", "contact": "担当確認"}
    if contact_type == "callback" or "翌営業日折り返し" in vendor_text:
        return {"arrangement_method": "折り返し対応", "contact": "担当確認"}
    return {"arrangement_method": "", "contact": ""}


TEAMS_AUTO_ACTIONS = {"依頼書PDF格納済み", "FAX済み", "メール依頼済み", "担当確認依頼済み", "折り返し対応依頼済み", "手配済み"}


def _auto_teams_request_action(vendor: str, contact_type: str = "") -> str:
    vendor_text = (vendor or "").strip()
    if contact_type == "callback" or "翌営業日折り返し" in vendor_text:
        return "折り返し対応依頼済み"
    if get_request_pdf_folder_info(vendor_text).get("required"):
        return "依頼書PDF格納済み"
    if "ユナイトサービス" in vendor_text or "ユナイト" in vendor_text:
        return "FAX済み"
    if "担当エスカ" in vendor_text or "要確認" in vendor_text:
        return "担当確認依頼済み"
    return "手配済み"


def resolve_teams_request_action(form: dict, vendor: str, contact_type: str = "") -> str:
    manual_action = (form.get("teams_action") or "").strip()
    if manual_action:
        return manual_action

    return _auto_teams_request_action(vendor, contact_type)


def form_for_current_teams_generation(form: dict, vendor: str, contact_type: str = "") -> dict:
    current_auto_action = _auto_teams_request_action(vendor, contact_type)
    manual_action = (form.get("teams_action") or "").strip()
    if manual_action in TEAMS_AUTO_ACTIONS and manual_action != current_auto_action:
        form = form.copy()
        form["teams_action"] = ""
    return form


def _build_teams_chat_message(form: dict, vendor: str, contact_type: str = "") -> str:
    rakuteru = (form.get("rakuteru_no") or "").strip()
    case_name = effective_call_line_for_form(form)
    product = (form.get("product") or "").strip()
    send_to = (vendor or "").strip()
    action = resolve_teams_request_action(form, vendor, contact_type)
    operator = (form.get("operator_name") or "").strip()
    lines = []
    if rakuteru:
        lines.append(rakuteru)
    for value in [case_name, product, f"{send_to}へ{action}" if send_to or action else ""]:
        if value:
            lines.append(value)
    if is_double_protect_plan(form.get("warranty_plan", "")):
        lines.append("DP案件・保証金額確認要")
    closing = "ご確認お願いします。"
    if operator:
        closing += operator
    lines.append(closing)
    return "\n".join(lines)


def warranty_report_store_name(form: dict) -> str:
    for field in ("operating_company", "store_company", "store_name", "store_original"):
        value = (form.get(field) or "").strip()
        if value:
            return value
    return ""


def warranty_report_vendor_short_name(vendor: str) -> str:
    vendor_text = (vendor or "").strip()
    if not vendor_text or "担当エスカ" in vendor_text or "要確認" in vendor_text:
        return ""
    if "ユナイト" in vendor_text:
        return "ユナイト"
    if "ソフマップ" in vendor_text:
        return "ソフマップ"
    if "WRT修理センター" in vendor_text:
        return "WRT修理センター"
    if "WRT修理受付センター" in vendor_text:
        return "WRT修理受付センター"
    return vendor_text


def warranty_report_send_method_label(vendor_result: dict, vendor: str = "", form: dict | None = None) -> str:
    vendor_result = vendor_result or {}
    raw_method = (
        vendor_result.get("send_method")
        or vendor_result.get("arrangement_method")
        or vendor_result.get("contact_method")
        or ""
    )
    if not raw_method and vendor:
        raw_method = resolve_teams_request_action(form or {}, vendor, vendor_result.get("contact_type", ""))
    method = str(raw_method or "").strip()
    if "FAX" in method or "ＦＡＸ" in method or "ファックス" in method:
        return "FAX送信済"
    if "メール" in method or "mail" in method.lower():
        return "メール送信済"
    return ""


def build_warranty_report_message(form: dict, decision: dict) -> str:
    rakuteru_no = (form.get("rakuteru_no") or form.get("rakutel_no") or "").strip() or "楽テルNO未入力"
    call_line = get_rakutel_line_name(form.get("call_line", "")) or (form.get("call_line") or "").strip() or "●●"
    content = (form.get("warranty_report_content") or "").strip() or "○○○○○○"
    return "　".join([
        rakuteru_no,
        call_line,
        content,
        "ご確認お願いします",
    ])


def get_warranty_report_missing_items(form: dict) -> list[str]:
    missing = []
    if not (form.get("rakuteru_no") or form.get("rakutel_no") or "").strip():
        missing.append("楽テルNOが未入力です")
    if not (form.get("call_line") or "").strip():
        missing.append("回線名が未選択です")
    if not (form.get("warranty_report_content") or "").strip():
        missing.append("確認内容が未入力です")
    return missing


def build_teams_send_preview_lines(teams_chat_message: str, rakuteru_no: str = "") -> list[str]:
    lines = [line.strip() for line in str(teams_chat_message or "").splitlines() if line.strip()]
    rakuteru_no = (rakuteru_no or "").strip()
    message_lines = list(lines)
    if rakuteru_no and message_lines and message_lines[0] == rakuteru_no:
        message_lines = message_lines[1:]

    preview = [f"楽テルNO：{rakuteru_no or '未入力'}"]
    labels = ["回線", "製品", "対応", "確認文"]
    preview.extend(f"{label}：{value}" for label, value in zip(labels, message_lines[:4]))
    return preview


def _build_after_call_texts(form: dict, warranty_result: dict, repair_type: str,
                            vendor: str, caller_type: str, notes_filled: str,
                            contact_type: str = "") -> dict:
    cost_estimate = form.get("cost_estimate", "")
    rakutel_form = dict(form)
    if caller_type and rakutel_form.get("counterparty_type") == "加入者" and rakutel_form.get("caller_type") == "加入者":
        rakutel_form["counterparty_type"] = caller_type
        rakutel_form["caller_type"] = caller_type
    return {
        "attention_memo": _build_after_call_memo(form, warranty_result, repair_type, vendor, notes_filled, cost_estimate),
        "rakutel_text": _build_rakutel_text(rakutel_form, caller_type, notes_filled),
        "teams_chat_message": _build_teams_chat_message(form, vendor, contact_type),
    }


AFTER_CALL_REGEN_SECTION_FIELDS = {
    "attention_memo": (
        "call_line", "appliance_type", "product", "manufacturer", "store_name",
        "warranty_plan", "warranty_start_date", "warranty_end_date", "product_price",
        "template_code", "template_label",
    ),
    "rakutel_text": (
        "call_line", "appliance_type", "product", "manufacturer", "store_name",
        "model_number", "wrt_no", "customer_name", "phone_number", "contact_phone",
        "operator_name", "extracted_time", "rakuteru_no", "warranty_plan",
        "call_direction", "counterparty_type", "counterparty_detail", "caller_type", "template_code", "template_label",
    ),
    "teams_chat_message": (
        "call_line", "product", "operator_name", "rakuteru_no", "teams_action",
        "warranty_plan", "template_code", "template_label",
    ),
}


def build_after_call_regeneration_context(form: dict, section: str, vendor: str = "",
                                         contact_type: str = "", notes_filled: str = "",
                                         repair_type: str = "") -> dict:
    fields = AFTER_CALL_REGEN_SECTION_FIELDS.get(section, ())
    return {
        "section": section,
        "fields": {field: form.get(field, "") for field in fields},
        "vendor": vendor,
        "contact_type": contact_type,
        "notes_filled": notes_filled,
        "repair_type": repair_type,
    }


def after_call_regeneration_context_hash(context: dict) -> str:
    payload = json.dumps(context, ensure_ascii=False, sort_keys=True, default=str)
    return stable_hash_text(payload, 16)


def get_after_call_regeneration_hash(form: dict, section: str, vendor: str = "",
                                     contact_type: str = "", notes_filled: str = "",
                                     repair_type: str = "") -> str:
    return after_call_regeneration_context_hash(
        build_after_call_regeneration_context(
            form, section, vendor=vendor, contact_type=contact_type,
            notes_filled=notes_filled, repair_type=repair_type,
        )
    )


def mark_after_call_section_regenerated(session_state, section: str, context_hash: str) -> None:
    hashes = dict(session_state.get("_after_call_regenerated_hashes") or {})
    hashes[section] = context_hash
    session_state["_after_call_regenerated_hashes"] = hashes


def after_call_section_needs_regeneration(session_state, section: str, context_hash: str) -> bool:
    hashes = session_state.get("_after_call_regenerated_hashes") or {}
    return bool(hashes.get(section) and hashes.get(section) != context_hash)


def _get_teams_send_body(form: dict) -> str:
    message = (form.get("teams_chat_message") or "").strip()
    if not message:
        return ""
    return teams_plain_text_to_html(
        message,
        bold_first_line=bool((form.get("rakuteru_no") or "").strip()),
    )


def teams_plain_text_to_html(message: str, bold_first_line: bool = False) -> str:
    lines = str(message or "").splitlines()
    html_lines = []
    for index, line in enumerate(lines):
        escaped = _escape_teams_html(line)
        if index == 0 and bold_first_line and line.strip():
            escaped = f"<b>{escaped}</b>"
        html_lines.append(escaped)
    return "<br>\n".join(html_lines)


def _can_send_teams_chat_message(teams_enabled: bool, confirmed: bool, form: dict,
                                 pdf_storage_confirmed: bool = True) -> bool:
    return bool(teams_enabled and confirmed and pdf_storage_confirmed and _get_teams_send_body(form))


def teams_config_unavailable_reasons(config: dict) -> list[str]:
    reasons = []
    if not os.path.exists(TEAMS_CONFIG_PATH) or not config.get("enabled"):
        reasons.append("config/teams_config.json が未作成、または enabled=false")
    if not (config.get("chat_id") or "").strip():
        reasons.append("chat_id が未設定")
    if (config.get("send_mode") or "").strip() not in SUPPORTED_TEAMS_SEND_MODES:
        reasons.append("send_mode は powershell_graph を指定してください")
    if not os.path.exists(TEAMS_SEND_SCRIPT_PATH):
        reasons.append("送信スクリプトが利用できない")
    if config.get("error"):
        reasons.append(str(config["error"]))
    return reasons


def warranty_teams_config_unavailable_reasons(config: dict) -> list[str]:
    reasons = []
    if config.get("warranty_enabled") is False:
        reasons.append("ワランティ送信設定が無効です")
    if not (config.get("warranty_chat_id") or "").strip():
        reasons.append("ワランティ送信先 chat_id が未設定です")
    if (config.get("send_mode") or "").strip() not in SUPPORTED_TEAMS_SEND_MODES:
        reasons.append("send_mode は powershell_graph を指定してください")
    if not os.path.exists(TEAMS_SEND_SCRIPT_PATH):
        reasons.append("Teams/PowerShell送信スクリプトが利用できません")
    if config.get("error"):
        reasons.append(str(config["error"]))
    return reasons


def _warranty_report_body_hash(message: str) -> str:
    body = teams_plain_text_to_html((message or "").strip())
    if not body:
        return ""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _warranty_report_already_sent(session_state, message: str) -> bool:
    body_hash = _warranty_report_body_hash(message)
    return bool(
        session_state.get("warranty_report_sent")
        and body_hash
        and session_state.get("warranty_report_sent_body_hash") == body_hash
    )


def validate_warranty_report_send_request(
    form: dict,
    decision: dict,
    teams_config: dict,
    message: str = "",
    already_sent: bool = False,
) -> list[str]:
    vendor_result = (decision or {}).get("vendor_result", {}) or {}
    vendor = (vendor_result.get("vendor_name") or (decision or {}).get("vendor") or "").strip()
    errors = []
    errors.extend(warranty_teams_config_unavailable_reasons(teams_config))
    if not (message or build_warranty_report_message(form, decision)).strip():
        errors.append("ワランティ送信文を生成できません")
    if already_sent:
        errors.append("同じ内容は送信済みです")
    return list(dict.fromkeys(errors))


def warranty_report_send_status_label(incomplete_reasons: list[str], already_sent: bool,
                                      send_failed: bool = False,
                                      in_progress: bool = False) -> str:
    if in_progress:
        return "送信処理中"
    if already_sent:
        return "送信済み"
    if incomplete_reasons:
        return "送信不可"
    if send_failed:
        return "送信失敗"
    return "送信可能"


def _warranty_report_send_in_progress(session_state, message: str) -> bool:
    body_hash = _warranty_report_body_hash(message)
    return bool(
        session_state.get("warranty_report_send_in_progress")
        and body_hash
        and session_state.get("warranty_report_send_in_progress_body_hash") == body_hash
    )


def _warranty_report_send_requested(session_state, message: str) -> bool:
    body_hash = _warranty_report_body_hash(message)
    return bool(
        session_state.get("warranty_report_send_requested")
        and body_hash
        and session_state.get("warranty_report_send_requested_body_hash") == body_hash
    )


def _warranty_report_last_send_failed(session_state, message: str) -> bool:
    body_hash = _warranty_report_body_hash(message)
    return bool(
        session_state.get("warranty_report_send_failed")
        and body_hash
        and session_state.get("warranty_report_send_failed_body_hash") == body_hash
    )


def _clear_warranty_report_send_requested(session_state) -> None:
    session_state["warranty_report_send_requested"] = False
    session_state["warranty_report_send_requested_body_hash"] = ""


def _clear_warranty_report_send_in_progress(session_state) -> None:
    session_state["warranty_report_send_in_progress"] = False
    session_state["warranty_report_send_in_progress_body_hash"] = ""
    session_state["warranty_report_send_started_at"] = ""


def _clear_stale_warranty_report_send_transient_state(session_state, message: str) -> None:
    body_hash = _warranty_report_body_hash(message)
    requested_hash = session_state.get("warranty_report_send_requested_body_hash")
    in_progress_hash = session_state.get("warranty_report_send_in_progress_body_hash")
    if requested_hash and requested_hash != body_hash:
        _clear_warranty_report_send_requested(session_state)
    if in_progress_hash and in_progress_hash != body_hash:
        _clear_warranty_report_send_in_progress(session_state)


def _mark_warranty_report_send_requested(session_state, message: str,
                                         now: datetime | None = None) -> None:
    now = now or datetime.now()
    body_hash = _warranty_report_body_hash(message)
    session_state["warranty_report_send_requested"] = True
    session_state["warranty_report_send_requested_body_hash"] = body_hash
    session_state["warranty_report_send_in_progress"] = True
    session_state["warranty_report_send_in_progress_body_hash"] = body_hash
    session_state["warranty_report_send_started_at"] = now.strftime("%Y/%m/%d %H:%M:%S")


def _mark_warranty_report_sent(session_state, message: str, result: dict | None = None,
                               now: datetime | None = None) -> None:
    now = now or datetime.now()
    session_state["warranty_report_sent"] = True
    session_state["warranty_report_sent_message"] = (message or "").strip()
    session_state["warranty_report_sent_at"] = now.strftime("%Y/%m/%d %H:%M:%S")
    session_state["warranty_report_sent_body_hash"] = _warranty_report_body_hash(message)
    if result:
        message_id = result.get("message_id") or _extract_teams_message_id(result.get("stdout", ""))
        if message_id:
            session_state["warranty_report_sent_message_id"] = message_id
    session_state["warranty_report_send_failed"] = False
    session_state["warranty_report_send_failed_body_hash"] = ""
    session_state["warranty_report_send_failed_at"] = ""
    session_state["warranty_report_send_error_message"] = ""
    _clear_warranty_report_send_requested(session_state)
    _clear_warranty_report_send_in_progress(session_state)


def _mark_warranty_report_send_failed(session_state, message: str, result: dict,
                                      now: datetime | None = None) -> None:
    now = now or datetime.now()
    session_state["warranty_report_send_failed"] = True
    session_state["warranty_report_send_failed_body_hash"] = _warranty_report_body_hash(message)
    session_state["warranty_report_send_failed_at"] = now.strftime("%Y/%m/%d %H:%M:%S")
    session_state["warranty_report_send_error_message"] = result.get("message", "") or "エラー内容を取得できませんでした"
    _clear_warranty_report_send_requested(session_state)
    _clear_warranty_report_send_in_progress(session_state)


def _teams_case_already_sent(session_state, form: dict) -> bool:
    message = (form.get("teams_chat_message") or "").strip()
    body_hash = _teams_message_body_hash(form)
    sent_body_hash = session_state.get("teams_sent_body_hash")
    return bool(
        session_state.get("teams_sent")
        and message
        and (
            (body_hash and sent_body_hash and sent_body_hash == body_hash)
            or (not sent_body_hash and session_state.get("teams_sent_message") == message)
        )
    )


def _teams_message_body_hash(form: dict) -> str:
    body = _get_teams_send_body(form)
    if not body:
        return ""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _extract_teams_message_id(stdout: str) -> str:
    for line in str(stdout or "").splitlines():
        line = line.strip()
        if line.startswith("SUCCESS"):
            return line.replace("SUCCESS", "", 1).strip()
    return ""


def _teams_last_send_failed(session_state, form: dict) -> bool:
    body_hash = _teams_message_body_hash(form)
    return bool(
        session_state.get("teams_send_failed")
        and body_hash
        and session_state.get("teams_send_failed_body_hash") == body_hash
    )


def _teams_send_in_progress(session_state, form: dict) -> bool:
    body_hash = _teams_message_body_hash(form)
    return bool(
        session_state.get("teams_send_in_progress")
        and body_hash
        and session_state.get("teams_send_in_progress_body_hash") == body_hash
    )


def _teams_send_requested(session_state, form: dict) -> bool:
    body_hash = _teams_message_body_hash(form)
    return bool(
        session_state.get("teams_send_requested")
        and body_hash
        and session_state.get("teams_send_requested_body_hash") == body_hash
    )


def _mark_teams_send_in_progress(session_state, form: dict,
                                 now: datetime | None = None) -> None:
    now = now or datetime.now()
    session_state["teams_send_in_progress"] = True
    session_state["teams_send_in_progress_body_hash"] = _teams_message_body_hash(form)
    session_state["teams_send_started_at"] = now.strftime("%Y/%m/%d %H:%M:%S")


def _mark_teams_send_requested(session_state, form: dict, allow_resend: bool = False,
                               now: datetime | None = None) -> None:
    body_hash = _teams_message_body_hash(form)
    session_state["teams_send_requested"] = True
    session_state["teams_send_requested_body_hash"] = body_hash
    session_state["teams_send_requested_allow_resend"] = bool(allow_resend)
    _mark_teams_send_in_progress(session_state, form, now)


def _clear_teams_send_requested(session_state) -> None:
    session_state["teams_send_requested"] = False
    session_state["teams_send_requested_body_hash"] = ""
    session_state["teams_send_requested_allow_resend"] = False


def _clear_teams_send_in_progress(session_state) -> None:
    session_state["teams_send_in_progress"] = False
    session_state["teams_send_in_progress_body_hash"] = ""
    session_state["teams_send_started_at"] = ""


def _clear_stale_teams_send_transient_state(session_state, form: dict) -> None:
    body_hash = _teams_message_body_hash(form)
    requested_hash = session_state.get("teams_send_requested_body_hash")
    in_progress_hash = session_state.get("teams_send_in_progress_body_hash")
    if requested_hash and requested_hash != body_hash:
        _clear_teams_send_requested(session_state)
    if in_progress_hash and in_progress_hash != body_hash:
        _clear_teams_send_in_progress(session_state)


def _mark_teams_message_sent(session_state, form: dict, now: datetime | None = None,
                             result: dict | None = None) -> None:
    now = now or datetime.now()
    session_state["teams_sent"] = True
    session_state["teams_sent_message"] = (form.get("teams_chat_message") or "").strip()
    session_state["teams_sent_at"] = now.strftime("%Y/%m/%d %H:%M:%S")
    session_state["teams_sent_body_hash"] = _teams_message_body_hash(form)
    if result:
        message_id = result.get("message_id") or _extract_teams_message_id(result.get("stdout", ""))
        if message_id:
            session_state["teams_sent_message_id"] = message_id
    session_state["teams_send_failed"] = False
    session_state["teams_send_failed_message"] = ""
    session_state["teams_send_failed_body_hash"] = ""
    session_state["teams_send_failed_at"] = ""
    session_state["teams_send_error_message"] = ""
    _clear_teams_send_requested(session_state)
    _clear_teams_send_in_progress(session_state)


def _mark_teams_message_send_failed(session_state, form: dict, result: dict,
                                    now: datetime | None = None) -> None:
    now = now or datetime.now()
    session_state["teams_send_failed"] = True
    session_state["teams_send_failed_message"] = (form.get("teams_chat_message") or "").strip()
    session_state["teams_send_failed_body_hash"] = _teams_message_body_hash(form)
    session_state["teams_send_failed_at"] = now.strftime("%Y/%m/%d %H:%M:%S")
    session_state["teams_send_error_message"] = result.get("message", "") or "エラー内容を取得できませんでした"
    _clear_teams_send_requested(session_state)
    _clear_teams_send_in_progress(session_state)


def validate_teams_send_request(
    form: dict,
    teams_enabled: bool,
    send_confirmed: bool,
    action_confirmed: bool,
    pdf_storage_confirmed: bool,
    vendor: str,
    contact_type: str = "",
) -> list[str]:
    errors = []
    message = (form.get("teams_chat_message") or "").strip()
    rakuteru_no = (form.get("rakuteru_no") or "").strip()
    action = resolve_teams_request_action(form, vendor, contact_type)
    vendor_text = (vendor or "").strip()

    if not teams_enabled:
        errors.append("Teams送信設定が未完了です。")
    if not message:
        errors.append("Teams報告文が空です。")
    if not rakuteru_no:
        errors.append("楽テルNOを入力してください。")
    if not action:
        errors.append("Teams報告アクションを入力または確定してください。")
    if not action_confirmed:
        errors.append("Teams報告アクションを確定してください。")
    if not send_confirmed:
        errors.append("送信内容と送信先を確認してください。")
    if get_request_pdf_folder_info(vendor_text).get("required") and not pdf_storage_confirmed:
        errors.append("依頼書PDFを指定フォルダへ格納済みにしてから送信してください。")
    if "担当エスカ" in vendor_text or "要確認" in vendor_text:
        if "依頼書PDF格納済み" in message:
            errors.append("担当エスカ案件のTeams本文が依頼書PDF格納済みになっています。Teams報告文を再生成してください。")
        if "担当確認依頼済み" not in message and "担当確認" not in message:
            errors.append("担当エスカ案件のTeams本文は担当確認依頼済みの内容にしてください。")
    if "drive.google.com" in message.lower():
        errors.append("Teams本文にDrive URLが含まれています。URLを削除してください。")
    return errors


def build_teams_send_incomplete_reasons(
    form: dict,
    teams_config: dict,
    send_confirmed: bool,
    action_confirmed: bool,
    pdf_storage_confirmed: bool,
    vendor: str,
    contact_type: str = "",
    already_sent: bool = False,
) -> list[str]:
    reasons = []
    if teams_config_unavailable_reasons(teams_config):
        reasons.append("Teams設定が未完了")
    if already_sent:
        reasons.append("送信済み（二重送信防止）")

    message = (form.get("teams_chat_message") or "").strip()
    vendor_text = (vendor or "").strip()
    if not message:
        reasons.append("Teams報告文が空")
    if not (form.get("rakuteru_no") or "").strip():
        reasons.append("楽テルNO未入力")
    if not resolve_teams_request_action(form, vendor, contact_type):
        reasons.append("Teams報告アクション未入力")
    if get_request_pdf_folder_info(vendor_text).get("required") and not pdf_storage_confirmed:
        reasons.append("PDF格納チェック未完了")
    if not send_confirmed:
        reasons.append("送信内容確認未完了")
    if not action_confirmed:
        reasons.append("Teams報告アクション確定未完了")
    if "drive.google.com" in message.lower():
        reasons.append("Teams本文にDrive URLが含まれています")
    if "担当エスカ" in vendor_text or "要確認" in vendor_text:
        if "依頼書PDF格納済み" in message:
            reasons.append("担当エスカ案件のTeams本文が依頼書PDF格納済み")
        if "担当確認依頼済み" not in message and "担当確認" not in message:
            reasons.append("担当エスカ案件のTeams本文が担当確認依頼済みではない")

    return list(dict.fromkeys(reasons))


def teams_send_status_label(incomplete_reasons: list[str], already_sent: bool,
                            send_failed: bool = False, in_progress: bool = False) -> str:
    if in_progress:
        return "送信処理中"
    if already_sent:
        return "送信済み"
    if incomplete_reasons:
        return "送信不可"
    if send_failed:
        return "送信失敗"
    return "送信可能"


def load_local_user_settings(path: str | None = None) -> dict:
    settings_path = path or LOCAL_USER_SETTINGS_PATH
    if not os.path.exists(settings_path):
        return {"default_operator_name": ""}
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            return {"default_operator_name": ""}
        return {
            "default_operator_name": str(loaded.get("default_operator_name", "") or "").strip()
        }
    except Exception:
        return {"default_operator_name": ""}


def save_local_user_settings(settings: dict, path: str | None = None) -> dict:
    settings_path = path or LOCAL_USER_SETTINGS_PATH
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    clean = {
        "default_operator_name": str(settings.get("default_operator_name", "") or "").strip()
    }
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return clean


def apply_default_operator_name(form: dict, settings: dict | None = None) -> dict:
    settings = settings or load_local_user_settings()
    default_name = (settings.get("default_operator_name") or "").strip()
    if default_name and not (form.get("operator_name") or "").strip():
        form["operator_name"] = default_name
    return form


def set_show_copy_import(session_state, show: bool) -> None:
    session_state["show_copy_import"] = bool(show)
    # Keep previous keys in sync for older session state/tests.
    session_state["copy_import_expanded"] = bool(show)
    session_state["copy_panel_open"] = bool(show)


def show_copy_import(session_state) -> bool:
    if "show_copy_import" in session_state:
        return bool(session_state.get("show_copy_import"))
    if "copy_import_expanded" in session_state:
        return bool(session_state.get("copy_import_expanded"))
    if "copy_panel_open" in session_state:
        return bool(session_state.get("copy_panel_open"))
    return True


def copy_import_expanded(session_state) -> bool:
    return show_copy_import(session_state)


def close_copy_import_panel(session_state) -> None:
    set_show_copy_import(session_state, False)


def request_case_clear(session_state) -> None:
    session_state["_pending_case_clear"] = True


def process_pending_case_clear(session_state, settings: dict | None = None) -> bool:
    if not session_state.get("_pending_case_clear"):
        return False
    reset_case_session_state(session_state, settings)
    for key in list(session_state.keys()):
        if key == "_pending_case_clear" or key.startswith("clear_case_pending_") or key.startswith("clear_case_done_"):
            del session_state[key]
    session_state["case_memo_global"] = ""
    session_state["form"]["call_memo"] = ""
    return True


CASE_BASIC_WIDGET_PREFIXES = (
    "case_basic_call_line_",
    "case_basic_appliance_type_",
    "case_basic_appliance_category_",
    "case_basic_product_",
    "case_basic_manufacturer_",
    "case_basic_store_name_",
    "call_line_input_",
    "appliance_type_input_",
    "appliance_category_input_",
    "product_input_",
    "manufacturer_input_",
    "store_name_input_",
    "case_basic_product_price_",
)

CASE_BASIC_FIELD_TO_WIDGET_STEM = {
    "call_line": "case_basic_call_line",
    "appliance_category": "case_basic_appliance_category",
    "product": "case_basic_product",
    "manufacturer": "case_basic_manufacturer",
    "store_name": "case_basic_store_name",
    "product_price": "case_basic_product_price",
}

APPLIANCE_CATEGORY_OPTIONS = ["", "家電", "住設（新築）", "住設（既築）", "住設（賃貸）"]


def get_case_basic_revision(session_state) -> int:
    if "case_basic_revision" not in session_state:
        session_state["case_basic_revision"] = 0
    return int(session_state.get("case_basic_revision") or 0)


def bump_case_basic_revision(session_state) -> int:
    revision = get_case_basic_revision(session_state) + 1
    session_state["case_basic_revision"] = revision
    session_state["_case_basic_widget_synced_values"] = {}
    return revision


def case_basic_widget_key(field: str, revision: int | None = None, session_state=None) -> str:
    if revision is None:
        revision = get_case_basic_revision(session_state if session_state is not None else st.session_state)
    return f"{CASE_BASIC_FIELD_TO_WIDGET_STEM[field]}_{revision}"


def case_basic_widget_to_field_map(revision: int | None = None, session_state=None) -> dict:
    if revision is None:
        revision = get_case_basic_revision(session_state if session_state is not None else st.session_state)
    return {
        case_basic_widget_key(field, revision): field
        for field in CASE_BASIC_FIELD_TO_WIDGET_STEM
    }


def request_case_basic_widget_refresh(session_state) -> None:
    bump_case_basic_revision(session_state)
    session_state["_pending_case_basic_widget_refresh"] = True


def process_pending_case_basic_widget_refresh(session_state) -> bool:
    if not session_state.get("_pending_case_basic_widget_refresh"):
        return False
    for key in list(session_state.keys()):
        if str(key).startswith(CASE_BASIC_WIDGET_PREFIXES):
            del session_state[key]
    session_state["_case_basic_widget_synced_values"] = {}
    del session_state["_pending_case_basic_widget_refresh"]
    return True


def reset_case_session_state(session_state, settings: dict | None = None) -> dict:
    bump_case_basic_revision(session_state)
    new_form = apply_default_operator_name(empty_form(), settings)
    session_state["form"] = new_form
    session_state["call_check_manual"] = {}
    session_state["extracted"] = {}
    session_state["pasted_text"] = ""
    set_show_copy_import(session_state, True)
    session_state["master_registration_candidate"] = {}
    for key in [
        "memo_after",
        "memo_after_widget",
        "_memo_after_widget_synced",
        "rakutel_text_display",
        "teams_chat_message_display",
        "teams_send_confirmed",
        "teams_action_confirmed",
        "teams_sent",
        "teams_sent_message",
        "teams_sent_at",
        "teams_sent_body_hash",
        "teams_sent_message_id",
        "teams_send_requested",
        "teams_send_requested_body_hash",
        "teams_send_requested_allow_resend",
        "teams_send_in_progress",
        "teams_send_in_progress_body_hash",
        "teams_send_started_at",
        "teams_send_failed",
        "teams_send_failed_message",
        "teams_send_failed_body_hash",
        "teams_send_failed_at",
        "teams_send_error_message",
        "counterparty_detail_input",
        "warranty_report_content_input",
        "warranty_report_message_display",
        "_warranty_report_source_hash",
        "warranty_report_send_requested",
        "warranty_report_send_requested_body_hash",
        "warranty_report_send_in_progress",
        "warranty_report_send_in_progress_body_hash",
        "warranty_report_send_started_at",
        "warranty_report_sent",
        "warranty_report_sent_message",
        "warranty_report_sent_at",
        "warranty_report_sent_body_hash",
        "warranty_report_sent_message_id",
        "warranty_report_send_failed",
        "warranty_report_send_failed_body_hash",
        "warranty_report_send_failed_at",
        "warranty_report_send_error_message",
        "request_pdf_storage_confirmed",
        "tpl_label_select_after",
        "teams_action_input",
        "_case_basic_widget_synced_values",
        "_after_call_regenerated_hashes",
        "call_memo_input",
        "after_call_memo_display",
        "case_memo_common",
        "call_memo_common_call",
        "call_memo_common_after",
    ]:
        if key in session_state:
            del session_state[key]
    session_state["case_memo_global"] = ""
    for key in list(session_state.keys()):
        if str(key).startswith((
            "manual_check_",
            "now_input_",
            "call_hearing_",
            *CASE_BASIC_WIDGET_PREFIXES,
        )):
            del session_state[key]
    return new_form


def load_teams_config() -> dict:
    """Teams送信設定を読み込む。実設定がない場合のみ環境変数を使う。"""
    config = DEFAULT_TEAMS_CONFIG.copy()
    config_exists = os.path.exists(TEAMS_CONFIG_PATH)

    if config_exists:
        try:
            with open(TEAMS_CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                config.update({k: v for k, v in loaded.items() if k in config})
        except Exception as exc:
            config["enabled"] = False
            config["error"] = f"Teams設定ファイルを読み込めません: {exc}"

    if not config.get("chat_id"):
        env_chat_id = os.environ.get("WRT_TEAMS_CHAT_ID", "").strip()
        if env_chat_id:
            config["chat_id"] = env_chat_id
            if not config_exists:
                config["enabled"] = True

    if not config.get("warranty_chat_id"):
        env_warranty_chat_id = os.environ.get("WRT_WARRANTY_TEAMS_CHAT_ID", "").strip()
        if env_warranty_chat_id:
            config["warranty_chat_id"] = env_warranty_chat_id
            if not config_exists:
                config["warranty_enabled"] = True

    if not config.get("chat_id"):
        config["enabled"] = False

    return config


def is_teams_send_enabled() -> bool:
    config = load_teams_config()
    send_mode = (config.get("send_mode") or "").strip()
    return bool(config.get("enabled") and config.get("chat_id") and send_mode in SUPPORTED_TEAMS_SEND_MODES)


def build_system_info_display() -> dict[str, str]:
    config = load_teams_config()
    send_mode = (config.get("send_mode") or "").strip()
    teams_ready = bool(config.get("enabled") and config.get("chat_id") and send_mode in SUPPORTED_TEAMS_SEND_MODES)
    warranty_ready = bool(config.get("warranty_enabled") and config.get("warranty_chat_id") and send_mode in SUPPORTED_TEAMS_SEND_MODES)
    return {
        "アプリ版": "2026.05.24",
        "最新commit": "d5f6cde",
        "テスト": "557 passed",
        "CSVマスタ": "読込済み",
        "Teams送信": "設定済み" if teams_ready else "未設定",
        "Teamsワランティ送信": "設定済み" if warranty_ready else "未設定",
    }


def send_teams_message_via_powershell(message: str, chat_id_override: str = "") -> dict:
    body = (message or "").strip()
    if not body:
        return {"ok": False, "message": "送信失敗: 送信本文が空です", "stdout": "", "stderr": ""}

    config = load_teams_config()
    chat_id = (chat_id_override or config.get("chat_id") or "").strip()
    if (not chat_id_override and not config.get("enabled")) or not chat_id:
        return {"ok": False, "message": "送信失敗: Teams送信設定が未完了です", "stdout": "", "stderr": ""}
    if (config.get("send_mode") or "").strip() not in SUPPORTED_TEAMS_SEND_MODES:
        return {"ok": False, "message": "送信失敗: send_mode は powershell_graph を指定してください", "stdout": "", "stderr": ""}

    if not os.path.exists(TEAMS_SEND_SCRIPT_PATH):
        return {"ok": False, "message": "送信失敗: PowerShell送信スクリプトが見つかりません", "stdout": "", "stderr": ""}

    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as f:
            f.write(body)
            temp_path = f.name

        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                TEAMS_SEND_SCRIPT_PATH,
                "-ChatId",
                chat_id,
                "-MessageFile",
                temp_path,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        if completed.returncode == 0 and "SUCCESS" in stdout:
            return {
                "ok": True,
                "message": "送信成功",
                "stdout": stdout,
                "stderr": stderr,
                "message_id": _extract_teams_message_id(stdout),
            }
        reason = stderr.strip() or stdout.strip() or f"PowerShell終了コード: {completed.returncode}"
        return {"ok": False, "message": f"送信失敗: {reason}", "stdout": stdout, "stderr": stderr}
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "message": "送信失敗: PowerShell送信がタイムアウトしました",
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
        }
    except Exception as exc:
        return {"ok": False, "message": f"送信失敗: {exc}", "stdout": "", "stderr": ""}
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def append_teams_send_log(result: dict, message: str, chat_name: str,
                          form: dict | None = None, vendor: str = "",
                          teams_action: str = "") -> list:
    if "teams_send_log" not in st.session_state:
        st.session_state.teams_send_log = []
    form = form or {}
    timestamp = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    entry = {
        "sent_at": timestamp,
        "ok": bool(result.get("ok")),
        "chat_name": chat_name,
        "message_preview": (message or "").replace("\n", " ")[:100],
        "error_message": "" if result.get("ok") else result.get("message", ""),
    }
    st.session_state.teams_send_log.insert(0, entry)
    try:
        if not form:
            return st.session_state.teams_send_log
        os.makedirs(os.path.dirname(TEAMS_SEND_LOG_PATH), exist_ok=True)
        file_exists = os.path.exists(TEAMS_SEND_LOG_PATH)
        with open(TEAMS_SEND_LOG_PATH, "a", encoding="utf-8-sig", newline="") as f:
            fieldnames = [
                "timestamp",
                "rakuteru_no",
                "wrt_no",
                "vendor",
                "teams_action",
                "result",
                "error_message",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow({
                "timestamp": timestamp,
                "rakuteru_no": (form.get("rakuteru_no") or "").strip(),
                "wrt_no": (form.get("wrt_no") or "").strip(),
                "vendor": (vendor or "").strip(),
                "teams_action": (teams_action or form.get("teams_action") or "").strip(),
                "result": "success" if result.get("ok") else "failure",
                "error_message": "" if result.get("ok") else result.get("message", ""),
            })
    except Exception as exc:
        entry["log_error"] = str(exc)
    return st.session_state.teams_send_log


# ── 新規: メーカーグループ / エリアグループ CSVローダー ──
def _load_simple_csv(filename: str, required_cols: list) -> pd.DataFrame:
    """priority/enabled フィルタなしのシンプルなCSVローダー（設定系CSV用）。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", filename)
    if not os.path.exists(path):
        return pd.DataFrame(columns=required_cols)
    try:
        df = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
    except Exception:
        return pd.DataFrame(columns=required_cols)
    if any(c not in df.columns for c in required_cols):
        return pd.DataFrame(columns=required_cols)
    return df.fillna("")


@st.cache_data
def load_manufacturer_groups_csv() -> pd.DataFrame:
    return _load_simple_csv("master_manufacturer_groups.csv", _MFR_GROUP_COLS)


@st.cache_data
def load_area_groups_csv() -> pd.DataFrame:
    return _load_simple_csv("master_area_groups.csv", _AREA_GROUP_COLS)


@st.cache_data
def load_script_links_csv() -> pd.DataFrame:
    return _load_simple_csv("master_script_links.csv", _SCRIPT_LINK_COLS)


def lookup_script_link(script_result: dict) -> dict:
    """script_result の sheet_name / part に対応する参照リンクを返す。URL空欄は未登録扱い。"""
    sheet = (script_result.get("sheet_name") or "").strip()
    part = (script_result.get("part") or "").strip()
    if not sheet or not part:
        return {"matched": False, "display_name": "", "url": "", "notes": ""}
    df = load_script_links_csv()
    if df.empty:
        return {"matched": False, "display_name": "", "url": "", "notes": ""}
    for _, row in df.iterrows():
        if (row.get("script_sheet") or "").strip() != sheet:
            continue
        if (row.get("script_part") or "").strip() != part:
            continue
        url = (row.get("url") or "").strip()
        if not url:
            return {"matched": False, "display_name": "", "url": "", "notes": (row.get("notes") or "").strip()}
        return {
            "matched": True,
            "display_name": (row.get("display_name") or "").strip() or "参照リンク",
            "url": url,
            "notes": (row.get("notes") or "").strip(),
        }
    return {"matched": False, "display_name": "", "url": "", "notes": ""}


def split_keywords(value: str) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"[;；\n\r]+", text) if part.strip()]


def _route_text_matches(text: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    target = str(text or "").casefold()
    return any(keyword.casefold() in target for keyword in keywords)


def _append_route_match(matched_by: list[str], label: str) -> None:
    if label not in matched_by:
        matched_by.append(label)


def _script_route_no_match() -> dict:
    return {
        "script_key": "",
        "display_name": "未判定",
        "url": "",
        "confidence": "none",
        "matched_by": [],
        "memo": "該当するトークスクリプト入口が未登録、または判定条件不足",
        "initial_line": "",
        "correction_reason": "",
    }


def _script_initial_line_label(call_line: str) -> str:
    text = str(call_line or "").strip()
    folded = text.casefold()
    if not text:
        return ""
    if any(keyword.casefold() in folded for keyword in ("駆けつけ", "24h", "24時間", "365days")):
        return "駆けつけ"
    if "住設" in text:
        return "住設"
    if "家電" in text:
        return "家電"
    if "0099" in text:
        return "0099"
    line_group = get_line_group(text)
    if line_group in ("家電", "住設"):
        return line_group
    return text


def _script_route_correction_reason(script_key: str, matched_by: list[str], initial_line: str) -> str:
    if not initial_line:
        return ""
    if "販売店" in matched_by and not script_key.startswith("0099_"):
        return "販売店別スクリプトを優先"
    if any(label in matched_by for label in ("製品", "メーカー")) and not script_key.startswith("0099_"):
        return "製品・メーカー別スクリプトを優先"
    return ""


def _script_route_row_result(row: pd.Series, matched_by: list[str], initial_line: str,
                             confidence: str | None = None, memo: str | None = None,
                             display_name: str | None = None) -> dict:
    script_key = (row.get("script_key") or "").strip()
    return {
        "script_key": script_key,
        "display_name": (display_name or (row.get("display_name") or "").strip() or "未判定"),
        "url": (row.get("url") or "").strip(),
        "confidence": (confidence or (row.get("confidence") or "").strip() or "medium"),
        "matched_by": matched_by,
        "memo": (memo if memo is not None else (row.get("memo") or "")).strip(),
        "initial_line": initial_line,
        "correction_reason": _script_route_correction_reason(script_key, matched_by, initial_line),
    }


def _script_route_row_by_key(df: pd.DataFrame, script_key: str) -> pd.Series | None:
    rows = df[df["script_key"].astype(str).str.strip() == script_key]
    if rows.empty:
        return None
    return rows.iloc[0]


def _script_route_jusetsu_display(category: str, phase: str) -> str:
    if category == "住設（新築）" or phase == "新築":
        return "0099回線（住設新築）"
    if category == "住設（既築）" or phase == "既築":
        return "0099回線（住設既築）"
    if category == "住設（賃貸）" or phase == "賃貸":
        return "0099回線（賃貸）"
    return ""


def _script_route_jusetsu_base_display(form: dict) -> str:
    category = (form.get("appliance_category") or "").strip()
    phase = (form.get("housing_phase") or "").strip()
    return _script_route_jusetsu_display(category, phase)


def _script_route_kaketsuke_correction(form: dict, result: dict) -> dict:
    if result.get("script_key") != "0099_kaketsuke":
        return result
    if result.get("initial_line") not in ("住設", "0099"):
        return result
    previous_display = _script_route_jusetsu_base_display(form)
    if not previous_display:
        return result
    result = result.copy()
    result["correction_reason"] = "保証情報貼り付け後、駆けつけ条件に一致"
    result["script_changed"] = True
    result["previous_script_display"] = previous_display
    return result


def _jusetsu_script_route_selection(form: dict, df: pd.DataFrame, initial_line: str) -> dict | None:
    category = (form.get("appliance_category") or "").strip()
    phase = (form.get("housing_phase") or "").strip()
    if initial_line not in ("住設", "0099"):
        return None
    if category == "住設（賃貸）" or phase == "賃貸":
        row = _script_route_row_by_key(df, "0099_rental")
        if row is not None:
            return _script_route_row_result(
                row,
                ["回線名", "案件分類"],
                initial_line,
                "high",
                "住設賃貸用の参照スクリプト。",
            )
    if category == "住設（新築）" or phase == "新築":
        row = _script_route_row_by_key(df, "0099_kaden_new")
        if row is not None:
            return _script_route_row_result(
                row,
                ["回線名", "案件分類"],
                initial_line,
                "high",
                "住設新築用の表示名。参照先URLは0099回線（家電/新築）を流用。",
                "0099回線（住設新築）",
            )
    if category == "住設（既築）" or phase == "既築":
        row = _script_route_row_by_key(df, "0099_used")
        if row is not None:
            return _script_route_row_result(
                row,
                ["回線名", "案件分類"],
                initial_line,
                "high",
                "住設既築用の表示名。参照先URLは0099回線（既築/中古）を流用。",
                "0099回線（住設既築）",
            )
    if initial_line == "住設":
        return {
            "script_key": "needs_jusetsu_type",
            "display_name": "住設区分を選択してください",
            "url": "",
            "confidence": "needs_selection",
            "matched_by": ["回線名"],
            "memo": "案件分類で「住設新築」「住設既築」または「住設賃貸」を選択してください",
            "initial_line": initial_line,
            "correction_reason": "",
        }
    return None


def judge_script_route(form: dict) -> dict:
    """Google Site / Sheets のトークスクリプト入口をマスタから判定する。"""
    form = apply_appliance_category_to_form((form or {}).copy())
    df = load_script_routes()
    if df.empty:
        return _script_route_no_match()

    call_line = " ".join(str(form.get(field) or "") for field in (
        "call_line", "call_line_original", "line_name",
    ))
    initial_line = _script_initial_line_label(call_line)
    appliance_text = " ".join(str(form.get(field) or "") for field in (
        "appliance_category", "appliance_type", "housing_phase",
    ))
    appliance_text = " ".join([appliance_text, initial_line]).strip()
    plan_text = " ".join(str(form.get(field) or "") for field in (
        "warranty_plan", "warranty_type", "store_name", "company_name",
        "case_memo", "call_memo", "symptom_detail", "notes",
        "call_line", "call_line_original", "line_name",
    ))
    store_text = " ".join(str(form.get(field) or "") for field in (
        "store_name", "store_name_original", "dealer_name",
        "call_line", "call_line_original", "line_name",
    ))
    company_text = " ".join(str(form.get(field) or "") for field in (
        "company_name", "store_name", "manufacturer", "manufacturer_original",
        "warranty_plan", "product", "product_original",
        "call_line", "call_line_original", "line_name",
    ))
    product_text = " ".join(str(form.get(field) or "") for field in (
        "product", "product_original", "series", "symptom_detail",
    ))
    repair_type = str(form.get("repair_type") or "").strip()

    for _, row in df.iterrows():
        matched_by: list[str] = []
        line_matched = False
        missing_required_line = False

        line_keywords = split_keywords(row.get("match_line", ""))
        if line_keywords:
            if call_line.strip():
                if not _route_text_matches(call_line, line_keywords):
                    continue
                line_matched = True
                _append_route_match(matched_by, "回線名")
            else:
                missing_required_line = True

        category_keywords = split_keywords(row.get("match_kaden_jusetsu", ""))
        if category_keywords:
            if not _route_text_matches(appliance_text, category_keywords):
                continue
            _append_route_match(matched_by, "案件分類")

        plan_keywords = split_keywords(row.get("match_plan_keywords", ""))
        if plan_keywords:
            if not _route_text_matches(plan_text, plan_keywords):
                continue
            _append_route_match(matched_by, "保証プラン")

        store_keywords = split_keywords(row.get("match_store_keywords", ""))
        if store_keywords:
            if not _route_text_matches(store_text, store_keywords):
                continue
            _append_route_match(matched_by, "販売店")

        company_keywords = split_keywords(row.get("match_company_keywords", ""))
        if company_keywords:
            if not _route_text_matches(company_text, company_keywords):
                continue
            _append_route_match(matched_by, "メーカー")

        product_keywords = split_keywords(row.get("match_product_keywords", ""))
        if product_keywords:
            if not _route_text_matches(product_text, product_keywords):
                continue
            _append_route_match(matched_by, "製品")

        repair_keywords = split_keywords(row.get("match_repair_type", ""))
        if repair_keywords:
            if not _route_text_matches(repair_type, repair_keywords):
                continue
            _append_route_match(matched_by, "修理方針")

        if missing_required_line and not matched_by:
            continue
        confidence = (row.get("confidence") or "").strip() or "medium"
        memo = (row.get("memo") or "").strip()
        if missing_required_line and not line_matched:
            if matched_by == ["案件分類"]:
                continue
            confidence = "medium" if confidence == "high" else confidence
            memo = (memo + " / " if memo else "") + "回線名未入力のため候補扱い"
        if initial_line and matched_by and "回線名" not in matched_by:
            matched_by.insert(0, "回線名")
        result = _script_route_row_result(row, matched_by, initial_line, confidence, memo)
        return _script_route_kaketsuke_correction(form, result)

    jusetsu_selection = _jusetsu_script_route_selection(form, df, initial_line)
    if jusetsu_selection:
        return jusetsu_selection
    return _script_route_no_match()


def _script_guidance_keyword_matches(value: str, keyword: str) -> bool:
    keyword = (keyword or "").strip()
    if not keyword:
        return True
    return keyword in (value or "")


def _script_guidance_script_key_matches(row_key: str, script_result: dict,
                                        script_reference: dict | None = None) -> bool:
    row_key = (row_key or "").strip()
    if not row_key:
        return True
    candidates = [
        script_result.get("sheet_name", ""),
        script_result.get("part", ""),
        script_result.get("display_name", ""),
    ]
    if script_reference:
        candidates.extend([
            script_reference.get("script_type", ""),
            script_reference.get("display", ""),
            script_reference.get("label", ""),
            script_reference.get("link_text", ""),
        ])
    return any(row_key in str(candidate or "") for candidate in candidates)


def select_script_guidance(form: dict, decision: dict,
                           script_reference: dict | None = None) -> dict:
    """通話補助マスタから、現在の判定に合う聴取事項・注意点を1件選ぶ。"""
    df = load_script_guidance_csv()
    if df.empty:
        return {"matched": False, "hearing_items": [], "notes": "", "title": ""}

    script_result = decision.get("script_result", {})
    repair_type = (decision.get("repair_type") or "").strip()
    appliance_type = (form.get("appliance_type") or "").strip()
    product_text = " ".join([
        str(decision.get("normalized_product") or ""),
        str(form.get("product") or ""),
        str(form.get("series") or ""),
        str(form.get("product_original") or ""),
    ])
    manufacturer_text = " ".join([
        str(form.get("manufacturer") or ""),
        str(form.get("manufacturer_original") or ""),
    ])

    for _, row in df.iterrows():
        if not _script_guidance_script_key_matches(row.get("script_key", ""), script_result, script_reference):
            continue
        row_repair_type = (row.get("repair_type") or "").strip()
        if row_repair_type and row_repair_type != repair_type:
            continue
        row_appliance_type = (row.get("appliance_type") or "").strip()
        if row_appliance_type and row_appliance_type != appliance_type:
            continue
        if not _script_guidance_keyword_matches(product_text, row.get("product_keyword", "")):
            continue
        if not _script_guidance_keyword_matches(manufacturer_text, row.get("manufacturer_keyword", "")):
            continue
        return {
            "matched": True,
            "title": (row.get("title") or "").strip() or "スクリプト補助",
            "hearing_items": _split_pipe_items(row.get("hearing_items", "")),
            "notes": (row.get("notes") or "").strip(),
            "official_script_label": (row.get("official_script_label") or "").strip(),
            "official_script_url": (row.get("official_script_url") or "").strip(),
        }
    return {"matched": False, "hearing_items": [], "notes": "", "title": ""}


def load_manufacturer_groups_dict() -> dict:
    """
    master_manufacturer_groups.csv から {group_name: set[manufacturer]} を返す。
    CSVが存在しない/空の場合はハードコード定数 DOMESTIC_PC_MAKERS にフォールバック。
    """
    df = load_manufacturer_groups_csv()
    result: dict = {}
    if not df.empty:
        for _, row in df.iterrows():
            gname = (row.get("group_name") or "").strip()
            mfrs  = (row.get("manufacturers") or "").strip()
            if gname and mfrs:
                result[gname] = set(m.strip() for m in mfrs.split(";") if m.strip())
    # ハードコードフォールバック（国内PCが未定義の場合）
    if "国内PC" not in result:
        result["国内PC"] = DOMESTIC_PC_MAKERS
    return result


def _manufacturer_text_matches_group(text: str, group: set) -> bool:
    target = (text or "").strip().lower()
    if not target:
        return False
    for name in group or set():
        keyword = (name or "").strip().lower()
        if keyword and keyword in target:
            return True
    return False


def infer_pc_manufacturer_type(manufacturer_original: str = "", manufacturer: str = "") -> str:
    """メーカー原文/選択メーカーからPCメーカー区分を推定する。"""
    groups = load_manufacturer_groups_dict()
    domestic = groups.get("国内PC", DOMESTIC_PC_MAKERS)
    foreign = groups.get("海外PC", set())
    candidates = [
        manufacturer_original,
        manufacturer,
        normalize_manufacturer(manufacturer_original),
        normalize_manufacturer(manufacturer),
    ]
    for candidate in candidates:
        if _manufacturer_text_matches_group(candidate, domestic):
            return PC_MANUFACTURER_TYPE_DOMESTIC
    for candidate in candidates:
        if _manufacturer_text_matches_group(candidate, foreign):
            return PC_MANUFACTURER_TYPE_FOREIGN
    return PC_MANUFACTURER_TYPE_UNKNOWN


def resolve_pc_manufacturer_type(form: dict) -> str:
    current = (form.get("pc_manufacturer_type") or "").strip()
    if current in (PC_MANUFACTURER_TYPE_DOMESTIC, PC_MANUFACTURER_TYPE_FOREIGN):
        return current
    return infer_pc_manufacturer_type(
        form.get("manufacturer_original", ""),
        form.get("manufacturer", ""),
    )


def load_area_groups_dict() -> dict:
    """
    master_area_groups.csv から {area_group_name: set[prefecture]} を返す。
    NTT東日本 / NTT西日本 等のエリアグループを保持する。
    """
    df = load_area_groups_csv()
    result: dict = {}
    if not df.empty:
        for _, row in df.iterrows():
            aname = (row.get("area_group") or "").strip()
            prefs = (row.get("prefectures") or "").strip()
            if aname and prefs:
                result[aname] = set(p.strip() for p in prefs.split(";") if p.strip())
    return result


def get_area_group(prefecture: str) -> str:
    """都道府県から master_area_groups.csv のエリアグループ名を返す。"""
    pref = (prefecture or "").strip()
    if not pref:
        return ""
    for area_group, prefs in load_area_groups_dict().items():
        if pref in prefs:
            return area_group
    return ""


def get_product_options() -> list:
    """修理形態ルールCSVから製品selectboxの選択肢を生成する。"""
    options = [""]
    seen = {""}
    df = load_repair_type_rules()
    if not df.empty:
        for value in df["product_keyword"].tolist():
            product = (value or "").strip()
            if product and product not in seen:
                options.append(product)
                seen.add(product)
    fallback = [
        "洗濯機", "冷蔵庫", "エアコン", "給湯器", "温水便座", "多機能便座",
        "温水洗浄便座", "シャワートイレ", "ウォシュレット", "IH",
        "レンジフード", "食器洗い乾燥機", "ドライヤー", "パソコン",
        "タブレット", "掃除機", "炊飯器", "トースター", "カーナビ",
        "ゲーム機", "Airdog", "テレビ", "プリンター", "サウンドバー",
        "プロジェクター", "ホームシアター", "腕時計",
    ]
    for product in fallback:
        if product not in seen:
            options.append(product)
            seen.add(product)
    if PRODUCT_OTHER not in seen:
        options.append(PRODUCT_OTHER)
    return options


def _split_master_aliases(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[;；]", str(value or "")) if item.strip()]


def _call_line_row_names(row) -> list[str]:
    names = []
    for col in ("display_name", "rakutel_line_name", "call_line"):
        value = str(row.get(col) or "").strip()
        if value:
            names.append(value)
    names.extend(_split_master_aliases(row.get("aliases", "")))
    return names


def _call_line_display_name(row) -> str:
    return str(row.get("display_name") or row.get("call_line") or "").strip()


def _call_line_rakutel_name(row) -> str:
    return str(row.get("rakutel_line_name") or row.get("display_name") or row.get("call_line") or "").strip()


def _find_call_line_row(call_line: str) -> dict:
    value = (call_line or "").strip()
    if not value:
        return {}
    df = load_call_lines()
    if df.empty:
        return {}
    folded = value.casefold()
    for _, row in df.iterrows():
        if any(name.casefold() == folded for name in _call_line_row_names(row)):
            return row.to_dict()
    return {}


def normalize_call_line(call_line: str) -> str:
    return get_call_line_display_name(call_line)


def get_call_line_display_name(call_line: str) -> str:
    value = (call_line or "").strip()
    if not value:
        return ""
    row = _find_call_line_row(value)
    if row:
        return _call_line_display_name(row) or value
    return value


def normalize_call_line_for_display(call_line: str) -> str:
    return get_call_line_display_name(call_line)


def get_rakutel_line_name(call_line: str) -> str:
    value = (call_line or "").strip()
    if not value:
        return ""
    row = _find_call_line_row(value)
    if row:
        return _call_line_rakutel_name(row) or get_call_line_display_name(value)
    return value


def build_rakutel_call_header(call_line: str, call_direction: str = "受電") -> str:
    rakutel_line_name = get_rakutel_line_name(call_line)
    if not rakutel_line_name:
        rakutel_line_name = _line_label_for_call_line(call_line).removesuffix("回線")
    if not rakutel_line_name:
        rakutel_line_name = "●●"
    direction = call_direction if call_direction in ("受電", "架電") else "受電"
    if direction == "架電":
        return f"【{rakutel_line_name}回線から架電】"
    return f"【{rakutel_line_name}回線に入電】"


def call_line_master_values_match(master_value: str, call_line: str) -> bool:
    master_norm = normalize_call_line_for_display(master_value)
    value_norm = normalize_call_line_for_display(call_line)
    if master_norm and value_norm and master_norm.casefold() == value_norm.casefold():
        return True
    return (master_value or "").strip().casefold() == (call_line or "").strip().casefold()


def get_call_line_options() -> list:
    """master_call_lines.csv の call_line から回線名候補を生成する。"""
    options = [""]
    seen = {""}
    df = load_call_lines()
    if not df.empty:
        for _, row in df.iterrows():
            val = _call_line_display_name(row)
            if val and val not in seen:
                options.append(val)
                seen.add(val)
    return options


def get_line_group(call_line: str) -> str:
    """回線名からline_group（家電/住設/その他）を返す。"""
    df = load_call_lines()
    if df.empty:
        return ""
    value = (call_line or "").strip().casefold()
    for _, row in df.iterrows():
        if any(name.casefold() == value for name in _call_line_row_names(row)):
            return row.get("line_group", "")
    return ""


def normalize_product_for_select(product: str) -> str:
    """自由入力や抽出結果を製品selectboxの選択肢へ寄せる。"""
    value = (product or "").strip()
    if not value:
        return ""
    options = get_product_options()
    if value in options:
        return value
    normalized = normalize_product("", value)
    if normalized in options:
        return normalized
    return PRODUCT_OTHER


def get_manufacturer_options() -> list:
    """メーカーグループCSVと費用CSVからメーカーselectbox候補を生成する。"""
    options = [""]
    seen = {""}

    df_groups = load_manufacturer_groups_csv()
    if not df_groups.empty:
        for mfrs in df_groups["manufacturers"].tolist():
            for manufacturer in (mfrs or "").split(";"):
                name = (manufacturer or "").strip()
                if name and name not in seen:
                    options.append(name)
                    seen.add(name)

    df_cost = load_cost_rules()
    if not df_cost.empty:
        for value in df_cost["manufacturer_keyword"].tolist():
            name = (value or "").strip()
            if name and name not in seen:
                options.append(name)
                seen.add(name)

    required = [
        "ダイキン", "アイリスオーヤマ", "パナソニック", "富士通",
        "Dell", "CASIO", "ダイソン", "エレクトロラックス・ジャパン",
        MANUFACTURER_OTHER, MANUFACTURER_UNKNOWN,
    ]
    for name in required:
        if name not in seen:
            options.append(name)
            seen.add(name)
    return options


def normalize_manufacturer_for_select(manufacturer: str) -> str:
    value = (manufacturer or "").strip()
    if not value:
        return ""
    normalized = normalize_manufacturer(value)
    options = get_manufacturer_options()
    if normalized in options:
        return normalized
    if value in options:
        return value
    return MANUFACTURER_OTHER


def parse_date_safe(value):
    """受付画面の日付文字列を date に変換する。不正・空欄は None。"""
    if isinstance(value, date):
        return value
    text = (value or "").strip()
    if not text:
        return None
    normalized = text.replace("-", "/")
    m = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日", normalized)
    if m:
        y, mo, d = map(int, m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", normalized)
    if m:
        y, mo, d = map(int, m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    return None


def format_date_yyyy_mm_dd(date_value) -> str:
    return date_value.strftime("%Y/%m/%d") if date_value else ""


def normalize_date_text(value: str) -> str:
    return format_date_yyyy_mm_dd(parse_date_safe(value))


def form_date_text_to_date(value):
    """フォーム保持文字列を date_input 用の date に変換する。空欄・不正は None。"""
    return parse_date_safe(value)


def date_to_form_date_text(value) -> str:
    """date_input の date をフォーム保持用 YYYY/MM/DD 文字列に変換する。"""
    return format_date_yyyy_mm_dd(parse_date_safe(value))


def determine_warranty_status(form: dict, today=None) -> dict:
    """保証開始日・終了日から、WRTで受付へ進めるかを判定する。"""
    today = today or date.today()
    start_raw = form.get("warranty_start_date", "")
    end_raw = form.get("warranty_end_date", "")
    start_date = parse_date_safe(start_raw)
    end_date = parse_date_safe(end_raw)

    unknown = {
        "warranty_status": "unknown",
        "can_accept": False,
        "severity": "warning",
        "title": "保証期間未確認",
        "message": "保証開始日・保証終了日が確認できないため、受付可否を確定できません。保証期間を確認してください。",
        "required_questions": "保証開始日・保証終了日を確認してください",
        "start_date": start_date,
        "end_date": end_date,
    }
    if not start_date or not end_date:
        return unknown

    if today < start_date:
        return {
            "warranty_status": "before_start",
            "can_accept": False,
            "severity": "warning",
            "title": "保証開始日前",
            "message": "保証開始日前のため、WRTでの修理受付はできません。メーカー保証または販売店・メーカー窓口をご案内してください。",
            "required_questions": "保証開始日とメーカー保証期間を確認してください",
            "start_date": start_date,
            "end_date": end_date,
        }
    if today > end_date:
        return {
            "warranty_status": "expired",
            "can_accept": False,
            "severity": "error",
            "title": "保証期間終了",
            "message": "保証期間終了後のため、WRTでの修理受付はできません。受付不可として案内してください。",
            "required_questions": "",
            "start_date": start_date,
            "end_date": end_date,
        }
    return {
        "warranty_status": "active",
        "can_accept": True,
        "severity": "ok",
        "title": "保証期間内",
        "message": "保証期間内のため、受付判定へ進めます。",
        "required_questions": "",
        "start_date": start_date,
        "end_date": end_date,
    }


def build_warranty_guidance(warranty_result: dict) -> str:
    status = warranty_result.get("warranty_status", "unknown")
    if status == "before_start":
        return "メーカー保証または販売店・メーカー窓口へ誘導"
    if status == "active":
        return "受付判定へ進む"
    if status == "expired":
        return "保証期間終了のため受付不可"
    return "保証開始日・保証終了日を確認"


def warranty_acceptance_label(warranty_result: dict) -> str:
    status = warranty_result.get("warranty_status", "unknown")
    if status == "active":
        return "受付可"
    if status in ("before_start", "expired"):
        return "受付不可"
    return "要確認"


@st.cache_data
def load_master_products() -> pd.DataFrame:
    """legacy: data/master_products.csv（後方互換・主判定には使わない）"""
    return _load_csv("master_products.csv", _MASTER_REQUIRED_COLS)


# ============================================================
# コア照合ヘルパー
# ============================================================
def _kw_match(keyword: str, target: str) -> bool:
    """
    keyword が空 → ワイルドカード（常に True）。
    そうでなければ keyword.lower() in target.lower() で包含チェック。
    regex / str.contains 禁止。通常の文字列包含のみ。
    """
    kw = (keyword or "").strip()
    if not kw:
        return True  # 空キーワード = ワイルドカード
    tg = (target or "").strip()
    return kw.lower() in tg.lower()


def _split_rule_keywords(keyword: str) -> list[str]:
    return [part.strip() for part in re.split(r"[;|｜、,\n]+", str(keyword or "")) if part.strip()]


def _kw_any_match(keyword: str, target: str) -> bool:
    parts = _split_rule_keywords(keyword)
    if not parts:
        return True
    return any(part.lower() in (target or "").lower() for part in parts)


def _repair_rule_reason(row) -> str:
    return (
        (row.get("reason") or "").strip()
        or (row.get("notes") or "").strip()
        or "master_repair_type_rules.csv に一致"
    )


def _rule_flag(row, field: str) -> bool:
    return str(row.get(field, "") or "").strip() == "1"


def is_missing_manufacturer_value(value: str) -> bool:
    return not (value or "").strip() or (value or "").strip() in (MANUFACTURER_OTHER, MANUFACTURER_UNKNOWN)


# ============================================================
# テキスト抽出
# ============================================================
_VALUE_SEP_PATTERN = r"(?:[ \t　]*[:：][ \t　]*|[ \t　]+|\n[ \t　]*)"


def make_label_pattern(labels: list) -> str:
    return r"(?:%s)" % "|".join(re.escape(label) for label in labels)


def extract_by_labels(text: str, labels: list, value_pattern: str = r"([^\t\n]+)"):
    pattern = make_label_pattern(labels) + _VALUE_SEP_PATTERN + value_pattern
    m = re.search(pattern, text, flags=re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _is_invalid_address(value: str) -> bool:
    compact = re.sub(r"[ \t　]+", "", value or "").strip()
    if not compact:
        return True
    return bool(re.fullmatch(r"(?:〒)?[-ー－]*", compact))


def _extract_section(text: str, start_label: str, end_labels: list) -> str:
    start = re.search(re.escape(start_label), text)
    if not start:
        return ""
    section_start = start.end()
    section_end = len(text)
    for label in end_labels:
        m = re.search(re.escape(label), text[section_start:])
        if m:
            section_end = min(section_end, section_start + m.start())
    return text[section_start:section_end]


def extract_customer_address(text: str) -> str:
    """顧客住所を優先抽出し、販売店情報の無効住所は採用しない。"""
    candidates = [
        extract_by_labels(text, ["ご住所"], r"([^\t\n]+)"),
    ]

    customer_section = _extract_section(
        text,
        "顧客情報",
        ["製品情報", "販売店情報", "保証情報", "■プラン詳細"],
    )
    if customer_section:
        candidates.extend([
            extract_by_labels(customer_section, ["ご住所"], r"([^\t\n]+)"),
            extract_by_labels(customer_section, ["住所", "お客様住所"], r"([^\t\n]+)"),
        ])

    candidates.append(extract_by_labels(text, ["お客様住所"], r"([^\t\n]+)"))
    candidates.append(extract_by_labels(text, ["住所"], r"([^\t\n]+)"))

    for candidate in candidates:
        candidate = (candidate or "").strip()
        if candidate and not _is_invalid_address(candidate):
            return candidate
    return ""


def _is_valid_phone_number(value: str) -> bool:
    return bool(re.search(r"\d", value or ""))


def extract_customer_phone_number(text: str) -> str:
    """顧客電話番号を優先抽出し、販売店情報の -- は採用しない。"""
    candidates = []
    customer_section = _extract_section(
        text,
        "顧客情報",
        ["製品情報", "販売店情報", "保証情報", "■プラン詳細"],
    )
    if customer_section:
        candidates.extend([
            extract_by_labels(customer_section, ["お電話番号", "電話番号", "お電話", "TEL", "Tel"], r"([0-9\-()（）]+)"),
        ])

    candidates.extend([
        extract_by_labels(text, ["お電話番号", "お電話", "TEL", "Tel"], r"([0-9\-()（）]+)"),
        extract_by_labels(text, ["電話番号"], r"([0-9\-()（）]+)"),
    ])

    for candidate in candidates:
        candidate = (candidate or "").strip()
        if candidate and _is_valid_phone_number(candidate):
            return candidate
    return ""


def extract_fields_from_pasted_text(text: str) -> dict:
    """貼り付けテキストから正規表現で各フィールドを抽出する。"""
    result = {}
    date_pattern = r"([0-9]{4}[/-][0-9]{1,2}[/-][0-9]{1,2}|[0-9]{4}年[0-9]{1,2}月[0-9]{1,2}日)"
    field_specs = {
        "operating_company": (["運営会社"], r"([^\t\n]+)"),
        "store_name": (["販売店", "店舗名", "購入店舗", "販売店名"], r"([^\t\n]+)"),
        "plan": (["プラン"], r"([^\t\n]+)"),
        "warranty_period": (["保証期間"], r"([^\t\n]+)"),
        "warranty_start_date": (["保証開始日", "保証開始", "保証開始年月日"], date_pattern),
        "warranty_end_date": (["保証終了日", "保証終了", "保証満了日", "保証満了年月日"], date_pattern),
        "payment_method": (["支払方法"], r"([^\t\n]+)"),
        "contract_status": (["ステータス"], r"([^\t\n]+)"),
        "customer_code": (["お客様コード"], r"([^\t\n]+)"),
        "customer_name": (["お名前（漢字）", "お名前", "氏名", "お客様名"], r"([^\t\n]+)"),
        "customer_name_kana": (["お名前（カナ）"], r"([^\t\n]+)"),
        "phone_number": (["お電話番号", "電話番号", "お電話", "TEL", "Tel"], r"([0-9\-()（）]+)"),
        "postal_code": (["郵便番号"], r"([0-9\-]+)"),
        "wrt_no": (["WRT-NO", "WRT No", "WRT番号", "受付番号"], r"([^\t\n]+)"),
        "payment_amount": (["支払金額"], r"([0-9,]+円)"),
        "product_price": (["商品価格", "商品金額", "購入金額", "税込価格"], r"([0-9,]+円)"),
        "genre": (["ジャンル"], r"([^\t\n]+)"),
        "category": (["分類"], r"([^\t\n]+)"),
        "series": (["シリーズ", "商品名", "製品名", "品目"], r"([^\t\n]+)"),
        "manufacturer": (["メーカー", "メーカー名", "製造メーカー"], r"([^\t\n]+)"),
        "model_number": (["型番", "品番", "モデル", "モデル番号"], r"([^\t\n\s]+)"),
        "serial_number": (["製造番号"], r"([^\t\n]+)"),
    }
    for key, (labels, value_pattern) in field_specs.items():
        val = extract_by_labels(text, labels, value_pattern)
        if key in ("warranty_start_date", "warranty_end_date"):
            val = normalize_date_text(val) or val
        if val:
            result[key] = val
    phone_number = extract_customer_phone_number(text)
    if phone_number:
        result["phone_number"] = phone_number
    addr = extract_customer_address(text)
    if addr:
        result["address"] = addr
    addr = result.get("address", "")
    if addr:
        result["prefecture"] = extract_prefecture(addr)
    return result


# ============================================================
# 正規化（フォールバック用に保持）
# ============================================================
def extract_prefecture(address: str) -> str:
    for pref in PREFECTURES:
        if address.startswith(pref):
            return pref
    for pref in PREFECTURES:
        if pref in address:
            return pref
    return ""


def normalize_product(series: str, product: str = "") -> str:
    """既存ロジックフォールバック。CSVエイリアスにヒットしない場合に使う。"""
    mapping = {
        "ドライヤー・ヘアアイロン": "ドライヤー", "ドライヤー": "ドライヤー",
        "ヘアアイロン": "ドライヤー", "洗濯機": "洗濯機", "冷蔵庫": "冷蔵庫",
        "エアコン": "エアコン", "パソコン": "パソコン", "PC": "パソコン",
        "プリンター": "プリンター", "カーナビ": "カーナビ", "電子レンジ": "電子レンジ",
        "食器洗い乾燥機": "食器洗い乾燥機", "食洗機": "食器洗い乾燥機",
        "エコキュート": "エコキュート", "ガス給湯器": "ガス給湯器",
        "石油給湯器": "石油給湯器", "ハイブリッド給湯器": "ハイブリッド給湯器",
        "エネファーム": "エネファーム", "電気温水器": "電気温水器",
        "電気暖房温水ボイラー": "電気暖房温水ボイラー",
        "給湯器": "給湯器", "温水便座": "温水便座", "多機能便座": "多機能便座",
        "温水洗浄便座": "温水洗浄便座", "シャワートイレ": "シャワートイレ",
        "ウォシュレット": "ウォシュレット", "掃除機": "掃除機",
        "炊飯器": "炊飯器", "トースター": "トースター", "ゲーム機": "ゲーム機",
        "テレビ": "テレビ", "タブレット": "タブレット",
        "腕時計（クォーツ）": "腕時計", "腕時計": "腕時計",
        "クォーツ": "腕時計", "時計": "腕時計",
        "デジタルカメラ": "デジカメ", "デジカメ": "デジカメ",
        "一眼レフカメラ": "一眼レフカメラ", "ビデオカメラ": "ビデオカメラ",
        "電子ピアノ（脚なし）": "電子ピアノ脚なし", "電子ピアノ脚なし": "電子ピアノ脚なし",
        "ピアノ（脚なし）": "ピアノ脚なし", "ピアノ脚なし": "ピアノ脚なし",
        "ミライウェーブ スーパーミニ": "パワーウエーブ",
        "パワーウエーブ ミニ": "パワーウエーブ",
        "パワーウエーブ ダブルスリム": "パワーウエーブ",
        "3in1 パワートレーナー": "パワーウエーブ",
        "パワーウエーブヒーロー": "パワーウエーブ",
        "セブン パワーウェーブ": "パワーウエーブ",
        "AVアンプ": "AV製品", "CDプレーヤー": "AV製品", "ホームシアター": "AV製品",
        "ブルーレイレコーダー": "ブルーレイレコーダー", "DVDレコーダー": "DVDレコーダー",
        "ドアホン": "ドアホン", "ドライブレコーダー": "ドライブレコーダー",
    }
    for k, v in mapping.items():
        if k in (series or ""):
            return v
    for k, v in mapping.items():
        if k in (product or ""):
            return v
    return series or product or ""


def normalize_manufacturer(manufacturer: str) -> str:
    mapping = {
        "パナソニック": "パナソニック", "Panasonic": "パナソニック",
        "ダイキン": "ダイキン", "DAIKIN": "ダイキン",
        "アイリスオーヤマ": "アイリスオーヤマ",
        "エレクトロラックス": "エレクトロラックス・ジャパン",
        "ダイソン": "ダイソン", "Dyson": "ダイソン",
        "シャープ": "シャープ", "SHARP": "シャープ",
        "日立": "日立", "東芝": "東芝", "三菱": "三菱",
        "富士通": "富士通", "ソニー": "ソニー", "SONY": "ソニー",
        "Roland": "ローランド", "ローランド": "ローランド",
        "FITプロジェクト": "FITプロジェクト", "TKクリエイト": "TKクリエイト",
        "パイオニア": "パイオニア", "PIONEER": "パイオニア",
        "CASIO": "CASIO", "カシオ計算機": "CASIO", "カシオ": "CASIO",
        "ヤマダ": "ヤマダ", "山善": "山善",
    }
    for k, v in mapping.items():
        if k.lower() in (manufacturer or "").lower():
            return v
    return manufacturer or ""


def apply_extracted_fields_to_form(extracted: dict, current_form: dict) -> dict:
    """抽出結果をフォーム辞書にマッピングして返す。"""
    mapping = {
        "plan": "warranty_plan", "warranty_start_date": "warranty_start_date",
        "warranty_end_date": "warranty_end_date", "customer_code": "customer_code",
        "customer_name": "customer_name", "phone_number": "phone_number",
        "address": "address", "prefecture": "prefecture",
        "wrt_no": "wrt_no", "product_price": "product_price",
        "manufacturer": "manufacturer", "model_number": "model_number",
        "series": "series", "store_name": "store_name",
        "genre": "genre", "category": "category",
        "operating_company": "operating_company",
    }
    form = current_form.copy()
    for src, dst in mapping.items():
        if src in extracted and extracted[src]:
            if dst == "prefecture" and extracted[src] not in PREFECTURES:
                form[dst] = ""
                continue
            if dst in ("warranty_start_date", "warranty_end_date"):
                form[dst] = normalize_date_text(extracted[src]) or extracted[src]
                continue
            form[dst] = extracted[src]
    raw_series = extracted.get("series", "")
    if raw_series:
        form["product_original"] = raw_series
        form["product"] = normalize_product_for_select(normalize_product(raw_series, ""))
    elif extracted.get("category") or extracted.get("genre"):
        raw_product_text = extracted.get("category") or extracted.get("genre")
        form["product_original"] = raw_product_text
        form["product"] = normalize_product_for_select(normalize_product(raw_product_text, ""))
    elif form.get("product"):
        form["product"] = normalize_product_for_select(form.get("product"))
    raw_mfr = extracted.get("manufacturer", "")
    if raw_mfr:
        form["manufacturer_original"] = raw_mfr
        form["manufacturer"] = normalize_manufacturer_for_select(raw_mfr)
    elif form.get("manufacturer"):
        form["manufacturer"] = normalize_manufacturer_for_select(form.get("manufacturer"))
    if form.get("product") == "パソコン":
        form["pc_manufacturer_type"] = infer_pc_manufacturer_type(
            form.get("manufacturer_original", ""),
            form.get("manufacturer", ""),
        )
    genre = extracted.get("genre", "")
    if genre or extracted.get("category") or extracted.get("plan"):
        form["appliance_type"] = infer_appliance_type_from_form(form, form.get("appliance_type"))
        form = apply_appliance_category_to_form(form)
    return form


# ============================================================
# Layer 1: 製品名エイリアス正規化
# ============================================================
def normalize_product_from_alias(form: dict) -> dict:
    """
    master_product_alias.csv を使って製品名を正規化する。
    照合対象: series + product + model_number を連結したテキスト。
    ヒットしない場合は既存の normalize_product() でフォールバック。
    """
    df = load_alias_csv()
    series  = (form.get("series") or "").strip()
    product = (form.get("product") or "").strip()
    model   = (form.get("model_number") or "").strip()
    target  = " ".join([series, product, model]).strip()

    if not df.empty:
        for _, row in df.iterrows():
            kw = (row.get("keyword") or "").strip()
            if not kw:
                continue
            if kw.lower() in target.lower():
                return {
                    "matched": True,
                    "normalized_product": (row.get("normalized_product") or "").strip(),
                    "product_group":      (row.get("product_group") or "").strip(),
                    "keyword":            kw,
                    "priority":           int(row.get("priority", 999)),
                    "csv_name":           "master_product_alias.csv",
                    "notes":              (row.get("notes") or "").strip(),
                }

    # フォールバック: 既存ロジック
    fallback = normalize_product(series, product)
    return {
        "matched":            False,
        "normalized_product": fallback,
        "product_group":      "",
        "keyword":            "",
        "priority":           None,
        "csv_name":           "",
        "notes":              "",
    }


# ============================================================
# Layer 2: 修理形態判定
# ============================================================
def determine_repair_type_from_rules(form: dict) -> dict:
    """
    master_repair_type_rules.csv を使って修理形態を判定する。
    空カラム = ワイルドカード。全非空条件の AND 一致。
    """
    df = load_repair_type_rules()
    product      = (form.get("product") or "").strip()
    manufacturer = (form.get("manufacturer") or "").strip()
    model        = (form.get("model_number") or "").strip()
    condition    = " ".join([
        (form.get("extra_condition") or "").strip(),
        (form.get("appliance_category") or "").strip(),
        (form.get("appliance_type") or "").strip(),
        (form.get("housing_phase") or "").strip(),
        (form.get("prefecture") or "").strip(),
        (form.get("area_group") or "").strip(),
    ]).strip()

    if not df.empty:
        for _, row in df.iterrows():
            if str(row.get("active", "")).strip() == "0":
                continue
            pk  = (row.get("product_keyword") or "").strip()
            mk  = (row.get("manufacturer_keyword") or "").strip()
            mok = (row.get("model_keyword") or "").strip()
            ck  = (row.get("condition_keyword") or "").strip()

            if not _kw_any_match(pk, product):      continue
            if not _kw_any_match(mk, manufacturer): continue
            if not _kw_any_match(mok, model):       continue
            if not _kw_any_match(ck, condition):    continue

            matched_kw = pk or mk or mok or ck or "(条件なし)"
            certainty = (row.get("certainty") or "").strip()
            manufacturer_required = _rule_flag(row, "manufacturer_required")
            model_required = _rule_flag(row, "model_required")
            manual_required = _rule_flag(row, "manual_required")
            missing_fields = []
            if manufacturer_required and is_missing_manufacturer_value(manufacturer):
                missing_fields.append("manufacturer")
            if model_required and not model:
                missing_fields.append("model_number")
            needs_confirmation = (
                str(row.get("needs_confirmation", "0")).strip() == "1"
                or certainty == "needs_check"
                or bool(missing_fields)
            )
            repair_type = (row.get("repair_type") or "要確認").strip()
            if missing_fields and repair_type != "要確認":
                repair_type = "要確認"
            reason = _repair_rule_reason(row)
            if missing_fields:
                missing_labels = "・".join(field_label(field) for field in missing_fields)
                reason = f"{reason}（{missing_labels}確認が必要）"
            return {
                "matched":           True,
                "repair_type":       repair_type,
                "needs_confirmation": needs_confirmation,
                "manufacturer_required": manufacturer_required,
                "model_required": model_required,
                "manual_required": manual_required,
                "missing_fields": missing_fields,
                "keyword":           matched_kw,
                "priority":          int(row.get("priority", 999)),
                "csv_name":          "master_repair_type_rules.csv",
                "notes":             (row.get("notes") or "").strip(),
                "certainty":         certainty,
                "reason":            reason,
                "memo_note":         (row.get("memo_note") or "").strip(),
                "rakutel_repair_type_override": (row.get("rakutel_repair_type_override") or "").strip(),
            }

    return {
        "matched": False, "repair_type": "", "needs_confirmation": False,
        "manufacturer_required": False, "model_required": False, "manual_required": False,
        "missing_fields": [],
        "keyword": "", "priority": None, "csv_name": "", "notes": "",
        "certainty": "", "reason": "", "memo_note": "", "rakutel_repair_type_override": "",
    }


# ── 既存ロジック（フォールバック・削除しない） ──
VISIT_REPAIR_PRODUCTS  = {
    "洗濯機", "冷蔵庫", "エアコン", "給湯器", "温水便座", "多機能便座",
    "温水洗浄便座", "シャワートイレ", "ウォシュレット", "食器洗い乾燥機",
    "エコキュート", "ガス給湯器", "石油給湯器", "ハイブリッド給湯器",
    "エネファーム", "電気温水器", "電気暖房温水ボイラー",
}
CARRY_IN_REPAIR_PRODUCTS = {
    "ドライヤー", "パソコン", "プリンター", "カーナビ", "ゲーム機",
    "掃除機", "炊飯器", "トースター", "タブレット"
}
CONFIRM_REPAIR_PRODUCTS = {"テレビ", "電子レンジ", "腕時計"}
WATCH_CONFIRMATION_REASON_MARKERS = ("腕時計ルール未登録", "腕時計はSV/担当確認")


def is_watch_repair_confirmation(form: dict, repair_type: str, repair_result: dict = None) -> bool:
    """腕時計の「要確認」を、製品不明ではなくSV/担当確認として扱う。"""
    if (form.get("product") or "").strip() != "腕時計" or repair_type != "要確認":
        return False
    notes = ((repair_result or {}).get("notes") or "").strip()
    return any(marker in notes for marker in WATCH_CONFIRMATION_REASON_MARKERS)


def determine_repair_type(form: dict) -> str:
    product = form.get("product", "")
    if product in VISIT_REPAIR_PRODUCTS:   return "出張修理"
    if product in CARRY_IN_REPAIR_PRODUCTS: return "持込修理"
    if product in CONFIRM_REPAIR_PRODUCTS:  return "要確認"
    if form.get("appliance_type") == "住設": return "出張修理"
    return "要確認"


# ============================================================
# Layer 3: 概算費用判定
# ============================================================
def _pending_cost_result(required_questions: str, internal_note: str,
                         customer_notice: str = "確認後にご案内します",
                         keyword: str = "安全ガード", missing_fields: list = None) -> dict:
    return {
        "matched": True,
        "cost_estimate": "未確定",
        "can_announce_cost": False,
        "needs_escalation": False,
        "cost_status": "pending",
        "guidance_scope": "always",
        "required_questions": required_questions,
        "customer_notice": customer_notice,
        "internal_note": internal_note,
        "missing_fields": missing_fields or [],
        "keyword": keyword,
        "priority": 0,
        "csv_name": "app.py safety guard",
        "notes": internal_note,
    }


def guard_pending_cost_before_rules(form: dict):
    """CSV/旧ロジックより優先する、誤案内防止の最終安全ガード。"""
    product = (form.get("product") or "").strip()
    manufacturer = normalize_manufacturer(form.get("manufacturer", "")).strip()
    condition = (form.get("extra_condition") or "").strip()
    manufacturer_needs_confirmation = manufacturer in (MANUFACTURER_OTHER, MANUFACTURER_UNKNOWN)
    pc_manufacturer_type = (form.get("pc_manufacturer_type") or PC_MANUFACTURER_TYPE_UNKNOWN).strip()

    if product == "エアコン" and (not manufacturer or manufacturer_needs_confirmation):
        return _pending_cost_result(
            "メーカーを確認してください",
            "エアコンはメーカー未確認時に概算費用を案内しない",
            keyword="エアコンメーカー未確認ガード",
            missing_fields=["manufacturer"],
        )
    if product == "エアコン" and manufacturer == "ダイキン" and not condition:
        return _pending_cost_result(
            "家庭用/業務用を確認してください",
            "ダイキンエアコンは家庭用/業務用未確認時に概算費用を案内しない",
            keyword="ダイキンエアコン補足条件未確認ガード",
            missing_fields=["extra_condition"],
        )
    if product == "パソコン" and pc_manufacturer_type == PC_MANUFACTURER_TYPE_UNKNOWN:
        return _pending_cost_result(
            "国内メーカー/海外メーカーを確認してください",
            "パソコンはメーカー未確認時に概算費用を案内しない",
            keyword="パソコンメーカー区分未確認ガード",
            missing_fields=["pc_manufacturer_type"],
        )
    return None


def _confirmed_cost_result(cost_estimate: str, keyword: str, internal_note: str = "") -> dict:
    return {
        "matched": True,
        "cost_estimate": cost_estimate,
        "can_announce_cost": True,
        "needs_escalation": False,
        "cost_status": "confirmed",
        "guidance_scope": "always",
        "required_questions": "",
        "customer_notice": "",
        "internal_note": internal_note,
        "missing_fields": [],
        "keyword": keyword,
        "priority": 0,
        "csv_name": "master_cost_rules.csv",
        "notes": internal_note,
    }


def determine_cost_from_rules(form: dict, repair_type: str) -> dict:
    """
    master_cost_rules.csv から概算費用ルールを判定する（拡張版）。

    拡張機能:
    - required_fields: 列挙フィールドが未入力なら cost_status="pending" を返す
    - cost_status: confirmed / pending / escalation
    - guidance_scope: always / eu_asked_only / internal / escalation_only
    - required_questions / customer_notice / internal_note も返す
    """
    df = load_cost_rules()
    mfr_groups   = load_manufacturer_groups_dict()
    product      = (form.get("product") or "").strip()
    manufacturer = (form.get("manufacturer") or "").strip()
    condition    = (form.get("extra_condition") or "").strip()
    norm_mfr     = normalize_manufacturer(manufacturer)

    guarded = guard_pending_cost_before_rules(form)
    if guarded:
        return guarded

    pc_manufacturer_type = (form.get("pc_manufacturer_type") or PC_MANUFACTURER_TYPE_UNKNOWN).strip()
    if product == "パソコン" and pc_manufacturer_type == PC_MANUFACTURER_TYPE_DOMESTIC:
        return _confirmed_cost_result(
            "2,000円～9,000円",
            "国内PC",
            "PCメーカー区分=国内メーカー",
        )
    if product == "パソコン" and pc_manufacturer_type == PC_MANUFACTURER_TYPE_FOREIGN:
        return _confirmed_cost_result(
            "12,000円前後",
            "海外PC",
            "PCメーカー区分=海外メーカー",
        )

    _no_match = {
        "matched": False, "cost_estimate": "", "can_announce_cost": True,
        "needs_escalation": False, "cost_status": "confirmed",
        "guidance_scope": "always", "required_questions": "",
        "customer_notice": "", "internal_note": "", "missing_fields": [],
        "keyword": "", "priority": None, "csv_name": "", "notes": "",
    }

    if df.empty:
        return _no_match

    for _, row in df.iterrows():
        pk  = (row.get("product_keyword") or "").strip()
        mk  = (row.get("manufacturer_keyword") or "").strip()
        mg  = (row.get("manufacturer_group") or "").strip()
        ck  = (row.get("condition_keyword") or "").strip()
        rt  = (row.get("repair_type") or "").strip()

        # repair_type: 完全一致（空=ワイルドカード）
        if rt and rt != repair_type:
            continue
        if not _kw_match(pk, product):      continue
        if not _kw_match(mk, manufacturer): continue
        if not _kw_match(ck, condition):    continue
        # manufacturer_group チェック（CSVロード済みグループ辞書を使用）
        if mg:
            group_set = mfr_groups.get(mg)
            if group_set is not None and norm_mfr not in group_set:
                continue  # グループに含まれないメーカーはスキップ
            # 未定義グループは無視（ワイルドカード扱い）

        matched_kw = pk or mk or mg or ck or rt or "(汎用)"

        # ── required_fields チェック ──────────────────────────────
        req_fields_str = (row.get("required_fields") or "").strip()
        if req_fields_str:
            missing = [
                f for f in req_fields_str.split(";")
                if not (form.get(f.strip()) or "").strip()
            ]
            if missing:
                # 必須フィールドが未入力 → pending を返す
                return {
                    "matched":            True,
                    "cost_estimate":      "未確定",
                    "can_announce_cost":  False,
                    "needs_escalation":   False,
                    "cost_status":        "pending",
                    "guidance_scope":     "always",
                    "required_questions": (row.get("required_questions") or "").strip(),
                    "customer_notice":    "確認後にご案内します",
                    "internal_note":      (row.get("internal_note") or "").strip(),
                    "missing_fields":     missing,
                    "keyword":            matched_kw,
                    "priority":           int(row.get("priority", 999)),
                    "csv_name":           "master_cost_rules.csv",
                    "notes":              (row.get("notes") or "").strip(),
                }

        # ── 通常マッチ ──────────────────────────────────────────
        esc = str(row.get("needs_escalation", "0")).strip() == "1"
        raw_status = (row.get("cost_status") or "").strip()
        if not raw_status:
            raw_status = "escalation" if esc else "confirmed"

        return {
            "matched":            True,
            "cost_estimate":      (row.get("cost_estimate") or "").strip(),
            "can_announce_cost":  (row.get("can_announce_cost") or "可").strip() != "不可",
            "needs_escalation":   esc,
            "cost_status":        raw_status,
            "guidance_scope":     (row.get("guidance_scope") or "always").strip(),
            "required_questions": (row.get("required_questions") or "").strip(),
            "customer_notice":    (row.get("customer_notice") or "").strip(),
            "internal_note":      (row.get("internal_note") or "").strip(),
            "missing_fields":     [],
            "keyword":            matched_kw,
            "priority":           int(row.get("priority", 999)),
            "csv_name":           "master_cost_rules.csv",
            "notes":              (row.get("notes") or "").strip(),
        }

    return _no_match


# ── 既存ロジック（フォールバック・削除しない） ──
def determine_cost_estimate(form: dict, repair_type: str) -> str:
    product      = form.get("product", "")
    manufacturer = normalize_manufacturer(form.get("manufacturer", ""))
    if repair_type == "要確認":       return "要確認"
    if manufacturer == "ダイキン" and "エアコン" in product:
        if form.get("appliance_type") == "住設" or "業務用" in form.get("extra_condition", ""):
            return "15,000円～22,000円前後"
        return "7,000円～16,000円前後"
    if manufacturer == "アイリスオーヤマ" and repair_type == "出張修理":
        return "15,000円前後"
    if manufacturer == "エレクトロラックス・ジャパン":
        if product in {"洗濯機", "食器洗い乾燥機"} or "レンジフード" in product:
            return "45,000円前後"
        if "IH" in product or "クッキングヒーター" in product:
            return "25,000円～30,000円前後"
    if manufacturer == "ダイソン" and product == "掃除機": return "10,000円前後"
    if product == "パソコン":
        domestic = {"パナソニック", "シャープ", "富士通", "東芝", "日立", "ソニー"}
        return "2,000円～9,000円" if manufacturer in domestic else "12,000円前後"
    if repair_type == "出張修理": return "5,000円～7,000円前後"
    if repair_type == "持込修理": return "2,000円～5,000円前後"
    return "要確認"


# ============================================================
# Layer 4: 修理拠点候補判定
# ============================================================
def build_vendor_missing_reason(form: dict, repair_type: str) -> str:
    product = (form.get("product") or form.get("product_original") or "製品未入力").strip()
    manufacturer = (
        form.get("manufacturer")
        or form.get("manufacturer_original")
        or "メーカー未入力"
    ).strip()
    prefecture = (form.get("prefecture") or "都道府県未入力").strip()
    repair_type = (repair_type or "修理形態未入力").strip()
    return f"{product} × {manufacturer} × {prefecture} × {repair_type} に一致する修理拠点ルールが未登録です。"


def determine_vendor_from_rules(form: dict, repair_type: str) -> dict:
    """
    master_vendor_rules.csv を使って修理拠点候補を判定する。
    - call_line / prefecture は完全一致（空=ワイルドカード）
    - area_group は AREA_GROUPS マッピングで都道府県が含まれるか判定
    - その他フィールドは keyword in target の包含一致
    """
    df = load_vendor_rules()
    call_line    = (form.get("call_line") or "").strip()
    appliance_category = (form.get("appliance_category") or "").strip()
    appliance_type = (form.get("appliance_type") or "").strip()
    housing_phase = (form.get("housing_phase") or "").strip()
    prefecture   = (form.get("prefecture") or "").strip()
    manufacturer = (form.get("manufacturer") or "").strip()
    product      = (form.get("product") or "").strip()
    store_targets = [
        (form.get("store_name") or "").strip(),
        (form.get("store_original") or "").strip(),
        (form.get("store_name_original") or "").strip(),
    ]
    store = " ".join(t for t in store_targets if t)

    if not df.empty:
        for _, row in df.iterrows():
            cl   = (row.get("call_line") or "").strip()
            pref = (row.get("prefecture") or "").strip()
            ag   = (row.get("area_group") or "").strip()
            mk   = (row.get("manufacturer_keyword") or "").strip()
            pk   = (row.get("product_keyword") or "").strip()
            sk   = (row.get("store_keyword") or "").strip()
            rt   = (row.get("repair_type") or "").strip()
            io10 = (row.get("is_over_10years") or "").strip()

            # call_line: 完全一致（空=ワイルドカード）
            if cl and not call_line_master_values_match(cl, call_line):         continue
            # prefecture: 完全一致（空=ワイルドカード）
            if pref and pref != prefecture:                     continue
            # area_group: CSVのNTT東西エリアと既存の地域グループを両方参照（空=ワイルドカード）
            if ag:
                if ag == "全国":
                    if not prefecture:
                        continue
                else:
                    area_groups = {**AREA_GROUPS, **load_area_groups_dict()}
                    group_set = area_groups.get(ag)
                    form_area_group = (form.get("area_group") or "").strip()
                    if ag != form_area_group and (group_set is None or prefecture not in group_set):
                        continue
            # keyword 包含一致
            if not _kw_match(mk, manufacturer):                continue
            if not _kw_match(pk, product):                     continue
            if not _kw_match(sk, store):                       continue
            # repair_type: 完全一致（空=ワイルドカード）
            if rt and rt != repair_type:                       continue
            # is_over_10years: 空=ワイルドカード / "0"=10年未満 / "1"=10年以上
            form_over = form.get("is_over_10years", False)
            if io10 == "1" and not form_over:                  continue
            if io10 == "0" and form_over:                      continue

            return {
                "matched":          True,
                "vendor_name":      (row.get("vendor_name") or "担当エスカ（要確認）").strip(),
                "reason":           (row.get("reason") or "").strip(),
                "contact_type":     (row.get("contact_type") or "").strip(),
                "needs_escalation": str(row.get("needs_escalation", "0")).strip() == "1",
                "keyword":          cl or pref or ag or mk or pk,
                "priority":         int(row.get("priority", 999)),
                "csv_name":         "master_vendor_rules.csv",
                "notes":            (row.get("notes") or "").strip(),
            }

    return {
        "matched": False, "vendor_name": "担当エスカ（要確認）",
        "reason": build_vendor_missing_reason(form, repair_type),
        "vendor_missing_reason": build_vendor_missing_reason(form, repair_type),
        "needs_escalation": True, "keyword": "",
        "priority": None, "csv_name": "", "notes": "",
    }


# ── 既存ロジック（フォールバック・削除しない） ──
def determine_vendor_candidate(form: dict) -> str:
    prefecture   = form.get("prefecture", "")
    product      = form.get("product", "")
    call_line    = form.get("call_line", "")
    manufacturer = normalize_manufacturer(form.get("manufacturer", ""))
    extra        = form.get("extra_condition", "")
    if call_line in ["ビックカメラ", "ソフマップ"]: return "ソフマップ修理センター"
    if "ヤマダオリジナル" in extra:                         return "㈱ヤマダデンキ"
    if prefecture == "沖縄県":                              return "宗建リノベーション"
    if prefecture in {"福岡県","佐賀県","長崎県","熊本県","大分県","宮崎県","鹿児島県"}:
        return "CER候補（担当確認）"
    if prefecture == "滋賀県" and product == "洗濯機":     return "ユナイトサービス㈱"
    if prefecture in {"東京都","神奈川県"} and product == "洗濯機": return "WRT修理センター"
    return "担当エスカ（要確認）"


# ============================================================
# 引き継ぎ要否判定
# ============================================================
def _int_or_default(value, default: int = 999) -> int:
    try:
        return int(str(value or "").strip())
    except (TypeError, ValueError):
        return default


def _flag_enabled(value) -> bool:
    return str(value or "").strip() == "1"


def infer_handover_call_kind(form: dict) -> str:
    """UI入力から引き継ぎ判定用の inquiry / repair を推定する。"""
    raw = " ".join(
        str(form.get(field) or "")
        for field in ("call_kind", "call_type", "reception_type", "case_type")
    )
    if any(token in raw for token in ("問い合わせ", "問合せ", "問合", "inquiry")):
        return "inquiry"
    return "repair"


def _handover_no_match(reason: str = "引き継ぎ対象ルールに一致なし") -> dict:
    return {
        "required": False,
        "matched": False,
        "reason": reason,
    }


def _handover_text_bundle(form: dict, decision: dict | None = None) -> dict:
    decision = decision or {}
    working_form = decision.get("working_form") or {}
    vendor_result = decision.get("vendor_result") or {}
    store_fields = (
        "operating_company", "store_company", "store_name", "store_original",
        "store_name_original", "warranty_plan", "call_line",
    )
    case_fields = (
        "case_keywords", "case_type", "reception_type", "call_type",
        "symptoms", "symptom", "symptom_detail", "memo", "call_memo",
        "teams_action", "vendor_result", "repair_type", "product",
        "manufacturer", "warranty_plan", "extra_condition",
    )
    appliance_values = [
        form.get("appliance_type"),
        working_form.get("appliance_type"),
        decision.get("appliance_type"),
    ]
    case_values = [form.get(field) for field in case_fields]
    case_values.extend([
        decision.get("teams_action"),
        decision.get("repair_type"),
        decision.get("vendor"),
        vendor_result.get("vendor_name"),
        vendor_result.get("reason"),
        vendor_result.get("notes"),
    ])
    return {
        "store": " ".join(str(form.get(field) or "") for field in store_fields).strip(),
        "case": " ".join(str(value or "") for value in case_values).strip(),
        "appliance_type": " ".join(str(value or "") for value in appliance_values).strip(),
    }


def _handover_match_reason(row, store_matched: bool, case_matched: bool, appliance_matched: bool) -> str:
    rule_name = (row.get("rule_name") or "").strip()
    if store_matched:
        return f"販売店/運営会社が{rule_name}に一致"
    if case_matched:
        return f"案件内容が{rule_name}に一致"
    if appliance_matched:
        return f"案件分類が{(row.get('appliance_type') or '').strip()}に一致"
    return f"{rule_name or '引き継ぎ要否ルール'}に一致"


def determine_handover_requirement(form: dict, decision: dict | None = None, call_kind: str = "repair") -> dict:
    """
    data/master_handover_rules.csv を使って、WRS/ワランティへの引き継ぎ要否を判定する。
    - priority 昇順で最初に一致したルールを採用
    - call_kind="inquiry" は call_type_inquiry=1 のみ対象
    - call_kind="repair" は call_type_repair=1 のみ対象
    - 楽テル用テキスト、修理依頼書メモ、Teams報告文には反映しない
    """
    normalized_kind = "inquiry" if str(call_kind or "").strip().lower() == "inquiry" else "repair"
    df = load_handover_rules()
    if df.empty:
        return _handover_no_match("引き継ぎ要否マスタが未登録です")

    texts = _handover_text_bundle(form or {}, decision or {})
    for _, row in df.iterrows():
        if not _flag_enabled(row.get("active", "1")):
            continue
        if normalized_kind == "inquiry" and not _flag_enabled(row.get("call_type_inquiry")):
            continue
        if normalized_kind == "repair" and not _flag_enabled(row.get("call_type_repair")):
            continue

        store_keywords = (row.get("store_keywords") or "").strip()
        case_keywords = (row.get("case_keywords") or "").strip()
        required_appliance = (row.get("appliance_type") or "").strip()
        if not any([store_keywords, case_keywords, required_appliance]):
            continue

        store_matched = bool(store_keywords) and _kw_any_match(store_keywords, texts["store"])
        case_matched = bool(case_keywords) and _kw_any_match(case_keywords, texts["case"])
        appliance_matched = bool(required_appliance) and required_appliance in texts["appliance_type"]

        if store_keywords and not store_matched:
            continue
        if case_keywords and not case_matched:
            continue
        if required_appliance and not appliance_matched:
            continue

        return {
            "required": True,
            "matched": True,
            "priority": _int_or_default(row.get("priority")),
            "rule_name": (row.get("rule_name") or "").strip(),
            "rakutel_status": (row.get("rakutel_status") or "").strip(),
            "handover_request_content": (row.get("handover_request_content") or "").strip(),
            "notes": (row.get("notes") or "").strip(),
            "exclude_wrong_number": _flag_enabled(row.get("exclude_wrong_number")),
            "reason": _handover_match_reason(row, store_matched, case_matched, appliance_matched),
            "csv_name": "master_handover_rules.csv",
        }

    return _handover_no_match()


# ============================================================
# call_line 属性推定（回線名 + 販売店名）
# ============================================================
def infer_call_line_attrs(form: dict) -> dict:
    """
    call_line と store_name から案件属性を補助判定する。
    戻り値: {"call_line": str, "is_bic_sofmap": bool}
    """
    call_line = (form.get("call_line") or "").strip()
    store = (form.get("store_name") or "").strip()
    is_bic_sofmap = (
        "ビックカメラ" in call_line or
        "ソフマップ" in call_line or
        "ビックカメラ" in store or
        "ソフマップ" in store
    )
    return {"call_line": call_line, "is_bic_sofmap": is_bic_sofmap}


# ============================================================
# スクリプトルート判定（既存ロジック・削除しない）
# ============================================================
def determine_script_route(form: dict, repair_type: str) -> dict:
    call_line      = form.get("call_line", "")
    form = apply_appliance_category_to_form(form.copy())
    appliance_type = form.get("appliance_type", "")
    appliance_category = form.get("appliance_category", "")
    is_dp = is_double_protect_plan(form.get("warranty_plan", ""))
    result = {
        "sheet_name": "", "part": "", "price_guidance_allowed": True,
        "notes": [], "escalation_needed": False, "reason": "",
        "script_type": "ダブルプロテクト" if is_dp else "通常",
        "display_name": "",
    }
    if call_line in ["ビックカメラ", "ソフマップ"]:
        result.update(sheet_name="⑩-1ビックカメラ・ソフマップ", part="案件別受付",
                      price_guidance_allowed=False,
                      notes=["保証対象外時の概算費用・上限金額などの金額案内はしない"],
                      reason="ビックカメラ/ソフマップ回線のため金額案内不可")
        return result
    line_group = get_line_group(call_line)
    if line_group == "住設" and appliance_category == "住設（新築）":
        result.update(sheet_name="家電出張・持込・新築住設", part="家電・出張修理",
                      display_name="住設新築受付",
                      reason="住設回線＋住設（新築）")
        return result
    if line_group == "住設" and appliance_category == "住設（既築）":
        result.update(sheet_name="住設【既築／中古のみ】", part="既築・中古住設受付",
                      display_name="住設・出張修理" if repair_type == "出張修理" else "住設受付",
                      reason="住設回線＋住設（既築）")
        return result
    if line_group == "住設":
        result.update(sheet_name="住設【既築／中古のみ】", part="住設受付",
                      display_name="住設受付",
                      reason="住設回線")
        return result
    if appliance_category == "住設（新築）":
        result.update(sheet_name="家電出張・持込・新築住設", part="家電・出張修理",
                      display_name="住設新築受付",
                      reason="住設（新築）")
        return result
    if appliance_category == "住設（既築）" or appliance_type == "住設":
        result.update(sheet_name="住設【既築／中古のみ】", part="住設受付",
                      display_name="住設・出張修理" if repair_type == "出張修理" else "住設受付",
                      reason="住設（既築）")
        return result
    if appliance_category == "家電" or appliance_type == "家電":
        part = "家電・持込修理" if repair_type == "持込修理" else "家電・出張修理"
        display_repair = "持込修理" if repair_type == "持込修理" else "出張修理"
        result.update(sheet_name="家電出張・持込・新築住設", part=part,
                      reason=f"家電＋{display_repair}",
                      display_name=f"家電・{display_repair}")
        if is_dp:
            result.update(display_name=f"ダブルプロテクト / {display_repair}",
                          reason=f"家電＋{display_repair}＋ダブルプロテクト")
        return result
    result.update(sheet_name="要確認", part="SV/担当確認",
                  escalation_needed=True, reason="回線名または案件分類が未確定")
    return result


# ============================================================
# データ消去同意判定（既存ロジック・削除しない）
# ============================================================
DATA_ERASE_PRODUCTS = {
    "パソコン", "タブレット", "プリンター", "カーナビ",
    "ドライブレコーダー", "ブルーレイレコーダー", "DVDレコーダー",
    "ドアホン", "ゲーム機",
}


def determine_data_erase_consent(form: dict) -> bool:
    return form.get("product", "") in DATA_ERASE_PRODUCTS


# ============================================================
# 確認項目ビルダー
# ============================================================
def build_required_questions(form: dict, repair_type: str, needs_data_erase: bool) -> list:
    common = ["症状の詳細", "発生時期", "発生頻度"]
    if repair_type == "出張修理":
        qs = common + ["設置場所", "訪問先住所", "他窓口へ修理依頼済みか"]
    elif repair_type == "持込修理":
        qs = common + ["付属品含めて送付可能か", "返送先住所"]
        if needs_data_erase:
            qs.append("データ消去同意（必須）")
    elif form.get("product") == "腕時計":
        qs = [
            "腕時計案件の対応可否をSV/担当へ確認",
            "スクリプトURL未登録のため手動参照",
        ]
    else:
        qs = ["製品詳細", "型番", "メーカー", "販売店", "保証内容", "SV/担当確認"]
    if is_double_protect_plan(form.get("warranty_plan", "")):
        _append_unique(qs, DOUBLE_PROTECT_AMOUNT_CONFIRMATION)
        _append_unique(qs, DOUBLE_PROTECT_DAMAGE_CONFIRMATION)
    if not form.get("model_number"):
        qs.insert(0, "型番の確認（未入力）")
    if not form.get("manufacturer"):
        qs.insert(0, "メーカーの確認（未入力）")
    return _dedupe_preserve_order(qs)


# ============================================================
# 概算案内補助文
# ============================================================
def build_customer_cost_guidance(repair_type: str, cost_estimate: str,
                                  price_guidance_allowed: bool) -> str:
    if not price_guidance_allowed:
        return ("【金額案内不可】\n"
                "こちらの案件は金額案内を行わず、正式スクリプトおよび担当確認に従って案内してください。")
    if repair_type == "出張修理":
        return (f"保証対象外の場合、訪問費用および故障検証費用として、概算で {cost_estimate} かかる可能性がございます。\n"
                "実際の金額は、メーカー・製品・設置状況・診断内容・地域により前後いたします。")
    if repair_type == "持込修理":
        return (f"保証対象外の場合、故障検証費用・返送費用等として、概算で {cost_estimate} かかる可能性がございます。\n"
                "実際の金額は、メーカー・製品・診断内容により前後いたします。")
    return ("恐れ入りますが、こちらの商品は確認が必要な内容となります。\n"
            "修理受付可否および概算費用を確認のうえ、ご案内いたします。")


def build_summary_card_display(decision: dict) -> dict:
    """判定結果カード用の表示文言をまとめる。判定値そのものは変更しない。"""
    repair_type = decision.get("repair_type", "")
    cost_estimate = decision.get("cost_estimate", "")
    script_result = decision.get("script_result", {})
    cost_result = decision.get("cost_result", {})
    vendor_result = decision.get("vendor_result", {})
    working_form = decision.get("working_form", {})
    repair_result = decision.get("repair_result", {})
    watch_confirmation = is_watch_repair_confirmation(working_form, repair_type, repair_result)
    warranty_result = decision.get("warranty_result", {})
    warranty_plan = working_form.get("warranty_plan", "")
    is_dp = is_double_protect_plan(warranty_plan)

    cost_status = cost_result.get("cost_status", "confirmed")
    if not script_result.get("price_guidance_allowed", True):
        cost_status = "unavailable"
    elif cost_result.get("needs_escalation") and cost_status not in ("pending",):
        cost_status = "escalation"

    contact_type = (vendor_result.get("contact_type") or "").strip()
    if contact_type == "callback":
        callback_label = (vendor_result.get("reason") or "").strip()
        repair_card = {
            "value": f"折り返し対応（{callback_label}）" if callback_label else "折り返し対応",
            "status": "📞 翌営業日折り返し",
            "color": "#6c3483",
        }
    elif repair_type in ("出張修理", "持込修理"):
        repair_card = {"value": repair_type, "status": "✅ 確定", "color": "#1a5276"}
    elif watch_confirmation:
        repair_card = {
            "value": "担当確認",
            "status": "⚠️ 腕時計はSV/担当確認",
            "color": "#784212",
        }
    else:
        repair_card = {"value": "要確認", "status": "⚠️ SV確認", "color": "#784212"}

    if watch_confirmation:
        cost_card = {
            "value": "案内不可" if cost_status == "unavailable" else "確認中",
            "status": "理由：腕時計は担当確認後に案内",
            "color": "#7d6608" if cost_status != "unavailable" else "#922b21",
        }
    elif cost_status == "pending":
        required_questions = cost_result.get("required_questions", "").strip() or "追加確認が必要です"
        cost_card = {"value": "確認中", "status": f"🔲 {required_questions}", "color": "#7d6608"}
    elif cost_status == "unavailable":
        cost_card = {"value": "案内不可", "status": "🚫", "color": "#922b21"}
    elif cost_status == "escalation":
        cost_card = {
            "value": cost_estimate or "要確認",
            "status": "⚠️ エスカ注意",
            "color": "#784212",
        }
    else:
        cost_card = {
            "value": cost_estimate or "要確認",
            "status": "✅ 案内可",
            "color": "#1e8449",
        }

    script_sheet = script_result.get("sheet_name") or "未確定"
    script_part = script_result.get("part") or "未確定"
    if watch_confirmation:
        script_sheet = "腕時計"
        script_part = "SV担当確認"
    script_type = script_result.get("script_type") or ("ダブルプロテクト" if is_dp else "通常")
    script_display = script_result.get("display_name") or f"{script_type} / {script_part}"

    warranty_title = warranty_result.get("title", "保証期間未確認")
    warranty_card = {
        "value": warranty_title,
        "status": f"{double_protect_plan_label(warranty_plan)} / 物損保証金額: {double_protect_amount_status(warranty_plan)}",
        "color": "#7d6608" if is_dp else "#566573",
        "is_double_protect": is_dp,
        "plan_label": double_protect_plan_label(warranty_plan),
        "amount_status": double_protect_amount_status(warranty_plan),
    }

    return {
        "warranty": warranty_card,
        "repair": repair_card,
        "cost": cost_card,
        "script_sheet": script_sheet,
        "script_part": script_part,
        "script_type": script_type,
        "script_display": script_display,
        "cost_status": cost_status,
        "watch_confirmation": watch_confirmation,
        "is_double_protect": is_dp,
        "dp_amount_status": double_protect_amount_status(warranty_plan),
    }


def build_script_reference_info(decision: dict) -> dict:
    summary = build_summary_card_display(decision)
    script_result = decision.get("script_result", {})
    route_form = (decision.get("working_form", {}) or {}).copy()
    route_form["repair_type"] = decision.get("repair_type", "")
    script_route = judge_script_route(route_form)
    if script_route.get("script_key"):
        url = script_route.get("url", "")
        confidence = script_route.get("confidence", "")
        matched = bool(url) and confidence not in ("needs_url", "needs_selection")
        display = script_route.get("display_name", "") or "未判定"
        matched_by = script_route.get("matched_by", [])
        basis = " / ".join(matched_by) if matched_by else "マスタ優先順位"
        if matched:
            message = ""
        elif confidence == "needs_selection":
            message = "案件分類で「住設新築 / 住設既築 / 住設賃貸」を選択してください"
        else:
            message = "URL未確認"
        if script_route.get("memo"):
            message = f"{message}\n{script_route['memo']}" if message else script_route["memo"]
        return {
            "title": "📘 参照スクリプト",
            "script_type": summary["script_type"],
            "display": display,
            "current_script_display": display,
            "label": f"{summary['script_type']} / {display}",
            "matched": matched,
            "url": url if matched else "",
            "link_text": "スクリプト" if matched else ("選択待ち" if confidence == "needs_selection" else "URL未確認"),
            "message": message,
            "confidence": confidence,
            "matched_by": matched_by,
            "basis": basis,
            "script_key": script_route.get("script_key", ""),
            "initial_line": script_route.get("initial_line", ""),
            "correction_reason": script_route.get("correction_reason", ""),
            "script_changed": bool(script_route.get("script_changed")),
            "previous_script_display": script_route.get("previous_script_display", ""),
            "initial_script_display": script_route.get("previous_script_display", "") or display,
        }
    script_link = lookup_script_link(script_result)
    script_type = summary["script_type"]
    script_display = script_result.get("display_name") or summary["script_part"] or summary["script_display"]
    if script_type == "ダブルプロテクト" and script_display.startswith("家電・"):
        script_display = script_display.replace("家電・", "", 1)
    matched = bool(script_link.get("matched"))
    message = "" if matched else f"{script_type} / {script_display}\nURL未登録（手動で参照）"
    if not matched and (decision.get("working_form", {}).get("appliance_type") == "住設" or "住設" in script_display):
        message = f"{script_type} / {script_display}\n住設スクリプト未登録（手動参照）"
    return {
        "title": "📘 参照スクリプト",
        "script_type": script_type,
        "display": script_display,
        "current_script_display": script_display,
        "label": f"{script_type} / {script_display}",
        "matched": matched,
        "url": script_link.get("url", ""),
        "link_text": script_link.get("display_name", "スクリプト"),
        "message": message,
        "confidence": "high" if matched else "none",
        "matched_by": ["旧スクリプト参照"] if matched else [],
        "basis": "旧スクリプト参照" if matched else "",
        "script_key": "",
        "initial_line": "",
        "correction_reason": "",
        "script_changed": False,
        "previous_script_display": "",
        "initial_script_display": script_display,
    }


def repair_policy_reason_for_display(decision: dict) -> str:
    repair_result = decision.get("repair_result", {}) or {}
    if repair_result.get("reason"):
        return str(repair_result.get("reason") or "").strip()
    if repair_result.get("notes"):
        return str(repair_result.get("notes") or "").strip()
    if repair_result.get("matched"):
        return "CSVマスタに一致"
    if decision.get("repair_source") == "既存ロジック":
        return "既存フォールバック判定"
    return "判定理由未登録"


def _missing_text(fields: list[str]) -> str:
    labels = compact_missing_field_labels(fields)
    return "不足：" + " / ".join(_dedupe_preserve_order(labels))


MISSING_FIELD_SHORT_LABELS = {
    "warranty_start_date": "保証期間",
    "warranty_end_date": "保証期間",
    "warranty_plan": "保証プラン",
    "product_price": "商品価格",
    "product": "製品",
    "manufacturer": "メーカー",
    "model_number": "型番",
    "prefecture": "住所/都道府県",
    "address": "住所/都道府県",
    "repair_type": "修理方針",
    "call_line": "回線名",
    "appliance_type": "案件分類",
    "appliance_category": "案件分類",
}


INITIAL_CASE_FIELDS = (
    "product",
    "manufacturer",
    "model_number",
    "warranty_start_date",
    "warranty_end_date",
    "warranty_plan",
    "store_name",
    "address",
    "prefecture",
    "customer_name",
    "wrt_no",
)


def compact_missing_field_labels(fields: list[str]) -> list[str]:
    labels = [MISSING_FIELD_SHORT_LABELS.get(field, field_label(field)) for field in fields]
    return _dedupe_preserve_order(labels)


def is_initial_case_state(form: dict | None) -> bool:
    form = form or {}
    return all(not str(form.get(field) or "").strip() for field in INITIAL_CASE_FIELDS)


def _repair_type_needs_model(repair_result: dict) -> bool:
    if repair_result.get("model_required"):
        return True
    text = " ".join(str(repair_result.get(field) or "") for field in ("reason", "notes", "memo_note"))
    return "型番" in text


def _repair_type_needs_manufacturer(repair_result: dict) -> bool:
    if repair_result.get("manufacturer_required"):
        return True
    return "manufacturer" in (repair_result.get("missing_fields") or [])


def decision_tag_missing_fields(decision: dict, form: dict | None = None) -> dict[str, list[str]]:
    form = form or decision.get("working_form", {})
    if "working_form" not in decision and not form:
        return {"受付可否": [], "修理方針": [], "拠点対応": [], "スクリプト": []}
    working_form = decision.get("working_form", form) or {}
    repair_type = (decision.get("repair_type") or "").strip()
    repair_result = decision.get("repair_result", {}) or {}

    warranty_missing = [
        field for field in ("warranty_start_date", "warranty_end_date", "warranty_plan")
        if not (form.get(field) or working_form.get(field) or "").strip()
    ]
    if warranty_missing and not (form.get("product_price") or working_form.get("product_price") or "").strip():
        warranty_missing.append("product_price")

    product = (working_form.get("product") or form.get("product") or "").strip()
    manufacturer = (working_form.get("manufacturer") or form.get("manufacturer") or "").strip()
    model = (working_form.get("model_number") or form.get("model_number") or "").strip()
    repair_missing: list[str] = []
    if not product or product == PRODUCT_OTHER:
        repair_missing.append("product")
    else:
        if _repair_type_needs_manufacturer(repair_result) and is_missing_manufacturer_value(manufacturer):
            repair_missing.append("manufacturer")
        if _repair_type_needs_model(repair_result) and not model:
            repair_missing.append("model_number")

    vendor_missing: list[str] = []
    if not (working_form.get("prefecture") or form.get("prefecture") or "").strip():
        vendor_missing.append("prefecture")
    if not product or product == PRODUCT_OTHER:
        vendor_missing.append("product")
    if not repair_type or repair_type == "要確認":
        vendor_missing.append("repair_type")

    script_missing: list[str] = []
    if not (working_form.get("call_line") or form.get("call_line") or "").strip():
        script_missing.append("call_line")
    if not (working_form.get("appliance_category") or form.get("appliance_category")
            or working_form.get("appliance_type") or form.get("appliance_type") or "").strip():
        script_missing.append("appliance_category")

    return {
        "受付可否": _dedupe_preserve_order(warranty_missing),
        "修理方針": _dedupe_preserve_order(repair_missing),
        "拠点対応": _dedupe_preserve_order(vendor_missing),
        "スクリプト": _dedupe_preserve_order(script_missing),
    }


def _missing_tag(title: str, fields: list[str], tertiary: str = "") -> dict:
    tag = {
        "title": title,
        "primary": "未判定",
        "secondary": _missing_text(fields),
        "color": TAG_COLOR_MISSING,
    }
    if tertiary:
        tag["tertiary"] = _decision_tag_short_note("確認：", tertiary.replace("確認：", "", 1))
    return tag


def _attention_tag(title: str, primary: str, fields: list[str], reason: str = "") -> dict:
    tag = {
        "title": title,
        "primary": primary or "要確認",
        "secondary": _missing_text(fields),
        "color": TAG_COLOR_WARNING,
    }
    if reason:
        tag["tertiary"] = _decision_tag_short_note("確認：", reason)
    return tag


def _script_reference_has_candidate(script_reference: dict) -> bool:
    confidence = (script_reference.get("confidence") or "").strip()
    display = (script_reference.get("display") or "").strip()
    if script_reference.get("matched") and script_reference.get("url") and display:
        return True
    return confidence in ("high", "medium", "needs_url", "needs_selection") and bool(display) and display != "未判定"


def _decision_tag_short_note(prefix: str, text: str) -> str:
    text = str(text or "").strip()
    if not text:
        return ""
    if len(text) > 18 or "CSVに明確な" in text:
        text = "要確認"
    return f"{prefix}{text}"


def _normalize_confirmation_action(action: str, timing: str = "call") -> str:
    text = (action or "").strip()
    if not text:
        return ""
    if "保証開始日" in text or "保証終了日" in text or "保証期間" in text:
        return "保証期間を確認"
    if "保証プラン" in text:
        return "保証プランを確認"
    if "商品価格" in text:
        return "商品価格を確認"
    if "都道府県" in text or "住所" in text:
        return "住所/都道府県を確認"
    if "メーカー" in text:
        return "メーカーを確認"
    if "型番" in text:
        return "型番を確認"
    if "製品" in text:
        return "製品を確認"
    if "回線名" in text:
        return "回線名を選択"
    if "案件分類" in text or "家電/住設" in text or "家電・住設" in text:
        return "案件分類を確認"
    if "修理方針" in text or "修理形態" in text or "取説" in text or "過去履歴" in text:
        return "修理形態を確認"
    if "Excel" in text or "正式" in text or "URL未登録" in text:
        return "正式Excelを参照"
    if "SV" in text or "担当" in text or "エスカ" in text or "拠点" in text:
        return "終話後に拠点確認" if timing == "after" else "拠点を確認"
    if text.endswith("してください"):
        text = text.removesuffix("してください")
    return text


def _confirmation_priority(action: str) -> int:
    order = {
        "保証期間を確認": 10,
        "保証プランを確認": 20,
        "商品価格を確認": 25,
        "製品を確認": 30,
        "メーカーを確認": 40,
        "型番を確認": 50,
        "住所/都道府県を確認": 60,
        "修理形態を確認": 70,
        "回線名を選択": 80,
        "案件分類を確認": 90,
        "正式Excelを参照": 120,
        "終話後に拠点確認": 130,
    }
    return order.get(action, 999)


def _confirmation_cards(call_required: list[str], after_call: list[str]) -> list[dict]:
    cards = [{"timing": "通話中", "text": text, "tone": "call"} for text in call_required]
    cards.extend({"timing": "終話後", "text": text, "tone": "after"} for text in after_call)
    return cards


def build_next_confirmation_sections(decision: dict, form: dict | None = None) -> dict:
    form = form or decision.get("working_form", {})
    missing = decision_tag_missing_fields(decision, form)
    call_required: list[str] = []
    after_call: list[str] = []

    if is_initial_case_state(form):
        call_required = ["回線名を選択", "保証情報を貼り付け"]
        script_reference = build_script_reference_info(decision)
        if script_reference.get("confidence") == "needs_selection":
            call_required.append("案件分類で「住設新築 / 住設既築 / 住設賃貸」を選択")
        return {
            "initial": True,
            "call_required": call_required,
            "after_call_ok": [],
            "detail_missing": missing,
            "cards": _confirmation_cards(call_required, []),
        }

    action_by_field = {
        "call_line": "回線名を選択",
        "warranty_start_date": "保証期間を確認",
        "warranty_end_date": "保証期間を確認",
        "warranty_plan": "保証プランを確認",
        "product_price": "商品価格を確認",
        "manufacturer": "メーカーを確認",
        "model_number": "型番を確認",
        "prefecture": "住所/都道府県を確認",
        "address": "住所/都道府県を確認",
        "product": "製品を確認",
        "appliance_type": "案件分類を確認",
        "appliance_category": "案件分類を確認",
        "repair_type": "修理形態を確認",
    }
    for fields in missing.values():
        for field in fields:
            action = action_by_field.get(field)
            if action:
                call_required.append(action)

    for item in sort_diagnostic_items((decision.get("diagnostics") or {}).get("items", [])):
        impact = item.get("impact")
        timing = "after" if impact == "after_call_ok" else "call"
        action = _normalize_confirmation_action(item.get("next_action") or "", timing)
        if not action:
            continue
        if impact in ("blocking", "call_time_required"):
            call_required.append(action)
        elif impact == "after_call_ok":
            after_call.append(action)

    script_reference = build_script_reference_info(decision)
    if script_reference.get("confidence") == "needs_selection":
        call_required.append("案件分類で「住設新築 / 住設既築 / 住設賃貸」を選択")
    if not script_reference.get("matched") and not missing.get("スクリプト"):
        after_call.append("正式Excelを参照")

    call_required = sorted(_dedupe_preserve_order(call_required), key=_confirmation_priority)[:5]
    after_call = sorted(_dedupe_preserve_order(after_call), key=_confirmation_priority)

    return {
        "initial": False,
        "call_required": call_required,
        "after_call_ok": after_call,
        "detail_missing": missing,
        "cards": _confirmation_cards(call_required, after_call),
    }


def build_script_guidance_panel_info(form: dict, decision: dict,
                                     script_reference: dict | None = None) -> dict:
    """公式本文ではなく、通話補助として表示する聴取事項・注意点を返す。"""
    script_reference = script_reference or build_script_reference_info(decision)
    guidance = select_script_guidance(form, decision, script_reference)
    if guidance.get("matched"):
        hearing_items = guidance.get("hearing_items", [])
        notes = guidance.get("notes", "")
        official_label = guidance.get("official_script_label") or script_reference.get("link_text", "")
        official_url = guidance.get("official_script_url") or script_reference.get("url", "")
        official_matched = bool(official_url)
        title = guidance.get("title") or "スクリプト補助"
    else:
        hearing_items = build_required_questions(
            form,
            decision.get("repair_type", ""),
            bool(decision.get("needs_data_erase")),
        )
        notes = "正式トークはリンク先の公式スクリプトを参照してください。"
        official_label = script_reference.get("link_text", "")
        official_url = script_reference.get("url", "")
        official_matched = bool(script_reference.get("matched"))
        title = "基本確認事項"

    return {
        "title": title,
        "matched": bool(guidance.get("matched")),
        "hearing_items": _dedupe_preserve_order(hearing_items),
        "notes": notes,
        "official_script_label": official_label or "スクリプト",
        "official_script_url": official_url,
        "official_script_matched": official_matched,
        "script_reference": script_reference,
    }


def build_decision_tag_items(decision: dict, form: dict | None = None,
                             script_reference: dict | None = None) -> list[dict]:
    form = form or decision.get("working_form", {})
    summary = build_summary_card_display(decision)
    warranty_result = decision.get("warranty_result", {})
    warranty_status = warranty_result.get("warranty_status", "unknown")
    vendor = decision.get("vendor", "")
    vendor_card = build_vendor_candidate_card_info(vendor, decision.get("vendor_result", {}))
    vendor_status = "終話後エスカ" if vendor_card.get("needs_escalation") else "確定"
    if not vendor:
        vendor_status = "要確認"
    script_reference = script_reference or build_script_reference_info(decision)

    product_display = (decision.get("normalized_product") or form.get("product") or "").strip() or "未選択"
    warranty_status_label = summary["warranty"]["value"]
    warranty_plan = (form.get("warranty_plan") or "").strip()
    product_price = (form.get("product_price") or "").strip()
    repair_reason = repair_policy_reason_for_display(decision)
    missing = decision_tag_missing_fields(decision, form)

    if missing["受付可否"]:
        warranty_tag = _missing_tag("受付可否", missing["受付可否"])
        warranty_tag["compact"] = True
    else:
        warranty_tag = {
            "title": "受付可否",
            "primary": warranty_status_label,
            "secondary": product_display,
            "tertiary": warranty_plan or "保証プラン未入力",
            "quaternary": f"商品価格　{product_price}" if product_price else "商品価格　未入力",
            "color": summary["warranty"]["color"],
            "compact": True,
        }

    if missing["修理方針"]:
        product_missing = "product" in missing["修理方針"]
        repair_primary = (
            summary["repair"]["value"]
            if not product_missing and decision.get("repair_type") in ("出張修理", "持込修理", "要確認")
            else "未判定"
        )
        repair_tag = (
            _missing_tag("修理方針", missing["修理方針"], f"確認：{repair_reason}")
            if repair_primary == "未判定"
            else _attention_tag("修理方針", repair_primary, missing["修理方針"], repair_reason)
        )
    else:
        repair_tag = {
            "title": "修理方針",
            "primary": summary["repair"]["value"],
            "secondary": summary["cost"]["value"],
            "tertiary": _decision_tag_short_note("判定理由: ", repair_reason),
            "color": summary["repair"]["color"],
        }

    if missing["拠点対応"]:
        vendor_tag = _missing_tag("拠点対応", missing["拠点対応"])
    else:
        vendor_tag = {
            "title": "拠点対応",
            "primary": vendor or "未確定",
            "secondary": vendor_status,
            "color": TAG_COLOR_WARNING if vendor_card.get("needs_escalation") else TAG_COLOR_OK,
        }

    script_has_candidate = _script_reference_has_candidate(script_reference)
    if not script_has_candidate:
        script_tag = _missing_tag("スクリプト", missing["スクリプト"] or ["call_line"])
    else:
        script_tertiary = f"根拠：{script_reference.get('basis', '')}" if script_reference.get("basis") else ""
        script_quaternary = f"confidence: {script_reference.get('confidence', '')}" if script_reference.get("confidence") else ""
        if script_reference.get("message") and not script_reference.get("matched"):
            script_quaternary = script_reference.get("message", "").splitlines()[0]
        script_quinary = ""
        if script_reference.get("correction_reason") and script_reference.get("matched"):
            script_quaternary = f"補正理由：{script_reference.get('correction_reason')}"
            script_quinary = f"confidence: {script_reference.get('confidence', '')}" if script_reference.get("confidence") else ""
        script_color = TAG_COLOR_WARNING if script_reference.get("confidence") in ("needs_url", "needs_selection") else TAG_COLOR_OK
        script_tag = {
            "title": "スクリプト",
            "primary": "参照スクリプト",
            "secondary": script_reference.get("display", ""),
            "tertiary": script_tertiary,
            "quaternary": script_quaternary,
            "quinary": script_quinary,
            "color": script_color,
            "url": script_reference.get("url", ""),
            "link_text": (script_reference.get("link_text", "") + " 該当箇所を開く")
                         if script_reference.get("matched")
                         else (script_reference.get("link_text") or "URL未登録（手動で参照）"),
            "matched": script_reference.get("matched", False),
        }

    return [
        warranty_tag,
        repair_tag,
        vendor_tag,
        script_tag,
    ]


# ============================================================
# 履歴テンプレ
# ============================================================
def build_history_template(form: dict, repair_type: str, script_result: dict,
                            cost_estimate: str, vendor: str,
                            warranty_result: dict = None,
                            diagnostics: dict = None) -> str:
    warranty_result = warranty_result or determine_warranty_status(form)
    lines = [
        "■対応履歴",
        f"WRT-NO　　　: {form.get('wrt_no', '未入力')}",
        f"回線名　　　: {form.get('call_line', '未選択')}",
        f"製造10年以上: {'はい' if form.get('is_over_10years') else 'いいえ / 未確認'}",
        f"テンプレートコード: {form.get('template_code', '未選択')}",
        f"テンプレート: {form.get('template_label', '未選択')}",
        f"お客様コード: {form.get('customer_code', '未入力')}",
        f"お客様名　　: {form.get('customer_name', '未入力')}",
        f"電話番号　　: {form.get('phone_number', '未入力')}",
        f"住所　　　　: {form.get('address', '未入力')}",
        f"製品　　　　: {form.get('product', '未入力')}",
        f"製品原文　　: {form.get('product_original', '未入力')}",
        f"メーカー　　: {form.get('manufacturer', '未入力')}",
    ]
    if form.get("manufacturer_original"):
        lines.append(f"メーカー原文: {form.get('manufacturer_original')}")
    lines.extend([
        f"型番　　　　: {form.get('model_number', '未入力')}",
        f"商品価格　　: {form.get('product_price', '未入力')}",
        f"保証プラン　: {form.get('warranty_plan', '未入力')}",
        f"保証種別　　: {double_protect_plan_label(form.get('warranty_plan', ''))}",
        f"物損保証金額: {double_protect_amount_status(form.get('warranty_plan', ''))}",
        f"保証開始日　: {form.get('warranty_start_date', '未入力')}",
        f"保証終了日　: {form.get('warranty_end_date', '未入力')}",
        "",
        "【受付可否】",
        f"受付可否：{warranty_acceptance_label(warranty_result)}",
        f"理由：{warranty_result.get('title', '保証期間未確認')}",
        f"対応方針：{build_warranty_guidance(warranty_result)}",
        "",
        "【保証期間判定】",
        f"ステータス：{warranty_result.get('title', '保証期間未確認')}",
        f"保証開始日：{form.get('warranty_start_date', '未入力') or '未入力'}",
        f"保証終了日：{form.get('warranty_end_date', '未入力') or '未入力'}",
        f"対応方針：{build_warranty_guidance(warranty_result)}",
        "",
        f"症状　　　　: {form.get('symptom', '未入力')}",
        f"案件分類　　: {form.get('appliance_category') or form.get('appliance_type') or '未入力'}",
        f"修理形態　　: {repair_type}",
        f"保証外概算　: {cost_estimate}",
        f"物損保証金額確認: {double_protect_amount_status(form.get('warranty_plan', ''))}",
        f"参照シート　: {script_result.get('sheet_name', '')}",
        f"該当パート　: {script_result.get('display_name') or script_result.get('part', '')}",
        f"注意事項　　: {' / '.join(script_result.get('notes', [])) or 'なし'}",
        f"修理拠点候補: {vendor}",
        f"次対応　　　: ",
    ])
    # ── 判定診断サマリー ──
    if diagnostics:
        lines.append("")
        lines.append("【判定診断】")
        by_area = {item.get("area", ""): item for item in diagnostics.get("items", [])}
        for area in DIAGNOSTIC_AREA_ORDER:
            item = by_area.get(area)
            if item:
                lines.append(f"{area}：{diagnostic_history_status(item)}")
    return "\n".join(lines)


# ============================================================
# 判定診断パネル
# ============================================================
def build_decision_diagnostics(form: dict, result: dict) -> dict:
    """
    フォームと run_decision() の戻り値から判定診断アイテムのリストを生成する。

    戻り値:
        {
            "overall_status": "ok" / "warning" / "error",
            "items": [
                {
                    "area": str,           # 判定エリア名
                    "status": str,         # "ok" / "warning" / "error"
                    "title": str,          # 短いタイトル
                    "reason": str,         # 詳細理由
                    "missing_fields": [],  # 未入力フィールドキー名リスト
                    "invalid_fields": [],  # 不正値フィールドキー名リスト
                    "next_action": str,    # 次に取るべきアクション
                    "impact": str,         # blocking / call_time_required / after_call_ok / info
                },
                ...
            ]
        }
    """
    items = []

    def _item(area, status, title, reason, missing_fields=None, invalid_fields=None,
              next_action="", impact="info"):
        return {
            "area": area,
            "status": status,
            "title": title,
            "reason": reason,
            "missing_fields": missing_fields or [],
            "invalid_fields": invalid_fields or [],
            "next_action": next_action,
            "impact": impact,
        }

    # ── 1. 保証期間判定 ──────────────────────────────────────────
    warranty_result = result.get("warranty_result", {})
    w_status = warranty_result.get("warranty_status", "unknown")
    start_raw = (form.get("warranty_start_date") or "").strip()
    end_raw   = (form.get("warranty_end_date") or "").strip()
    # 未入力 vs フォーマット不正を区別する
    invalid_dates: list = []
    missing_dates: list = []
    if not start_raw:
        missing_dates.append("warranty_start_date")
    elif parse_date_safe(start_raw) is None:
        invalid_dates.append("warranty_start_date")
    if not end_raw:
        missing_dates.append("warranty_end_date")
    elif parse_date_safe(end_raw) is None:
        invalid_dates.append("warranty_end_date")

    if w_status == "active":
        items.append(_item(
            "保証期間判定", "ok", "保証期間内",
            "保証期間内のため、受付判定へ進めます。",
            next_action="修理形態・費用の確認へ進む",
            impact="info",
        ))
    elif w_status == "before_start":
        items.append(_item(
            "保証期間判定", "warning", "保証開始日前",
            "保証開始日前のためWRT受付不可。メーカー保証または販売店・メーカー窓口へ誘導してください。",
            next_action="メーカー保証期間・窓口を案内",
            impact="call_time_required",
        ))
    elif w_status == "expired":
        items.append(_item(
            "保証期間判定", "error", "保証期間終了 — 受付不可",
            "保証期間終了後のためWRT受付不可。受付不可として案内してください。",
            next_action="受付不可を案内して終話",
            impact="blocking",
        ))
    else:  # unknown
        reason_parts = []
        if missing_dates:
            reason_parts.append(
                "日付が未入力: " + "、".join(FIELD_LABELS.get(f, f) for f in missing_dates)
            )
        if invalid_dates:
            reason_parts.append(
                "日付フォーマット不正（YYYY/MM/DD）: "
                + "、".join(FIELD_LABELS.get(f, f) for f in invalid_dates)
            )
        if not reason_parts:
            reason_parts.append("保証開始日・保証終了日が確認できません")
        items.append(_item(
            "保証期間判定", "warning", "保証期間未確認",
            " / ".join(reason_parts),
            missing_fields=missing_dates,
            invalid_fields=invalid_dates,
            next_action="保証開始日・保証終了日を確認",
            impact="call_time_required",
        ))

    # ── 2. 参照スクリプト判定 ────────────────────────────────────
    script_result = result.get("script_result", {})
    sheet = (script_result.get("sheet_name") or "").strip()
    part  = (script_result.get("part") or "").strip()
    escalation_needed = script_result.get("escalation_needed", False)

    if sheet and sheet != "要確認":
        items.append(_item(
            "参照スクリプト判定", "ok", "スクリプト確認済み",
            f"シート: {sheet} / パート: {part or '─'}",
            next_action="当該シートの当該パートを参照",
            impact="info",
        ))
    else:
        missing_for_script: list = []
        reasons: list = []
        if not (form.get("product") or "").strip():
            missing_for_script.append("product")
            reasons.append("製品が未選択")
        if not (form.get("appliance_category") or form.get("appliance_type") or "").strip():
            missing_for_script.append("appliance_category")
            reasons.append("案件分類が未選択")
        if "product" in missing_for_script:
            items.append(_item(
                "参照スクリプト判定", "warning", "製品未入力",
                "製品が未選択のため参照スクリプトを確定できません。",
                missing_fields=["product"],
                next_action="製品を入力してください",
                impact="call_time_required",
            ))
        if "appliance_category" in missing_for_script:
            items.append(_item(
                "参照スクリプト判定", "warning", "案件分類未入力",
                "案件分類が未選択のため参照スクリプトを確定できません。",
                missing_fields=["appliance_category"],
                next_action="案件分類を入力してください",
                impact="call_time_required",
            ))
        script_next_action = "SV/担当に確認"
        repair_type = result.get("repair_type", "")
        if not repair_type or repair_type == "要確認":
            if form.get("product") == "腕時計":
                reasons.append("腕時計案件の修理形態はSV/担当確認")
                script_next_action = "腕時計案件の修理形態をSV/担当へ確認"
            else:
                reasons.append("修理形態別案内は要確認")
        if escalation_needed:
            reasons.append("エスカレーションが必要")
        non_missing_reasons = [r for r in reasons if r not in ("製品が未選択", "案件分類が未選択")]
        if non_missing_reasons or not missing_for_script:
            reason_str = " / ".join(non_missing_reasons) if non_missing_reasons else "スクリプト参照先が確定していません"
            items.append(_item(
                "参照スクリプト判定", "warning", "スクリプト参照先が未確定",
                reason_str,
                missing_fields=[],
                next_action=script_next_action,
                impact="call_time_required" if not missing_for_script else "after_call_ok",
            ))

    # ── 3. 概算費用判定 ──────────────────────────────────────────
    cost_result   = result.get("cost_result", {})
    cost_status   = cost_result.get("cost_status", "confirmed")
    needs_esc     = cost_result.get("needs_escalation", False)
    price_ok      = script_result.get("price_guidance_allowed", True)
    repair_type   = result.get("repair_type", "")
    repair_result = result.get("repair_result", {})
    product_val   = (form.get("product") or "").strip()
    watch_confirmation = is_watch_repair_confirmation(form, repair_type, repair_result)

    # UIと同じ表示状態を計算
    disp_cost = cost_status
    if not price_ok:
        disp_cost = "unavailable"
    elif needs_esc and cost_status not in ("pending",):
        disp_cost = "escalation"

    if watch_confirmation:
        items.append(_item(
            "概算費用判定", "warning", "概算費用: 確認中",
            "腕時計は担当確認後に案内します。",
            next_action="腕時計案件の対応可否をSV/担当へ確認",
            impact="call_time_required",
        ))
    elif disp_cost == "unavailable":
        items.append(_item(
            "概算費用判定", "warning", "金額案内不可",
            "案件区分により金額案内は行いません（スクリプト・担当確認に従う）。",
            next_action="スクリプトに従い金額を案内しない",
            impact="call_time_required",
        ))
    elif disp_cost == "pending":
        missing_cost = cost_result.get("missing_fields", [])
        rq = (cost_result.get("required_questions") or "").strip()
        reason_str = (f"費用確定のための必須入力が不足しています。{rq}"
                      if rq else "費用確定のための情報が不足しています")
        items.append(_item(
            "概算費用判定", "warning", "概算費用: 未確定（追加確認が必要）",
            reason_str,
            missing_fields=missing_cost,
            next_action=rq or "不足フィールドを入力して費用を確定",
            impact="call_time_required",
        ))
    elif disp_cost == "escalation":
        cost_estimate = result.get("cost_estimate", "")
        items.append(_item(
            "概算費用判定", "warning", f"高額エスカ注意: {cost_estimate}",
            "費用が高額のため概算案内には注意が必要です。エスカレーション推奨。",
            next_action="SVへエスカレーション",
            impact="call_time_required",
        ))
    else:  # confirmed
        cost_estimate = result.get("cost_estimate", "")
        if cost_estimate and cost_estimate not in ("", "要確認", "未確定"):
            eu_note = " ※EUから質問があった場合のみ案内" if cost_result.get("guidance_scope") == "eu_asked_only" else ""
            items.append(_item(
                "概算費用判定", "ok", f"概算費用確定: {cost_estimate}",
                f"費用の案内が可能です。{eu_note}",
                next_action="必要に応じてお客様へ概算を案内",
                impact="info",
            ))
        else:
            items.append(_item(
                "概算費用判定", "warning", "概算費用: 要確認",
                "修理形態または製品情報が不足しているため費用を確定できません。",
                next_action="製品・修理形態を確認",
                impact="call_time_required",
            ))

    # ── 4. 修理形態判定 ──────────────────────────────────────────
    mfr_val       = (form.get("manufacturer") or "").strip()

    if repair_type in ("出張修理", "持込修理"):
        next_rt = ("訪問先住所・設置場所を確認"
                   if repair_type == "出張修理" else "付属品・返送先住所を確認")
        reason = repair_policy_reason_for_display(result)
        items.append(_item(
            "修理形態判定", "ok", f"修理形態: {repair_type}",
            f"修理形態が確定しました。判定理由: {reason}",
            next_action=next_rt,
            impact="info",
        ))
    else:
        reasons: list = []
        missing_repair: list = []
        if watch_confirmation:
            reasons.append("腕時計はSV/担当確認")
        if not product_val or product_val == PRODUCT_OTHER:
            reasons.append("製品が未選択または「その他・要確認」")
            missing_repair.append("product")
        if mfr_val in (MANUFACTURER_OTHER, MANUFACTURER_UNKNOWN):
            reasons.append("メーカーが「その他・要確認」または「不明」")
        for field in repair_result.get("missing_fields", []) or []:
            if field not in missing_repair:
                missing_repair.append(field)
        if repair_result.get("needs_confirmation"):
            note = (repair_result.get("notes") or "型番・詳細確認要").strip()
            reasons.append(f"確認要: {note}")
        if not reasons:
            reasons.append("修理形態が「要確認」または未確定です")
        repair_next_action = (
            "腕時計案件の修理形態をSV/担当へ確認"
            if product_val == "腕時計"
            else "製品を入力してください"
            if "product" in missing_repair
            else "SV/担当に確認"
        )
        items.append(_item(
            "修理形態判定", "warning", "修理形態: 担当確認" if watch_confirmation else "修理形態: 要確認",
            " / ".join(reasons),
            missing_fields=missing_repair,
            next_action=repair_next_action,
            impact="call_time_required",
        ))

    # ── 5. 修理拠点判定 ──────────────────────────────────────────
    vendor        = result.get("vendor", "")
    vendor_result = result.get("vendor_result", {})

    if "担当エスカ" in vendor or vendor_result.get("needs_escalation", False):
        missing_vendor: list = []
        reasons_v: list = []
        if not (form.get("prefecture") or "").strip():
            missing_vendor.append("prefecture")
            reasons_v.append("都道府県が未選択")
        if not product_val:
            if "product" not in missing_vendor:
                missing_vendor.append("product")
            reasons_v.append("製品が未選択")
        if not reasons_v:
            reasons_v.append("修理拠点が確定していません。担当にエスカレーションしてください。")
        items.append(_item(
            "修理拠点判定", "warning", f"修理拠点: 終話後確認 ({vendor})",
            "修理拠点は終話後に担当確認してください。" + (" / " + " / ".join(reasons_v) if reasons_v else ""),
            missing_fields=missing_vendor,
            next_action="終話後に担当へエスカレーションして拠点確定",
            impact="after_call_ok",
        ))
    else:
        items.append(_item(
            "修理拠点判定", "ok", f"修理拠点: {vendor}",
            "修理拠点が確定しました。",
            next_action="終話後処理タブで手配を進める",
            impact="after_call_ok",
        ))

    # ── overall_status 計算（impact ベース）──────────────────────
    if any(item["impact"] == "blocking" and item["status"] == "error" for item in items):
        overall_status = "error"
    elif any(
        item["impact"] == "call_time_required" and item["status"] in ("warning", "error")
        for item in items
    ):
        overall_status = "warning"
    else:
        overall_status = "ok"

    return {"overall_status": overall_status, "items": sort_diagnostic_items(items)}


# ============================================================
# Legacy: 旧 master_products.csv 判定（後方互換・主判定には使わない）
# ============================================================
def determine_repair_info_from_master(form: dict) -> dict:
    """legacy: Phase2-1 の旧判定関数。run_decision では使わない。"""
    _not_matched = {
        "matched": False, "source": "既存ロジック判定",
        "keyword": "", "priority": None, "match_target": "",
        "product": "", "appliance_type": "", "repair_type": "",
        "cost_estimate": "", "script_result": None,
        "data_erase_required": None, "notes": "", "_row": None,
    }
    df = load_master_products()
    if df.empty:
        return _not_matched

    model_number   = (form.get("model_number") or "").strip()
    series_text    = (form.get("series") or "").strip()
    product_text   = (form.get("product") or "").strip()
    norm_product   = normalize_product(series_text, product_text)
    manufacturer   = (form.get("manufacturer") or "").strip()
    appliance_type = (form.get("appliance_type") or "").strip()
    category       = (form.get("category") or "").strip()
    genre          = (form.get("genre") or "").strip()
    extra          = (form.get("extra_condition") or "").strip()
    any_text = " ".join([model_number, series_text, product_text, norm_product,
                         manufacturer, appliance_type, category, genre, extra])
    matched_row = None
    for _, row in df.iterrows():
        keyword      = (row.get("keyword") or "").strip()
        match_target = (row.get("match_target") or "").strip().lower()
        if not keyword:
            continue
        target = {
            "model": model_number, "series": series_text,
            "product": norm_product + " " + product_text,
            "manufacturer": manufacturer,
        }.get(match_target, any_text)
        if keyword.lower() in target.lower():
            matched_row = row
            break
    if matched_row is None:
        return _not_matched
    can_cost_raw    = (matched_row.get("can_announce_cost") or "").strip()
    erase_raw       = (matched_row.get("data_erase_required") or "").strip()
    notes_str       = (matched_row.get("notes") or "").strip()
    script_result   = {
        "sheet_name": (matched_row.get("script_sheet") or "").strip(),
        "part":       (matched_row.get("script_part") or "").strip(),
        "price_guidance_allowed": can_cost_raw != "不可",
        "notes":      [notes_str] if notes_str else [],
        "escalation_needed": False,
        "reason": f"legacy CSV一致: {matched_row.get('keyword','')}",
    }
    return {
        "matched": True, "source": "legacy CSVマスタ一致",
        "keyword": matched_row.get("keyword", ""),
        "priority": int(matched_row.get("priority", 0)),
        "match_target": matched_row.get("match_target", ""),
        "product": (matched_row.get("normalized_product") or "").strip(),
        "appliance_type": (matched_row.get("category") or "").strip(),
        "repair_type": (matched_row.get("repair_type") or "").strip(),
        "cost_estimate": (matched_row.get("cost_estimate") or "").strip(),
        "script_result": script_result,
        "data_erase_required": erase_raw == "必要",
        "notes": notes_str, "_row": matched_row.to_dict(),
    }


# ============================================================
# 4層パイプライン統合判定
# ============================================================
def run_decision(form: dict) -> dict:
    """
    判定順:
      1. normalize_product_from_alias     (製品名正規化)
      2. determine_repair_type_from_rules (修理形態)
      3. determine_cost_from_rules        (概算費用)
      4. determine_vendor_from_rules      (修理拠点候補)
      + determine_script_route            (スクリプト誘導・既存ロジック)
      + determine_data_erase_consent      (データ消去同意)
    各層でCSVにヒットしなければ既存ロジックにフォールバック。
    """
    # ── 準備: メーカー正規化 + call_line 属性推定 ──
    working_form = form.copy()
    selected_manufacturer = (form.get("manufacturer") or "").strip()
    if selected_manufacturer in (MANUFACTURER_OTHER, MANUFACTURER_UNKNOWN):
        working_form["manufacturer"] = selected_manufacturer
    else:
        working_form["manufacturer"] = normalize_manufacturer(selected_manufacturer)
    inferred_call_line_attrs = infer_call_line_attrs(working_form)
    working_form["call_line"] = normalize_call_line_for_display(working_form.get("call_line", ""))
    working_form["appliance_type"] = infer_appliance_type_from_form(
        working_form,
        working_form.get("appliance_type", ""),
    )
    working_form = apply_appliance_category_to_form(working_form)
    area_group = get_area_group(working_form.get("prefecture", ""))
    working_form["area_group"] = area_group
    warranty_result = determine_warranty_status(working_form)

    # ── Layer 1: 製品名エイリアス ──
    alias_result = normalize_product_from_alias(working_form)
    if alias_result["normalized_product"]:
        working_form["product"] = alias_result["normalized_product"]
    if working_form.get("product") == "パソコン":
        working_form["pc_manufacturer_type"] = resolve_pc_manufacturer_type(working_form)

    # ── Layer 2: 修理形態 ──
    repair_result = determine_repair_type_from_rules(working_form)
    if repair_result["matched"]:
        repair_type = repair_result["repair_type"]
        repair_source = "CSVマスタ"
    else:
        repair_type   = determine_repair_type(working_form)
        repair_source = "既存ロジック"

    # ── Layer 3: 概算費用（要確認なら短絡） ──
    if repair_type == "要確認":
        cost_result = {
            "matched": False, "cost_estimate": "要確認",
            "can_announce_cost": True, "needs_escalation": False,
            "cost_status": "pending", "guidance_scope": "always",
            "required_questions": "", "customer_notice": "",
            "internal_note": repair_result.get("notes", ""),
            "missing_fields": [],
            "keyword": "", "priority": None, "csv_name": "",
            "notes": repair_result.get("notes", ""),
        }
        cost_source = "要確認のため短絡"
    else:
        cost_result = determine_cost_from_rules(working_form, repair_type)
        if cost_result["matched"]:
            cost_source = "CSVマスタ"
        else:
            cost_source = "既存ロジック"
    guarded_cost = guard_pending_cost_before_rules(working_form)
    if guarded_cost:
        cost_result = guarded_cost
        cost_source = "安全ガード"

    if cost_result.get("cost_status") == "pending" and not cost_result.get("can_announce_cost", True):
        cost_estimate = cost_result.get("cost_estimate") or "未確定"
    else:
        cost_estimate = cost_result["cost_estimate"] or determine_cost_estimate(working_form, repair_type)

    # ── スクリプトルート（既存ロジック） ──
    script_result = determine_script_route(working_form, repair_type)

    # ── データ消去同意 ──
    needs_data_erase = determine_data_erase_consent(working_form)

    # ── Layer 4: 修理拠点候補 ──
    vendor_result = determine_vendor_from_rules(working_form, repair_type)
    if vendor_result["matched"]:
        vendor = vendor_result["vendor_name"]
    else:
        vendor = determine_vendor_candidate(working_form)
        vendor_result["vendor_name"] = vendor
        if "担当エスカ" in vendor or "要確認" in vendor:
            vendor_result["reason"] = vendor_result.get("vendor_missing_reason") or build_vendor_missing_reason(working_form, repair_type)
        else:
            vendor_result["reason"] = ""
            vendor_result["vendor_missing_reason"] = ""
    handover_requirement = determine_handover_requirement(
        working_form,
        {
            "repair_type": repair_type,
            "vendor": vendor,
            "vendor_result": vendor_result,
            "teams_action": form.get("teams_action", ""),
            "working_form": working_form,
        },
        infer_handover_call_kind(working_form),
    )

    _result_core = {
        # ── 主要判定結果 ──
        "repair_type":         repair_type,
        "cost_estimate":       cost_estimate,
        "script_result":       script_result,
        "needs_data_erase":    needs_data_erase,
        "vendor":              vendor,
        "normalized_product":  working_form.get("product", ""),
        "area_group":          area_group,
        "warranty_result":     warranty_result,
        "warranty_status":     warranty_result["warranty_status"],
        "can_accept":          warranty_result["can_accept"],
        "handover_requirement": handover_requirement,
        # ── 各層の判定詳細 ──
        "alias_result":        alias_result,
        "repair_result":       repair_result,
        "repair_source":       repair_source,
        "cost_result":         cost_result,
        "cost_source":         cost_source,
        "vendor_result":       vendor_result,
        # ── 自動推定 ──
        "inferred_call_line_attrs": inferred_call_line_attrs,
        # ── working_form（デバッグ用） ──
        "working_form":        working_form,
    }
    # ── 判定診断パネル ──
    diagnostics = build_decision_diagnostics(working_form, _result_core)
    _result_core["diagnostics"]    = diagnostics
    _result_core["overall_status"] = diagnostics["overall_status"]
    return _result_core


# ============================================================
# UI ヘルパー
# ============================================================
def _src_badge(source: str) -> str:
    """判定ソースの小バッジ HTML を返す。"""
    color = "#16a085" if source == "CSVマスタ" else "#7f8c8d"
    return (f'<span style="background:{color};color:white;padding:1px 6px;'
            f'border-radius:3px;font-size:0.75em;margin-left:4px;">{source}</span>')


def collect_diagnostic_field_sets(diagnostics: dict) -> tuple:
    missing: set = set()
    invalid: set = set()
    for item in diagnostics.get("items", []):
        missing.update(item.get("missing_fields", []))
        invalid.update(item.get("invalid_fields", []))
    return missing, invalid


def field_actions_for(diagnostics: dict, field_name: str) -> list[str]:
    actions: list[str] = []
    seen: set = set()
    for item in sort_diagnostic_items(diagnostics.get("items", [])):
        fields = set(item.get("missing_fields", [])) | set(item.get("invalid_fields", []))
        if field_name not in fields:
            continue
        action = (item.get("next_action") or "").strip()
        if action and action not in seen:
            actions.append(action)
            seen.add(action)
    return actions


def render_field_anchor(field_name: str):
    st.markdown(field_anchor_html(field_name), unsafe_allow_html=True)


def render_field_attention(field_name: str, missing_fields: set, invalid_fields: set, diagnostics: dict):
    actions = field_actions_for(diagnostics, field_name)
    action_text = " / ".join(actions)
    if field_name in invalid_fields:
        if field_name in ("warranty_start_date", "warranty_end_date"):
            msg = f"⚠️ 形式確認：{field_label(field_name)}を確認してください"
        else:
            msg = f"⚠️ 形式確認：YYYY/MM/DD形式で入力してください"
        if action_text:
            msg += f"（{action_text}）"
        st.warning(msg)
    elif field_name in missing_fields:
        if field_name in ("warranty_start_date", "warranty_end_date"):
            msg = f"⚠️ 必須確認：{field_label(field_name)}を確認してください"
        elif field_name == "product":
            msg = "⚠️ 必須確認：製品を入力してください"
            action_text = ""
        elif field_name in ("appliance_type", "appliance_category"):
            msg = "⚠️ 必須確認：案件分類を入力してください"
            action_text = ""
        else:
            msg = "⚠️ 必須確認"
        if action_text:
            sep = "（" if field_name in ("warranty_start_date", "warranty_end_date") else "："
            end = "）" if sep == "（" else ""
            msg += f"{sep}{action_text}{end}"
        st.warning(msg)


def render_field_marker(field_name: str, missing_fields: set, invalid_fields: set, diagnostics: dict):
    render_field_anchor(field_name)
    render_field_attention(field_name, missing_fields, invalid_fields, diagnostics)


def render_step_list(title: str, steps: list[str]):
    if not steps:
        return
    st.markdown(f"##### {title}")
    for idx, step in enumerate(steps, 1):
        st.markdown(f"**{idx}.** {step}")


# ── 判定タグ色定数 ────────────────────────────────────────────────
TAG_COLOR_NEUTRAL = "#566573"   # 受付可否（未確認・中立）
TAG_COLOR_OK      = "#1E8449"   # 受付OK・拠点確定
TAG_COLOR_WARNING = "#7D6608"   # 要確認・エスカ
TAG_COLOR_ACTION  = "#1A5276"   # 修理方針・スクリプト（通常）
TAG_COLOR_DP      = "#6C3483"   # ダブルプロテクト案件
TAG_COLOR_ERROR   = "#922B21"   # 受付不可・エラー
TAG_COLOR_MISSING = "#B03A2E"   # 未入力・未判定・不足あり
# ─────────────────────────────────────────────────────────────────


def _ui_v3_escape(value) -> str:
    return (str(value or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _ui_v3_block(title: str, lines: list[tuple[str, str]], bg_color: str,
                 min_height: int = 112, link: dict | None = None,
                 compact: bool = False) -> str:
    body_parts = []
    for i, (label, value) in enumerate(lines):
        if compact and i == 0:
            # primary 行は必ず省略せず表示する
            body_parts.append(
                f'<div class="wrt-decision-tag-primary">{_ui_v3_escape(value)}</div>'
            )
        elif i == 1:
            body_parts.append(
                f'<div class="wrt-decision-tag-secondary">'
                f'{_ui_v3_escape(value)}</div>'
            )
        elif i == 0:
            body_parts.append(
                f'<div class="wrt-decision-tag-primary">'
                f'{_ui_v3_escape(value)}</div>'
            )
        else:
            body_parts.append(
                f'<div class="wrt-decision-tag-tertiary">'
                f'{_ui_v3_escape(value)}</div>'
            )
    if link is not None:
        url = link.get("url", "")
        text = link.get("text", "")
        if url and text:
            body_parts.append(
                f'<div style="margin-top:5px;font-size:0.84em;">'
                f'<a href="{_ui_v3_escape(url)}" target="_blank" '
                f'style="color:white;text-decoration:underline;opacity:0.92;">'
                f'{_ui_v3_escape(text)} ↗</a></div>'
            )
        elif text:
            body_parts.append(
                f'<div style="margin-top:5px;font-size:0.84em;opacity:0.7;">'
                f'{_ui_v3_escape(text)}</div>'
            )
    return (
        f'<div class="wrt-decision-tag" style="background:{bg_color};color:white;">'
        f'<div class="wrt-decision-tag-title">{_ui_v3_escape(title)}</div>'
        f'{"".join(body_parts)}'
        f'</div>'
    )


def sync_case_memo_global(form: dict, session_state) -> dict:
    if "case_memo_global" not in session_state:
        session_state["case_memo_global"] = form.get("call_memo", "")
    form["call_memo"] = session_state.get("case_memo_global", "")
    session_state["form"] = form
    return form


def render_common_case_memo(form: dict, key: str = "case_memo_global", height: int = 110) -> None:
    sync_case_memo_global(form, st.session_state)
    st.markdown("##### 📝 案件メモ")
    st.text_area(
        "案件メモ",
        height=height,
        key=key,
        label_visibility="collapsed",
        help="修理依頼書メモやラクテル用テキスト、Teams報告文には自動反映されません。",
    )
    sync_case_memo_global(form, st.session_state)


def _next_confirmation_card_html(cards: list[dict]) -> str:
    tone_styles = {
        "call": ("#fff6e8", "#f2c06b", "#6f4b00"),
        "after": ("#eef5fb", "#b8d5f0", "#234c72"),
        "info": ("#eef8f1", "#9ed6ad", "#23613a"),
    }
    parts = [
        "<div class='next-confirmation-cards' style='display:flex;flex-wrap:wrap;gap:6px;margin:4px 0 8px 0;'>"
    ]
    for card in cards:
        bg, border, fg = tone_styles.get(card.get("tone"), tone_styles["call"])
        timing = html.escape(str(card.get("timing") or "通話中"))
        text = html.escape(str(card.get("text") or ""))
        parts.append(
            "<div style='display:flex;align-items:center;gap:6px;"
            f"background:{bg};border:1px solid {border};color:{fg};"
            "border-radius:8px;padding:5px 8px;font-size:0.86rem;line-height:1.25;'>"
            f"<span style='font-weight:700;font-size:0.75rem;'>{timing}</span>"
            f"<span>{text}</span>"
            "</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def render_next_confirmation_sections(next_sections: dict) -> None:
    cards = next_sections.get("cards") or _confirmation_cards(
        next_sections.get("call_required", []),
        next_sections.get("after_call_ok", []),
    )
    if cards:
        title = "次にやること" if next_sections.get("initial") else "次に確認すること"
        st.markdown(f"##### {title}")
        st.markdown(_next_confirmation_card_html(cards), unsafe_allow_html=True)

    detail_missing = next_sections.get("detail_missing") or {}
    if any(detail_missing.values()):
        with st.expander("不足項目の詳細を開く", expanded=False):
            for area, fields in detail_missing.items():
                if not fields:
                    continue
                st.markdown(f"**{area}**")
                for label in compact_missing_field_labels(fields):
                    st.markdown(f"- {label}")


def _html_lines(lines: list[str]) -> str:
    return "".join(f"<div>{html.escape(str(line))}</div>" for line in lines if str(line or "").strip())


def _status_card_html(tone: str, pill: str, title: str, lines: list[str] | None = None) -> str:
    tone = tone if tone in {"warning", "error", "info", "success"} else "info"
    body = _html_lines(lines or [])
    return (
        f'<div class="wrt-status-card {tone}">'
        '<div class="wrt-status-card-head">'
        f'<span class="wrt-pill {tone}">{html.escape(str(pill or ""))}</span>'
        f'<strong>{html.escape(str(title or ""))}</strong>'
        '</div>'
        f'<div class="wrt-status-card-body">{body}</div>'
        '</div>'
    )


def render_handover_requirement_panel(handover: dict) -> None:
    st.markdown("##### 🔁 引き継ぎ要否")
    handover = handover or _handover_no_match()
    if handover.get("required"):
        priority = _int_or_default(handover.get("priority"))
        tone = "error" if priority <= 2 or "クレーム" in (handover.get("rule_name") or "") else "warning"
        lines = [
            f"楽テルステータス：{handover['rakutel_status']}" if handover.get("rakutel_status") else "",
            f"依頼内容：{handover['handover_request_content']}" if handover.get("handover_request_content") else "",
            f"備考：{handover['notes']}" if handover.get("notes") else "",
            f"理由：{handover['reason']}" if handover.get("reason") else "",
        ]
        st.markdown(
            _status_card_html(tone, "必要", handover.get("rule_name") or "未設定", lines),
            unsafe_allow_html=True,
        )
    else:
        reason = handover.get("reason") or "引き継ぎ対象ルールに一致なし"
        st.markdown(_status_card_html("info", "不要", reason), unsafe_allow_html=True)


def render_warranty_report_send_panel(form: dict, decision: dict) -> None:
    st.markdown("##### 📣 Teamsワランティ送信")
    teams_config = load_teams_config()
    chat_name = teams_config.get("warranty_chat_name") or DEFAULT_TEAMS_CONFIG["warranty_chat_name"]
    if "warranty_report_content_input" in st.session_state:
        form["warranty_report_content"] = st.session_state.get("warranty_report_content_input", "")
    warranty_report_content = st.text_input(
        "確認内容",
        value=form.get("warranty_report_content", ""),
        key="warranty_report_content_input",
        placeholder="例：ユナイトへFAX送信済 / 担当確認お願いします",
    )
    form["warranty_report_content"] = warranty_report_content
    st.session_state.form = form
    generated_message = build_warranty_report_message(form, decision)
    content_hash = stable_hash_text("|".join([
        form.get("rakuteru_no") or form.get("rakutel_no") or "",
        form.get("call_line") or "",
        form.get("warranty_report_content") or "",
    ]))
    if st.session_state.get("_warranty_report_source_hash") != content_hash:
        st.session_state["_warranty_report_source_hash"] = content_hash
        st.session_state["warranty_report_message_display"] = generated_message
    preview_value = st.session_state.get("warranty_report_message_display", generated_message)
    message_for_status = str(preview_value or "")
    _clear_stale_warranty_report_send_transient_state(st.session_state, message_for_status)
    already_sent = _warranty_report_already_sent(st.session_state, message_for_status)
    in_progress = _warranty_report_send_in_progress(st.session_state, message_for_status)
    send_failed = _warranty_report_last_send_failed(st.session_state, message_for_status)
    incomplete_reasons = validate_warranty_report_send_request(
        form,
        decision,
        teams_config,
        message_for_status,
        already_sent=already_sent,
    )
    missing_items = get_warranty_report_missing_items(form)
    status_lines: list[str] = []
    if incomplete_reasons and not already_sent:
        status_lines.extend(["理由："] + [f"- {reason}" for reason in incomplete_reasons[:5]])
        tone = "warning"
        pill = "送信不可"
    elif already_sent:
        sent_at = st.session_state.get("warranty_report_sent_at") or "日時不明"
        status_lines.append(f"送信日時：{sent_at}")
        tone = "info"
        pill = "送信済み"
    elif send_failed:
        error_message = st.session_state.get("warranty_report_send_error_message") or "エラー内容を取得できませんでした"
        status_lines.append(f"ワランティ送信に失敗しました：{error_message}")
        tone = "error"
        pill = "送信失敗"
    elif in_progress:
        started_at = st.session_state.get("warranty_report_send_started_at") or "日時不明"
        status_lines.extend(["ワランティへ送信しています。完了まで画面を閉じないでください。", f"開始時刻：{started_at}"])
        tone = "info"
        pill = "送信処理中"
    else:
        status_lines.append("全案件、ワランティ報告チャットへ送信してください。")
        if missing_items:
            status_lines.extend(
                ["注意：未入力項目があります。内容を確認してから送信してください。"]
                + [f"- {reason}" for reason in missing_items]
            )
            tone = "warning"
        else:
            tone = "success"
        pill = "送信可能"
    st.markdown(_status_card_html(tone, pill, chat_name, status_lines), unsafe_allow_html=True)
    if len(incomplete_reasons) > 5 and not already_sent:
        with st.expander("送信不可理由をすべて表示", expanded=False):
            st.markdown("\n".join(f"- {reason}" for reason in incomplete_reasons[5:]))

    message = st.text_area(
        "送信文プレビュー",
        value=preview_value,
        height=90,
        key="warranty_report_message_display",
        help="ワランティ報告専用の送信文です。ラクテル用テキスト、修理依頼書メモ、既存Teams報告文には反映されません。",
    )

    def request_warranty_report_send(allow_resend: bool = False):
        current_already_sent = _warranty_report_already_sent(st.session_state, message)
        validation_errors = validate_warranty_report_send_request(
            form,
            decision,
            teams_config,
            message,
            already_sent=(current_already_sent and not allow_resend),
        )
        if validation_errors:
            st.warning("送信できない設定があります。Teamsワランティ送信パネルの送信不可理由を確認してください。")
            return
        if in_progress:
            st.warning("ワランティ送信処理中です。完了まで画面を閉じないでください。")
            return
        _mark_warranty_report_send_requested(st.session_state, message)
        st.rerun()

    def execute_requested_warranty_report_send():
        warranty_chat_id = (teams_config.get("warranty_chat_id") or "").strip()
        body = teams_plain_text_to_html(message)
        with st.spinner("Teamsワランティへ送信中です... Microsoft Graph / PowerShell の応答待ちです。"):
            result = send_teams_message_via_powershell(body, chat_id_override=warranty_chat_id)
        vendor_name = ((decision.get("vendor_result") or {}).get("vendor_name") or decision.get("vendor") or "")
        append_teams_send_log(
            result,
            message,
            chat_name,
            form=form,
            vendor=vendor_name,
            teams_action="Teamsワランティ送信",
        )
        if result.get("ok"):
            _mark_warranty_report_sent(st.session_state, message, result=result)
            st.rerun()
        else:
            _mark_warranty_report_send_failed(st.session_state, message, result)
            st.rerun()

    if in_progress:
        st.button(
            "送信処理中...",
            key="warranty_report_sending_button",
            disabled=True,
            use_container_width=True,
        )
    elif already_sent:
        st.button(
            "送信済み",
            key="warranty_report_sent_button",
            disabled=True,
            use_container_width=True,
        )
        if st.button(
            "同じ内容を再送する",
            key="warranty_report_resend_button",
            use_container_width=True,
        ):
            request_warranty_report_send(allow_resend=True)
    elif incomplete_reasons:
        st.button(
            "送信不可",
            key="warranty_report_send_incomplete_button",
            disabled=True,
            use_container_width=True,
        )
    else:
        if st.button(
            "Teamsワランティへ送信",
            key="warranty_report_send_button",
            type="primary",
            use_container_width=True,
        ):
            request_warranty_report_send()

    if _warranty_report_send_requested(st.session_state, message):
        execute_requested_warranty_report_send()


def render_decision_tags_panel(form: dict) -> None:
    st.markdown("##### 🧭 判定タグ")
    try:
        decision = run_decision(form)
        script_reference = build_script_reference_info(decision)
        tags = build_decision_tag_items(decision, form, script_reference)
        next_sections = build_next_confirmation_sections(decision, form)
    except Exception as exc:
        st.warning(f"判定タグを生成できません: {exc}")
        return

    tag_cols = st.columns(4)
    for idx, tag in enumerate(tags):
        with tag_cols[idx]:
            link = None
            if idx == 3:
                if tag.get("matched") and tag.get("url"):
                    link = {"url": tag["url"], "text": tag["link_text"]}
                else:
                    link = {"url": "", "text": tag.get("link_text", "URL未登録（手動で参照）")}
            lines = [("", tag["primary"]), ("", tag["secondary"])]
            if tag.get("tertiary"):
                lines.append(("", tag["tertiary"]))
            if tag.get("quaternary"):
                lines.append(("", tag["quaternary"]))
            if tag.get("quinary"):
                lines.append(("", tag["quinary"]))
            st.markdown(
                _ui_v3_block(tag["title"], lines, tag["color"],
                             min_height=104, link=link,
                             compact=tag.get("compact", False)),
                unsafe_allow_html=True,
            )
    render_next_confirmation_sections(next_sections)


def render_global_top_panels(form: dict) -> None:
    memo_col, tags_col = st.columns([1, 2], gap="medium")
    with memo_col:
        render_common_case_memo(form, "case_memo_global", height=90)
    with tags_col:
        render_decision_tags_panel(form)


def render_common_call_memo(form: dict, key: str, height: int = 110) -> None:
    render_common_case_memo(form, key, height)


def render_tab_local_call_memo_enabled() -> bool:
    return False


def render_case_clear_controls(scope: str, use_container_width: bool = False) -> None:
    pending_key = f"clear_case_pending_{scope}"
    done_key = f"clear_case_done_{scope}"
    confirm_message = "入力中の案件情報をすべてクリアします。必要な送信・記録が完了していることを確認してください。"
    dialog_factory = getattr(st, "dialog", None)

    if callable(dialog_factory):
        @dialog_factory("この案件をクリア")
        def _confirm_case_clear():
            st.warning(confirm_message)
            col_run, col_cancel = st.columns(2)
            with col_run:
                if st.button("クリア実行", key=f"clear_case_dialog_execute_{scope}", type="primary",
                             use_container_width=True):
                    request_case_clear(st.session_state)
                    st.rerun()
            with col_cancel:
                if st.button("キャンセル", key=f"clear_case_dialog_cancel_{scope}", use_container_width=True):
                    st.rerun()

        if st.button("この案件をクリア", key=f"clear_case_prepare_{scope}", type="secondary",
                     use_container_width=use_container_width):
            _confirm_case_clear()
        return

    if not st.session_state.get(pending_key):
        if st.button("この案件をクリア", key=f"clear_case_prepare_{scope}", type="secondary",
                     use_container_width=use_container_width):
            st.session_state[pending_key] = True
            st.rerun()
        return

    st.warning(confirm_message)
    done = st.checkbox("送信・記録が完了しています", key=done_key)
    col_run, col_cancel = st.columns(2)
    with col_run:
        if st.button("クリア実行", key=f"clear_case_execute_{scope}", type="primary",
                     disabled=not done, use_container_width=True):
            request_case_clear(st.session_state)
            st.rerun()
    with col_cancel:
        if st.button("キャンセル", key=f"clear_case_cancel_{scope}", use_container_width=True):
            st.session_state[pending_key] = False
            if done_key in st.session_state:
                del st.session_state[done_key]
            st.rerun()


def build_case_basic_template_display(form: dict, repair_type: str = "") -> str:
    df_tpl = load_template_codes()
    repair_type = repair_type or determine_repair_type(form)
    selected = select_template_for_form(
        form,
        repair_type,
        form.get("warranty_plan", ""),
        df_tpl,
    )
    store_rule = selected.get("store_rule", {})
    if store_rule.get("matched"):
        code_label = _template_option_label(selected)
        lines = [
            "テンプレート判定" + "結果：",
            code_label,
        ]
        matched_label = store_rule.get("matched_source_label") or "判定根拠"
        matched_value = store_rule.get("matched_source_value") or store_rule.get("normalized_store") or store_rule.get("store_keyword")
        if matched_value:
            lines.extend(["", "判定根拠：", f"{matched_label}：{matched_value}"])
        detail = (
            store_rule.get("notes")
            or store_rule.get("template_group")
            or store_rule.get("template_label")
            or store_rule.get("template_code")
        )
        if detail:
            lines.extend(["", "判定内容：", detail])
        display_store = store_rule.get("display_store") or form.get("store_name", "")
        if display_store and display_store != matched_value:
            lines.extend(["", "表示販売店：", display_store])
        return "\n".join(lines)
    return format_store_template_rule_display(store_rule)


def sync_global_case_basic_widget_state(form: dict, session_state) -> dict:
    last_synced = dict(session_state.get("_case_basic_widget_synced_values") or {})
    next_synced = {}
    for widget_key, field in case_basic_widget_to_field_map(session_state=session_state).items():
        form_value = form.get(field, "")
        if widget_key in session_state:
            widget_value = session_state.get(widget_key, "")
            last_value = last_synced.get(widget_key)
            if widget_value == form_value:
                pass
            elif last_value is not None and widget_value != last_value:
                if field == "call_line":
                    form["manual_call_line"] = True
                form[field] = widget_value
                form_value = widget_value
            elif not form_value and widget_value:
                form[field] = widget_value
                form_value = widget_value
            else:
                session_state[widget_key] = form_value
        next_synced[widget_key] = form.get(field, "")
    form = apply_appliance_category_to_form(form)
    session_state["_case_basic_widget_synced_values"] = next_synced
    session_state["form"] = form
    return form


def remember_case_basic_widget_synced_values(form: dict, session_state) -> None:
    session_state["_case_basic_widget_synced_values"] = {
        widget_key: form.get(field, "")
        for widget_key, field in case_basic_widget_to_field_map(session_state=session_state).items()
    }


def _send_inline_candidate_to_master(candidate: dict, key: str) -> None:
    if st.button("マスタ管理で確認して登録", key=key, type="secondary"):
        st.session_state["master_registration_candidate"] = candidate
        st.success("マスタ管理タブへ候補を引き継ぎました。")


def render_inline_manufacturer_registration(form: dict) -> None:
    candidate = build_inline_manufacturer_candidate(form)
    if not candidate:
        return
    st.warning(f"メーカー未登録：{candidate['manufacturer_original']}")
    with st.expander("このメーカーをマスタ登録", expanded=False):
        manufacturer_original = st.text_input(
            "メーカー原文",
            value=candidate["manufacturer_original"],
            key="inline_mfr_original",
            disabled=True,
        )
        normalized = st.text_input(
            "正規化メーカー名",
            value=candidate["normalized_manufacturer"],
            key="inline_mfr_normalized",
        )
        group_name = st.selectbox(
            "メーカーグループ",
            MANUFACTURER_INLINE_GROUP_OPTIONS,
            index=MANUFACTURER_INLINE_GROUP_OPTIONS.index(candidate["group_name"]),
            key="inline_mfr_group",
        )
        row = {
            "group_name": group_name,
            "manufacturers": normalized.strip(),
            "notes": candidate["notes"],
            "manufacturer_original": manufacturer_original,
            "normalized_manufacturer": normalized.strip(),
        }
        st.dataframe(pd.DataFrame([row]), use_container_width=True)
        disabled = not normalized.strip() or normalized.strip() in (MANUFACTURER_OTHER, MANUFACTURER_UNKNOWN)
        if st.button("メーカーを保存", key="inline_mfr_save", type="primary", disabled=disabled):
            result = append_master_manufacturer_group(row)
            _show_master_append_result(result)
            if result.get("ok"):
                st.cache_data.clear()
                bump_case_basic_revision(st.session_state)
                st.rerun()
        _send_inline_candidate_to_master({"manufacturer_group": row, "source_fields": {"manufacturer_original": manufacturer_original}}, "inline_mfr_send_master")


def render_inline_product_alias_registration(form: dict) -> None:
    candidate = build_inline_product_alias_candidate(form)
    if not candidate:
        return
    st.warning(f"製品未登録：{candidate['keyword']}")
    with st.expander("この製品をマスタ登録", expanded=False):
        row = {
            "priority": "10",
            "enabled": "1",
            "keyword": st.text_input("keyword", value=candidate["keyword"], key="inline_alias_keyword"),
            "normalized_product": st.text_input("normalized_product", value=candidate["normalized_product"], key="inline_alias_normalized"),
            "product_group": st.text_input("product_group", value=candidate["product_group"], key="inline_alias_group"),
            "notes": st.text_input("notes", value=candidate["notes"], key="inline_alias_notes"),
        }
        _preview_master_row(row, _ALIAS_COLS)
        duplicate = bool(row["keyword"]) and master_csv_has_duplicate("master_product_alias.csv", row, ["keyword"])
        if duplicate:
            st.warning("同じ keyword が既にあります。")
        disabled = not row["keyword"].strip() or not row["normalized_product"].strip() or duplicate
        if st.button("製品エイリアスを保存", key="inline_alias_save", type="primary", disabled=disabled):
            result = append_master_product_alias(row)
            _show_master_append_result(result)
            if result.get("ok"):
                st.cache_data.clear()
                bump_case_basic_revision(st.session_state)
                st.rerun()
        _send_inline_candidate_to_master({"product_alias": row, "source_fields": {"product_original": candidate["keyword"]}}, "inline_alias_send_master")


def render_inline_store_rule_registration(form: dict, template_selection: dict) -> None:
    candidate = build_inline_store_rule_candidate(form, template_selection)
    if not candidate:
        return
    st.caption(f"販売店テンプレート未登録：{form.get('store_name')}")
    with st.expander("販売店テンプレート候補を作成", expanded=False):
        row = {
            "priority": "10",
            "enabled": "1",
            "store_keyword": st.text_input("store_keyword", value=candidate["store_keyword"], key="inline_store_keyword"),
            "normalized_store": st.text_input("normalized_store", value=candidate["normalized_store"], key="inline_store_normalized"),
            "template_code": st.text_input("template_code", value=candidate["template_code"], key="inline_store_template_code"),
            "template_label": st.text_input("template_label", value=candidate["template_label"], key="inline_store_template_label"),
            "template_group": st.text_input("template_group", value=candidate["template_group"], key="inline_store_template_group"),
            "notes": st.text_input("notes", value=candidate["notes"], key="inline_store_notes"),
        }
        _preview_master_row(row, _STORE_RULE_COLS)
        if st.button("販売店テンプレート候補を保存", key="inline_store_save", type="primary", disabled=not row["store_keyword"].strip()):
            result = append_master_store_rule(row)
            _show_master_append_result(result)
            if result.get("ok"):
                st.cache_data.clear()
                bump_case_basic_revision(st.session_state)
                st.rerun()
        _send_inline_candidate_to_master({"store_rule": row, "source_fields": {"store_name": form.get("store_name", "")}}, "inline_store_send_master")


def render_inline_vendor_rule_registration(form: dict, decision: dict) -> None:
    candidate = build_inline_vendor_rule_candidate(form, decision)
    if not candidate:
        return
    st.warning("修理拠点未確定")
    with st.expander("この条件で修理拠点ルール候補を作成", expanded=False):
        vendor_default = candidate["vendor_name"] if candidate["vendor_name"] in VENDOR_INLINE_OPTIONS else VENDOR_INLINE_OPTIONS[-1]
        row = {
            "priority": "10",
            "enabled": "1",
            "call_line": st.text_input("call_line", value=candidate["call_line"], key="inline_vendor_call_line"),
            "prefecture": st.text_input("prefecture", value=candidate["prefecture"], key="inline_vendor_prefecture"),
            "area_group": st.text_input("area_group", value=candidate["area_group"], key="inline_vendor_area_group"),
            "manufacturer_keyword": st.text_input("manufacturer_keyword", value=candidate["manufacturer_keyword"], key="inline_vendor_manufacturer"),
            "product_keyword": st.text_input("product_keyword", value=candidate["product_keyword"], key="inline_vendor_product"),
            "store_keyword": st.text_input("store_keyword", value=candidate["store_keyword"], key="inline_vendor_store"),
            "repair_type": st.text_input("repair_type", value=candidate["repair_type"], key="inline_vendor_repair_type"),
            "is_over_10years": candidate["is_over_10years"],
            "vendor_name": st.selectbox("vendor_name", VENDOR_INLINE_OPTIONS, index=VENDOR_INLINE_OPTIONS.index(vendor_default), key="inline_vendor_name"),
            "reason": st.text_input("reason", value=candidate["reason"], key="inline_vendor_reason"),
            "needs_escalation": st.selectbox("needs_escalation", ["0", "1"], index=1, key="inline_vendor_needs_escalation"),
            "notes": st.text_input("notes", value=candidate["notes"], key="inline_vendor_notes"),
            "contact_type": st.text_input("contact_type", value=candidate["contact_type"], key="inline_vendor_contact_type"),
        }
        _preview_master_row(row, _VENDOR_COLS)
        confirmed = st.checkbox("内容を確認して保存する", key="inline_vendor_confirm")
        disabled = not confirmed or not row["repair_type"].strip() or not row["vendor_name"].strip()
        if st.button("修理拠点ルール候補を保存", key="inline_vendor_save", type="primary", disabled=disabled):
            result = append_master_vendor_rule(row)
            _show_master_append_result(result)
            if result.get("ok"):
                st.cache_data.clear()
                bump_case_basic_revision(st.session_state)
                st.rerun()
        source_fields = {
            field: form.get(field, "")
            for field in ("call_line", "prefecture", "product", "manufacturer", "store_name")
        }
        _send_inline_candidate_to_master({"vendor_rule": row, "source_fields": source_fields}, "inline_vendor_send_master")


def _send_inline_candidate_to_master(candidate: dict, key: str) -> None:
    if st.button(INLINE_SEND_TO_MASTER_LABEL, key=key, type="secondary"):
        st.session_state["master_registration_candidate"] = candidate
        st.success("マスタ管理タブへ候補を引き継ぎました。")


def render_inline_manufacturer_registration(form: dict) -> None:
    candidate = build_inline_manufacturer_candidate(form)
    if not candidate:
        return
    st.warning(f"メーカー未登録：{candidate['manufacturer_original']}")
    st.caption(f"現在のメーカー判定：{form.get('manufacturer') or '未入力'} / 原文：{candidate['manufacturer_original']}")
    if st.button(INLINE_MANUFACTURER_OPEN_LABEL, key="inline_mfr_open", type="secondary"):
        st.session_state["inline_mfr_registration_open"] = True
    if not st.session_state.get("inline_mfr_registration_open"):
        return
    with st.expander(INLINE_MANUFACTURER_OPEN_LABEL, expanded=True):
        manufacturer_original = st.text_input(
            "メーカー原文",
            value=candidate["manufacturer_original"],
            key="inline_mfr_original_v2",
            disabled=True,
        )
        normalized = st.text_input(
            "正規化メーカー名",
            value=candidate["normalized_manufacturer"],
            key="inline_mfr_normalized_v2",
        )
        group_name = st.selectbox(
            "メーカーグループ",
            MANUFACTURER_INLINE_GROUP_OPTIONS,
            index=MANUFACTURER_INLINE_GROUP_OPTIONS.index(candidate["group_name"]),
            key="inline_mfr_group_v2",
        )
        row = {
            "group_name": group_name,
            "manufacturers": ";".join(_manufacturer_inline_aliases(manufacturer_original, normalized.strip())),
            "notes": candidate["notes"],
            "manufacturer_original": manufacturer_original,
            "normalized_manufacturer": normalized.strip(),
        }
        st.dataframe(pd.DataFrame([row]), use_container_width=True)
        disabled = not normalized.strip() or normalized.strip() in (MANUFACTURER_OTHER, MANUFACTURER_UNKNOWN)
        save_col, master_col = st.columns(2)
        with save_col:
            if st.button(INLINE_SAVE_AND_REDECIDE_LABEL, key="inline_mfr_save_v2", type="primary", disabled=disabled):
                result = append_master_manufacturer_group(row)
                _show_master_append_result(result)
                if result.get("ok"):
                    st.cache_data.clear()
                    form["manufacturer"] = normalized.strip()
                    form["manufacturer_original"] = manufacturer_original
                    st.session_state.form = form
                    st.session_state["inline_mfr_registration_open"] = False
                    bump_case_basic_revision(st.session_state)
                    st.rerun()
        with master_col:
            _send_inline_candidate_to_master(
                {"manufacturer_group": row, "source_fields": {"manufacturer_original": manufacturer_original}},
                "inline_mfr_send_master_v2",
            )


def render_inline_product_alias_registration(form: dict) -> None:
    candidate = build_inline_product_alias_candidate(form)
    if not candidate:
        return
    st.warning(f"製品未登録：{candidate['keyword']}")
    with st.expander("製品登録候補を開く", expanded=False):
        row = {
            "priority": "10",
            "enabled": "1",
            "keyword": st.text_input("keyword", value=candidate["keyword"], key="inline_alias_keyword_v2"),
            "normalized_product": st.text_input("normalized_product", value=candidate["normalized_product"], key="inline_alias_normalized_v2"),
            "product_group": st.text_input("product_group", value=candidate["product_group"], key="inline_alias_group_v2"),
            "notes": st.text_input("notes", value=candidate["notes"], key="inline_alias_notes_v2"),
        }
        _preview_master_row(row, _ALIAS_COLS)
        duplicate = bool(row["keyword"]) and master_csv_has_duplicate("master_product_alias.csv", row, ["keyword"])
        if duplicate:
            st.warning("同じ keyword が既にあります。")
        disabled = not row["keyword"].strip() or not row["normalized_product"].strip() or duplicate
        save_col, master_col = st.columns(2)
        with save_col:
            if st.button(INLINE_SAVE_AND_REDECIDE_LABEL, key="inline_alias_save_v2", type="primary", disabled=disabled):
                result = append_master_product_alias(row)
                _show_master_append_result(result)
                if result.get("ok"):
                    st.cache_data.clear()
                    form["product"] = row["normalized_product"].strip()
                    st.session_state.form = form
                    bump_case_basic_revision(st.session_state)
                    st.rerun()
        with master_col:
            _send_inline_candidate_to_master(
                {"product_alias": row, "source_fields": {"product_original": candidate["keyword"]}},
                "inline_alias_send_master_v2",
            )


def render_inline_store_rule_registration(form: dict, template_selection: dict) -> None:
    candidate = build_inline_store_rule_candidate(form, template_selection)
    if not candidate:
        return
    st.caption(f"販売店テンプレート未登録：{form.get('store_name')}")
    with st.expander("販売店テンプレート候補を開く", expanded=False):
        row = {
            "priority": "10",
            "enabled": "1",
            "store_keyword": st.text_input("store_keyword", value=candidate["store_keyword"], key="inline_store_keyword_v2"),
            "normalized_store": st.text_input("normalized_store", value=candidate["normalized_store"], key="inline_store_normalized_v2"),
            "template_code": st.text_input("template_code", value=candidate["template_code"], key="inline_store_template_code_v2"),
            "template_label": st.text_input("template_label", value=candidate["template_label"], key="inline_store_template_label_v2"),
            "template_group": st.text_input("template_group", value=candidate["template_group"], key="inline_store_template_group_v2"),
            "notes": st.text_input("notes", value=candidate["notes"], key="inline_store_notes_v2"),
        }
        _preview_master_row(row, _STORE_RULE_COLS)
        save_col, master_col = st.columns(2)
        with save_col:
            if st.button(INLINE_SAVE_AND_REDECIDE_LABEL, key="inline_store_save_v2", type="primary", disabled=not row["store_keyword"].strip()):
                result = append_master_store_rule(row)
                _show_master_append_result(result)
                if result.get("ok"):
                    st.cache_data.clear()
                    bump_case_basic_revision(st.session_state)
                    st.rerun()
        with master_col:
            _send_inline_candidate_to_master(
                {"store_rule": row, "source_fields": {"store_name": form.get("store_name", "")}},
                "inline_store_send_master_v2",
            )


def render_inline_vendor_rule_registration(form: dict, decision: dict) -> None:
    candidate = build_inline_vendor_rule_candidate(form, decision)
    if not candidate:
        return
    vendor_result = decision.get("vendor_result", {}) or {}
    if vendor_result.get("vendor_missing_reason"):
        st.warning(f"拠点未確定：担当確認が必要\n\n理由：{vendor_result['vendor_missing_reason']}")
    else:
        st.warning("修理拠点未確定")
    if st.button("修理拠点ルール候補を開く", key="inline_vendor_open_v2", type="secondary"):
        st.session_state["inline_vendor_registration_open"] = True
    if not st.session_state.get("inline_vendor_registration_open"):
        return
    with st.expander("修理拠点ルール候補を開く", expanded=True):
        vendor_default = candidate["vendor_name"] if candidate["vendor_name"] in VENDOR_INLINE_OPTIONS else VENDOR_INLINE_OPTIONS[-1]
        row = {
            "priority": "10",
            "enabled": "1",
            "call_line": st.text_input("call_line", value=candidate["call_line"], key="inline_vendor_call_line_v2"),
            "prefecture": st.text_input("prefecture", value=candidate["prefecture"], key="inline_vendor_prefecture_v2"),
            "area_group": st.text_input("area_group", value=candidate["area_group"], key="inline_vendor_area_group_v2"),
            "manufacturer_keyword": st.text_input("manufacturer_keyword", value=candidate["manufacturer_keyword"], key="inline_vendor_manufacturer_v2"),
            "product_keyword": st.text_input("product_keyword", value=candidate["product_keyword"], key="inline_vendor_product_v2"),
            "store_keyword": st.text_input("store_keyword", value=candidate["store_keyword"], key="inline_vendor_store_v2"),
            "repair_type": st.text_input("repair_type", value=candidate["repair_type"], key="inline_vendor_repair_type_v2"),
            "is_over_10years": candidate["is_over_10years"],
            "vendor_name": st.selectbox("vendor_name", VENDOR_INLINE_OPTIONS, index=VENDOR_INLINE_OPTIONS.index(vendor_default), key="inline_vendor_name_v2"),
            "reason": st.text_input("reason", value=candidate["reason"], key="inline_vendor_reason_v2"),
            "needs_escalation": st.selectbox("needs_escalation", ["0", "1"], index=1, key="inline_vendor_needs_escalation_v2"),
            "notes": st.text_input("notes", value=candidate["notes"], key="inline_vendor_notes_v2"),
            "contact_type": st.text_input("contact_type", value=candidate["contact_type"], key="inline_vendor_contact_type_v2"),
        }
        _preview_master_row(row, _VENDOR_COLS)
        confirmed = st.checkbox("内容を確認して保存する", key="inline_vendor_confirm_v2")
        disabled = not confirmed or not row["repair_type"].strip() or not row["vendor_name"].strip()
        save_col, master_col = st.columns(2)
        with save_col:
            if st.button(INLINE_SAVE_AND_REDECIDE_LABEL, key="inline_vendor_save_v2", type="primary", disabled=disabled):
                result = append_master_vendor_rule(row)
                _show_master_append_result(result)
                if result.get("ok"):
                    st.cache_data.clear()
                    bump_case_basic_revision(st.session_state)
                    st.rerun()
        with master_col:
            source_fields = {
                field: form.get(field, "")
                for field in ("call_line", "prefecture", "product", "manufacturer", "store_name")
            }
            _send_inline_candidate_to_master({"vendor_rule": row, "source_fields": source_fields}, "inline_vendor_send_master_v2")


def render_shared_case_basic_editor(form: dict, key_suffix: str, show_template_result: bool = True) -> dict:
    header_col, action_col = st.columns([2.2, 1])
    with header_col:
        if show_template_result:
            st.markdown("##### 🧾 案件基本（共通）")
        else:
            st.markdown("##### 案件基本")
    with action_col:
        render_case_clear_controls(f"case_basic_{key_suffix}", use_container_width=True)

    form["call_line"] = normalize_call_line_for_display(form.get("call_line", ""))
    call_line_opts = get_call_line_options()
    if form.get("call_line") and form.get("call_line") not in call_line_opts:
        call_line_opts = [form.get("call_line")] + call_line_opts
    form = apply_appliance_category_to_form(form)

    revision = get_case_basic_revision(st.session_state)
    inferred_appliance_type = infer_appliance_type_from_form(form, form.get("appliance_type", ""))
    if not form.get("appliance_category") and inferred_appliance_type != form.get("appliance_type", ""):
        form["appliance_type"] = inferred_appliance_type
        form = apply_appliance_category_to_form(form)
        appliance_widget_key = case_basic_widget_key("appliance_category", revision)
        if appliance_widget_key in st.session_state:
            st.session_state[appliance_widget_key] = form.get("appliance_category", "")
    if form.get("call_line") and form.get("call_line") not in call_line_opts:
        call_line_opts = [form.get("call_line")] + call_line_opts
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        form["call_line"] = st.selectbox(
            "回線名",
            call_line_opts,
            index=call_line_opts.index(form.get("call_line", ""))
            if form.get("call_line", "") in call_line_opts else 0,
            key=case_basic_widget_key("call_line", revision),
        )
        form["product"] = st.text_input(
            "製品",
            value=form.get("product", ""),
            key=case_basic_widget_key("product", revision),
        )
    with col_b:
        form["appliance_category"] = st.selectbox(
            "案件分類",
            APPLIANCE_CATEGORY_OPTIONS,
            index=APPLIANCE_CATEGORY_OPTIONS.index(form.get("appliance_category", ""))
            if form.get("appliance_category", "") in APPLIANCE_CATEGORY_OPTIONS else 0,
            key=case_basic_widget_key("appliance_category", revision),
        )
        form = apply_appliance_category_to_form(form)
        manufacturer_opts = get_manufacturer_options()
        current_manufacturer = form.get("manufacturer", "")
        if current_manufacturer and current_manufacturer not in manufacturer_opts:
            form["manufacturer_original"] = form.get("manufacturer_original") or current_manufacturer
            current_manufacturer = normalize_manufacturer_for_select(current_manufacturer)
        form["manufacturer"] = st.selectbox(
            "メーカー",
            manufacturer_opts,
            index=manufacturer_opts.index(current_manufacturer)
            if current_manufacturer in manufacturer_opts else 0,
            key=case_basic_widget_key("manufacturer", revision),
        )
        if form.get("manufacturer") in (MANUFACTURER_OTHER, MANUFACTURER_UNKNOWN) and form.get("manufacturer_original"):
            st.caption(f"原文：{form.get('manufacturer_original')}")
    with col_c:
        form["store_name"] = st.text_input(
            "販売店",
            value=form.get("store_name", ""),
            key=case_basic_widget_key("store_name", revision),
        )
        form["product_price"] = st.text_input(
            "商品価格",
            value=form.get("product_price", ""),
            key=case_basic_widget_key("product_price", revision),
        )
        if show_template_result:
            preview_decision = run_decision(form)
            template_display = build_case_basic_template_display(
                form,
                preview_decision.get("repair_type", ""),
            )
            st.markdown("**修理依頼文テンプレ**")
            st.info(template_display)
            df_tpl = load_template_codes()
            template_selection = select_template_for_form(
                form,
                preview_decision.get("repair_type", ""),
                form.get("warranty_plan", ""),
                df_tpl,
            )
            render_inline_store_rule_registration(form, template_selection)

    render_inline_manufacturer_registration(form)
    render_inline_product_alias_registration(form)
    st.session_state.form = form
    remember_case_basic_widget_synced_values(form, st.session_state)
    return form


def render_global_case_basic_panel(form: dict) -> dict:
    return render_shared_case_basic_editor(form, "global", show_template_result=False)


def sync_after_call_rakutel_action_inputs(form: dict, session_state) -> dict:
    revision = get_case_basic_revision(session_state)
    call_line_key = case_basic_widget_key("call_line", revision)
    call_line_value = (session_state.get(call_line_key) or "").strip()
    if call_line_value:
        form["call_line"] = normalize_call_line_for_display(call_line_value)
    for widget_key, field_name in [
        ("call_direction_select", "call_direction"),
        ("counterparty_type_select", "counterparty_type"),
        ("counterparty_detail_input", "counterparty_detail"),
        ("contact_phone_input", "contact_phone"),
        ("operator_name_input", "operator_name"),
    ]:
        if widget_key in session_state:
            form[field_name] = session_state.get(widget_key, "")
    form["caller_type"] = form.get("counterparty_type") or form.get("caller_type") or "加入者"
    session_state.form = form
    return form


def _set_manual_check(item_id: str, value: bool) -> None:
    manual = dict(st.session_state.get("call_check_manual", {}))
    manual[item_id] = bool(value)
    st.session_state["call_check_manual"] = manual


def manual_check_widget_key(item: dict, index: int = 0, prefix: str = "manual_check") -> str:
    item_id = item.get("id") or "manual_item"
    label = item.get("label") or item.get("input_label") or item_id
    return f"{prefix}_{item_id}_{index}_{stable_hash_text(label)}"


def _choice_text_hearing_value(form: dict, field_name: str, options: list[str],
                               *, choice_key: str, text_key: str, label: str,
                               placeholder: str) -> str:
    current = get_hearing_value(form, field_name)
    selected_index = options.index(current) if current in options else 0
    selected = st.selectbox(
        label,
        options,
        index=selected_index,
        key=choice_key,
    )
    text_initial = current if current and current not in options else ""
    st.markdown(
        '<div class="wrt-sub-input-label">補足入力</div>',
        unsafe_allow_html=True,
    )
    typed = st.text_input(
        "補足入力",
        value=text_initial,
        key=text_key,
        placeholder=placeholder,
        label_visibility="collapsed",
    )
    form[f"{field_name}_choice"] = selected
    form[f"{field_name}_text"] = typed
    return _resolve_choice_text_value(selected, typed)


def render_call_hearing_inputs(form: dict) -> None:
    sync_hearing_widget_state_to_form(form)
    st.markdown("### 📋 聴取内容（修理依頼書メモ反映）")
    form["symptom_detail"] = st.text_area(
        "具体的な症状",
        value=form.get("symptom_detail", ""),
        height=80,
        key="call_hearing_symptom_detail",
    )
    form["occurrence_time"] = _choice_text_hearing_value(
        form,
        "occurrence_time",
        _SELECT_WITH_OTHER_OPTIONS.get("occurrence_time", []),
        choice_key="call_hearing_occurrence_time_choice",
        text_key="call_hearing_occurrence_time_text",
        label="発生時期",
        placeholder="例：2〜3日前から",
    )
    form["occurrence_frequency"] = _choice_text_hearing_value(
        form,
        "occurrence_frequency",
        _SELECT_WITH_OTHER_OPTIONS.get("occurrence_frequency", []),
        choice_key="call_hearing_occurrence_frequency_choice",
        text_key="call_hearing_occurrence_frequency_text",
        label="発生頻度",
        placeholder="例：朝だけ、使用中だけ",
    )
    st.info(
        "修理依頼書メモ反映予定\n"
        + "\n".join(build_attention_memo_preview_lines(form))
    )
    st.session_state.form = form


def render_now_action_item(item: dict, form: dict, index: int = 0) -> None:
    item_id = item["id"]
    if item_id in HEARING_INPUT_FIELD_IDS:
        return
    st.markdown(f"**{item['label']}**")
    input_type = item.get("input")
    fields = item.get("fields") or ()
    input_key = f"now_input_{item_id}_{index}_{stable_hash_text(item.get('label', ''))}"
    if input_type == "textarea" and fields:
        form[fields[0]] = st.text_area(
            item.get("input_label") or field_label(fields[0]),
            value=form.get(fields[0], ""),
            height=70,
            key=input_key,
        )
    elif input_type == "text" and fields:
        form[fields[0]] = st.text_input(
            item.get("input_label") or field_label(fields[0]),
            value=form.get(fields[0], ""),
            key=input_key,
        )
    elif input_type == "select_with_other" and fields:
        field_name = fields[0]
        options = _SELECT_WITH_OTHER_OPTIONS.get(item_id, [])
        predefined = [o for o in options if o != "その他"]
        current = (form.get(field_name) or "").strip()
        display_options = [""] + options
        if current in predefined:
            sel_idx = display_options.index(current)
        elif current:
            sel_idx = display_options.index("その他") if "その他" in display_options else 0
        else:
            sel_idx = 0
        selected = st.selectbox(
            item.get("input_label") or field_label(field_name),
            display_options,
            index=sel_idx,
            key=input_key,
            format_func=lambda x: "（未選択）" if x == "" else x,
        )
        if selected == "その他":
            free_key = f"{input_key}_free"
            free_initial = current if current and current not in options else ""
            typed = st.text_input("詳細を入力", value=free_initial, key=free_key)
            form[field_name] = typed
        elif selected:
            form[field_name] = selected
        else:
            form[field_name] = ""
    elif input_type == "select_other_repair_requested" and fields:
        current = (form.get(fields[0]) or "未確認").strip() or "未確認"
        options = ["未確認", "なし", "あり"]
        if current not in options:
            current = "未確認"
        form[fields[0]] = st.selectbox(
            item.get("input_label") or field_label(fields[0]),
            options,
            index=options.index(current),
            key=input_key,
        )
    elif input_type == "address_with_check":
        form["address"] = st.text_input(
            "訪問先住所",
            value=form.get("address", ""),
            key="now_input_visit_address",
        )
        checked = st.checkbox(
            "訪問先住所確認済み",
            value=_manual_check_done(st.session_state.get("call_check_manual", {}), item_id),
            key=manual_check_widget_key(item, index),
        )
        _set_manual_check(item_id, checked)
    elif input_type == "checkbox" and fields:
        value = st.checkbox(
            item.get("input_label") or field_label(fields[0]),
            value=bool(form.get(fields[0])),
            key=f"now_input_{item_id}",
        )
        form[fields[0]] = value
    else:
        checked = st.checkbox(
            "確認済み",
            value=_manual_check_done(st.session_state.get("call_check_manual", {}), item_id),
            key=manual_check_widget_key(item, index),
        )
        _set_manual_check(item_id, checked)
    st.session_state.form = form


def render_warranty_date_input(field_name: str, label: str, form: dict,
                               missing_fields: set, invalid_fields: set, diagnostics: dict):
    """保証日付をカレンダー入力し、フォームには YYYY/MM/DD 文字列で保持する。"""
    render_field_marker(field_name, missing_fields, invalid_fields, diagnostics)
    current_date = form_date_text_to_date(form.get(field_name, ""))
    unknown_key = f"{field_name}_unknown"
    date_key = f"{field_name}_date"
    clear_key = f"{field_name}_clear"

    if current_date and st.session_state.get(unknown_key):
        st.session_state[unknown_key] = False

    unknown = st.checkbox(
        f"{label} 未確認",
        value=(current_date is None),
        key=unknown_key,
        help="ONの場合は空欄扱いになり、保証期間判定は未確認になります。",
    )
    if unknown:
        form[field_name] = ""
        if st.session_state.get(date_key) is not None:
            st.session_state[date_key] = None
        st.date_input(label, value=None, key=date_key, disabled=True)
    else:
        if current_date and st.session_state.get(date_key) != current_date:
            st.session_state[date_key] = current_date
        selected = st.date_input(label, value=current_date, key=date_key)
        form[field_name] = date_to_form_date_text(selected)

    if st.button(f"{label}をクリア", key=clear_key, use_container_width=False):
        form[field_name] = ""
        st.session_state[unknown_key] = True
        st.session_state[date_key] = None
        st.rerun()


def empty_form() -> dict:
    form = {k: "" for k in FIELD_LABELS}
    form["is_over_10years"] = False
    form["genre"] = ""
    form["category"] = ""
    form["operator_name"] = ""
    form["rakuteru_no"] = ""
    form["contact_phone"] = ""
    form["caller_type"] = "加入者"
    form["call_direction"] = "受電"
    form["counterparty_type"] = "加入者"
    form["counterparty_detail"] = ""
    form["warranty_report_content"] = ""
    form["extracted_time"] = ""
    form["attention_memo"] = ""
    form["rakutel_text"] = ""
    form["teams_chat_message"] = ""
    return form


def init_session():
    if "form" not in st.session_state:
        st.session_state.form = empty_form()
    else:
        for key, value in empty_form().items():
            st.session_state.form.setdefault(key, value)
    if "case_basic_revision" not in st.session_state:
        st.session_state.case_basic_revision = 0
    st.session_state.form = apply_default_operator_name(st.session_state.form)
    if "extracted" not in st.session_state:
        st.session_state.extracted = {}
    if "pasted_text" not in st.session_state:
        st.session_state.pasted_text = ""
    if "teams_send_log" not in st.session_state:
        st.session_state.teams_send_log = []
    if "master_registration_candidate" not in st.session_state:
        st.session_state.master_registration_candidate = {}
    if "call_check_manual" not in st.session_state:
        st.session_state.call_check_manual = {}
    if "show_copy_import" not in st.session_state:
        set_show_copy_import(st.session_state, show_copy_import(st.session_state))


# ============================================================
# タブ1: 通話中判定
# ============================================================
def render_tab_call():
    # UI改修: 通話中判定タブ専用の表示密度を調整
    st.markdown(
        """
        <style>
        div[data-testid="stHorizontalBlock"] {
            gap: 16px;
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.1rem;
        }
        div[data-testid="stMetricDelta"] {
            font-size: 0.9rem;
        }
        div[data-testid="stAlert"] {
            padding-top: 0.45rem;
            padding-bottom: 0.45rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # UI改修: 左=入力パネル、右=判定結果の2カラム構成
    col_input, col_result = st.columns([1, 2], gap="medium")

    # UI改修: 左カラムにコピー取り込みとフォームを集約
    with col_input:
        st.markdown("##### 📋 コピー情報取り込み")
        with st.expander(
            "保証画面などのテキストを貼り付ける",
            expanded=show_copy_import(st.session_state),
        ):
            if _PYPERCLIP_AVAILABLE:
                if st.button("📋 クリップボードから直接抽出", use_container_width=True, type="secondary"):
                    try:
                        text = pyperclip.paste()
                        if not text or not text.strip():
                            st.warning("クリップボードが空です。手動貼り付け欄を使ってください。")
                        else:
                            st.session_state["pasted_text"] = text
                            extracted = extract_fields_from_pasted_text(text)
                            st.session_state["extracted"] = extracted
                            if extracted:
                                st.session_state["form"] = apply_extracted_fields_to_form(
                                    extracted, st.session_state["form"])
                                st.session_state["form"]["extracted_time"] = _format_extracted_time()
                                request_case_basic_widget_refresh(st.session_state)
                                close_copy_import_panel(st.session_state)
                                st.rerun()
                            else:
                                st.warning("抽出できる項目が見つかりませんでした。貼り付け内容を確認してください。")
                    except Exception as e:
                        st.warning(f"クリップボード読み取り失敗（{e}）。手動貼り付け欄を使ってください。")
            else:
                st.info("pyperclip が使えません。手動貼り付け欄を使ってください。")

            pasted = st.text_area(
                "保証画面などのテキストを貼り付け",
                value=st.session_state.pasted_text,
                height=190,
                key="paste_area",
                placeholder="ここにコピーしたテキストを貼り付けてください...",
            )
            st.session_state.pasted_text = pasted

            if st.button("🔍 抽出する", use_container_width=True):
                if pasted.strip():
                    extracted = extract_fields_from_pasted_text(pasted)
                    st.session_state.extracted = extracted
                    if extracted:
                        st.success("抽出しました。内容を確認してからフォームへ反映してください。")
                    else:
                        st.warning("抽出できる項目が見つかりませんでした。貼り付け内容を確認してください。")
                else:
                    st.warning("テキストを貼り付けてください。")

            if st.session_state.extracted:
                st.markdown("**抽出結果**")
                ext = st.session_state.extracted
                label_map = {
                    "plan": "保証プラン", "warranty_start_date": "保証開始日",
                    "warranty_end_date": "保証終了日", "customer_code": "お客様コード",
                    "customer_name": "お客様名", "phone_number": "電話番号",
                    "address": "住所", "prefecture": "都道府県",
                    "wrt_no": "WRT-NO", "product_price": "商品価格",
                    "manufacturer": "メーカー", "model_number": "型番",
                    "series": "シリーズ", "store_name": "販売店",
                }
                rows = [f"- **{lbl}**: {ext.get(k,'') or '─'}" for k, lbl in label_map.items()]
                st.markdown("\n".join(rows))
                if st.button("📥 フォームへ反映", use_container_width=True):
                    st.session_state.form = apply_extracted_fields_to_form(
                        st.session_state.extracted, st.session_state.form)
                    st.session_state["form"]["extracted_time"] = _format_extracted_time()
                    request_case_basic_widget_refresh(st.session_state)
                    close_copy_import_panel(st.session_state)
                    st.success("フォームへ反映しました。")
                    st.rerun()

        form = st.session_state.form

        st.subheader("📝 受付補足情報")
        pre_decision = run_decision(form)  # UI修正v2
        pre_diagnostics = pre_decision.get("diagnostics", {})  # UI修正v2
        missing_fields_set, invalid_fields_set = collect_diagnostic_field_sets(pre_diagnostics)

        pref_opts = [""] + PREFECTURES

        st.markdown("##### 通話中に見る補足項目")
        if SHOW_CALL_TYPE_IN_CALL_FORM:
            call_type_opts = ["", "新規入電", "折り返し", "再入電", "その他"]
            form["call_type"] = st.selectbox(
                "入電種別",
                call_type_opts,
                index=call_type_opts.index(form.get("call_type", ""))
                if form.get("call_type", "") in call_type_opts else 0,
            )
        render_field_marker("prefecture", missing_fields_set, invalid_fields_set, pre_diagnostics)
        form["prefecture"]    = st.selectbox("都道府県", pref_opts,
            index=pref_opts.index(form.get("prefecture","")) if form.get("prefecture") in pref_opts else 0)
        render_field_marker("model_number", missing_fields_set, invalid_fields_set, pre_diagnostics)
        form["model_number"]  = st.text_input("型番",         form.get("model_number",""))
        form["warranty_plan"] = st.text_input("保証プラン",   form.get("warranty_plan",""))
        if is_double_protect_plan(form.get("warranty_plan", "")):
            st.warning(f"物損付 / DP案件: {double_protect_plan_label(form.get('warranty_plan', ''))}。物損保証金額はシステム確認。")

        with st.expander("補助情報を開く", expanded=True):
            render_field_marker("address", missing_fields_set, invalid_fields_set, pre_diagnostics)
            form["address"]       = st.text_input("お客様住所",   form.get("address",""))
            form["product_original"] = st.text_input(
                "製品メモ / 原文製品名",
                form.get("product_original",""),
                placeholder="コピー抽出されたシリーズ名・分類名など",
            )
            form["series"]        = st.text_input("シリーズ",     form.get("series",""))
            form["manufacturer_original"] = st.text_input(
                "メーカー原文 / コピー元メーカー名",
                form.get("manufacturer_original",""),
                placeholder="コピー抽出されたメーカー名など",
            )
            if form.get("product") == "パソコン":
                current_pc_type = form.get("pc_manufacturer_type") or infer_pc_manufacturer_type(
                    form.get("manufacturer_original", ""),
                    form.get("manufacturer", ""),
                )
                if current_pc_type not in PC_MANUFACTURER_TYPE_OPTIONS:
                    current_pc_type = PC_MANUFACTURER_TYPE_UNKNOWN
                render_field_marker("pc_manufacturer_type", missing_fields_set, invalid_fields_set, pre_diagnostics)
                form["pc_manufacturer_type"] = st.selectbox(
                    "PCメーカー区分",
                    PC_MANUFACTURER_TYPE_OPTIONS,
                    index=PC_MANUFACTURER_TYPE_OPTIONS.index(current_pc_type),
                )
            else:
                form["pc_manufacturer_type"] = PC_MANUFACTURER_TYPE_UNKNOWN
            st.caption("商品価格は「案件基本（共通）」で編集します。")
            form["wrt_no"]        = st.text_input("WRT-NO",       form.get("wrt_no",""))
            form["customer_code"] = st.text_input("お客様コード", form.get("customer_code",""))
            form["customer_name"] = st.text_input("お客様名",     form.get("customer_name",""))
            form["phone_number"]  = st.text_input("電話番号",     form.get("phone_number",""))
            sync_hearing_widget_state_to_form(form)
            hearing_summary_lines = build_hearing_summary_lines(form)
            st.markdown("##### 聴取内容まとめ")
            for line in hearing_summary_lines:
                st.markdown(line)
            form["maker_warranty_period"] = st.text_input("メーカー保証期間", form.get("maker_warranty_period",""))
            form["install_type"]  = st.text_input("設置形態",     form.get("install_type",""))
            render_warranty_date_input(
                "warranty_start_date", "保証開始日",
                form, missing_fields_set, invalid_fields_set, pre_diagnostics,
            )
            # 製造10年以上チェック（賃貸・既築案件の業者判定に使用）
            warranty_start = form.get("warranty_start_date", "")
            years_hint = ""
            if warranty_start:
                start_dt = parse_date_safe(warranty_start)
                if start_dt:
                    years = (date.today() - start_dt).days // 365
                    years_hint = f"（保証開始日から約 {years} 年）"
            form["is_over_10years"] = st.checkbox(
                f"製造10年以上 {years_hint}",
                value=form.get("is_over_10years", False),
                key="is_over_10years_cb",
                help="賃貸・既築案件の修理業者判定に使用します。製造年が不明な場合はお客様に確認してください。",
            )
            render_warranty_date_input(
                "warranty_end_date", "保証終了日",
                form, missing_fields_set, invalid_fields_set, pre_diagnostics,
            )
            render_field_marker("store_name", missing_fields_set, invalid_fields_set, pre_diagnostics)
            form["store_name"]    = st.text_input("販売店",       form.get("store_name",""))
            render_field_marker("extra_condition", missing_fields_set, invalid_fields_set, pre_diagnostics)
            form["extra_condition"] = st.text_area(
                "補足条件",
                form.get("extra_condition",""),
                height=90,
                placeholder="例: 家庭用 / 業務用 / ガス漏れ / 未確認",
            )
            if "エアコン" in (form.get("product") or ""):
                q_cols = st.columns(4)
                for idx, label in enumerate(["家庭用", "業務用", "ガス漏れ", "未確認"]):
                    if q_cols[idx].button(label, key=f"ac_extra_{label}", use_container_width=True):
                        form["extra_condition"] = label
                        st.session_state.form = form
                        st.rerun()
        st.session_state.form = form

    # ── 判定実行（form確定後・right描画前に1回だけ）──
    decision = pre_decision  # UI修正v2
    repair_type      = decision["repair_type"]
    cost_estimate    = decision["cost_estimate"]
    script_result    = decision["script_result"]
    needs_data_erase = decision["needs_data_erase"]
    alias_result     = decision["alias_result"]
    repair_result    = decision["repair_result"]
    repair_source    = decision["repair_source"]
    cost_result      = decision["cost_result"]
    cost_source      = decision["cost_source"]
    vendor              = decision["vendor"]
    vendor_result       = decision["vendor_result"]
    normalized_product  = decision["normalized_product"]
    inferred_call_line_attrs = decision.get("inferred_call_line_attrs", {})
    area_group          = decision.get("area_group", "")
    warranty_result     = decision["warranty_result"]
    warranty_status     = warranty_result.get("warranty_status", "unknown")
    warranty_can_accept = warranty_result.get("can_accept", False)
    diagnostics         = pre_diagnostics  # UI修正v2

    guidance_text = build_customer_cost_guidance(
        repair_type, cost_estimate, script_result["price_guidance_allowed"])

    # UI改修: 右カラムはゾーンB/C/Dの順で判定結果を表示
    with col_result:
        st.subheader("⚡ 通話中判定結果")
        manual_check = st.session_state.get("call_check_manual", {})
        script_reference = build_script_reference_info(decision)
        script_guidance = build_script_guidance_panel_info(st.session_state.form, decision, script_reference)
        question_categories = build_question_categories(
            st.session_state.form, repair_type, needs_data_erase,
            diagnostics, warranty_result, cost_result, manual_check,
            script_guidance.get("hearing_items", []),
        )
        now_action_plan = build_now_action_plan(
            st.session_state.form, repair_type, needs_data_erase,
            diagnostics, warranty_result, cost_result, manual_check,
            script_guidance.get("hearing_items", []),
        )

        st.markdown("##### 参照スクリプト")
        st.markdown(f"推奨：**{script_reference.get('display', '未判定')}**")
        if script_reference.get("initial_line"):
            st.caption(f"初期回線：{script_reference.get('initial_line')}")
        if script_reference.get("basis"):
            st.caption(f"判定根拠：{script_reference.get('basis')}")
        if script_reference.get("correction_reason"):
            st.caption(f"補正理由：{script_reference.get('correction_reason')}")
        if script_reference.get("script_changed") and script_reference.get("previous_script_display"):
            st.caption(
                f"優先切替：{script_reference.get('previous_script_display')} → "
                f"{script_reference.get('current_script_display') or script_reference.get('display')}"
            )
        if script_reference.get("confidence"):
            st.caption(f"confidence: {script_reference.get('confidence')}")
        if script_reference.get("matched") and script_reference.get("url"):
            st.markdown(f"[{script_reference.get('link_text', 'スクリプトを開く')}]({script_reference['url']})")
        elif script_reference.get("message"):
            st.warning(script_reference.get("message"))

        hearing_items = script_guidance.get("hearing_items", [])
        if hearing_items:
            compact_hearing = " / ".join(hearing_items[:5])
            if len(hearing_items) > 5:
                compact_hearing += " / ..."
            st.caption(f"聴取事項：{compact_hearing}")
        if len(hearing_items) > 5 or script_guidance.get("notes"):
            with st.expander("📘 スクリプト補助の詳細", expanded=False):
                st.markdown("**聴取事項：**")
                for hearing_item in hearing_items:
                    st.markdown(f"- {hearing_item}")
                if script_guidance.get("notes"):
                    st.markdown("**注意：**")
                    st.info(script_guidance["notes"])

        render_call_hearing_inputs(st.session_state.form)

        st.markdown("### ✅ 今聞くこと")
        call_required_items = now_action_plan["call_required"]
        hearing_missing_items = [
            item for item in call_required_items
            if item.get("id") in HEARING_INPUT_FIELD_IDS
        ]
        regular_required_items = [
            item for item in call_required_items
            if item.get("id") not in HEARING_INPUT_FIELD_IDS
        ]
        if hearing_missing_items:
            st.markdown("**未入力：** " + " / ".join(item["label"] for item in hearing_missing_items))
        if regular_required_items:
            for idx, item in enumerate(regular_required_items):
                render_now_action_item(item, st.session_state.form, idx)
        if not hearing_missing_items and not regular_required_items:
            st.success("通話中の必須確認はありません")
        if now_action_plan["completed"]:
            with st.expander("✅ 完了済み", expanded=False):
                for item in now_action_plan["completed"]:
                    st.markdown(f"- {format_completed_check_item(item, st.session_state.form)}")

        # UI v3: ゾーンC（判定サマリー大カード4枚）

        summary_display = build_summary_card_display(decision)
        cost_status = summary_display["cost_status"]

        repair_card_value = summary_display["repair"]["value"]  # UI v3
        repair_card_status = summary_display["repair"]["status"]  # UI v3
        repair_card_color = summary_display["repair"]["color"]  # UI v3
        cost_card_value = summary_display["cost"]["value"]  # UI v3
        cost_card_status = summary_display["cost"]["status"]  # UI v3
        cost_card_color = summary_display["cost"]["color"]  # UI v3
        warranty_card_value = summary_display["warranty"]["value"]  # UI v3
        warranty_card_status = summary_display["warranty"]["status"]  # UI v3
        warranty_card_color = summary_display["warranty"]["color"]  # UI v3

        product_display = decision.get("normalized_product") or form.get("product") or "未選択"
        manufacturer_display = (form.get("manufacturer") or "").strip()
        model_display = (form.get("model_number") or "").strip()
        product_line = " / ".join(filter(None, [
            product_display,
            " ".join(filter(None, [manufacturer_display, model_display])),
        ]))
        st.caption(f"製品：{product_line or '未選択'}")

        acceptance_label = {
            "active": "受付判定へ進む",
            "before_start": "受付不可",
            "expired": "受付不可",
            "unknown": "要確認",
        }.get(warranty_status, "要確認")
        vendor_card = build_vendor_candidate_card_info(vendor, vendor_result)
        request_folder = vendor_card["request_folder"]

        # 詳細アラート
        missing_warranty_fields = []
        if not st.session_state.form.get("warranty_start_date"):
            missing_warranty_fields.append("保証開始日")
        if not st.session_state.form.get("warranty_end_date"):
            missing_warranty_fields.append("保証終了日")

        if warranty_status == "expired":
            st.error("保証期間終了 — 受付不可 / 受付不可を案内して終話")
        elif warranty_status == "before_start":
            st.warning("保証開始日前 — メーカー保証または販売店・メーカー窓口へ誘導")
        elif warranty_status == "unknown":
            missing_text = "、".join(missing_warranty_fields) if missing_warranty_fields else "保証期間情報"
            st.warning(f"保証期間未確認 — 不足項目：{missing_text}")

        if warranty_status == "expired":
            st.caption("参考値（受付不可）")

        other_warning = build_other_repair_requested_warning(st.session_state.form)
        if other_warning:
            st.warning(
                "\n".join([
                    other_warning["title"],
                    f"理由：{other_warning['reason']}",
                    f"次アクション：{other_warning['next_action']}",
                ])
            )

        stop_conditions = []
        if other_warning:
            stop_conditions.append("他窓口へ修理依頼済み=あり")
        if "担当エスカ" in (vendor or "") or vendor_result.get("needs_escalation", False):
            stop_conditions.append("拠点未確定")
        if warranty_status == "unknown":
            stop_conditions.append("保証期間未確認")
        st.markdown("### ⛔ 手配前に止める条件")
        if stop_conditions:
            st.markdown("\n".join(f"- {item}" for item in stop_conditions))
        else:
            st.caption("現時点で手配前に止める条件はありません")

        st.markdown("### 🕓 終話後でよい")
        after_call_items = question_categories.get("after_call", [])
        if after_call_items:
            st.markdown("\n".join(
                f"- {item['label'] if isinstance(item, dict) else item}"
                for item in after_call_items
            ))
        else:
            st.caption("終話後に回せる確認事項はありません")

        if "担当エスカ" in (vendor or "") or vendor_result.get("needs_escalation", False):  # UI v3
            esc = build_vendor_escalation_info(vendor, vendor_result)
            drive_line = ""
            if request_folder.get("required"):
                drive_line = (
                    f'<div><strong>依頼書PDF格納先：</strong>'
                    f'<a href="{_ui_v3_escape(request_folder.get("url", ""))}" target="_blank">'
                    f'{_ui_v3_escape(request_folder.get("name", ""))} Google Drive を開く↗</a></div>'
                )
            st.markdown(
                (
                    '<div style="background:#fff3cd;border:1px solid #f1c40f;'
                    'border-radius:8px;padding:14px 16px;color:#3b2f00;line-height:1.7;">'
                    f'<div style="font-weight:700;">{_ui_v3_escape(esc["title"])}</div>'
                    f'<div><strong>理由：</strong>{_ui_v3_escape(esc["reason"])}</div>'
                    f'<div><strong>次アクション：</strong>{_ui_v3_escape(esc["next_action"])}</div>'
                    f'{drive_line}'
                    '</div>'
                ),
                unsafe_allow_html=True,
            )  # UI v3
        else:  # UI v3
            st.success(f"✅ 拠点確定：{vendor}\n\n{format_confirmed_vendor_block(vendor, vendor_card)}")  # UI v3

        # UI改修: ゾーンD（詳細）は折りたたみ
        with st.expander("✅ 確認項目リスト", expanded=True):  # UI v3
            render_inline_vendor_rule_registration(st.session_state.form, decision)

            category_defs = [
                ("🔴 通話中に必ず確認", "call_required", "#c0392b"),
                ("🟡 終話後でよい", "after_call", "#7d6608"),
                ("✅ 完了済み", "completed", "#1e8449"),
            ]
            for title, key, color in category_defs:
                st.markdown(f"**{title}**")
                items = question_categories.get(key, [])
                if items:
                    for item in items:
                        label = item["label"] if isinstance(item, dict) else item
                        st.markdown(f'<span style="color:{color};">- {label}</span>',
                                    unsafe_allow_html=True)
                elif key == "call_required":
                    st.caption("通話中の必須確認はありません")
                else:
                    st.caption("該当なし")

        with st.expander("📊 判定診断パネル", expanded=False):  # UI v3
            _diag_icon = {"ok": "✅", "warning": "⚠️", "error": "❌"}
            _overall   = diagnostics.get("overall_status", "ok")
            _overall_display = DIAGNOSTIC_OVERALL_DISPLAY.get(
                _overall, DIAGNOSTIC_OVERALL_DISPLAY["warning"]
            )
            _overall_header = f"{_overall_display['icon']} {_overall_display['title']}"
            _overall_message = _overall_display["message"]
            if _overall == "ok":
                st.success(f"### {_overall_header}\n{_overall_message}")
            elif _overall == "error":
                st.error(f"### {_overall_header}\n{_overall_message}")
            else:
                st.warning(f"### {_overall_header}\n{_overall_message}")

            for _d in diagnostics.get("items", []):
                _icon = _diag_icon.get(_d["status"], "?")
                _impact = _d.get("impact", "info")
                _impact_label = DIAGNOSTIC_IMPACT_LABELS.get(_impact, _impact)
                _header = f"{_icon} **{_d['area']}** — {_d['title']}"
                if _d["status"] == "ok":
                    st.success(_header)
                elif _d["status"] == "error":
                    st.error(_header)
                    if _d.get("reason"):
                        st.markdown(f"　{_d['reason']}")
                else:
                    st.warning(_header)
                    if _d.get("reason"):
                        st.markdown(f"　{_d['reason']}")
                st.caption(f"ラベル：{_impact_label}")
                if _d.get("missing_fields"):
                    links = diagnostic_field_links(_d["missing_fields"])
                    st.info("不足項目：\n" + "\n".join(f"- {link}" for link in links))
                if _d.get("invalid_fields"):
                    links = diagnostic_field_links(_d["invalid_fields"])
                    st.warning("形式不正：\n" + "\n".join(f"- {link}" for link in links))
                if _d.get("next_action"):
                    st.info(f"**次に確認：{_d['next_action']}**")

        with st.expander("💬 履歴テンプレ・概算案内補助文", expanded=False):  # UI v3
            st.markdown("##### 💬 お客様への概算案内補助文")
            st.caption("※ 正式スクリプト本文ではありません。概算案内の参考としてのみ使用してください。")
            st.text_area("概算案内補助文", guidance_text, height=110, key="guidance_display")
            history_tmpl = build_history_template(
                st.session_state.form, repair_type, script_result, cost_estimate, vendor,
                warranty_result, diagnostics)
            st.markdown("##### 📄 対応履歴テンプレ")
            st.text_area(
                "履歴テンプレ（コピーして使用）",
                history_tmpl,
                height=110,
                key=f"history_display_{stable_hash_text(history_tmpl, 12)}",
            )

        if should_offer_master_registration_candidate(st.session_state.form, decision):
            with st.expander("マスタ登録候補", expanded=False):
                candidate = build_master_registration_candidate(st.session_state.form, decision)
                st.caption("抽出結果から候補を作成します。自動保存はしません。マスタ管理タブで確認して追加してください。")
                st.dataframe(
                    pd.DataFrame([
                        candidate["product_alias"],
                        candidate["repair_type_rule"],
                        candidate["store_rule"],
                    ]),
                    use_container_width=True,
                )
                if st.button("この内容をマスタ管理タブへ引き継ぐ", key="send_master_candidate", type="primary"):
                    st.session_state["master_registration_candidate"] = candidate
                    st.success("マスタ管理タブへ候補を渡しました。内容を確認して追加してください。")

        # ─── 判定デバッグ情報 ───
        with st.expander("🔍 判定デバッグ情報（4層）", expanded=False):  # UI v3
            # Layer 1
            st.markdown("**Layer 1 — 製品名エイリアス**")
            if alias_result["matched"]:
                st.markdown(f"- CSV: `{alias_result['csv_name']}`  priority={alias_result['priority']}")
                st.markdown(f"- keyword: `{alias_result['keyword']}` → **{alias_result['normalized_product']}**")
            else:
                st.info("CSVにヒットなし → normalize_product() フォールバック")
                st.markdown(f"- 結果: `{alias_result['normalized_product']}`")

            st.markdown("**Layer 2 — 修理形態**")
            if repair_result["matched"]:
                st.markdown(f"- CSV: `{repair_result['csv_name']}`  priority={repair_result['priority']}")
                st.markdown(f"- keyword: `{repair_result['keyword']}` → **{repair_result['repair_type']}**")
                if repair_result.get("reason"):
                    st.markdown(f"- reason: {repair_result['reason']}")
                if repair_result["notes"]:
                    st.markdown(f"- notes: {repair_result['notes']}")
            else:
                st.info("CSVにヒットなし → determine_repair_type() フォールバック")
                st.markdown(f"- 結果: `{repair_type}`")

            st.markdown("**Layer 3 — 概算費用**")
            if repair_type == "要確認":
                st.info("要確認のため短絡（概算費用ルールをスキップ）")
            elif cost_result["matched"]:
                st.markdown(f"- CSV: `{cost_result['csv_name']}`  priority={cost_result['priority']}")
                st.markdown(f"- keyword: `{cost_result['keyword']}` → **{cost_result['cost_estimate']}**")
                if cost_result["notes"]:
                    st.markdown(f"- notes: {cost_result['notes']}")
            else:
                st.info("CSVにヒットなし → determine_cost_estimate() フォールバック")
                st.markdown(f"- 結果: `{cost_estimate}`")

            st.markdown("**Layer 4 — 修理拠点候補**")
            if vendor_result["matched"]:
                st.markdown(f"- CSV: `{vendor_result['csv_name']}`  priority={vendor_result['priority']}")
                st.markdown(f"- keyword: `{vendor_result['keyword']}` → **{vendor_result['vendor_name']}**")
                if vendor_result["notes"]:
                    st.markdown(f"- notes: {vendor_result['notes']}")
            else:
                st.info("CSVにヒットなし → determine_vendor_candidate() フォールバック")
                st.markdown(f"- 結果: `{vendor}`")


# ============================================================
# タブ2: 終話後処理
# ============================================================
def render_tab_after_call():
    st.subheader("終話後処理")
    form = st.session_state.form
    decision = run_decision(form)
    repair_type = decision["repair_type"]
    cost_estimate = decision["cost_estimate"]
    script_result = decision["script_result"]
    vendor = decision["vendor"]
    warranty_result = decision["warranty_result"]
    history_tmpl = build_history_template(
        form, repair_type, script_result, cost_estimate, vendor,
        warranty_result, decision.get("diagnostics"),
    )

    # col1/col2 間で共有する変数を先に初期化
    selected_notes = ""
    selected_code = ""
    selected_label_val = ""

    col1, col2 = st.columns(2)

    with col1:
        name_col, save_col, spacer_col = st.columns([2, 1.6, 2.4])
        with name_col:
            form["operator_name"] = st.text_input(
                "オペレーター名",
                form.get("operator_name", ""),
                placeholder="例: 大濱",
                key="operator_name_input",
            )
        with save_col:
            st.markdown("<div style='height: 1.75rem;'></div>", unsafe_allow_html=True)
            save_default_operator_clicked = st.button(
                "既定値に保存",
                key="save_default_operator_name",
            )
        if save_default_operator_clicked:
            saved = save_local_user_settings({
                "default_operator_name": form.get("operator_name", "")
            })
            if saved.get("default_operator_name"):
                st.success("既定値として保存しました。")
            else:
                st.warning("オペレーター名が空のため、既定値も空で保存しました。")
        st.session_state.form = form
        df_tpl = load_template_codes()
        call_line_val = form.get("call_line", "")
        repair_type_val = decision["repair_type"]
        warranty_plan_val = form.get("warranty_plan", "")
        template_selection = select_template_for_form(
            form, repair_type_val, warranty_plan_val, df_tpl)
        vr = decision["vendor_result"]
        vendor_card = build_vendor_candidate_card_info(vendor, vr)
        request_folder = vendor_card["request_folder"]

        st.markdown("##### 案件サマリー")
        summary_template_code = normalize_template_code(form.get("template_code") or template_selection.get("template_code"))
        summary_template_label = form.get("template_label") or template_selection.get("label", "")
        if summary_template_code or summary_template_label:
            st.markdown(f"テンプレート：{summary_template_code or '----'} {summary_template_label or '名称未設定'}")
        else:
            st.markdown("テンプレート：未確定")
        st.markdown(f"修理拠点：{vendor or '未確定'}")
        if vendor_card.get("arrangement_method"):
            st.caption(f"手配方法：{vendor_card['arrangement_method']}")
        display_store_summary = form.get("store_name") or form.get("store_company") or form.get("operating_company")
        if display_store_summary:
            st.caption(f"販売店：{display_store_summary}")

        with st.expander("送付テンプレート・拠点の詳細を開く", expanded=False):
            st.markdown("###### 業者送付コード")
            st.caption("使用する業者送付コード・テンプレートを確認します。")
            if is_double_protect_plan(warranty_plan_val):
                st.warning(f"物損付 / DP案件: {double_protect_plan_label(warranty_plan_val)}。ダブルプロテクト系テンプレートを優先します。")

            if not df_tpl.empty:
                template_candidates = template_selection.get("candidates") or build_template_candidates_for_form(
                    form, repair_type_val, warranty_plan_val, df_tpl, template_selection
                )
                if template_candidates:
                    option_rows = {_template_option_label(candidate): candidate for candidate in template_candidates}
                    auto_option = _template_option_label({
                        "template_code": template_selection.get("template_code", ""),
                        "label": template_selection.get("label", ""),
                    })
                    tpl_labels = [""] + list(option_rows.keys())
                    current_code = normalize_template_code(form.get("template_code"))
                    current_label = form.get("template_label", "") or template_selection.get("label", "")
                    current_option = ""
                    for option_label, candidate in option_rows.items():
                        if current_code and candidate.get("template_code") == current_code:
                            current_option = option_label
                            break
                        if current_label and candidate.get("label") == current_label:
                            current_option = option_label
                            break
                    idx = tpl_labels.index(current_option) if current_option in tpl_labels else 0

                    selected_option_val = st.selectbox(
                        "テンプレートを選択",
                        tpl_labels,
                        index=idx,
                        key="tpl_label_select_after",
                    )
                    if auto_option:
                        summary = build_after_call_template_vendor_summary(
                            form, decision, template_selection, selected_option_val or auto_option
                        )
                        st.markdown("**テンプレート：**")
                        st.markdown(summary["template"])
                        if summary["template_reason"]:
                            st.caption(f"理由：{summary['template_reason']}")
                        if summary["template_source_value"]:
                            st.caption(f"判定根拠：{summary['template_source_label']} {summary['template_source_value']}")
                        if summary["display_store"]:
                            st.caption(f"表示販売店：{summary['display_store']}")
                        st.markdown("**修理拠点：**")
                        st.markdown(summary["vendor"] or "未確定")
                        if summary["vendor_reason"]:
                            st.caption(f"理由：{summary['vendor_reason']}")
                        st.caption(f"状態：{summary['vendor_status']}")
                    with st.expander("候補テンプレートの詳細を見る", expanded=False):
                        st.caption("選択可能テンプレート：")
                        for option_label in option_rows.keys():
                            st.caption(f"- {option_label}")
                    if selected_option_val:
                        row = option_rows.get(selected_option_val, {})
                        selected_code = normalize_template_code(row.get("template_code"))
                        selected_label_val = row.get("label", "")
                        selected_notes = (row.get("notes") or "").strip()
                        if selected_code:
                            st.code(selected_code, language=None)
                        if selected_code == "0009":
                            st.caption("修理依頼書メモは 0009 【出張修理】自然故障テンプレートから生成されます。")
                        if selected_notes:
                            st.info(f"📋 備考: {selected_notes}")
                        if row.get("data_erase_required") == "条件付き":
                            st.warning("⚠️ データ消去同意【データ消去同意済】を依頼書へ記載")
                        if row.get("cost_guidance_allowed") == "不可":
                            st.error("🚫 金額案内不可案件")
                        form["template_code"] = selected_code
                        form["template_label"] = selected_label_val
                        st.session_state.form = form
                    else:
                        form["template_code"] = ""
                        form["template_label"] = ""
                    if not (vr["matched"] and not vr.get("needs_escalation")):
                        st.warning("テンプレートは選択可能です。修理拠点は別途確認してください。")
                else:
                    st.warning("テンプレート候補がありません。回線名・製品・保証種別を確認してください。")
            else:
                st.warning("テンプレート候補がありません。回線名・製品・保証種別を確認してください。")

        with st.expander("修理拠点・手配詳細を開く", expanded=False):
            if vr["matched"] and not vr.get("needs_escalation"):
                st.markdown("##### 🏭 修理拠点")
                st.info(format_confirmed_vendor_block(vendor, vendor_card))
            elif vr["matched"]:
                st.markdown("##### 🏭 修理拠点候補")
                st.info(f"{vendor}\n\n状態：終話後エスカ")
                if vr["needs_escalation"]:
                    esc = vendor_card["escalation"]
                    st.warning(
                        f"{esc['title']}\n\n"
                        f"理由：{esc['reason']}\n\n"
                        f"次アクション：{esc['next_action']}"
                    )
            else:
                st.markdown("##### 🏭 修理拠点候補")
                st.info(vendor)

            if request_folder.get("required"):
                if vendor_card.get("arrangement_method"):
                    st.caption(f"手配方法：{vendor_card['arrangement_method']}")
                st.markdown("###### Drive格納先リンク")
                st.caption("依頼書PDF格納先：")
                st.markdown(f"[{request_folder['name']} Google Drive を開く]({request_folder['url']})")

            with st.expander("手配方法・連絡先の詳細", expanded=False):
                st.markdown(
                    """| 拠点 | 手配方法 | 連絡先 |
|------|----------|--------|
| WRT修理センター | 社内システムで手配 | 内線 ─ |
| ユナイトサービス㈱ | メール依頼 | 担当確認 |
| ソフマップ修理センター | 所定フォーム | 担当確認 |
| 宗建リノベーション | 電話依頼 | 担当確認 |
| CER候補 | 担当エスカ | 担当確認 |"""
                )

    with col2:
        st.markdown("##### 補助情報")
        if script_result.get("url"):
            st.markdown(f"[参照スクリプトを開く]({script_result['url']})")
        elif script_result.get("reason"):
            st.caption(script_result.get("reason", ""))
        else:
            st.caption("必要な補助情報がある場合に表示します。")

    caller_type = form.get("counterparty_type") or form.get("caller_type", "加入者")
    contact_type = decision["vendor_result"].get("contact_type", "")
    if "rakuteru_no_input" in st.session_state:
        form["rakuteru_no"] = st.session_state.get("rakuteru_no_input", "")
    if "teams_action_input" in st.session_state:
        form["teams_action"] = st.session_state.get("teams_action_input", "")
    st.session_state.form = form

    st.markdown("##### 📝 記録文")

    # ── 修理依頼書メモ（備考欄反映）──
    st.markdown("##### 📝 修理依頼書メモ")
    notes_filled = _fill_template_notes(selected_notes, form)
    generated_attention_memo = sanitize_generated_body_text(_build_after_call_memo(
        form, warranty_result, repair_type, vendor, notes_filled, cost_estimate))
    form["attention_memo"] = sanitize_generated_body_text(form.get("attention_memo", ""))
    attention_hash = get_after_call_regeneration_hash(
        form, "attention_memo", vendor=vendor, contact_type=contact_type,
        notes_filled=notes_filled, repair_type=repair_type)
    memo_widget_key = "memo_after_widget"

    if st.session_state.pop("_pending_regenerate_attention_memo", False):
        form["attention_memo"] = sanitize_generated_body_text(generated_attention_memo)
        st.session_state[memo_widget_key] = form["attention_memo"]
        st.session_state["_memo_after_widget_synced"] = form["attention_memo"]
        mark_after_call_section_regenerated(st.session_state, "attention_memo", attention_hash)
        st.session_state.form = form
        st.session_state["_attention_memo_regenerate_message"] = "修理依頼書メモを再生成しました。"

    pending_snippet_id = str(st.session_state.pop("_pending_append_memo_snippet_id", "") or "").strip()
    if pending_snippet_id:
        added_snippets = append_attention_memo_snippets(form, [pending_snippet_id])
        st.session_state[memo_widget_key] = form["attention_memo"]
        st.session_state["_memo_after_widget_synced"] = form["attention_memo"]
        st.session_state.form = form
        st.session_state["_memo_snippet_append_message"] = (
            "修理依頼書メモへ追記しました。"
            if added_snippets else "この文言はすでに修理依頼書メモに含まれています。"
        )

    memo_value = sanitize_generated_body_text(form.get("attention_memo") or generated_attention_memo)
    if memo_widget_key in st.session_state:
        widget_value = sanitize_generated_body_text(st.session_state.get(memo_widget_key, ""))
        if widget_value != st.session_state.get("_memo_after_widget_synced"):
            memo_value = widget_value
            form["attention_memo"] = memo_value
        else:
            st.session_state[memo_widget_key] = memo_value
    else:
        st.session_state[memo_widget_key] = memo_value
    st.session_state["_memo_after_widget_synced"] = memo_value

    memo_col, memo_action_col = st.columns([2, 3], gap="large")
    with memo_col:
        memo_display = st.text_area(
            "修理依頼書メモ",
            memo_value,
            height=260,
            key=memo_widget_key,
        )
        form["attention_memo"] = sanitize_generated_body_text(memo_display)
        st.session_state["_memo_after_widget_synced"] = form["attention_memo"]

    with memo_action_col:
        st.markdown("###### 修理依頼書メモ 操作")
        st.markdown("###### 修理依頼文テンプレ")
        memo_template_code = normalize_template_code(form.get("template_code") or selected_code or template_selection.get("template_code"))
        memo_template_label = form.get("template_label") or selected_label_val or template_selection.get("label", "")
        memo_template_reason = build_template_selection_reason(template_selection)
        if memo_template_code or memo_template_label:
            st.markdown(f"**{memo_template_code or '----'} {memo_template_label or 'テンプレート名未設定'}**")
            if memo_template_reason:
                st.caption(f"理由：{memo_template_reason}")
            if selected_notes:
                st.caption(f"備考：{selected_notes}")
        else:
            st.info("テンプレート未確定")
            st.caption("テンプレート候補がありません。回線名・製品・保証種別を確認してください。")
        if not (vr["matched"] and not vr.get("needs_escalation")):
            st.warning("テンプレートは選択可能です。修理拠点は別途確認してください。")
        regen_message = str(st.session_state.pop("_attention_memo_regenerate_message", "") or "").strip()
        if regen_message:
            st.success(regen_message)
        if after_call_section_needs_regeneration(st.session_state, "attention_memo", attention_hash):
            st.warning("基本項目が変更されています。修理依頼書メモを再生成してください。")
        if st.button("再生成", key="regenerate_attention_memo"):
            st.session_state["_pending_regenerate_attention_memo"] = True
            st.rerun()
        st.caption("再生成すると、現在の修理依頼書メモは上書きされます。")
        render_copy_button("📋 コピー", sanitize_generated_body_text(form["attention_memo"]), "copy_attention_memo")

        snippets_df = load_memo_snippets()
        if not snippets_df.empty:
            st.markdown("###### 追記候補")
            st.caption("必要な定型文を選択して、現在の修理依頼書メモへ追記できます。")
            snippet_message = str(st.session_state.pop("_memo_snippet_append_message", "") or "").strip()
            if snippet_message:
                if snippet_message == "修理依頼書メモへ追記しました。":
                    st.success(snippet_message)
                else:
                    st.info(snippet_message)
            snippet_options = [""] + [
                str(row.get("snippet_id") or "").strip()
                for _, row in snippets_df.iterrows()
                if str(row.get("snippet_id") or "").strip()
            ]
            selected_snippet_id = st.selectbox(
                "追記する定型文を選択",
                snippet_options,
                format_func=lambda snippet_id: (
                    "選択してください"
                    if not snippet_id
                    else memo_snippet_option_label(memo_snippet_row_by_id(snippets_df, snippet_id))
                ),
                key="memo_snippet_selectbox",
            )
            selected_row = memo_snippet_row_by_id(snippets_df, selected_snippet_id)
            if selected_row:
                condition_text = str(selected_row.get("condition_text") or "").strip()
                body = sanitize_generated_body_text(selected_row.get("body") or "").strip()
                if condition_text:
                    st.caption(f"追記条件：{condition_text}")
                if "\n" in body:
                    st.caption("追記内容：")
                    st.code(body, language=None)
            if st.button("この文言を追記", key="memo_snippet_append_current_button"):
                if selected_snippet_id:
                    st.session_state["_pending_append_memo_snippet_id"] = selected_snippet_id
                    st.rerun()
                else:
                    st.warning("追記する定型文を選択してください。")

    # ── ラクテル用テキスト ──
    st.markdown("##### 📝 ラクテル用テキスト")
    form = sync_after_call_rakutel_action_inputs(form, st.session_state)
    rakutel_text_col, rakutel_action_col = st.columns([2, 3], gap="large")
    with rakutel_action_col:
        st.markdown("###### ラクテル用テキスト 操作")
        rakutel_regen_message_slot = st.empty()
        if st.button("再生成", key="regenerate_rakutel_text"):
            st.session_state["_pending_regenerate_rakutel_text"] = True
            st.rerun()
        rakutel_copy_slot = st.empty()
        call_direction_options = ["受電", "架電"]
        call_direction = st.selectbox(
            "通話方向",
            call_direction_options,
            index=call_direction_options.index(form.get("call_direction", "受電"))
            if form.get("call_direction", "受電") in call_direction_options else 0,
            key="call_direction_select",
        )
        counterparty_options = ["加入者", "販売店", "メーカー", "担当エスカ", "修理拠点", "その他"]
        default_counterparty = form.get("counterparty_type") or form.get("caller_type", "加入者")
        counterparty_type = st.selectbox(
            "相手区分",
            counterparty_options,
            index=counterparty_options.index(default_counterparty)
            if default_counterparty in counterparty_options else 0,
            key="counterparty_type_select",
        )
        counterparty_detail = st.text_input(
            "相手名・担当者名（任意）",
            value=form.get("counterparty_detail", ""),
            key="counterparty_detail_input",
            placeholder="例：あかりと空調の専門店 山田様",
        )
        contact_phone = st.text_input(
            "日程調整時の連絡先",
            value=form.get("contact_phone", ""),
            key="contact_phone_input",
            placeholder="例：072-950-0880　5/26 12時以降",
        )
    form["call_direction"] = call_direction
    form["counterparty_type"] = counterparty_type
    form["caller_type"] = counterparty_type
    form["counterparty_detail"] = counterparty_detail
    form["contact_phone"] = contact_phone
    form = sync_after_call_rakutel_action_inputs(form, st.session_state)
    st.session_state.form = form
    caller_type = form.get("counterparty_type") or counterparty_type
    generated_rakutel_text = _build_rakutel_text(form, caller_type, notes_filled)
    rakutel_hash = get_after_call_regeneration_hash(
        form, "rakutel_text", vendor=vendor, contact_type=contact_type,
        notes_filled=notes_filled, repair_type=repair_type)
    missing_rakutel_fields = [
        label for field, label in [
            ("call_line", "回線名"),
            ("product", "製品"),
            ("manufacturer", "メーカー"),
        ]
        if not (form.get(field) or "").strip()
    ]
    if st.session_state.pop("_pending_regenerate_rakutel_text", False):
        form["rakutel_text"] = generated_rakutel_text
        st.session_state["rakutel_text_display"] = form["rakutel_text"]
        mark_after_call_section_regenerated(st.session_state, "rakutel_text", rakutel_hash)
        st.session_state.form = form
        with rakutel_regen_message_slot:
            st.success("ラクテル用テキストを再生成しました。")
    with rakutel_action_col:
        if missing_rakutel_fields:
            st.warning("未入力の基本項目があります: " + " / ".join(missing_rakutel_fields))
        if after_call_section_needs_regeneration(st.session_state, "rakutel_text", rakutel_hash):
            st.warning("基本項目が変更されています。ラクテル用テキストを再生成してください。")
    with rakutel_text_col:
        rakutel_text_display = st.text_area(
            "ラクテル用テキスト",
            form.get("rakutel_text") or generated_rakutel_text,
            height=180,
            key="rakutel_text_display",
        )
    form["rakutel_text"] = rakutel_text_display
    with rakutel_copy_slot.container():
        render_copy_button("📋 コピー", form["rakutel_text"], "copy_rakutel_text")

    # ── Teams報告文 ──
    st.markdown("##### 💬 Teams報告文")
    teams_text_col, teams_action_col = st.columns([2, 3], gap="large")
    with teams_action_col:
        st.markdown("###### Teams報告文 操作")
        teams_regen_message_slot = st.empty()
        if st.button("再生成", key="regenerate_teams_chat_message"):
            st.session_state["_pending_regenerate_teams_chat_message"] = True
            st.rerun()
        teams_copy_slot = st.empty()
        rakuteru_val = st.text_input(
            "楽テルNO",
            value=form.get("rakuteru_no", ""),
            key="rakuteru_no_input",
            placeholder="楽テル登録後に入力",
        )
        form["rakuteru_no"] = rakuteru_val
        auto_teams_action = resolve_teams_request_action(form, vendor, contact_type)
        auto_teams_action_display = f"{vendor}へ{auto_teams_action}" if vendor or auto_teams_action else ""
        form["teams_action"] = st.text_input(
            "Teams報告文に入れる対応内容",
            value=form.get("teams_action", ""),
            placeholder=auto_teams_action,
            key="teams_action_input",
            help="自動判定と異なる場合のみ変更",
        )
        if auto_teams_action_display:
            st.caption(f"自動判定：{auto_teams_action_display}")
        st.caption("自動判定と異なる場合のみ変更")
    st.session_state.form = form
    teams_generation_form = form_for_current_teams_generation(form, vendor, contact_type)
    generated_teams_message = _build_teams_chat_message(teams_generation_form, vendor, contact_type)
    teams_hash = get_after_call_regeneration_hash(
        teams_generation_form, "teams_chat_message", vendor=vendor, contact_type=contact_type,
        notes_filled=notes_filled, repair_type=repair_type)
    if st.session_state.pop("_pending_regenerate_teams_chat_message", False):
        form["teams_chat_message"] = generated_teams_message
        st.session_state["teams_chat_message_display"] = form["teams_chat_message"]
        mark_after_call_section_regenerated(st.session_state, "teams_chat_message", teams_hash)
        st.session_state.form = form
        with teams_regen_message_slot:
            st.success("Teams報告文を再生成しました。")
    with teams_action_col:
        if after_call_section_needs_regeneration(st.session_state, "teams_chat_message", teams_hash):
            st.warning("基本項目が変更されています。Teams報告文を再生成してください。")
    with teams_text_col:
        teams_chat_message = st.text_area(
            "Teams報告文",
            form.get("teams_chat_message") or generated_teams_message,
            height=160,
            key="teams_chat_message_display",
        )
    form["teams_chat_message"] = teams_chat_message
    teams_preview_lines = build_teams_send_preview_lines(teams_chat_message, form.get("rakuteru_no", ""))
    with teams_copy_slot.container():
        render_copy_button("📋 コピー", teams_chat_message, "copy_teams_chat_message")
    st.session_state.form = form

    with teams_action_col:
        if teams_preview_lines:
            st.markdown("送信内容プレビュー：")
            st.info("\n".join(teams_preview_lines))
        st.markdown("###### Teams送信")
        st.caption("送信前チェックと送信状態")
        request_folder = get_request_pdf_folder_info(vendor)
        teams_config = load_teams_config()
        teams_send_mode = (teams_config.get("send_mode") or "").strip()
        teams_enabled = bool(
            teams_config.get("enabled")
            and teams_config.get("chat_id")
            and teams_send_mode in SUPPORTED_TEAMS_SEND_MODES
        )
        chat_name = teams_config.get("chat_name") or DEFAULT_TEAMS_CONFIG["chat_name"]
        config_reasons = teams_config_unavailable_reasons(teams_config)

        pdf_storage_confirmed = True
        if request_folder.get("required"):
            pdf_storage_confirmed = bool(st.session_state.get("request_pdf_storage_confirmed", False))
        confirmed = bool(st.session_state.get("teams_send_confirmed", False))
        action_confirmed = bool(st.session_state.get("teams_action_confirmed", False))
        effective_teams_action = resolve_teams_request_action(form, vendor, contact_type)
        _clear_stale_teams_send_transient_state(st.session_state, form)
        already_sent = _teams_case_already_sent(st.session_state, form)
        in_progress = _teams_send_in_progress(st.session_state, form)
        send_failed = _teams_last_send_failed(st.session_state, form)
        incomplete_reasons = build_teams_send_incomplete_reasons(
            form,
            teams_config,
            confirmed,
            action_confirmed,
            pdf_storage_confirmed,
            vendor,
            contact_type,
            already_sent,
        )
        send_status = teams_send_status_label(incomplete_reasons, already_sent, send_failed, in_progress)
        st.markdown(f"**送信先：** {chat_name}")
        st.markdown(f"**Teams送信：{'有効' if teams_enabled else '無効'}**")
        if config_reasons:
            st.markdown("**理由：**")
            st.markdown("\n".join(f"- {reason}" for reason in config_reasons))
        if send_status == "送信可能":
            st.success(f"状態：{send_status}")
        elif send_status == "送信処理中":
            st.info(f"状態：{send_status}")
        elif send_status == "送信済み":
            st.info(f"状態：{send_status}")
        elif send_status == "送信失敗":
            st.error(f"状態：{send_status}")
        else:
            st.warning(f"状態：{send_status}")
        if in_progress:
            st.markdown("**未完了：なし**")
        elif already_sent:
            st.markdown("**未完了：なし**")
        elif incomplete_reasons:
            st.markdown("**未完了：**")
            st.markdown("\n".join(f"- {reason}" for reason in incomplete_reasons))
        else:
            st.markdown("**未完了：なし**")
        if not teams_enabled:
            st.caption("対応：config/teams_config.json をローカルに作成し、enabled=true と送信先chat_idを設定してください。")
        if in_progress:
            started_at = st.session_state.get("teams_send_started_at") or "日時不明"
            st.info(
                f"Teamsへ送信しています。完了まで画面を閉じないでください。\n"
                f"送信先：{chat_name}\n"
                f"開始時刻：{started_at}"
            )
        elif already_sent:
            sent_at = st.session_state.get("teams_sent_at") or "日時不明"
            st.success(f"Teamsへ送信しました。\n送信先：{chat_name}\n送信日時：{sent_at}")
            with st.expander("送信済み本文（確認用）", expanded=False):
                st.code(st.session_state.get("teams_sent_message", "") or "（なし）", language=None)
        elif send_failed:
            error_message = st.session_state.get("teams_send_error_message") or "エラー内容を取得できませんでした"
            st.error(f"Teams送信に失敗しました：{error_message}")
        st.markdown("**送信前チェック：**")
        if request_folder.get("required"):
            pdf_storage_confirmed = st.checkbox(
                "依頼書PDFを指定フォルダへ格納しました",
                key="request_pdf_storage_confirmed",
            )
        confirmed = st.checkbox(
            "送信内容と送信先を確認しました",
            key="teams_send_confirmed",
        )
        action_confirmed = st.checkbox(
            "Teams報告アクションを確定しました",
            key="teams_action_confirmed",
        )

        def request_teams_send(allow_resend: bool = False):
            validation_errors = validate_teams_send_request(
                form,
                teams_enabled,
                confirmed,
                action_confirmed,
                pdf_storage_confirmed,
                vendor,
                contact_type,
            )
            if validation_errors:
                st.warning("未完了項目があります。Teams自動送信パネルの未完了一覧を確認してください。")
                return
            if already_sent and not allow_resend:
                st.warning("すでに送信済みです。再送する場合のみ実行してください。")
                return
            if in_progress:
                st.warning("Teams送信処理中です。完了まで画面を閉じないでください。")
                return

            _mark_teams_send_requested(st.session_state, form, allow_resend=allow_resend)
            st.rerun()

        def execute_requested_teams_send():
            teams_send_body = _get_teams_send_body(form)
            with st.spinner("Teamsへ送信中です... Microsoft Graph / PowerShell の応答待ちです。"):
                result = send_teams_message_via_powershell(teams_send_body)
            append_teams_send_log(
                result,
                teams_chat_message,
                chat_name,
                form=form,
                vendor=vendor,
                teams_action=effective_teams_action,
            )
            if result.get("ok"):
                _mark_teams_message_sent(st.session_state, form, result=result)
                st.rerun()
            else:
                _mark_teams_message_send_failed(st.session_state, form, result)
                st.rerun()
            with st.expander("PowerShell実行結果", expanded=not result.get("ok")):
                st.text("stdout")
                st.code(result.get("stdout", "") or "（なし）", language=None)
                st.text("stderr")
                st.code(result.get("stderr", "") or "（なし）", language=None)

        if in_progress:
            st.button("送信処理中...", disabled=True, use_container_width=True)
        elif already_sent:
            st.button("送信済み", disabled=True, use_container_width=True)
            if st.button("同じ内容を再送する", disabled=not teams_enabled, use_container_width=True):
                request_teams_send(allow_resend=True)
        elif incomplete_reasons:
            st.button("未完了項目があります", disabled=True, use_container_width=True)
        else:
            if st.button("Teamsチャットへ送信", disabled=not teams_enabled, type="primary", use_container_width=True):
                request_teams_send(allow_resend=False)

        if _teams_send_requested(st.session_state, form):
            execute_requested_teams_send()

        recent_logs = st.session_state.get("teams_send_log", [])[:3]
        if recent_logs:
            with st.expander("Teams送信ログ（直近3件）", expanded=False):
                for log in recent_logs:
                    status = "成功" if log.get("ok") else "失敗"
                    st.markdown(
                        f"- {log.get('sent_at', '─')} / {status} / "
                        f"{log.get('chat_name', '─')} / {log.get('message_preview', '')}"
                    )
                    if log.get("error_message"):
                        st.caption(log["error_message"])

    render_handover_requirement_panel(decision.get("handover_requirement"))
    render_warranty_report_send_panel(form, decision)

    st.divider()
    with st.expander("対応履歴テンプレ（旧形式・必要時のみ）", expanded=False):
        st.caption("通常はラクテル用テキストまたはTeams報告文を使用してください。旧形式の履歴貼付が必要な場合のみ使用します。")
        st.text_area(
            "履歴テンプレ",
            history_tmpl,
            height=220,
            key=f"history_after_{stable_hash_text(history_tmpl, 12)}",
        )
        render_copy_button("📋 コピー", history_tmpl, "copy_history_after_template")


# ============================================================
# タブ3: マスタ管理
# ============================================================
def _candidate_field(section: str, field: str, default: str = "") -> str:
    candidate = st.session_state.get("master_registration_candidate") or {}
    return str((candidate.get(section) or {}).get(field, default) or "")


def _preview_master_row(row: dict, columns: list[str]) -> None:
    st.caption("保存前プレビュー")
    st.dataframe(pd.DataFrame([{col: row.get(col, "") for col in columns}]), use_container_width=True)


def _show_master_append_result(result: dict) -> None:
    if result.get("ok"):
        st.success(f"CSVへ1行追加しました。バックアップ: {os.path.basename(result.get('backup_path', ''))}")
    elif result.get("reason") == "duplicate":
        st.warning("同じキーの行が既にあるため追加しませんでした。既存行を確認してください。")
    elif result.get("reason") == "missing_required":
        st.error("必須項目が未入力です: " + ", ".join(result.get("missing", [])))
    else:
        st.error("CSVへの追加に失敗しました。入力内容を確認してください。")


def _render_product_alias_append_ui() -> None:
    st.markdown("##### 製品エイリアス追加")
    row = {
        "priority": "10",
        "enabled": "1",
        "keyword": st.text_input("キーワード keyword", value=_candidate_field("product_alias", "keyword"), key="master_alias_keyword"),
        "normalized_product": st.text_input("正規化後の製品名 normalized_product", value=_candidate_field("product_alias", "normalized_product"), key="master_alias_normalized_product"),
        "product_group": st.text_input("製品グループ product_group", value=_candidate_field("product_alias", "product_group"), key="master_alias_product_group"),
        "notes": st.text_input("備考 notes", value=_candidate_field("product_alias", "notes"), key="master_alias_notes"),
    }
    _preview_master_row(row, _ALIAS_COLS)
    duplicate = bool(row["keyword"]) and master_csv_has_duplicate("master_product_alias.csv", row, ["keyword"])
    if duplicate:
        st.warning("同一 keyword が既にあります。原則追加しません。")
    disabled = not row["keyword"].strip() or not row["normalized_product"].strip() or duplicate
    if st.button("製品エイリアスを追加", key="master_alias_add", type="primary", disabled=disabled):
        _show_master_append_result(append_master_product_alias(row))
        st.rerun()


def _render_repair_type_append_ui() -> None:
    st.markdown("##### 修理形態ルール追加")
    repair_default = _candidate_field("repair_type_rule", "repair_type")
    repair_options = ["", "出張修理", "持込修理", "要確認"]
    repair_index = repair_options.index(repair_default) if repair_default in repair_options else 0
    needs_default = _candidate_field("repair_type_rule", "needs_confirmation", "1")
    manufacturer_required_default = _candidate_field("repair_type_rule", "manufacturer_required", "0")
    model_required_default = _candidate_field("repair_type_rule", "model_required", "0")
    manual_required_default = _candidate_field("repair_type_rule", "manual_required", "0")
    row = {
        "priority": "10",
        "enabled": "1",
        "product_keyword": st.text_input("製品キーワード product_keyword", value=_candidate_field("repair_type_rule", "product_keyword"), key="master_repair_product_keyword"),
        "manufacturer_keyword": st.text_input("メーカーキーワード manufacturer_keyword", value=_candidate_field("repair_type_rule", "manufacturer_keyword"), key="master_repair_manufacturer_keyword"),
        "model_keyword": st.text_input("型番キーワード model_keyword", value=_candidate_field("repair_type_rule", "model_keyword"), key="master_repair_model_keyword"),
        "condition_keyword": st.text_input("条件キーワード condition_keyword", value=_candidate_field("repair_type_rule", "condition_keyword"), key="master_repair_condition_keyword"),
        "repair_type": st.selectbox("修理形態 repair_type", repair_options, index=repair_index, key="master_repair_type"),
        "manufacturer_required": st.radio("メーカー必須 manufacturer_required", ["0", "1"], index=0 if manufacturer_required_default == "0" else 1, horizontal=True, key="master_repair_manufacturer_required"),
        "model_required": st.radio("型番必須 model_required", ["0", "1"], index=0 if model_required_default == "0" else 1, horizontal=True, key="master_repair_model_required"),
        "manual_required": st.radio("取説確認 manual_required", ["0", "1"], index=0 if manual_required_default == "0" else 1, horizontal=True, key="master_repair_manual_required"),
        "needs_confirmation": st.radio("確認要否 needs_confirmation", ["0", "1"], index=0 if needs_default == "0" else 1, horizontal=True, key="master_repair_needs_confirmation"),
        "notes": st.text_input("備考 notes", value=_candidate_field("repair_type_rule", "notes"), key="master_repair_notes"),
    }
    _preview_master_row(row, _REPAIR_TYPE_COLS)
    duplicate_cols = ["product_keyword", "manufacturer_keyword", "model_keyword", "condition_keyword"]
    duplicate = bool(row["product_keyword"]) and master_csv_has_duplicate("master_repair_type_rules.csv", row, duplicate_cols)
    if duplicate:
        st.warning("同一 product_keyword + manufacturer_keyword + model_keyword + condition_keyword が既にあります。")
    disabled = not row["product_keyword"].strip() or not row["repair_type"].strip() or duplicate
    if st.button("修理形態ルールを追加", key="master_repair_add", type="primary", disabled=disabled):
        _show_master_append_result(append_master_repair_type_rule(row))
        st.rerun()


def _render_store_rule_append_ui() -> None:
    st.markdown("##### 販売店テンプレートルール追加")
    row = {
        "priority": "10",
        "enabled": "1",
        "store_keyword": st.text_input("販売店キーワード store_keyword", value=_candidate_field("store_rule", "store_keyword"), key="master_store_keyword"),
        "normalized_store": st.text_input("正規化販売店名 normalized_store", value=_candidate_field("store_rule", "normalized_store"), key="master_store_normalized_store"),
        "template_code": st.text_input("テンプレートコード template_code", value=_candidate_field("store_rule", "template_code"), key="master_store_template_code"),
        "template_label": st.text_input("テンプレートラベル template_label", value=_candidate_field("store_rule", "template_label"), key="master_store_template_label"),
        "template_group": st.text_input("テンプレートグループ template_group", value=_candidate_field("store_rule", "template_group"), key="master_store_template_group"),
        "notes": st.text_input("備考 notes", value=_candidate_field("store_rule", "notes"), key="master_store_notes"),
    }
    _preview_master_row(row, _STORE_RULE_COLS)
    duplicate = bool(row["store_keyword"]) and master_csv_has_duplicate("master_store_rules.csv", row, ["store_keyword"])
    if duplicate:
        st.warning("同一 store_keyword が既にあります。原則追加しません。")
    disabled = not row["store_keyword"].strip() or duplicate
    if st.button("販売店テンプレートルールを追加", key="master_store_add", type="primary", disabled=disabled):
        _show_master_append_result(append_master_store_rule(row))
        st.rerun()


def _render_vendor_rule_append_ui() -> None:
    vendor_default = _candidate_field("vendor_rule", "vendor_name", "担当エスカ（要確認）")
    if vendor_default not in VENDOR_INLINE_OPTIONS:
        vendor_default = "担当エスカ（要確認）"
    row = {
        "priority": "10",
        "enabled": "1",
        "call_line": st.text_input("回線名 call_line", value=_candidate_field("vendor_rule", "call_line"), key="master_vendor_call_line"),
        "prefecture": st.text_input("都道府県 prefecture", value=_candidate_field("vendor_rule", "prefecture"), key="master_vendor_prefecture"),
        "area_group": st.text_input("エリアグループ area_group", value=_candidate_field("vendor_rule", "area_group"), key="master_vendor_area_group"),
        "manufacturer_keyword": st.text_input("メーカー manufacturer_keyword", value=_candidate_field("vendor_rule", "manufacturer_keyword"), key="master_vendor_manufacturer"),
        "product_keyword": st.text_input("製品 product_keyword", value=_candidate_field("vendor_rule", "product_keyword"), key="master_vendor_product"),
        "store_keyword": st.text_input("販売店 store_keyword", value=_candidate_field("vendor_rule", "store_keyword"), key="master_vendor_store"),
        "repair_type": st.text_input("修理形態 repair_type", value=_candidate_field("vendor_rule", "repair_type"), key="master_vendor_repair_type"),
        "is_over_10years": st.text_input("10年以上 is_over_10years", value=_candidate_field("vendor_rule", "is_over_10years"), key="master_vendor_over10"),
        "vendor_name": st.selectbox("修理拠点 vendor_name", VENDOR_INLINE_OPTIONS, index=VENDOR_INLINE_OPTIONS.index(vendor_default), key="master_vendor_name"),
        "reason": st.text_input("理由 reason", value=_candidate_field("vendor_rule", "reason"), key="master_vendor_reason"),
        "needs_escalation": st.selectbox("要確認 needs_escalation", ["0", "1"], index=1 if _candidate_field("vendor_rule", "needs_escalation", "1") == "1" else 0, key="master_vendor_needs"),
        "notes": st.text_input("備考 notes", value=_candidate_field("vendor_rule", "notes"), key="master_vendor_notes"),
        "contact_type": st.text_input("連絡種別 contact_type", value=_candidate_field("vendor_rule", "contact_type"), key="master_vendor_contact"),
    }
    _preview_master_row(row, _VENDOR_COLS)
    confirmed = st.checkbox("保存前確認", key="master_vendor_confirm")
    disabled = not confirmed or not row["repair_type"].strip() or not row["vendor_name"].strip()
    if st.button("修理拠点ルールを追加", key="master_vendor_add", type="primary", disabled=disabled):
        _show_master_append_result(append_master_vendor_rule(row))
        st.rerun()


def _render_manufacturer_group_append_ui() -> None:
    candidate = st.session_state.get("master_registration_candidate") or {}
    mfr_candidate = candidate.get("manufacturer_group") or {}
    group_default = mfr_candidate.get("group_name") or "国内家電メーカー"
    if group_default not in MANUFACTURER_INLINE_GROUP_OPTIONS:
        group_default = "その他"
    row = {
        "group_name": st.selectbox("メーカーグループ group_name", MANUFACTURER_INLINE_GROUP_OPTIONS, index=MANUFACTURER_INLINE_GROUP_OPTIONS.index(group_default), key="master_mfr_group_name"),
        "manufacturers": st.text_input("メーカー manufacturers", value=str(mfr_candidate.get("manufacturers") or mfr_candidate.get("normalized_manufacturer") or ""), key="master_mfr_manufacturers"),
        "notes": st.text_input("備考 notes", value=str(mfr_candidate.get("notes") or "インライン登録候補"), key="master_mfr_notes"),
    }
    _preview_master_row(row, _MFR_GROUP_COLS)
    disabled = not row["group_name"].strip() or not row["manufacturers"].strip() or row["manufacturers"].strip() in (MANUFACTURER_OTHER, MANUFACTURER_UNKNOWN)
    if st.button("メーカーグループへ追加", key="master_mfr_add", type="primary", disabled=disabled):
        _show_master_append_result(append_master_manufacturer_group(row))
        st.rerun()


def _render_call_line_master_edit_ui() -> None:
    st.markdown("##### 回線名マスタ編集")
    df = load_call_lines()
    labels = []
    if not df.empty:
        labels = [
            f"{row.get('call_line_code') or row.get('call_line') or row.get('display_name')} / {_call_line_display_name(row)}"
            for _, row in df.iterrows()
        ]
    mode = st.radio("編集モード", ["既存編集", "新規追加"], horizontal=True, key="call_line_master_mode")
    selected_row = {}
    if mode == "既存編集" and labels:
        selected = st.selectbox("既存回線名", labels, key="call_line_master_select")
        selected_row = df.iloc[labels.index(selected)].to_dict()

    enabled_default = str(selected_row.get("enabled", "1") or "1")
    row = {
        "priority": st.text_input("priority", value=str(selected_row.get("priority", "10") or "10"), key="call_line_master_priority"),
        "enabled": st.selectbox("enabled", ["1", "0"], index=0 if enabled_default != "0" else 1, key="call_line_master_enabled"),
        "call_line": st.text_input("legacy call_line", value=str(selected_row.get("call_line", "") or ""), key="call_line_master_legacy"),
        "line_group": st.text_input("line_group", value=str(selected_row.get("line_group", "") or ""), key="call_line_master_line_group"),
        "notes": st.text_input("notes", value=str(selected_row.get("notes", "") or ""), key="call_line_master_notes"),
        "call_line_code": st.text_input("call_line_code", value=str(selected_row.get("call_line_code", "") or ""), key="call_line_master_code"),
        "display_name": st.text_input("display_name", value=str(selected_row.get("display_name", "") or _call_line_display_name(selected_row)), key="call_line_master_display"),
        "rakutel_line_name": st.text_input("rakutel_line_name", value=str(selected_row.get("rakutel_line_name", "") or _call_line_rakutel_name(selected_row)), key="call_line_master_rakutel"),
        "aliases": st.text_input("aliases（; 区切り）", value=str(selected_row.get("aliases", "") or ""), key="call_line_master_aliases"),
    }
    _preview_master_row(row, _CALL_LINE_COLS)
    display = row["display_name"].strip()
    code = (row["call_line_code"] or display).strip()
    duplicate_display = False
    if display and not df.empty:
        for _, existing in df.iterrows():
            same_code = _normalize_duplicate_value(existing.get("call_line_code") or existing.get("call_line")) == _normalize_duplicate_value(code)
            same_display = _normalize_duplicate_value(_call_line_display_name(existing)) == _normalize_duplicate_value(display)
            if same_display and not same_code:
                duplicate_display = True
                break
    if duplicate_display:
        st.warning("同じ display_name の回線名が既にあります。")
    disabled = not display or duplicate_display
    if st.button("回線名マスタを保存", key="call_line_master_save", type="primary", disabled=disabled):
        result = upsert_master_call_line(row)
        _show_master_append_result(result)
        if result.get("ok"):
            bump_case_basic_revision(st.session_state)
        st.rerun()


def _render_vendor_send_template_edit_ui() -> None:
    st.markdown("##### テンプレート編集")
    df = load_vendor_send_templates()
    labels = []
    if not df.empty:
        labels = [
            f"{row.get('template_code')} / {row.get('template_label')}"
            for _, row in df.iterrows()
        ]
    mode = st.radio("テンプレート編集モード", ["既存編集", "新規追加"], horizontal=True, key="vendor_send_template_mode")
    selected_row = {}
    if mode == "既存編集" and labels:
        selected = st.selectbox("template_code で検索", labels, key="vendor_send_template_select")
        selected_row = df.iloc[labels.index(selected)].to_dict()

    enabled_default = str(selected_row.get("enabled", "1") or "1")
    row = {
        "priority": st.text_input("priority", value=str(selected_row.get("priority", "10") or "10"), key="vendor_send_tpl_priority"),
        "enabled": st.selectbox("enabled", ["1", "0"], index=0 if enabled_default != "0" else 1, key="vendor_send_tpl_enabled"),
        "template_code": st.text_input("template_code", value=str(selected_row.get("template_code", "") or ""), key="vendor_send_tpl_code"),
        "template_label": st.text_input("template_label", value=str(selected_row.get("template_label", "") or ""), key="vendor_send_tpl_label"),
        "repair_type": st.text_input("repair_type", value=str(selected_row.get("repair_type", "") or ""), key="vendor_send_tpl_repair_type"),
        "warranty_type": st.text_input("warranty_type", value=str(selected_row.get("warranty_type", "") or ""), key="vendor_send_tpl_warranty_type"),
        "attention_memo_template": st.text_area("attention_memo_template", value=str(selected_row.get("attention_memo_template", "") or ""), height=160, key="vendor_send_tpl_attention"),
        "rakutel_template": st.text_area("rakutel_template", value=str(selected_row.get("rakutel_template", "") or ""), height=120, key="vendor_send_tpl_rakutel"),
        "teams_template": st.text_area("teams_template", value=str(selected_row.get("teams_template", "") or ""), height=120, key="vendor_send_tpl_teams"),
        "notes": st.text_input("notes", value=str(selected_row.get("notes", "") or ""), key="vendor_send_tpl_notes"),
    }
    _preview_master_row(row, _VENDOR_SEND_TEMPLATE_COLS)
    preview_context = build_vendor_send_template_context(
        st.session_state.get("form") or {},
        {},
        row.get("repair_type", ""),
        "",
        "5,000円～7,000円前後",
    )
    st.caption("プレースホルダー差し込みプレビュー")
    st.text_area(
        "attention_memo_template preview",
        render_vendor_send_template_text(row["attention_memo_template"], preview_context),
        height=140,
        key="vendor_send_tpl_preview",
    )
    disabled = not row["template_code"].strip()
    if st.button("テンプレートを保存", key="vendor_send_tpl_save", type="primary", disabled=disabled):
        _show_master_append_result(upsert_vendor_send_template(row))
        st.rerun()


def _render_master_candidate_box() -> None:
    candidate = st.session_state.get("master_registration_candidate") or {}
    if not candidate:
        st.info("通話中判定で未登録・要確認の候補を作成すると、ここに入力候補が表示されます。")
        return
    st.success("抽出結果から作成したマスタ登録候補を入力欄に反映しています。内容を確認してから追加してください。")
    safe_fields = candidate.get("source_fields") or {}
    if safe_fields:
        st.caption("候補に使った項目（個人情報フィールドは含めません）")
        st.dataframe(pd.DataFrame([safe_fields]), use_container_width=True)
    if st.button("候補をクリア", key="clear_master_candidate"):
        st.session_state["master_registration_candidate"] = {}
        st.rerun()


def render_tab_master():
    st.subheader("⚙️ マスタ管理")
    st.markdown(
        """
<div style="border-left:4px solid #475569;padding:8px 12px;margin:6px 0 12px 0;background:#F8FAFC;">
  <strong style="color:#475569;">管理画面</strong>
</div>
""",
        unsafe_allow_html=True,
    )
    st.markdown("##### キャッシュ")
    st.info(
        "CSVを編集してStreamlitをリロードすると反映されます。\n"
        "CSV更新後に古い判定が残る場合は、下の「CSVキャッシュをクリア」を押してください。"
    )
    if st.button("CSVキャッシュをクリア", type="secondary", use_container_width=True):
        st.cache_data.clear()
        st.success("CSVキャッシュをクリアしました。")
        st.rerun()

    st.markdown("##### システム情報")
    st.table(build_system_info_display())

    st.markdown("##### 不足マスタ候補")
    _render_master_candidate_box()

    st.markdown("##### CSV編集")
    st.caption("デバッグ/レガシー用途のCSVは、各タブ内で折りたたみながら整理していきます。")
    master_tabs = st.tabs([
        "製品エイリアス", "修理形態ルール", "概算費用ルール",
        "修理拠点ルール", "テンプレートコード", "販売店テンプレート", "回線名マスタ",
        "メーカーグループ", "エリアグループ", "レガシーマスタ",
    ])

    with master_tabs[0]:
        st.markdown("##### 📄 master_product_alias.csv")
        with st.expander("CSVへ製品エイリアスを追加", expanded=bool(_candidate_field("product_alias", "keyword"))):
            _render_product_alias_append_ui()
        df = load_alias_csv()
        if df.empty:
            st.warning("CSVが見つかりません: data/master_product_alias.csv")
        else:
            st.success(f"読み込み済み: {len(df)} 行（有効行）")
            st.dataframe(df, use_container_width=True)
            st.caption("keyword → normalized_product へのエイリアス変換ルール")

    with master_tabs[1]:
        st.markdown("##### 📄 master_repair_type_rules.csv")
        with st.expander("CSVへ修理形態ルールを追加", expanded=bool(_candidate_field("repair_type_rule", "product_keyword"))):
            _render_repair_type_append_ui()
        df = load_repair_type_rules()
        if df.empty:
            st.warning("CSVが見つかりません: data/master_repair_type_rules.csv")
        else:
            st.success(f"読み込み済み: {len(df)} 行（有効行）")
            st.dataframe(df, use_container_width=True)
            st.caption("製品/メーカー/型番/条件から修理形態（出張/持込/要確認）を判定")

    with master_tabs[2]:
        st.markdown("##### 📄 master_cost_rules.csv")
        df = load_cost_rules()
        if df.empty:
            st.warning("CSVが見つかりません: data/master_cost_rules.csv")
        else:
            st.success(f"読み込み済み: {len(df)} 行（有効行）")
            st.dataframe(df, use_container_width=True)
            st.caption("製品/メーカー/修理形態から保証対象外概算費用を判定")
            st.caption(f"国内PCメーカーグループ (manufacturer_group=国内PC): {sorted(DOMESTIC_PC_MAKERS)}")

    with master_tabs[3]:
        st.markdown("##### 📄 master_vendor_rules.csv")
        with st.expander("CSVへ修理拠点ルールを追加", expanded=bool(_candidate_field("vendor_rule", "repair_type"))):
            _render_vendor_rule_append_ui()
        df = load_vendor_rules()
        if df.empty:
            st.warning("CSVが見つかりません: data/master_vendor_rules.csv")
        else:
            st.success(f"読み込み済み: {len(df)} 行（有効行）")
            st.dataframe(df, use_container_width=True)
            st.caption("案件区分/都道府県/エリア/製品/メーカーから修理拠点候補を判定")
            with st.expander("エリアグループ定義"):
                for ag, prefs in AREA_GROUPS.items():
                    st.markdown(f"- **{ag}**: {', '.join(sorted(prefs))}")

    with master_tabs[4]:
        st.markdown("##### 📄 master_template_codes.csv")
        with st.expander("業者送付コードテンプレートを編集", expanded=False):
            _render_vendor_send_template_edit_ui()
        df = load_template_codes()
        if df.empty:
            st.warning("CSVが見つかりません: data/master_template_codes.csv")
        else:
            st.success(f"読み込み済み: {len(df)} 行（有効行）")
            st.dataframe(df, use_container_width=True)
            st.caption("業者送付テンプレートコードと案件区分候補")

        df_send_tpl = load_vendor_send_templates()
        st.markdown("##### master_vendor_send_templates.csv")
        if df_send_tpl.empty:
            st.info("CSVが見つかりません: data/master_vendor_send_templates.csv")
        else:
            st.dataframe(df_send_tpl, use_container_width=True)

    with master_tabs[5]:
        st.markdown("##### 📄 master_store_rules.csv")
        with st.expander("CSVへ販売店テンプレートルールを追加", expanded=bool(_candidate_field("store_rule", "store_keyword"))):
            _render_store_rule_append_ui()
        df = load_store_rules()
        if df.empty:
            st.warning("CSVが見つかりません: data/master_store_rules.csv")
        else:
            st.success(f"読み込み済み: {len(df)} 行（有効行）")
            st.dataframe(df, use_container_width=True)
            st.caption("販売店名から終話後処理テンプレートを優先判定")

    with master_tabs[6]:
        st.markdown("##### 📄 master_call_lines.csv")
        with st.expander("回線名マスタを編集", expanded=False):
            _render_call_line_master_edit_ui()
        df = load_call_lines()
        if df.empty:
            st.warning("CSVが見つかりません: data/master_call_lines.csv")
        else:
            st.success(f"読み込み済み: {len(df)} 行（有効行）")
            st.dataframe(df, use_container_width=True)
            st.caption("入電回線名と回線グループ")

    with master_tabs[7]:
        st.markdown("##### 📄 master_manufacturer_groups.csv")
        with st.expander("CSVへメーカーグループを追加", expanded=bool((st.session_state.get("master_registration_candidate") or {}).get("manufacturer_group"))):
            _render_manufacturer_group_append_ui()
        df_mg = load_manufacturer_groups_csv()
        if df_mg.empty:
            st.warning("CSVが見つかりません: data/master_manufacturer_groups.csv")
        else:
            st.success(f"読み込み済み: {len(df_mg)} グループ定義")
            st.dataframe(df_mg, use_container_width=True)
            st.caption("group_name 列 = master_cost_rules.csv の manufacturer_group で参照するグループ名")
            mfr_dict = load_manufacturer_groups_dict()
            with st.expander("展開済みグループ定義"):
                for gname, mfrs in mfr_dict.items():
                    st.markdown(f"- **{gname}**: {', '.join(sorted(mfrs))}")

    with master_tabs[8]:
        st.markdown("##### 📄 master_area_groups.csv（NTT東西エリア等）")
        df_ag = load_area_groups_csv()
        if df_ag.empty:
            st.warning("CSVが見つかりません: data/master_area_groups.csv")
        else:
            st.success(f"読み込み済み: {len(df_ag)} エリアグループ定義")
            st.dataframe(df_ag, use_container_width=True)
            st.caption("vendor判定・NTT東西エリア判定等に利用可能")
            area_dict = load_area_groups_dict()
            with st.expander("展開済みエリアグループ定義"):
                for aname, prefs in area_dict.items():
                    st.markdown(f"- **{aname}** ({len(prefs)}県): {', '.join(sorted(prefs))}")

    with master_tabs[9]:
        st.markdown("##### 📄 master_products.csv（legacy・後方互換）")
        df = load_master_products()
        if df.empty:
            st.info("master_products.csv は存在しないか無効です（主判定には使いません）")
        else:
            st.warning(f"レガシーCSV読み込み済み: {len(df)} 行（主判定では使用しません）")
            st.dataframe(df, use_container_width=True)

    st.divider()
    with st.expander("既存ロジック参照（各層のフォールバック用定数）"):
        st.markdown(f"- 出張修理製品: {sorted(VISIT_REPAIR_PRODUCTS)}")
        st.markdown(f"- 持込修理製品: {sorted(CARRY_IN_REPAIR_PRODUCTS)}")
        st.markdown(f"- 要確認製品: {sorted(CONFIRM_REPAIR_PRODUCTS)}")
        st.markdown(f"- データ消去同意必要: {sorted(DATA_ERASE_PRODUCTS)}")
    st.caption("※ 録音・文字起こし機能はPhase2後続コミットで実装予定。")


# ============================================================
# メイン
# ============================================================
def main():
    st.set_page_config(
        page_title="修理受付 支援ツール MVP",
        page_icon="🔧",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.title("🔧 修理受付 支援ツール MVP")
    init_session()
    process_pending_case_clear(st.session_state)
    process_pending_case_basic_widget_refresh(st.session_state)
    sync_global_case_basic_widget_state(st.session_state.form, st.session_state)
    render_global_top_panels(st.session_state.form)
    render_global_case_basic_panel(st.session_state.form)
    st.markdown("""
<style>
div[data-baseweb="tab-list"] {
    border-bottom: 1px solid #D0D5DD !important;
    gap: 4px;
}
button[data-baseweb="tab"] {
    font-size: 1.0em;
    font-weight: 500 !important;
    color: #667085 !important;
    padding: 8px 18px;
    border-bottom: 3px solid transparent;
}
button[data-baseweb="tab"][aria-selected="true"] {
    font-weight: 700 !important;
    color: #2563EB !important;
    background-color: #EFF6FF !important;
    border-bottom: 3px solid #2563EB;
}
button[data-baseweb="tab"][aria-selected="true"] * {
    color: #2563EB !important;
}
div[data-baseweb="tab-highlight"] {
    background-color: #2563EB !important;
}
button[data-baseweb="tab"]:hover:not([aria-selected="true"]) {
    color: #475569;
    background-color: #F8FAFC;
}
</style>
""", unsafe_allow_html=True)
    st.markdown("""
<style>
.wrt-status-card {
    width: 100%;
    box-sizing: border-box;
    overflow-wrap: anywhere;
    border-radius: 10px;
    padding: 12px 14px;
    margin: 8px 0;
    min-height: 72px;
    border: 1px solid #e5e7eb;
    color: #1f2937;
}
.wrt-status-card.warning {
    background: #fff7ed;
    border-color: #fdba74;
}
.wrt-status-card.error {
    background: #fef2f2;
    border-color: #fca5a5;
}
.wrt-status-card.info {
    background: #f8fafc;
    border-color: #cbd5e1;
}
.wrt-status-card.success {
    background: #f0fdf4;
    border-color: #86efac;
}
.wrt-status-card-head {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 6px;
}
.wrt-status-card-body {
    font-size: 0.92rem;
    line-height: 1.55;
    overflow-wrap: anywhere;
}
.wrt-text-section,
.wrt-action-panel {
    width: 100%;
    box-sizing: border-box;
    overflow-wrap: anywhere;
}
.wrt-sub-input-label {
    font-size: 0.82rem;
    color: #6b7280;
    margin-top: -4px;
    margin-bottom: 2px;
}
.wrt-sub-input-help {
    font-size: 0.78rem;
    color: #9ca3af;
    margin-bottom: 2px;
}
.wrt-pill {
    display: inline-block;
    min-width: 88px;
    text-align: center;
    border-radius: 999px;
    padding: 2px 10px;
    font-size: 12px;
    font-weight: 700;
    border: 1px solid transparent;
}
.wrt-pill.warning {
    background: #fed7aa;
    color: #7c2d12;
}
.wrt-pill.error {
    background: #fecaca;
    color: #7f1d1d;
}
.wrt-pill.info {
    background: #e2e8f0;
    color: #334155;
}
.wrt-pill.success {
    background: #bbf7d0;
    color: #14532d;
}
.wrt-decision-tag {
    min-height: 124px;
    height: 124px;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    gap: 4px;
    overflow: hidden;
    border-radius: 8px;
    padding: 11px 12px;
    margin-bottom: 8px;
    font-size: 0.92em;
}
.wrt-decision-tag-title {
    font-size: 0.78rem;
    font-weight: 700;
    line-height: 1.25;
    white-space: nowrap;
    opacity: 0.82;
}
.wrt-decision-tag-primary {
    font-size: 1.1rem;
    font-weight: 800;
    line-height: 1.25;
    white-space: nowrap;
}
.wrt-decision-tag-secondary {
    font-size: 0.76rem;
    line-height: 1.35;
    max-height: 3.0em;
    opacity: 0.9;
    overflow: hidden;
}
.wrt-decision-tag-tertiary {
    font-size: 0.72rem;
    line-height: 1.3;
    max-height: 2.6em;
    opacity: 0.9;
    overflow: hidden;
}
.wrt-snippet-group-label {
    display: inline-block;
    margin-top: 8px;
    margin-bottom: 2px;
    color: #334155;
    font-size: 0.86rem;
    font-weight: 700;
}
.wrt-memo-snippet-row {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 8px 10px;
    margin: 6px 0;
    background: #ffffff;
}
</style>
""", unsafe_allow_html=True)
    tab_call, tab_after, tab_master = st.tabs([
        "通話中判定",
        "終話後処理",
        "マスタ管理",
    ])
    with tab_call:
        render_tab_call()
    with tab_after:
        render_tab_after_call()
    with tab_master:
        render_tab_master()


if __name__ == "__main__":
    main()
