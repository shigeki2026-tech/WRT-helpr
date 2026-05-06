# -*- coding: utf-8 -*-
"""修理受付 支援ツール MVP - app.py  (Phase2-2: 4-layer CSV decision)"""

import re
import os
import csv  # CSV読み込み改善
import json
import hashlib
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
DEFAULT_TEAMS_CONFIG = {
    "enabled": False,
    "chat_id": "",
    "chat_name": "WRT報告用チャット",
    "send_mode": "powershell_graph",
}
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
    "appliance_type": "家電/住設",
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
    "extracted_time": "入電時刻",
    "symptom": "症状",
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


CHECK_ITEM_DEFINITIONS = {
    "症状の詳細": {
        "id": "symptom_detail",
        "fields": ("symptom",),
        "input": "textarea",
        "label": "症状の詳細",
        "input_label": "症状",
    },
    "発生時期": {
        "id": "occurrence_time",
        "fields": ("occurrence_time",),
        "input": "text",
        "label": "発生時期",
    },
    "発生頻度": {
        "id": "occurrence_frequency",
        "fields": ("occurrence_frequency",),
        "input": "text",
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
_REPAIR_TYPE_COLS  = ["priority", "enabled", "product_keyword", "manufacturer_keyword",
                      "model_keyword", "condition_keyword", "repair_type", "needs_confirmation", "notes"]
_COST_COLS         = ["priority", "enabled", "product_keyword", "manufacturer_keyword",
                      "manufacturer_group", "condition_keyword", "repair_type",
                      "cost_estimate", "can_announce_cost", "needs_escalation",
                      "required_fields", "cost_status", "guidance_scope",
                      "required_questions", "customer_notice", "internal_note", "notes"]
_MFR_GROUP_COLS    = ["group_name", "manufacturers", "notes"]
_AREA_GROUP_COLS   = ["area_group", "prefectures", "notes"]
_SCRIPT_LINK_COLS   = ["script_sheet", "script_part", "display_name", "url", "notes"]
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
_CALL_LINE_COLS = ["priority", "enabled", "call_line", "line_group", "notes"]
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
        return pd.DataFrame(columns=required_cols)
    df["priority"] = pd.to_numeric(df["priority"], errors="coerce").fillna(999).astype(int)
    df["enabled"]  = pd.to_numeric(df["enabled"],  errors="coerce").fillna(0).astype(int)
    df = df[df["enabled"] == 1].copy()
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
def _load_script_guidance_cached(mtime: float) -> pd.DataFrame:
    return _load_csv("master_script_guidance.csv", _SCRIPT_GUIDANCE_COLS)


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


def load_script_guidance_csv() -> pd.DataFrame:
    return _load_script_guidance_cached(_csv_mtime("master_script_guidance.csv"))


MASTER_APPEND_TARGETS = {
    "master_product_alias.csv": _ALIAS_COLS,
    "master_repair_type_rules.csv": _REPAIR_TYPE_COLS,
    "master_store_rules.csv": _STORE_RULE_COLS,
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
    filtered = df_tpl[df_tpl["category"] == call_line]
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
            return {
                "matched": True,
                "store_keyword": keyword,
                "normalized_store": (row.get("normalized_store") or keyword).strip(),
                "template_code": (row.get("template_code") or "").strip(),
                "template_label": (row.get("template_label") or "").strip(),
                "template_group": (row.get("template_group") or "").strip(),
                "notes": (row.get("notes") or "").strip(),
                "priority": int(row.get("priority", 999)),
            }

    if default_row is not None:
        base.update({
            "normalized_store": (default_row.get("normalized_store") or "").strip(),
            "template_code": (default_row.get("template_code") or "").strip(),
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
        matched = df_tpl[df_tpl["template_code"] == template_code]
        if not matched.empty:
            return matched.iloc[0]
    if template_label:
        matched = df_tpl[df_tpl["label"] == template_label]
        if not matched.empty:
            return matched.iloc[0]
    return None


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
            code = (row.get("template_code") or "").strip()
        else:
            label = store_rule.get("template_label", "")
            code = store_rule.get("template_code", "")
        source = "store_direct"
    elif store_rule.get("matched") and store_rule.get("template_group"):
        label = _auto_select_template_by_group(
            store_rule["template_group"], repair_type, warranty_plan, df_tpl
        )
        if label:
            row = _template_row_by_code_or_label(df_tpl, template_label=label)
            code = (row.get("template_code") or "").strip() if row is not None else ""
            source = "store_group"

    if not label:
        label = _auto_select_template(
            form.get("call_line", ""), repair_type, warranty_plan, df_tpl
        )
        row = _template_row_by_code_or_label(df_tpl, template_label=label)
        code = (row.get("template_code") or "").strip() if row is not None else ""
        source = "fallback"

    return {
        "label": label,
        "template_code": code,
        "source": source,
        "store_rule": store_rule,
    }


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
                           vendor: str, notes_filled: str = "") -> str:
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
        f"症状: {form.get('symptom','─')}\n"
        f"拠点候補: {vendor}"
        f"{dp_note}"
    )
    store_attention_notes = build_store_attention_notes(form)
    if store_attention_notes:
        memo += "\n\n【販売店別注意】\n" + "\n".join(f"- {note}" for note in store_attention_notes)
    if notes_filled:
        memo += f"\n\n【備考】\n{notes_filled}"
    return memo


def _rakutel_call_direction(form: dict) -> str:
    direction = (form.get("call_direction") or "").strip()
    return direction if direction in ("受電", "架電") else "受電"


def _rakutel_counterparty(form: dict, caller_type: str = "") -> str:
    counterparty = (form.get("counterparty_type") or "").strip()
    legacy_caller = (caller_type or "").strip()
    form_caller = (form.get("caller_type") or "").strip()
    if legacy_caller and counterparty and form_caller and counterparty == form_caller and legacy_caller != form_caller:
        return legacy_caller
    if counterparty:
        return counterparty
    return (legacy_caller or form_caller or "加入者").strip() or "加入者"


def _rakutel_call_arrow(form: dict, caller_type: str = "") -> str:
    operator = (form.get("operator_name") or "").strip() or "●●"
    counterparty = _rakutel_counterparty(form, caller_type)
    if _rakutel_call_direction(form) == "架電":
        return f"MPG{operator}→{counterparty}"
    return f"{counterparty}→MPG{operator}"


def _rakutel_call_heading(form: dict) -> str:
    line_label = _line_label_for_call_line(form.get("call_line", ""))
    if _rakutel_call_direction(form) == "架電":
        return f"【{line_label}から架電】"
    return f"【{line_label}に入電】"


def _build_rakutel_text(form: dict, caller_type: str, notes_filled: str = "") -> str:
    operator = (form.get("operator_name") or "").strip() or "●●"
    extracted_time = (form.get("extracted_time") or "").strip()
    contact = (form.get("contact_phone") or "").strip() or (form.get("phone_number") or "").strip() or "─"
    rakuteru = (form.get("rakuteru_no") or "").strip()

    rakutel_text = (
        f"{_rakutel_call_heading(form)}\n"
        f"{extracted_time}　{_rakutel_call_arrow(form, caller_type)}\n\n"
        f"【修理受付】\n"
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

    return {
        "title": title,
        "reason": reason,
        "next_action": next_action,
    }


def build_vendor_candidate_card_info(vendor: str, vendor_result: dict | None = None) -> dict:
    vendor_result = vendor_result or {}
    folder = get_request_pdf_folder_info(vendor)
    action = "依頼書PDF格納" if folder.get("required") else ""
    return {
        "vendor": vendor,
        "reason": (vendor_result.get("reason") or "").strip(),
        "needs_escalation": bool(vendor_result.get("needs_escalation")),
        "escalation": build_vendor_escalation_info(vendor, vendor_result) if vendor_result.get("needs_escalation") else {},
        "request_folder": folder,
        "arrangement_method": action,
    }


def resolve_teams_request_action(form: dict, vendor: str, contact_type: str = "") -> str:
    manual_action = (form.get("teams_action") or "").strip()
    if manual_action:
        return manual_action

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


def _build_teams_chat_message(form: dict, vendor: str, contact_type: str = "") -> str:
    rakuteru = (form.get("rakuteru_no") or "").strip()
    case_name = (form.get("call_line") or "").strip()
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


def _build_after_call_texts(form: dict, warranty_result: dict, repair_type: str,
                            vendor: str, caller_type: str, notes_filled: str,
                            contact_type: str = "") -> dict:
    return {
        "attention_memo": _build_after_call_memo(form, warranty_result, repair_type, vendor, notes_filled),
        "rakutel_text": _build_rakutel_text(form, caller_type, notes_filled),
        "teams_chat_message": _build_teams_chat_message(form, vendor, contact_type),
    }


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
    for key in [
        "_pending_case_clear",
        "clear_case_pending_call",
        "clear_case_pending_after",
        "clear_case_done_call",
        "clear_case_done_after",
    ]:
        if key in session_state:
            del session_state[key]
    session_state["case_memo_global"] = ""
    session_state["form"]["call_memo"] = ""
    return True


def reset_case_session_state(session_state, settings: dict | None = None) -> dict:
    new_form = apply_default_operator_name(empty_form(), settings)
    session_state["form"] = new_form
    session_state["call_check_manual"] = {}
    session_state["extracted"] = {}
    session_state["pasted_text"] = ""
    set_show_copy_import(session_state, True)
    session_state["master_registration_candidate"] = {}
    for key in [
        "memo_after",
        "rakutel_text_display",
        "teams_chat_message_display",
        "teams_send_confirmed",
        "request_pdf_storage_confirmed",
        "tpl_label_select_after",
        "teams_action_input",
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
        if str(key).startswith(("manual_check_", "now_input_")):
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

    if not config.get("chat_id"):
        config["enabled"] = False

    return config


def is_teams_send_enabled() -> bool:
    config = load_teams_config()
    return bool(config.get("enabled") and config.get("chat_id"))


def send_teams_message_via_powershell(message: str) -> dict:
    body = (message or "").strip()
    if not body:
        return {"ok": False, "message": "送信失敗: 送信本文が空です", "stdout": "", "stderr": ""}

    config = load_teams_config()
    chat_id = (config.get("chat_id") or "").strip()
    if not config.get("enabled") or not chat_id:
        return {"ok": False, "message": "送信失敗: Teams送信設定が未完了です", "stdout": "", "stderr": ""}

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
            return {"ok": True, "message": "送信成功", "stdout": stdout, "stderr": stderr}
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


def append_teams_send_log(result: dict, message: str, chat_name: str) -> list:
    if "teams_send_log" not in st.session_state:
        st.session_state.teams_send_log = []
    entry = {
        "sent_at": datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
        "ok": bool(result.get("ok")),
        "chat_name": chat_name,
        "message_preview": (message or "").replace("\n", " ")[:100],
        "error_message": "" if result.get("ok") else result.get("message", ""),
    }
    st.session_state.teams_send_log.insert(0, entry)
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
        "洗濯機", "冷蔵庫", "エアコン", "給湯器", "温水便座", "IH",
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


def get_call_line_options() -> list:
    """master_call_lines.csv の call_line から回線名候補を生成する。"""
    options = [""]
    seen = {""}
    df = load_call_lines()
    if not df.empty:
        for val in df["call_line"].tolist():
            if val and val not in seen:
                options.append(val)
                seen.add(val)
    return options


def get_line_group(call_line: str) -> str:
    """回線名からline_group（家電/住設/その他）を返す。"""
    df = load_call_lines()
    if df.empty:
        return ""
    rows = df[df["call_line"] == call_line]
    if rows.empty:
        return ""
    return rows.iloc[0].get("line_group", "")


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
        "給湯器": "給湯器", "温水便座": "温水便座", "掃除機": "掃除機",
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
    if genre:
        form["appliance_type"] = "住設" if any(
            x in genre for x in ["住設", "給湯", "温水", "ビルトイン"]
        ) else "家電"
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
    condition    = (form.get("extra_condition") or "").strip()

    if not df.empty:
        for _, row in df.iterrows():
            pk  = (row.get("product_keyword") or "").strip()
            mk  = (row.get("manufacturer_keyword") or "").strip()
            mok = (row.get("model_keyword") or "").strip()
            ck  = (row.get("condition_keyword") or "").strip()

            if not _kw_match(pk, product):      continue
            if not _kw_match(mk, manufacturer): continue
            if not _kw_match(mok, model):       continue
            if not _kw_match(ck, condition):    continue

            matched_kw = pk or mk or mok or ck or "(条件なし)"
            return {
                "matched":           True,
                "repair_type":       (row.get("repair_type") or "要確認").strip(),
                "needs_confirmation": str(row.get("needs_confirmation", "0")).strip() == "1",
                "keyword":           matched_kw,
                "priority":          int(row.get("priority", 999)),
                "csv_name":          "master_repair_type_rules.csv",
                "notes":             (row.get("notes") or "").strip(),
            }

    return {
        "matched": False, "repair_type": "", "needs_confirmation": False,
        "keyword": "", "priority": None, "csv_name": "", "notes": "",
    }


# ── 既存ロジック（フォールバック・削除しない） ──
VISIT_REPAIR_PRODUCTS  = {
    "洗濯機", "冷蔵庫", "エアコン", "給湯器", "温水便座", "食器洗い乾燥機",
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
def determine_vendor_from_rules(form: dict, repair_type: str) -> dict:
    """
    master_vendor_rules.csv を使って修理拠点候補を判定する。
    - call_line / prefecture は完全一致（空=ワイルドカード）
    - area_group は AREA_GROUPS マッピングで都道府県が含まれるか判定
    - その他フィールドは keyword in target の包含一致
    """
    df = load_vendor_rules()
    call_line    = (form.get("call_line") or "").strip()
    prefecture   = (form.get("prefecture") or "").strip()
    manufacturer = (form.get("manufacturer") or "").strip()
    product      = (form.get("product") or "").strip()
    store        = (form.get("store_name") or "").strip()

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
            if cl and cl.lower() != call_line.lower():         continue
            # prefecture: 完全一致（空=ワイルドカード）
            if pref and pref != prefecture:                     continue
            # area_group: CSVのNTT東西エリアと既存の地域グループを両方参照（空=ワイルドカード）
            if ag:
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
        "reason": "", "needs_escalation": True, "keyword": "",
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
# call_line 属性推定（回線名 + 販売店名）
# ============================================================
def infer_call_line_attrs(form: dict) -> dict:
    """
    call_line と store_name から案件属性を自動推定する。
    戻り値: {"call_line": str, "is_bic_sofmap": bool}
    """
    call_line = (form.get("call_line") or "").strip()
    store = (form.get("store_name") or "").strip()
    inferred_call_line = call_line
    if not inferred_call_line:
        if "ビックカメラ" in store or ("ビック" in store and "カメラ" in store):
            inferred_call_line = "ビックカメラ"
        elif "ソフマップ" in store:
            inferred_call_line = "ソフマップ"
    is_bic_sofmap = (
        "ビックカメラ" in inferred_call_line or
        "ソフマップ" in inferred_call_line or
        "ビックカメラ" in store or
        "ソフマップ" in store
    )
    return {"call_line": inferred_call_line, "is_bic_sofmap": is_bic_sofmap}


# ============================================================
# スクリプトルート判定（既存ロジック・削除しない）
# ============================================================
def determine_script_route(form: dict, repair_type: str) -> dict:
    call_line      = form.get("call_line", "")
    appliance_type = form.get("appliance_type", "")
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
    if get_line_group(call_line) == "住設":
        result.update(sheet_name="住設【既築／中古のみ】", part="既築・中古住設受付",
                      reason="住設回線")
        return result
    if appliance_type == "住設":
        result.update(sheet_name="住設【既築／中古のみ】", part="住設受付", reason="住設製品")
        return result
    if appliance_type == "家電" and repair_type == "出張修理":
        result.update(sheet_name="家電出張・持込・新築住設", part="家電・出張修理",
                      reason="家電＋出張修理")
        if is_dp:
            result.update(display_name="ダブルプロテクト / 出張修理",
                          reason="家電＋出張修理＋ダブルプロテクト")
        return result
    if appliance_type == "家電" and repair_type == "持込修理":
        result.update(sheet_name="家電出張・持込・新築住設", part="家電・持込修理",
                      reason="家電＋持込修理")
        if is_dp:
            result.update(display_name="ダブルプロテクト / 持込修理",
                          reason="家電＋持込修理＋ダブルプロテクト")
        return result
    result.update(sheet_name="要確認", part="SV/担当確認",
                  escalation_needed=True, reason="家電/住設区分または修理形態が未確定")
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
    script_link = lookup_script_link(script_result)
    script_type = summary["script_type"]
    script_display = summary["script_part"] or summary["script_display"]
    if script_type == "ダブルプロテクト" and script_display.startswith("家電・"):
        script_display = script_display.replace("家電・", "", 1)
    return {
        "title": "📘 参照スクリプト",
        "script_type": script_type,
        "display": script_display,
        "label": f"{script_type} / {script_display}",
        "matched": bool(script_link.get("matched")),
        "url": script_link.get("url", ""),
        "link_text": script_link.get("display_name", "スクリプト"),
        "message": "" if script_link.get("matched") else f"{script_type} / {script_display}\nURL未登録（手動で参照）",
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

    return [
        {
            "title": "受付可否",
            "primary": warranty_status_label,
            "secondary": product_display,
            "tertiary": warranty_plan or "保証プラン未入力",
            "quaternary": f"商品価格　{product_price}" if product_price else "商品価格　未入力",
            "color": summary["warranty"]["color"],
            "compact": True,
        },
        {
            "title": "修理方針",
            "primary": summary["repair"]["value"],
            "secondary": summary["cost"]["value"],
            "color": summary["repair"]["color"],
        },
        {
            "title": "拠点対応",
            "primary": vendor or "未確定",
            "secondary": vendor_status,
            "color": TAG_COLOR_WARNING if vendor_card.get("needs_escalation") else TAG_COLOR_OK,
        },
        {
            "title": "スクリプト",
            "primary": script_reference.get("script_type", ""),
            "secondary": script_reference.get("display", ""),
            "color": TAG_COLOR_DP if summary.get("is_double_protect") else TAG_COLOR_ACTION,
            "url": script_reference.get("url", ""),
            "link_text": (script_reference.get("link_text", "") + " 該当箇所を開く")
                         if script_reference.get("matched") else "URL未登録（手動で参照）",
            "matched": script_reference.get("matched", False),
        },
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
        f"家電/住設　 : {form.get('appliance_type', '未入力')}",
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
        if not (form.get("appliance_type") or "").strip():
            missing_for_script.append("appliance_type")
            reasons.append("家電/住設が未選択")
        if "product" in missing_for_script:
            items.append(_item(
                "参照スクリプト判定", "warning", "製品未入力",
                "製品が未選択のため参照スクリプトを確定できません。",
                missing_fields=["product"],
                next_action="製品を入力してください",
                impact="call_time_required",
            ))
        if "appliance_type" in missing_for_script:
            items.append(_item(
                "参照スクリプト判定", "warning", "家電/住設区分未入力",
                "家電/住設区分が未選択のため参照スクリプトを確定できません。",
                missing_fields=["appliance_type"],
                next_action="家電/住設区分を入力してください",
                impact="call_time_required",
            ))
        script_next_action = "SV/担当に確認"
        repair_type = result.get("repair_type", "")
        if not repair_type or repair_type == "要確認":
            if form.get("product") == "腕時計":
                reasons.append("腕時計案件の修理形態はSV/担当確認")
                script_next_action = "腕時計案件の修理形態をSV/担当へ確認"
            else:
                reasons.append("修理形態が要確認または未確定")
        if escalation_needed:
            reasons.append("エスカレーションが必要")
        non_missing_reasons = [r for r in reasons if r not in ("製品が未選択", "家電/住設が未選択")]
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
        items.append(_item(
            "修理形態判定", "ok", f"修理形態: {repair_type}",
            "修理形態が確定しました。",
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
        if repair_result.get("needs_confirmation"):
            note = (repair_result.get("notes") or "型番・詳細確認要").strip()
            reasons.append(f"確認要: {note}")
        if not reasons:
            reasons.append("修理形態が「要確認」または未確定です")
        repair_next_action = (
            "腕時計案件の修理形態をSV/担当へ確認"
            if product_val == "腕時計"
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
    if inferred_call_line_attrs.get("call_line"):
        working_form["call_line"] = inferred_call_line_attrs["call_line"]
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
        elif field_name == "appliance_type":
            msg = "⚠️ 必須確認：家電/住設区分を入力してください"
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
            # primary 行は compact でも大きく太字で強調
            body_parts.append(
                f'<div style="font-size:1.16em;font-weight:800;line-height:1.35;'
                f'margin-bottom:5px;word-break:break-all;">'
                f'{_ui_v3_escape(value)}</div>'
            )
        elif compact:
            body_parts.append(
                f'<div style="font-size:0.86em;opacity:0.9;line-height:1.5;'
                f'margin-bottom:2px;word-break:break-all;">'
                f'{_ui_v3_escape(value)}</div>'
            )
        elif i == 0:
            body_parts.append(
                f'<div style="font-size:1.18em;font-weight:800;line-height:1.35;margin-bottom:3px;">'
                f'{_ui_v3_escape(value)}</div>'
            )
        else:
            body_parts.append(
                f'<div style="font-size:0.88em;opacity:0.88;line-height:1.5;">'
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
        f'<div style="background:{bg_color};color:white;padding:12px 14px;'
        f'border-radius:8px;font-size:0.92em;margin-bottom:8px;min-height:{min_height}px;">'
        f'<div style="font-size:0.84em;opacity:0.8;margin-bottom:5px;">{_ui_v3_escape(title)}</div>'
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
        help="ラクテル用テキストやTeams報告文には自動反映されません。",
    )
    sync_case_memo_global(form, st.session_state)


def render_decision_tags_panel(form: dict) -> None:
    st.markdown("##### 🧭 判定タグ")
    try:
        decision = run_decision(form)
        script_reference = build_script_reference_info(decision)
        tags = build_decision_tag_items(decision, form, script_reference)
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
            st.markdown(
                _ui_v3_block(tag["title"], lines, tag["color"],
                             min_height=104, link=link,
                             compact=tag.get("compact", False)),
                unsafe_allow_html=True,
            )


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
    if not st.session_state.get(pending_key):
        if st.button("🧹 この案件をクリア", key=f"clear_case_prepare_{scope}", type="secondary",
                     use_container_width=use_container_width):
            st.session_state[pending_key] = True
            st.rerun()
        return

    st.warning("次の案件へ移る前に、必要な送信・記録が完了していることを確認してください。")
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
    return format_store_template_rule_display(selected.get("store_rule", {}))


def render_after_call_basic_panel(form: dict) -> dict:
    st.markdown("##### 🧾 案件基本（共通）")
    st.caption("基本項目を変更すると、テンプレート判定・ラクテル文・Teams報告文に反映されます。")

    call_line_opts = get_call_line_options()
    if form.get("call_line") and form.get("call_line") not in call_line_opts:
        call_line_opts = [form.get("call_line")] + call_line_opts
    appliance_type_opts = ["", "家電", "住設"]

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        form["call_line"] = st.selectbox(
            "回線名",
            call_line_opts,
            index=call_line_opts.index(form.get("call_line", ""))
            if form.get("call_line", "") in call_line_opts else 0,
            key="call_line_input_after",
        )
        form["product"] = st.text_input(
            "製品",
            value=form.get("product", ""),
            key="product_input_after",
        )
    with col_b:
        form["appliance_type"] = st.selectbox(
            "家電/住設",
            appliance_type_opts,
            index=appliance_type_opts.index(form.get("appliance_type", ""))
            if form.get("appliance_type", "") in appliance_type_opts else 0,
            key="appliance_type_input_after",
        )
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
            key="manufacturer_input_after",
        )
    with col_c:
        form["store_name"] = st.text_input(
            "販売店",
            value=form.get("store_name", ""),
            key="store_name_input_after",
        )
        preview_decision = run_decision(form)
        template_display = build_case_basic_template_display(
            form,
            preview_decision.get("repair_type", ""),
        )
        st.markdown("**テンプレート判定結果**")
        st.info(template_display)

    st.session_state.form = form
    return form


def _set_manual_check(item_id: str, value: bool) -> None:
    manual = dict(st.session_state.get("call_check_manual", {}))
    manual[item_id] = bool(value)
    st.session_state["call_check_manual"] = manual


def manual_check_widget_key(item: dict, index: int = 0, prefix: str = "manual_check") -> str:
    item_id = item.get("id") or "manual_item"
    label = item.get("label") or item.get("input_label") or item_id
    return f"{prefix}_{item_id}_{index}_{stable_hash_text(label)}"


def render_now_action_item(item: dict, form: dict, index: int = 0) -> None:
    item_id = item["id"]
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
        render_case_clear_controls("call")

        toggle_label = "📋 コピー情報取り込みを閉じる" if show_copy_import(st.session_state) else "📋 コピー情報取り込みを開く"
        if st.button(toggle_label, key="toggle_copy_import", use_container_width=True):
            set_show_copy_import(st.session_state, not show_copy_import(st.session_state))
            st.rerun()

        if show_copy_import(st.session_state):
            st.markdown("##### 📋 コピー情報取り込み")
            if _PYPERCLIP_AVAILABLE:
                st.caption("⚠️ クリップボード読み取りはローカルPC起動時のみ有効です")
                if st.button("📋 クリップボードから直接抽出", use_container_width=True, type="primary"):
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
                        st.session_state["form"]["extracted_time"] = _format_extracted_time()
                        close_copy_import_panel(st.session_state)
                        st.rerun()
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
                    close_copy_import_panel(st.session_state)
                    st.success("フォームへ反映しました。")
                    st.rerun()

        form = st.session_state.form

        st.subheader("📝 受付情報フォーム")
        pre_decision = run_decision(form)  # UI修正v2
        pre_diagnostics = pre_decision.get("diagnostics", {})  # UI修正v2
        missing_fields_set, invalid_fields_set = collect_diagnostic_field_sets(pre_diagnostics)

        call_line_opts    = get_call_line_options()
        appliance_type_opts = ["", "家電", "住設"]
        pref_opts = [""] + PREFECTURES

        st.markdown("##### 通話中に見る項目")
        if SHOW_CALL_TYPE_IN_CALL_FORM:
            call_type_opts = ["", "新規入電", "折り返し", "再入電", "その他"]
            form["call_type"] = st.selectbox(
                "入電種別",
                call_type_opts,
                index=call_type_opts.index(form.get("call_type", ""))
                if form.get("call_type", "") in call_type_opts else 0,
            )
        render_field_marker("call_line", missing_fields_set, invalid_fields_set, pre_diagnostics)
        form["call_line"]     = st.selectbox("回線名", call_line_opts,
            index=call_line_opts.index(form.get("call_line","")) if form.get("call_line") in call_line_opts else 0)
        render_field_marker("appliance_type", missing_fields_set, invalid_fields_set, pre_diagnostics)
        form["appliance_type"]= st.selectbox("家電/住設", appliance_type_opts,
            index=appliance_type_opts.index(form.get("appliance_type","")) if form.get("appliance_type") in appliance_type_opts else 0)
        render_field_marker("prefecture", missing_fields_set, invalid_fields_set, pre_diagnostics)
        form["prefecture"]    = st.selectbox("都道府県", pref_opts,
            index=pref_opts.index(form.get("prefecture","")) if form.get("prefecture") in pref_opts else 0)
        product_opts = get_product_options()
        current_product = form.get("product", "")
        if current_product and current_product not in product_opts:
            form["product_original"] = form.get("product_original") or current_product
            current_product = PRODUCT_OTHER
        render_field_marker("product", missing_fields_set, invalid_fields_set, pre_diagnostics)
        form["product"] = st.selectbox(
            "製品",
            product_opts,
            index=product_opts.index(current_product) if current_product in product_opts else 0,
        )
        manufacturer_opts = get_manufacturer_options()
        current_manufacturer = form.get("manufacturer", "")
        if current_manufacturer and current_manufacturer not in manufacturer_opts:
            form["manufacturer_original"] = form.get("manufacturer_original") or current_manufacturer
            current_manufacturer = normalize_manufacturer_for_select(current_manufacturer)
        render_field_marker("manufacturer", missing_fields_set, invalid_fields_set, pre_diagnostics)
        form["manufacturer"] = st.selectbox(
            "メーカー",
            manufacturer_opts,
            index=manufacturer_opts.index(current_manufacturer) if current_manufacturer in manufacturer_opts else 0,
        )
        render_field_marker("model_number", missing_fields_set, invalid_fields_set, pre_diagnostics)
        form["model_number"]  = st.text_input("型番",         form.get("model_number",""))
        form["warranty_plan"] = st.text_input("保証プラン",   form.get("warranty_plan",""))
        if is_double_protect_plan(form.get("warranty_plan", "")):
            st.warning(f"物損付 / DP案件: {double_protect_plan_label(form.get('warranty_plan', ''))}。物損保証金額はシステム確認。")

        with st.expander("補助情報を開く", expanded=False):
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
            form["product_price"] = st.text_input("商品価格",     form.get("product_price",""))
            form["wrt_no"]        = st.text_input("WRT-NO",       form.get("wrt_no",""))
            form["customer_code"] = st.text_input("お客様コード", form.get("customer_code",""))
            form["customer_name"] = st.text_input("お客様名",     form.get("customer_name",""))
            form["phone_number"]  = st.text_input("電話番号",     form.get("phone_number",""))
            form["symptom"]       = st.text_area("症状",          form.get("symptom",""), height=60)
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

        hearing_items = script_guidance.get("hearing_items", [])
        if hearing_items:
            compact_hearing = " / ".join(hearing_items[:5])
            if len(hearing_items) > 5:
                compact_hearing += " / ..."
            st.caption(f"聴取事項：{compact_hearing}")
        if script_guidance.get("notes"):
            st.caption("注意：正式トークはリンク先を正本として参照")
        if len(hearing_items) > 5 or script_guidance.get("notes"):
            with st.expander("📘 スクリプト補助の詳細", expanded=False):
                st.markdown("**聴取事項：**")
                for hearing_item in hearing_items:
                    st.markdown(f"- {hearing_item}")
                if script_guidance.get("notes"):
                    st.markdown("**注意：**")
                    st.info(script_guidance["notes"])

        st.markdown("### ✅ 今聞くこと")
        if now_action_plan["call_required"]:
            for idx, item in enumerate(now_action_plan["call_required"]):
                render_now_action_item(item, st.session_state.form, idx)
        else:
            st.success("通話中の必須確認はありません")
        if now_action_plan["completed"]:
            with st.expander("✅ 完了済み", expanded=False):
                for item in now_action_plan["completed"]:
                    st.markdown(f"- {item['label']}")

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
            arrangement = vendor_card.get("arrangement_method") or "手配方法を確認"
            st.success(f"✅ 拠点確定：{vendor}\n\n手配方法：{arrangement}")  # UI v3

        # UI改修: ゾーンD（詳細）は折りたたみ
        with st.expander("✅ 確認項目リスト", expanded=True):  # UI v3
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
            st.text_area("履歴テンプレ（コピーして使用）", history_tmpl, height=110, key="history_display")

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
    render_case_clear_controls("after")
    form = render_after_call_basic_panel(form)
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
        form["operator_name"] = st.text_input(
            "オペレーター名",
            form.get("operator_name", ""),
            placeholder="例: 大濱",
            key="operator_name_input",
        )
        if st.button("この名前を既定値として保存", key="save_default_operator_name"):
            saved = save_local_user_settings({
                "default_operator_name": form.get("operator_name", "")
            })
            if saved.get("default_operator_name"):
                st.success(f"既定オペレーター名を保存しました: {saved['default_operator_name']}")
            else:
                st.warning("オペレーター名が空のため、既定値も空で保存しました。")
        st.session_state.form = form
        st.markdown("##### 📋 テンプレート（業者送付コード）")
        df_tpl = load_template_codes()
        call_line_val = form.get("call_line", "")
        repair_type_val = decision["repair_type"]
        warranty_plan_val = form.get("warranty_plan", "")
        template_selection = select_template_for_form(
            form, repair_type_val, warranty_plan_val, df_tpl)
        store_rule_display = format_store_template_rule_display(
            template_selection["store_rule"])
        st.caption("販売店テンプレート判定：")
        st.info(store_rule_display)
        if is_double_protect_plan(warranty_plan_val):
            st.warning(f"物損付 / DP案件: {double_protect_plan_label(warranty_plan_val)}。ダブルプロテクト系テンプレートを優先します。")

        if (call_line_val or template_selection.get("label")) and not df_tpl.empty:
            filtered = df_tpl[df_tpl["category"] == call_line_val] if call_line_val else df_tpl.iloc[0:0]
            auto_label = template_selection.get("label", "")
            if not filtered.empty or auto_label:
                tpl_labels = [""] + filtered["label"].tolist()
                if auto_label and auto_label not in tpl_labels:
                    tpl_labels.append(auto_label)
                current_label = form.get("template_label", "") or auto_label
                idx = tpl_labels.index(current_label) if current_label in tpl_labels else 0

                selected_label_val = st.selectbox(
                    "テンプレートを選択",
                    tpl_labels,
                    index=idx,
                    key="tpl_label_select_after",
                )
                if selected_label_val:
                    matched = filtered[filtered["label"] == selected_label_val]
                    if matched.empty:
                        matched = df_tpl[df_tpl["label"] == selected_label_val]
                    if not matched.empty:
                        row = matched.iloc[0]
                        selected_code = row["template_code"]
                        selected_notes = (row.get("notes") or "").strip()
                        st.code(selected_code, language=None)
                        if selected_notes:
                            st.info(f"📋 備考: {selected_notes}")
                        if row.get("data_erase_required") == "条件付き":
                            st.warning("⚠️ データ消去同意【データ消去同意済】を依頼書へ記載")
                        if row.get("cost_guidance_allowed") == "不可":
                            st.error("🚫 金額案内不可案件")
                        form["template_code"] = selected_code
                        form["template_label"] = selected_label_val
                        st.session_state.form = form
                    elif selected_label_val == template_selection.get("label"):
                        selected_code = template_selection.get("template_code", "")
                        selected_notes = template_selection["store_rule"].get("notes", "")
                        if selected_code:
                            st.code(selected_code, language=None)
                        if selected_notes:
                            st.info(f"📋 備考: {selected_notes}")
                        form["template_code"] = selected_code
                        form["template_label"] = selected_label_val
                        st.session_state.form = form
                else:
                    form["template_code"] = ""
                    form["template_label"] = ""
            else:
                st.caption("基本項目を変更すると、テンプレート判定・ラクテル文・Teams報告文に反映されます。")
        else:
            st.caption("基本項目を変更すると、テンプレート判定・ラクテル文・Teams報告文に反映されます。")

        st.divider()

        st.markdown("##### 🏭 修理拠点候補")
        vr = decision["vendor_result"]
        vendor_card = build_vendor_candidate_card_info(vendor, vr)
        if vr["matched"]:
            st.info(f"{vendor}\n\n（判定根拠: {vr.get('reason','')}）")
            if vr["needs_escalation"]:
                esc = vendor_card["escalation"]
                st.warning(
                    f"{esc['title']}\n\n"
                    f"理由：{esc['reason']}\n\n"
                    f"次アクション：{esc['next_action']}"
                )
        else:
            st.info(vendor)

        request_folder = vendor_card["request_folder"]
        if request_folder.get("required"):
            if vendor_card.get("arrangement_method"):
                st.caption(f"手配方法：{vendor_card['arrangement_method']}")
            st.caption("依頼書PDF格納先：")
            st.markdown(f"[{request_folder['name']} Google Drive を開く]({request_folder['url']})")

        st.markdown("##### 📋 手配方法・連絡先")
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
        contact_phone = st.text_input(
            "日程調整時の連絡先",
            value=form.get("contact_phone", "") or form.get("phone_number", ""),
            key="contact_phone_input",
            placeholder="電話番号（デフォルトはフォームの電話番号）",
        )
        form["contact_phone"] = contact_phone
        st.session_state.form = form

        form["teams_action"] = st.text_input(
            "Teams報告アクション（手入力優先）",
            value=form.get("teams_action", ""),
            placeholder=resolve_teams_request_action(form, vendor, decision["vendor_result"].get("contact_type", "")),
            key="teams_action_input",
        )
        st.session_state.form = form

        caller_type = form.get("counterparty_type") or form.get("caller_type", "加入者")

        # ── 注意内容メモ（備考欄反映）──
        st.markdown("##### 📝 注意内容メモ")
        notes_filled = _fill_template_notes(selected_notes, form)
        generated_texts = _build_after_call_texts(
            form, warranty_result, repair_type, vendor, caller_type, notes_filled,
            decision["vendor_result"].get("contact_type", ""))
        if st.button("🔄 ラクテル用・Teams用テキストを再生成", use_container_width=True):
            form["attention_memo"] = generated_texts["attention_memo"]
            form["rakutel_text"] = generated_texts["rakutel_text"]
            form["teams_chat_message"] = generated_texts["teams_chat_message"]
            st.session_state["memo_after"] = form["attention_memo"]
            st.session_state["rakutel_text_display"] = form["rakutel_text"]
            st.session_state["teams_chat_message_display"] = form["teams_chat_message"]
            st.session_state.form = form

        memo_display = st.text_area(
            "注意内容メモ",
            form.get("attention_memo") or generated_texts["attention_memo"],
            height=260,
            key="memo_after",
        )
        form["attention_memo"] = memo_display

        # ── ラクテル用テキスト ──
        st.markdown("##### 📝 ラクテル用テキスト")
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
        form["call_direction"] = call_direction
        form["counterparty_type"] = counterparty_type
        form["caller_type"] = counterparty_type
        st.session_state.form = form
        rakutel_text_display = st.text_area(
            "ラクテル用テキスト",
            form.get("rakutel_text") or generated_texts["rakutel_text"],
            height=180,
            key="rakutel_text_display",
        )
        form["rakutel_text"] = rakutel_text_display

        # ── Teams報告文 ──
        st.markdown("##### 💬 Teams 報告文")
        rakuteru_val = st.text_input(
            "楽テルNO",
            value=form.get("rakuteru_no", ""),
            key="rakuteru_no_input",
            placeholder="楽テル登録後に入力",
        )
        form["rakuteru_no"] = rakuteru_val
        st.session_state.form = form
        request_folder = get_request_pdf_folder_info(vendor)
        teams_chat_message = st.text_area(
            "Teams報告文",
            form.get("teams_chat_message") or generated_texts["teams_chat_message"],
            height=100,
            key="teams_chat_message_display",
        )
        form["teams_chat_message"] = teams_chat_message
        st.session_state.form = form

        teams_config = load_teams_config()
        teams_enabled = bool(teams_config.get("enabled") and teams_config.get("chat_id"))
        chat_name = teams_config.get("chat_name") or DEFAULT_TEAMS_CONFIG["chat_name"]
        st.caption(f"送信先：{chat_name}")
        st.caption(f"Teams送信：{'有効' if teams_enabled else '無効'}")
        if not teams_config.get("chat_id"):
            st.warning("設定未完了のため送信できません")
        if teams_config.get("error"):
            st.error(teams_config["error"])

        pdf_storage_confirmed = True
        if request_folder.get("required"):
            pdf_storage_confirmed = st.checkbox(
                "依頼書PDFを指定フォルダへ格納しました",
                key="request_pdf_storage_confirmed",
            )
        confirmed = st.checkbox(
            "送信内容と送信先を確認しました",
            key="teams_send_confirmed",
        )
        teams_send_body = _get_teams_send_body(form)
        send_disabled = not _can_send_teams_chat_message(
            teams_enabled, confirmed, form, pdf_storage_confirmed)
        if st.button("Teamsチャットへ送信", disabled=send_disabled, type="primary", use_container_width=True):
            result = send_teams_message_via_powershell(teams_send_body)
            append_teams_send_log(result, teams_send_body, chat_name)
            if result.get("ok"):
                st.success("Teamsチャットへ送信しました")
            else:
                st.error("Teams送信に失敗しました")
            with st.expander("PowerShell実行結果", expanded=not result.get("ok")):
                st.text("stdout")
                st.code(result.get("stdout", "") or "（なし）", language=None)
                st.text("stderr")
                st.code(result.get("stderr", "") or "（なし）", language=None)

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
    st.divider()
    st.markdown("##### 📄 対応履歴テンプレ（コピー用）")
    st.text_area("履歴テンプレ", history_tmpl, height=300, key="history_after")


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
    row = {
        "priority": "10",
        "enabled": "1",
        "product_keyword": st.text_input("製品キーワード product_keyword", value=_candidate_field("repair_type_rule", "product_keyword"), key="master_repair_product_keyword"),
        "manufacturer_keyword": st.text_input("メーカーキーワード manufacturer_keyword", value=_candidate_field("repair_type_rule", "manufacturer_keyword"), key="master_repair_manufacturer_keyword"),
        "model_keyword": st.text_input("型番キーワード model_keyword", value=_candidate_field("repair_type_rule", "model_keyword"), key="master_repair_model_keyword"),
        "condition_keyword": st.text_input("条件キーワード condition_keyword", value=_candidate_field("repair_type_rule", "condition_keyword"), key="master_repair_condition_keyword"),
        "repair_type": st.selectbox("修理形態 repair_type", repair_options, index=repair_index, key="master_repair_type"),
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
    st.info(
        "CSVを編集してStreamlitをリロードすると反映されます。\n"
        "CSV更新後に古い判定が残る場合は、下の「CSVキャッシュをクリア」を押してください。"
    )
    if st.button("CSVキャッシュをクリア", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.success("CSVキャッシュをクリアしました。")
        st.rerun()

    _render_master_candidate_box()

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
        df = load_template_codes()
        if df.empty:
            st.warning("CSVが見つかりません: data/master_template_codes.csv")
        else:
            st.success(f"読み込み済み: {len(df)} 行（有効行）")
            st.dataframe(df, use_container_width=True)
            st.caption("業者送付テンプレートコードと案件区分候補")

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
        df = load_call_lines()
        if df.empty:
            st.warning("CSVが見つかりません: data/master_call_lines.csv")
        else:
            st.success(f"読み込み済み: {len(df)} 行（有効行）")
            st.dataframe(df, use_container_width=True)
            st.caption("入電回線名と回線グループ")

    with master_tabs[7]:
        st.markdown("##### 📄 master_manufacturer_groups.csv")
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
    st.caption("通話中の判断補助ツール — 正式スクリプト本文は先方管理のExcelを参照してください")
    init_session()
    process_pending_case_clear(st.session_state)
    render_global_top_panels(st.session_state.form)
    st.markdown("""
<style>
div[data-baseweb="tab-list"] {
    border-bottom: 2px solid #e0e0e0;
    gap: 4px;
}
button[data-baseweb="tab"] {
    font-size: 1.0em;
    font-weight: 400;
    color: #666;
    padding: 8px 18px;
    border-bottom: 3px solid transparent;
}
button[data-baseweb="tab"][aria-selected="true"] {
    font-weight: 700;
    color: #d6336c;
    background-color: #fff5f7;
    border-bottom: 3px solid #d6336c;
}
button[data-baseweb="tab"]:hover:not([aria-selected="true"]) {
    color: #444;
    background-color: #f5f5f5;
}
</style>
""", unsafe_allow_html=True)
    tab_call, tab_after, tab_master = st.tabs([
        "📞 通話中判定",
        "📋 終話後処理",
        "⚙️ マスタ管理",
    ])
    with tab_call:
        render_tab_call()
    with tab_after:
        render_tab_after_call()
    with tab_master:
        render_tab_master()


if __name__ == "__main__":
    main()
