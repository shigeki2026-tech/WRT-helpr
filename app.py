# -*- coding: utf-8 -*-
"""修理受付 支援ツール MVP - app.py  (Phase2-2: 4-layer CSV decision)"""

import re
import os
import streamlit as st
from datetime import date
import pandas as pd

try:
    import pyperclip
    _PYPERCLIP_AVAILABLE = True
except ImportError:
    _PYPERCLIP_AVAILABLE = False

# ============================================================
# 定数
# ============================================================
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
    "call_type": "入電種別",
    "case_type": "案件区分",
    "appliance_type": "家電/住設",
    "prefecture": "都道府県",
    "address": "お客様住所",
    "product": "製品",
    "product_original": "製品メモ / 原文製品名",
    "series": "シリーズ",
    "manufacturer": "メーカー",
    "manufacturer_original": "メーカー原文 / コピー元メーカー名",
    "model_number": "型番",
    "product_price": "商品価格",
    "warranty_plan": "保証プラン",
    "warranty_start_date": "保証開始日",
    "warranty_end_date": "保証終了日",
    "store_name": "販売店",
    "wrt_no": "WRT-NO",
    "customer_code": "お客様コード",
    "customer_name": "お客様名",
    "phone_number": "電話番号",
    "symptom": "症状",
    "maker_warranty_period": "メーカー保証期間",
    "install_type": "設置形態",
    "extra_condition": "補足条件",
}

# 国内PCメーカー判定グループ
DOMESTIC_PC_MAKERS = {
    "パナソニック", "シャープ", "富士通", "東芝", "日立", "ソニー", "NEC", "VAIO",
}

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
_VENDOR_COLS       = ["priority", "enabled", "case_type", "prefecture", "area_group",
                      "manufacturer_keyword", "product_keyword", "store_keyword",
                      "repair_type", "vendor_name", "reason", "needs_escalation", "notes"]
# legacy
_MASTER_REQUIRED_COLS = [
    "priority", "enabled", "match_target", "keyword",
    "normalized_product", "category", "repair_type", "cost_estimate",
    "script_sheet", "script_part", "can_announce_cost", "data_erase_required", "notes",
]

PRODUCT_OTHER = "その他・要確認"
MANUFACTURER_OTHER = "その他・要確認"
MANUFACTURER_UNKNOWN = "不明"


# ============================================================
# Generic CSV ローダー（キャッシュなし・内部用）
# ============================================================
def _load_csv(filename: str, required_cols: list) -> pd.DataFrame:
    """
    data/<filename> を読み込む。
    - utf-8-sig エンコード
    - enabled=1 の行のみ
    - priority 昇順ソート
    - 失敗時は空 DataFrame を返す（呼び出し元でフォールバック）
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", filename)
    if not os.path.exists(path):
        return pd.DataFrame(columns=required_cols)
    try:
        df = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
    except Exception:
        return pd.DataFrame(columns=required_cols)
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
        "プロジェクター", "ホームシアター",
    ]
    for product in fallback:
        if product not in seen:
            options.append(product)
            seen.add(product)
    if PRODUCT_OTHER not in seen:
        options.append(PRODUCT_OTHER)
    return options


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
        "Dell", "ダイソン", "エレクトロラックス・ジャパン",
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
        "address": (["ご住所", "住所", "お客様住所"], r"([^\t\n]+)"),
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
        "給湯器": "給湯器", "温水便座": "温水便座", "掃除機": "掃除機",
        "炊飯器": "炊飯器", "トースター": "トースター", "ゲーム機": "ゲーム機",
        "テレビ": "テレビ", "タブレット": "タブレット",
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
        "パイオニア": "パイオニア", "PIONEER": "パイオニア",
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
VISIT_REPAIR_PRODUCTS  = {"洗濯機", "冷蔵庫", "エアコン", "給湯器", "温水便座", "食器洗い乾燥機"}
CARRY_IN_REPAIR_PRODUCTS = {
    "ドライヤー", "パソコン", "プリンター", "カーナビ", "ゲーム機",
    "掃除機", "炊飯器", "トースター", "タブレット"
}
CONFIRM_REPAIR_PRODUCTS = {"テレビ", "電子レンジ"}


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
                         keyword: str = "安全ガード") -> dict:
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
        "missing_fields": [],
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

    if product == "エアコン" and (not manufacturer or manufacturer_needs_confirmation):
        return _pending_cost_result(
            "メーカーを確認してください",
            "エアコンはメーカー未確認時に概算費用を案内しない",
            keyword="エアコンメーカー未確認ガード",
        )
    if product == "エアコン" and manufacturer == "ダイキン" and not condition:
        return _pending_cost_result(
            "家庭用/業務用を確認してください",
            "ダイキンエアコンは家庭用/業務用未確認時に概算費用を案内しない",
            keyword="ダイキンエアコン補足条件未確認ガード",
        )
    if product == "パソコン" and (not manufacturer or manufacturer_needs_confirmation):
        return _pending_cost_result(
            "国内メーカー/海外メーカーを確認してください" if manufacturer_needs_confirmation else "メーカーを確認してください",
            "パソコンはメーカー未確認時に概算費用を案内しない",
            keyword="パソコンメーカー未確認ガード",
        )
    return None


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
    - case_type / prefecture は完全一致（空=ワイルドカード）
    - area_group は AREA_GROUPS マッピングで都道府県が含まれるか判定
    - その他フィールドは keyword in target の包含一致
    """
    df = load_vendor_rules()
    case_type    = (form.get("case_type") or "").strip()
    prefecture   = (form.get("prefecture") or "").strip()
    manufacturer = (form.get("manufacturer") or "").strip()
    product      = (form.get("product") or "").strip()
    store        = (form.get("store_name") or "").strip()

    if not df.empty:
        for _, row in df.iterrows():
            ct   = (row.get("case_type") or "").strip()
            pref = (row.get("prefecture") or "").strip()
            ag   = (row.get("area_group") or "").strip()
            mk   = (row.get("manufacturer_keyword") or "").strip()
            pk   = (row.get("product_keyword") or "").strip()
            sk   = (row.get("store_keyword") or "").strip()
            rt   = (row.get("repair_type") or "").strip()

            # case_type: 完全一致（空=ワイルドカード）
            if ct and ct.lower() != case_type.lower():         continue
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

            return {
                "matched":          True,
                "vendor_name":      (row.get("vendor_name") or "担当エスカ（要確認）").strip(),
                "reason":           (row.get("reason") or "").strip(),
                "needs_escalation": str(row.get("needs_escalation", "0")).strip() == "1",
                "keyword":          ct or pref or ag or mk or pk,
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
    case_type    = form.get("case_type", "")
    manufacturer = normalize_manufacturer(form.get("manufacturer", ""))
    extra        = form.get("extra_condition", "")
    if case_type in ["ビックカメラ案件", "ソフマップ案件"]: return "ソフマップ修理センター"
    if "ヤマダオリジナル" in extra:                         return "㈱ヤマダデンキ"
    if prefecture == "沖縄県":                              return "宗建リノベーション"
    if prefecture in {"福岡県","佐賀県","長崎県","熊本県","大分県","宮崎県","鹿児島県"}:
        return "CER候補（担当確認）"
    if prefecture == "滋賀県" and product == "洗濯機":     return "ユナイトサービス㈱"
    if prefecture in {"東京都","神奈川県"} and product == "洗濯機": return "WRT修理センター"
    return "担当エスカ（要確認）"


# ============================================================
# case_type 自動推定（販売店名 → 案件区分）
# ============================================================
def infer_case_type(form: dict) -> str:
    """
    case_type が未入力の場合に、販売店名・運営会社名から自動推定する。
    すでに case_type が設定されていればそのまま返す。
    """
    existing = (form.get("case_type") or "").strip()
    if existing:
        return existing
    store = (form.get("store_name") or "").strip()
    if "ビックカメラ" in store or "ビックカメラ" in store.lower():
        return "ビックカメラ案件"
    if "ビック" in store and "カメラ" in store:
        return "ビックカメラ案件"
    if "ソフマップ" in store:
        return "ソフマップ案件"
    return ""


# ============================================================
# スクリプトルート判定（既存ロジック・削除しない）
# ============================================================
def determine_script_route(form: dict, repair_type: str) -> dict:
    case_type      = form.get("case_type", "")
    appliance_type = form.get("appliance_type", "")
    result = {
        "sheet_name": "", "part": "", "price_guidance_allowed": True,
        "notes": [], "escalation_needed": False, "reason": "",
    }
    if case_type in ["ビックカメラ案件", "ソフマップ案件"]:
        result.update(sheet_name="⑩-1ビックカメラ・ソフマップ", part="案件別受付",
                      price_guidance_allowed=False,
                      notes=["保証対象外時の概算費用・上限金額などの金額案内はしない"],
                      reason="ビックカメラ/ソフマップ案件のため金額案内不可")
        return result
    if case_type == "既築中古":
        result.update(sheet_name="住設【既築／中古のみ】", part="既築・中古住設受付",
                      reason="既築中古案件")
        return result
    if appliance_type == "住設":
        result.update(sheet_name="住設【既築／中古のみ】", part="住設受付", reason="住設製品")
        return result
    if appliance_type == "家電" and repair_type == "出張修理":
        result.update(sheet_name="家電出張・持込・新築住設", part="家電・出張修理",
                      reason="家電＋出張修理")
        return result
    if appliance_type == "家電" and repair_type == "持込修理":
        result.update(sheet_name="家電出張・持込・新築住設", part="家電・持込修理",
                      reason="家電＋持込修理")
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
    else:
        qs = ["製品詳細", "型番", "メーカー", "販売店", "保証内容", "SV/担当確認"]
    if not form.get("model_number"):
        qs.insert(0, "型番の確認（未入力）")
    if not form.get("manufacturer"):
        qs.insert(0, "メーカーの確認（未入力）")
    return qs


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


# ============================================================
# 履歴テンプレ
# ============================================================
def build_history_template(form: dict, repair_type: str, script_result: dict,
                            cost_estimate: str, vendor: str,
                            warranty_result: dict = None) -> str:
    warranty_result = warranty_result or determine_warranty_status(form)
    lines = [
        "■対応履歴",
        f"WRT-NO　　　: {form.get('wrt_no', '未入力')}",
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
        f"参照シート　: {script_result.get('sheet_name', '')}",
        f"該当パート　: {script_result.get('part', '')}",
        f"注意事項　　: {' / '.join(script_result.get('notes', [])) or 'なし'}",
        f"修理拠点候補: {vendor}",
        f"次対応　　　: ",
    ])
    return "\n".join(lines)


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
    # ── 準備: メーカー正規化 + case_type 自動推定 ──
    working_form = form.copy()
    selected_manufacturer = (form.get("manufacturer") or "").strip()
    if selected_manufacturer in (MANUFACTURER_OTHER, MANUFACTURER_UNKNOWN):
        working_form["manufacturer"] = selected_manufacturer
    else:
        working_form["manufacturer"] = normalize_manufacturer(selected_manufacturer)
    inferred_case_type = infer_case_type(working_form)
    if inferred_case_type:
        working_form["case_type"] = inferred_case_type
    area_group = get_area_group(working_form.get("prefecture", ""))
    working_form["area_group"] = area_group
    warranty_result = determine_warranty_status(working_form)

    # ── Layer 1: 製品名エイリアス ──
    alias_result = normalize_product_from_alias(working_form)
    if alias_result["normalized_product"]:
        working_form["product"] = alias_result["normalized_product"]

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

    return {
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
        "inferred_case_type":  inferred_case_type,
        # ── working_form（デバッグ用） ──
        "working_form":        working_form,
    }


# ============================================================
# UI ヘルパー
# ============================================================
def _src_badge(source: str) -> str:
    """判定ソースの小バッジ HTML を返す。"""
    color = "#16a085" if source == "CSVマスタ" else "#7f8c8d"
    return (f'<span style="background:{color};color:white;padding:1px 6px;'
            f'border-radius:3px;font-size:0.75em;margin-left:4px;">{source}</span>')


def empty_form() -> dict:
    form = {k: "" for k in FIELD_LABELS}
    form["genre"] = ""
    form["category"] = ""
    return form


def init_session():
    if "form" not in st.session_state:
        st.session_state.form = empty_form()
    if "extracted" not in st.session_state:
        st.session_state.extracted = {}
    if "pasted_text" not in st.session_state:
        st.session_state.pasted_text = ""


# ============================================================
# タブ1: 通話中判定
# ============================================================
def render_tab_call():
    col_left, col_center, col_right = st.columns([1.2, 1.5, 1.5], gap="medium")

    # ─── 左カラム: コピー情報取り込み ───
    with col_left:
        st.subheader("📋 コピー情報取り込み")

        if _PYPERCLIP_AVAILABLE:
            st.caption("⚠️ クリップボード読み取りはローカルPC起動時のみ有効です")
            if st.button("📋 クリップボードから直接抽出", use_container_width=True):
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
                        st.rerun()
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

        if st.button("🔍 抽出する", use_container_width=True, type="primary"):
            if pasted.strip():
                st.session_state.extracted = extract_fields_from_pasted_text(pasted)
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
                st.success("フォームへ反映しました。")
                st.rerun()

    # ─── 中央カラム: 受付情報フォーム ───
    with col_center:
        st.subheader("📝 受付情報フォーム")
        form = st.session_state.form

        call_type_opts    = ["", "新規入電", "折り返し", "再入電", "その他"]
        case_type_opts    = ["", "通常", "ビックカメラ案件", "ソフマップ案件",
                             "既築中古", "ヤマダオリジナル", "その他"]
        appliance_type_opts = ["", "家電", "住設"]
        pref_opts = [""] + PREFECTURES

        form["call_type"]     = st.selectbox("入電種別", call_type_opts,
            index=call_type_opts.index(form.get("call_type","")) if form.get("call_type") in call_type_opts else 0)
        form["case_type"]     = st.selectbox("案件区分", case_type_opts,
            index=case_type_opts.index(form.get("case_type","")) if form.get("case_type") in case_type_opts else 0)
        form["appliance_type"]= st.selectbox("家電/住設", appliance_type_opts,
            index=appliance_type_opts.index(form.get("appliance_type","")) if form.get("appliance_type") in appliance_type_opts else 0)
        form["prefecture"]    = st.selectbox("都道府県", pref_opts,
            index=pref_opts.index(form.get("prefecture","")) if form.get("prefecture") in pref_opts else 0)
        form["address"]       = st.text_input("お客様住所",   form.get("address",""))
        product_opts = get_product_options()
        current_product = form.get("product", "")
        if current_product and current_product not in product_opts:
            form["product_original"] = form.get("product_original") or current_product
            current_product = PRODUCT_OTHER
        form["product"] = st.selectbox(
            "製品",
            product_opts,
            index=product_opts.index(current_product) if current_product in product_opts else 0,
        )
        form["product_original"] = st.text_input(
            "製品メモ / 原文製品名",
            form.get("product_original",""),
            placeholder="コピー抽出されたシリーズ名・分類名など",
        )
        form["series"]        = st.text_input("シリーズ",     form.get("series",""))
        manufacturer_opts = get_manufacturer_options()
        current_manufacturer = form.get("manufacturer", "")
        if current_manufacturer and current_manufacturer not in manufacturer_opts:
            form["manufacturer_original"] = form.get("manufacturer_original") or current_manufacturer
            current_manufacturer = normalize_manufacturer_for_select(current_manufacturer)
        form["manufacturer"] = st.selectbox(
            "メーカー",
            manufacturer_opts,
            index=manufacturer_opts.index(current_manufacturer) if current_manufacturer in manufacturer_opts else 0,
        )
        form["manufacturer_original"] = st.text_input(
            "メーカー原文 / コピー元メーカー名",
            form.get("manufacturer_original",""),
            placeholder="コピー抽出されたメーカー名など",
        )
        form["model_number"]  = st.text_input("型番",         form.get("model_number",""))
        form["product_price"] = st.text_input("商品価格",     form.get("product_price",""))
        form["warranty_plan"] = st.text_input("保証プラン",   form.get("warranty_plan",""))
        form["warranty_start_date"] = st.text_input("保証開始日", form.get("warranty_start_date",""))
        form["warranty_end_date"]   = st.text_input("保証終了日", form.get("warranty_end_date",""))
        form["store_name"]    = st.text_input("販売店",       form.get("store_name",""))
        form["wrt_no"]        = st.text_input("WRT-NO",       form.get("wrt_no",""))
        form["customer_code"] = st.text_input("お客様コード", form.get("customer_code",""))
        form["customer_name"] = st.text_input("お客様名",     form.get("customer_name",""))
        form["phone_number"]  = st.text_input("電話番号",     form.get("phone_number",""))
        form["symptom"]       = st.text_area("症状",          form.get("symptom",""), height=60)
        form["maker_warranty_period"] = st.text_input("メーカー保証期間", form.get("maker_warranty_period",""))
        form["install_type"]  = st.text_input("設置形態",     form.get("install_type",""))
        form["extra_condition"] = st.text_area(
            "補足条件・費用判定メモ",
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
    decision = run_decision(st.session_state.form)
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
    inferred_case_type  = decision.get("inferred_case_type", "")
    area_group          = decision.get("area_group", "")
    warranty_result     = decision["warranty_result"]
    warranty_status     = warranty_result.get("warranty_status", "unknown")
    warranty_can_accept = warranty_result.get("can_accept", False)

    guidance_text = build_customer_cost_guidance(
        repair_type, cost_estimate, script_result["price_guidance_allowed"])

    # ─── 右カラム: 通話中判定結果 ───
    with col_right:
        st.subheader("⚡ 通話中判定結果")

        # --- 保証期間判定（受付可否の最優先表示） ---
        st.markdown("##### 🛡️ 保証期間判定")
        warranty_color = {
            "ok": "#27ae60",
            "warning": "#f39c12",
            "error": "#c0392b",
        }.get(warranty_result.get("severity"), "#7f8c8d")
        st.markdown(
            f'<div style="background:{warranty_color};color:white;padding:12px 16px;'
            f'border-radius:8px;font-size:1.15em;font-weight:bold;line-height:1.7;">'
            f'{warranty_result.get("title", "保証期間未確認")}<br>'
            f'<span style="font-size:0.9em;font-weight:normal;">{warranty_result.get("message", "")}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if not warranty_result.get("can_accept", False):
            st.error(f"受付可否: 受付不可 / 最優先対応: {build_warranty_guidance(warranty_result)}")
        else:
            st.success("受付可否: 受付判定へ進めます")
        st.divider()

        # --- case_type 自動推定バッジ ---
        if inferred_case_type and not (st.session_state.form.get("case_type") or "").strip():
            st.warning(f"⚠️ 案件区分を自動推定しました: **{inferred_case_type}** （フォームで確認してください）")

        # --- 正規化製品 ---
        if normalized_product:
            st.markdown(
                f'<div style="background:#2c3e50;color:#ecf0f1;padding:6px 14px;'
                f'border-radius:6px;font-size:1.0em;margin-bottom:6px;">'
                f'📦 正規化製品: <b>{normalized_product}</b>'
                + (_src_badge("CSVマスタ") if alias_result["matched"] else _src_badge("既存ロジック"))
                + '</div>',
                unsafe_allow_html=True,
            )
        if st.session_state.form.get("prefecture"):
            st.markdown(
                f'<div style="background:#eef6ff;color:#1f4e79;padding:8px 12px;'
                f'border-radius:6px;margin-bottom:8px;line-height:1.7;">'
                f'<b>都道府県:</b> {st.session_state.form.get("prefecture")}<br>'
                f'<b>エリア:</b> {area_group or "未判定"}</div>',
                unsafe_allow_html=True,
            )

        # --- 参照スクリプト（最重要） ---
        st.markdown("##### 📖 参照スクリプト")
        sheet = script_result["sheet_name"] or "─"
        part  = script_result["part"] or "─"
        st.markdown(
            f'<div style="background:#1e3a5f;color:#fff;padding:12px 16px;'
            f'border-radius:8px;font-size:1.1em;line-height:2.0;">'
            f'<b>シート名:</b> {sheet}<br><b>該当パート:</b> {part}</div>',
            unsafe_allow_html=True,
        )
        st.text_input("シート名コピー用", sheet, key="copy_sheet", label_visibility="collapsed")

        st.divider()

        # --- 修理形態 ---
        repair_color = {"出張修理": "#2ecc71", "持込修理": "#3498db", "要確認": "#e67e22"}
        if not warranty_can_accept:
            repair_color = {"出張修理": "#95a5a6", "持込修理": "#95a5a6", "要確認": "#95a5a6"}
        st.markdown(
            f'##### 🔧 修理形態'
            + (f'<span style="font-size:0.75em;color:#888;margin-left:8px;">({repair_source})</span>'
               if True else ""),
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="background:{repair_color.get(repair_type,"#95a5a6")};'
            f'color:white;padding:8px 14px;border-radius:8px;font-size:1.05em;'
            f'font-weight:bold;text-align:center;">{repair_type}</div>',
            unsafe_allow_html=True,
        )
        if not warranty_can_accept:
            st.caption("保証期間判定が優先です。修理形態は入力確認用の補助表示です。")
        if repair_result.get("needs_confirmation"):
            confirm_note = repair_result.get("notes") or "型番・詳細確認要"
            st.warning(f"⚠️ 要確認理由: {confirm_note}")

        # --- 概算費用（4状態: confirmed / pending / unavailable / escalation）---
        st.markdown("##### 💴 保証対象外時の概算費用")
        if not warranty_can_accept:
            warranty_cost_message = {
                "before_start": "保証開始日前のため、WRT概算案内対象外",
                "expired": "保証期間終了後のため、WRT概算案内対象外",
                "unknown": "保証期間未確認のため、概算費用は補助情報です。先に保証開始日・保証終了日を確認してください。",
            }.get(warranty_status, "保証期間判定を優先してください")
            st.warning(warranty_cost_message)
            if cost_estimate and cost_estimate not in ("未確定", ""):
                st.caption(f"裏側判定の参考概算: {cost_estimate}")
        else:
            # 表示状態を決定
            _disp_status = cost_result.get("cost_status", "confirmed")
            if not script_result.get("price_guidance_allowed", True):
                _disp_status = "unavailable"
            elif cost_result.get("needs_escalation") and _disp_status not in ("pending",):
                _disp_status = "escalation"

            if _disp_status == "unavailable":
                st.error("🚫 金額案内不可 — スクリプト・担当確認に従うこと")
            elif _disp_status == "pending":
                st.warning("🟡 概算費用: 追加確認が必要です（未確定）")
                rq = cost_result.get("required_questions", "").strip()
                if rq:
                    st.markdown(f"**▶ 確認事項:** {rq}")
                note = cost_result.get("internal_note", "").strip()
                if note:
                    st.caption(f"内部メモ: {note}")
            elif _disp_status == "escalation":
                st.markdown(
                    f'<div style="background:#e67e22;color:white;padding:10px 16px;'
                    f'border-radius:8px;font-size:1.4em;font-weight:bold;text-align:center;">'
                    f'{cost_estimate}</div>',
                    unsafe_allow_html=True,
                )
                esc_note = cost_result.get("notes") or "費用が高額のため概算案内に注意"
                st.warning(f"⚠️ 高額エスカ注意: {esc_note}")
            else:  # confirmed
                cost_color = "#c0392b" if cost_estimate in ("要確認", "") else "#27ae60"
                st.markdown(
                    f'<div style="background:{cost_color};color:white;padding:10px 16px;'
                    f'border-radius:8px;font-size:1.4em;font-weight:bold;text-align:center;">'
                    f'{cost_estimate}</div>',
                    unsafe_allow_html=True,
                )
                # eu_asked_only の場合は注記を表示
                if cost_result.get("guidance_scope") == "eu_asked_only":
                    cn = cost_result.get("customer_notice") or "EUから質問があった場合のみ案内"
                    st.caption(f"⚠️ EU質問時のみ案内: {cn}")

            # --- 金額案内可否（unavailableは上で表示済み）---
            if _disp_status != "unavailable":
                if not script_result.get("price_guidance_allowed", True):
                    st.error("🚫 金額案内不可（スクリプト・担当確認に従うこと）")
                elif _disp_status == "confirmed" and cost_estimate not in ("要確認", "未確定", ""):
                    st.success("✅ 金額案内可")

        # --- データ消去同意 ---
        if needs_data_erase:
            st.warning("⚠️ データ消去同意が必要な製品です")

        # --- スクリプトエスカレーション ---
        if script_result["escalation_needed"]:
            st.error("🔺 エスカレーション必要 — SV/担当確認")

        st.divider()

        # --- 注意事項 ---
        st.markdown("##### 📌 注意事項")
        notes = script_result.get("notes", [])
        st.markdown("\n".join(f"- {n}" for n in notes) if notes else "なし")

        st.divider()

        # --- 次に確認する項目 ---
        st.markdown("##### ✅ 次に確認する項目")
        req_questions = build_required_questions(
            st.session_state.form, repair_type, needs_data_erase)
        if warranty_result.get("warranty_status") == "before_start":
            req_questions.insert(0, "メーカー保証期間を確認")
            req_questions.insert(1, "メーカーまたは販売店窓口への誘導")
        elif warranty_result.get("warranty_status") == "unknown":
            req_questions.insert(0, "保証開始日・保証終了日を確認")
        elif warranty_result.get("warranty_status") == "expired":
            req_questions.insert(0, "受付不可。保証期間終了後であることを案内")
        # 費用未確定の場合は確認事項を先頭に追加
        if cost_result.get("cost_status") == "pending":
            cost_rq = cost_result.get("required_questions", "").strip()
            if cost_rq:
                req_questions.insert(0, f"【費用確定のため必須】{cost_rq}")
        for i, q in enumerate(req_questions, 1):
            color = "#c0392b" if ("必須" in q or "未入力" in q) else "inherit"
            st.markdown(f'<span style="color:{color};">{i}. {q}</span>',
                        unsafe_allow_html=True)

        st.divider()

        # --- 修理拠点（終話後へ） ---
        st.markdown("##### 🏭 修理拠点判定")
        if warranty_status == "expired":
            st.warning("受付不可のため手配対象外")
        elif warranty_status in ("before_start", "unknown"):
            st.caption("保証期間判定が優先です。修理拠点は日付確認後に扱ってください。")
        else:
            st.info("終話後処理タブで確定してください。")

        # ─── 判定デバッグ情報 ───
        with st.expander("🔍 判定デバッグ情報（4層）"):
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

    # ─── 下部: 補助文 + 履歴テンプレ ───
    st.divider()
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("##### 💬 お客様への概算案内補助文")
        st.caption("※ 正式スクリプト本文ではありません。概算案内の参考としてのみ使用してください。")
        st.text_area("概算案内補助文", guidance_text, height=110, key="guidance_display")
    with col_b:
        history_tmpl = build_history_template(
            st.session_state.form, repair_type, script_result, cost_estimate, vendor, warranty_result)
        st.markdown("##### 📄 対応履歴テンプレ")
        st.text_area("履歴テンプレ（コピーして使用）", history_tmpl, height=110, key="history_display")


# ============================================================
# タブ2: 終話後処理
# ============================================================
def render_tab_after_call():
    st.subheader("終話後処理")
    form     = st.session_state.form
    decision = run_decision(form)
    repair_type   = decision["repair_type"]
    cost_estimate = decision["cost_estimate"]
    script_result = decision["script_result"]
    vendor        = decision["vendor"]
    warranty_result = decision["warranty_result"]
    history_tmpl  = build_history_template(form, repair_type, script_result, cost_estimate, vendor, warranty_result)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### 🏭 修理拠点候補")
        vr = decision["vendor_result"]
        if vr["matched"]:
            st.info(f"{vendor}\n\n（判定根拠: {vr.get('reason','')}）")
            if vr["needs_escalation"]:
                st.warning("⚠️ 担当エスカレーション推奨")
        else:
            st.info(vendor)
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
        st.markdown("##### 📝 修理依頼票用メモ")
        memo = (
            f"WRT-NO: {form.get('wrt_no','─')}\n"
            f"製品: {form.get('product','─')} / {form.get('manufacturer','─')} {form.get('model_number','─')}\n"
            f"保証期間判定: {warranty_result.get('title','─')}\n"
            f"修理形態: {repair_type}\n"
            f"症状: {form.get('symptom','─')}\n"
            f"拠点候補: {vendor}"
        )
        st.text_area("依頼票メモ", memo, height=120)
        st.markdown("##### 💬 Chatwork/Teams 報告文")
        report = (
            f"【修理受付報告】\n"
            f"WRT-NO: {form.get('wrt_no','─')}\n"
            f"お客様名: {form.get('customer_name','─')}\n"
            f"製品: {form.get('product','─')}（{form.get('manufacturer','─')} {form.get('model_number','─')}）\n"
            f"保証期間判定: {warranty_result.get('title','─')}\n"
            f"修理形態: {repair_type} / 概算: {cost_estimate}\n"
            f"拠点候補: {vendor}\n"
            f"症状: {form.get('symptom','─')}"
        )
        st.text_area("報告文", report, height=140)
    st.divider()
    st.markdown("##### 📄 対応履歴テンプレ（コピー用）")
    st.text_area("履歴テンプレ", history_tmpl, height=300, key="history_after")


# ============================================================
# タブ3: マスタ管理
# ============================================================
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

    master_tabs = st.tabs([
        "製品エイリアス", "修理形態ルール", "概算費用ルール",
        "修理拠点ルール", "メーカーグループ", "エリアグループ", "レガシーマスタ",
    ])

    with master_tabs[0]:
        st.markdown("##### 📄 master_product_alias.csv")
        df = load_alias_csv()
        if df.empty:
            st.warning("CSVが見つかりません: data/master_product_alias.csv")
        else:
            st.success(f"読み込み済み: {len(df)} 行（有効行）")
            st.dataframe(df, use_container_width=True)
            st.caption("keyword → normalized_product へのエイリアス変換ルール")

    with master_tabs[1]:
        st.markdown("##### 📄 master_repair_type_rules.csv")
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

    with master_tabs[5]:
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

    with master_tabs[6]:
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
    tab1, tab2, tab3 = st.tabs(["📞 通話中判定", "📋 終話後処理", "⚙️ マスタ管理"])
    with tab1:
        render_tab_call()
    with tab2:
        render_tab_after_call()
    with tab3:
        render_tab_master()


if __name__ == "__main__":
    main()
