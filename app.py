# -*- coding: utf-8 -*-
"""修理受付 支援ツール MVP - app.py"""

import re
import streamlit as st
from datetime import date

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
    "series": "シリーズ",
    "manufacturer": "メーカー",
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

# ============================================================
# 1. テキスト抽出
# ============================================================
def extract_fields_from_pasted_text(text: str) -> dict:
    """貼り付けテキストから正規表現で各フィールドを抽出する。"""
    result = {}

    patterns = {
        "operating_company": r"運営会社\s*[\t　](.+?)(?:\t|\n|　|販売店)",
        "store_name":         r"販売店\s*[\t　](.+?)(?:\t|\n|$)",
        "plan":               r"プラン\s*[\t　](.+?)(?:\t|\n|$)",
        "warranty_period":    r"保証期間\s*[\t　]([^\t\n]+)",
        "warranty_start_date":r"保証開始日\s*[\t　]([0-9]{4}/[0-9]{2}/[0-9]{2})",
        "warranty_end_date":  r"保証終了日\s*[\t　]([0-9]{4}/[0-9]{2}/[0-9]{2})",
        "payment_method":     r"支払方法\s*[\t　]([^\t\n]+)",
        "contract_status":    r"ステータス\s*[\t　]([^\t\n]+)",
        "customer_code":      r"お客様コード\s*[\t　]([^\t\n]+)",
        "customer_name":      r"お名前（漢字）\s*[\t　](.+?)(?:\t|\n|お名前)",
        "customer_name_kana": r"お名前（カナ）\s*[\t　]([^\t\n]+)",
        "phone_number":       r"お電話番号\s*[\t　]([0-9\-()（）]+)",
        "postal_code":        r"郵便番号\s*[\t　]([0-9\-]+)",
        "address":            r"ご住所\s*[\t　]([^\t\n]+)",
        "wrt_no":             r"WRT-NO\s*[\t　]([^\t\n]+)",
        "payment_amount":     r"支払金額\s*[\t　]([0-9,]+円)",
        "product_price":      r"商品価格\s*[\t　]([0-9,]+円)",
        "genre":              r"ジャンル\s*[\t　](.+?)(?:\t|\n|　|分類)",
        "category":           r"分類\s*[\t　]([^\t\n]+)",
        "series":             r"シリーズ\s*[\t　](.+?)(?:\t|\n|　|メーカー)",
        "manufacturer":       r"メーカー\s*[\t　]([^\t\n]+)",
        "model_number":       r"型番\s*[\t　]([^\t\n\s]+)",
        "serial_number":      r"製造番号\s*[\t　]([^\t\n]+)",
    }

    for key, pattern in patterns.items():
        m = re.search(pattern, text)
        if m:
            val = m.group(1).strip()
            if val:
                result[key] = val

    # 住所から都道府県抽出
    addr = result.get("address", "")
    if addr:
        result["prefecture"] = extract_prefecture(addr)

    return result


# ============================================================
# 2. 正規化
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
    mapping = {
        "ドライヤー": "ドライヤー",
        "ヘアアイロン": "ドライヤー",
        "ドライヤー・ヘアアイロン": "ドライヤー",
        "洗濯機": "洗濯機",
        "冷蔵庫": "冷蔵庫",
        "エアコン": "エアコン",
        "パソコン": "パソコン",
        "PC": "パソコン",
        "プリンター": "プリンター",
        "カーナビ": "カーナビ",
        "電子レンジ": "電子レンジ",
        "食器洗い乾燥機": "食器洗い乾燥機",
        "食洗機": "食器洗い乾燥機",
        "給湯器": "給湯器",
        "温水便座": "温水便座",
        "掃除機": "掃除機",
        "炊飯器": "炊飯器",
        "トースター": "トースター",
        "ゲーム機": "ゲーム機",
        "テレビ": "テレビ",
        "タブレット": "タブレット",
        "ブルーレイレコーダー": "ブルーレイレコーダー",
        "DVDレコーダー": "DVDレコーダー",
        "ドアホン": "ドアホン",
        "ドライブレコーダー": "ドライブレコーダー",
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
        "パナソニック": "パナソニック",
        "Panasonic": "パナソニック",
        "ダイキン": "ダイキン",
        "DAIKIN": "ダイキン",
        "アイリスオーヤマ": "アイリスオーヤマ",
        "エレクトロラックス": "エレクトロラックス・ジャパン",
        "ダイソン": "ダイソン",
        "Dyson": "ダイソン",
        "シャープ": "シャープ",
        "SHARP": "シャープ",
        "日立": "日立",
        "東芝": "東芝",
        "三菱": "三菱",
        "富士通": "富士通",
        "ソニー": "ソニー",
        "SONY": "ソニー",
        "ヤマダ": "ヤマダ",
    }
    for k, v in mapping.items():
        if k.lower() in (manufacturer or "").lower():
            return v
    return manufacturer or ""


def apply_extracted_fields_to_form(extracted: dict, current_form: dict) -> dict:
    """抽出結果をフォーム辞書にマッピングして返す。"""
    mapping = {
        "plan":               "warranty_plan",
        "warranty_start_date":"warranty_start_date",
        "warranty_end_date":  "warranty_end_date",
        "customer_code":      "customer_code",
        "customer_name":      "customer_name",
        "phone_number":       "phone_number",
        "address":            "address",
        "prefecture":         "prefecture",
        "wrt_no":             "wrt_no",
        "product_price":      "product_price",
        "manufacturer":       "manufacturer",
        "model_number":       "model_number",
        "series":             "series",
        "store_name":         "store_name",
    }
    form = current_form.copy()
    for src, dst in mapping.items():
        if src in extracted and extracted[src]:
            form[dst] = extracted[src]

    # 製品正規化
    raw_series = extracted.get("series", "")
    if raw_series:
        form["product"] = normalize_product(raw_series, "")

    # メーカー正規化
    raw_mfr = extracted.get("manufacturer", "")
    if raw_mfr:
        form["manufacturer"] = normalize_manufacturer(raw_mfr)

    # 家電/住設 自動判定
    genre = extracted.get("genre", "")
    if genre:
        if any(x in genre for x in ["住設", "給湯", "温水", "ビルトイン"]):
            form["appliance_type"] = "住設"
        else:
            form["appliance_type"] = "家電"

    return form


# ============================================================
# 3. 修理形態判定
# ============================================================
VISIT_REPAIR_PRODUCTS = {
    "洗濯機", "冷蔵庫", "エアコン", "給湯器", "温水便座", "食器洗い乾燥機"
}
CARRY_IN_REPAIR_PRODUCTS = {
    "ドライヤー", "パソコン", "プリンター", "カーナビ", "ゲーム機",
    "掃除機", "炊飯器", "トースター", "タブレット"
}
CONFIRM_REPAIR_PRODUCTS = {"テレビ", "電子レンジ"}


def determine_repair_type(form: dict) -> str:
    product = form.get("product", "")
    if product in VISIT_REPAIR_PRODUCTS:
        return "出張修理"
    if product in CARRY_IN_REPAIR_PRODUCTS:
        return "持込修理"
    if product in CONFIRM_REPAIR_PRODUCTS:
        return "要確認"
    if form.get("appliance_type") == "住設":
        return "出張修理"
    return "要確認"


# ============================================================
# 4. 概算費用判定
# ============================================================
def determine_cost_estimate(form: dict, repair_type: str) -> str:
    product = form.get("product", "")
    manufacturer = normalize_manufacturer(form.get("manufacturer", ""))

    if repair_type == "要確認":
        return "要確認"

    # メーカー×製品 特殊ルール
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

    if manufacturer == "ダイソン" and product == "掃除機":
        return "10,000円前後"

    if product == "パソコン":
        domestic = {"パナソニック", "シャープ", "富士通", "東芝", "日立", "ソニー"}
        if manufacturer in domestic:
            return "2,000円～9,000円"
        return "12,000円前後"

    if repair_type == "出張修理":
        return "5,000円～7,000円前後"
    if repair_type == "持込修理":
        return "2,000円～5,000円前後"

    return "要確認"


# ============================================================
# 5. スクリプトルート判定
# ============================================================
def determine_script_route(form: dict, repair_type: str) -> dict:
    case_type = form.get("case_type", "")
    appliance_type = form.get("appliance_type", "")
    result = {
        "sheet_name": "",
        "part": "",
        "price_guidance_allowed": True,
        "notes": [],
        "escalation_needed": False,
        "reason": "",
    }

    # ルール1: ビックカメラ・ソフマップ
    if case_type in ["ビックカメラ案件", "ソフマップ案件"]:
        result["sheet_name"] = "⑩-1ビックカメラ・ソフマップ"
        result["part"] = "案件別受付"
        result["price_guidance_allowed"] = False
        result["notes"].append("保証対象外時の概算費用・上限金額などの金額案内はしない")
        result["reason"] = "ビックカメラ/ソフマップ案件のため金額案内不可"
        return result

    # ルール2: 既築中古
    if case_type == "既築中古":
        result["sheet_name"] = "住設【既築／中古のみ】"
        result["part"] = "既築・中古住設受付"
        result["reason"] = "既築中古案件"
        return result

    # ルール3: 住設
    if appliance_type == "住設":
        result["sheet_name"] = "住設【既築／中古のみ】"
        result["part"] = "住設受付"
        result["reason"] = "住設製品"
        return result

    # ルール4: 家電×出張
    if appliance_type == "家電" and repair_type == "出張修理":
        result["sheet_name"] = "家電出張・持込・新築住設"
        result["part"] = "家電・出張修理"
        result["reason"] = "家電＋出張修理"
        return result

    # ルール5: 家電×持込
    if appliance_type == "家電" and repair_type == "持込修理":
        result["sheet_name"] = "家電出張・持込・新築住設"
        result["part"] = "家電・持込修理"
        result["reason"] = "家電＋持込修理"
        return result

    # ルール6: 不明
    result["sheet_name"] = "要確認"
    result["part"] = "SV/担当確認"
    result["escalation_needed"] = True
    result["reason"] = "家電/住設区分または修理形態が未確定"
    return result


# ============================================================
# 6. データ消去同意判定
# ============================================================
DATA_ERASE_PRODUCTS = {
    "パソコン", "タブレット", "プリンター", "カーナビ",
    "ドライブレコーダー", "ブルーレイレコーダー", "DVDレコーダー",
    "ドアホン", "ゲーム機",
}


def determine_data_erase_consent(form: dict) -> bool:
    return form.get("product", "") in DATA_ERASE_PRODUCTS


# ============================================================
# 7. 確認項目ビルダー
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

    # 型番・メーカー未入力の場合は追加
    if not form.get("model_number"):
        qs.insert(0, "型番の確認（未入力）")
    if not form.get("manufacturer"):
        qs.insert(0, "メーカーの確認（未入力）")

    return qs


# ============================================================
# 8. 概算案内補助文
# ============================================================
def build_customer_cost_guidance(repair_type: str, cost_estimate: str,
                                  price_guidance_allowed: bool) -> str:
    if not price_guidance_allowed:
        return (
            "【金額案内不可】\n"
            "こちらの案件は金額案内を行わず、正式スクリプトおよび担当確認に従って案内してください。"
        )
    if repair_type == "出張修理":
        return (
            f"保証対象外の場合、訪問費用および故障検証費用として、概算で {cost_estimate} かかる可能性がございます。\n"
            "実際の金額は、メーカー・製品・設置状況・診断内容・地域により前後いたします。"
        )
    if repair_type == "持込修理":
        return (
            f"保証対象外の場合、故障検証費用・返送費用等として、概算で {cost_estimate} かかる可能性がございます。\n"
            "実際の金額は、メーカー・製品・診断内容により前後いたします。"
        )
    return (
        "恐れ入りますが、こちらの商品は確認が必要な内容となります。\n"
        "修理受付可否および概算費用を確認のうえ、ご案内いたします。"
    )


# ============================================================
# 9. 修理拠点候補
# ============================================================
def determine_vendor_candidate(form: dict) -> str:
    prefecture = form.get("prefecture", "")
    product = form.get("product", "")
    case_type = form.get("case_type", "")
    manufacturer = normalize_manufacturer(form.get("manufacturer", ""))
    extra = form.get("extra_condition", "")

    if case_type in ["ビックカメラ案件", "ソフマップ案件"]:
        return "ソフマップ修理センター"
    if "ヤマダオリジナル" in extra:
        return "㈱ヤマダデンキ"
    if prefecture == "沖縄県":
        return "宗建リノベーション"
    if prefecture in {"福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県"}:
        return "CER候補（担当確認）"
    if prefecture == "滋賀県" and product == "洗濯機":
        return "ユナイトサービス㈱"
    if prefecture in {"東京都", "神奈川県"} and product == "洗濯機":
        return "WRT修理センター"
    return "担当エスカ（要確認）"


# ============================================================
# 10. 履歴テンプレ
# ============================================================
def build_history_template(form: dict, repair_type: str, result: dict,
                            cost_estimate: str, vendor: str) -> str:
    lines = [
        "■対応履歴",
        f"WRT-NO　　　: {form.get('wrt_no', '未入力')}",
        f"お客様コード: {form.get('customer_code', '未入力')}",
        f"お客様名　　: {form.get('customer_name', '未入力')}",
        f"電話番号　　: {form.get('phone_number', '未入力')}",
        f"住所　　　　: {form.get('address', '未入力')}",
        f"製品　　　　: {form.get('product', '未入力')}",
        f"メーカー　　: {form.get('manufacturer', '未入力')}",
        f"型番　　　　: {form.get('model_number', '未入力')}",
        f"商品価格　　: {form.get('product_price', '未入力')}",
        f"保証プラン　: {form.get('warranty_plan', '未入力')}",
        f"保証開始日　: {form.get('warranty_start_date', '未入力')}",
        f"保証終了日　: {form.get('warranty_end_date', '未入力')}",
        f"症状　　　　: {form.get('symptom', '未入力')}",
        f"家電/住設　 : {form.get('appliance_type', '未入力')}",
        f"修理形態　　: {repair_type}",
        f"保証外概算　: {cost_estimate}",
        f"参照シート　: {result.get('sheet_name', '')}",
        f"該当パート　: {result.get('part', '')}",
        f"注意事項　　: {' / '.join(result.get('notes', [])) or 'なし'}",
        f"修理拠点候補: {vendor}",
        f"次対応　　　: ",
    ]
    return "\n".join(lines)


# ============================================================
# UI ヘルパー
# ============================================================
def label_badge(label: str, value: str, color: str = "#1f77b4") -> str:
    return (
        f'<span style="background:{color};color:white;padding:2px 8px;'
        f'border-radius:4px;font-size:0.85em;margin-right:4px;">{label}</span>'
        f'<strong>{value}</strong>'
    )


def empty_form() -> dict:
    return {k: "" for k in FIELD_LABELS}


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
        pasted = st.text_area(
            "保証画面などのテキストを貼り付け",
            value=st.session_state.pasted_text,
            height=220,
            key="paste_area",
            placeholder="ここにコピーしたテキストを貼り付けてください...",
        )
        st.session_state.pasted_text = pasted

        if st.button("🔍 抽出する", use_container_width=True, type="primary"):
            if pasted.strip():
                extracted = extract_fields_from_pasted_text(pasted)
                st.session_state.extracted = extracted
            else:
                st.warning("テキストを貼り付けてください。")

        # 抽出結果表示
        if st.session_state.extracted:
            st.markdown("**抽出結果**")
            ext = st.session_state.extracted
            rows = []
            label_map = {
                "plan": "保証プラン", "warranty_start_date": "保証開始日",
                "warranty_end_date": "保証終了日", "customer_code": "お客様コード",
                "customer_name": "お客様名", "phone_number": "電話番号",
                "address": "住所", "prefecture": "都道府県",
                "wrt_no": "WRT-NO", "product_price": "商品価格",
                "manufacturer": "メーカー", "model_number": "型番",
                "series": "シリーズ", "store_name": "販売店",
            }
            for k, lbl in label_map.items():
                val = ext.get(k, "")
                rows.append(f"- **{lbl}**: {val if val else '─'}")
            st.markdown("\n".join(rows))

            if st.button("📥 フォームへ反映", use_container_width=True):
                st.session_state.form = apply_extracted_fields_to_form(
                    st.session_state.extracted, st.session_state.form
                )
                st.success("フォームへ反映しました。")
                st.rerun()

    # ─── 中央カラム: 受付情報フォーム ───
    with col_center:
        st.subheader("📝 受付情報フォーム")
        form = st.session_state.form

        call_type_opts = ["", "新規入電", "折り返し", "再入電", "その他"]
        case_type_opts = ["", "通常", "ビックカメラ案件", "ソフマップ案件",
                          "既築中古", "ヤマダオリジナル", "その他"]
        appliance_type_opts = ["", "家電", "住設"]

        form["call_type"] = st.selectbox("入電種別", call_type_opts,
            index=call_type_opts.index(form.get("call_type", "")) if form.get("call_type") in call_type_opts else 0)
        form["case_type"] = st.selectbox("案件区分", case_type_opts,
            index=case_type_opts.index(form.get("case_type", "")) if form.get("case_type") in case_type_opts else 0)
        form["appliance_type"] = st.selectbox("家電/住設", appliance_type_opts,
            index=appliance_type_opts.index(form.get("appliance_type", "")) if form.get("appliance_type") in appliance_type_opts else 0)

        pref_opts = [""] + PREFECTURES
        form["prefecture"] = st.selectbox("都道府県", pref_opts,
            index=pref_opts.index(form.get("prefecture", "")) if form.get("prefecture") in pref_opts else 0)

        form["address"]           = st.text_input("お客様住所",         form.get("address", ""))
        form["product"]           = st.text_input("製品",               form.get("product", ""), placeholder="例: 洗濯機")
        form["series"]            = st.text_input("シリーズ",           form.get("series", ""))
        form["manufacturer"]      = st.text_input("メーカー",           form.get("manufacturer", ""))
        form["model_number"]      = st.text_input("型番",               form.get("model_number", ""))
        form["product_price"]     = st.text_input("商品価格",           form.get("product_price", ""))
        form["warranty_plan"]     = st.text_input("保証プラン",         form.get("warranty_plan", ""))
        form["warranty_start_date"] = st.text_input("保証開始日",       form.get("warranty_start_date", ""))
        form["warranty_end_date"]   = st.text_input("保証終了日",       form.get("warranty_end_date", ""))
        form["store_name"]        = st.text_input("販売店",             form.get("store_name", ""))
        form["wrt_no"]            = st.text_input("WRT-NO",             form.get("wrt_no", ""))
        form["customer_code"]     = st.text_input("お客様コード",       form.get("customer_code", ""))
        form["customer_name"]     = st.text_input("お客様名",           form.get("customer_name", ""))
        form["phone_number"]      = st.text_input("電話番号",           form.get("phone_number", ""))
        form["symptom"]           = st.text_area("症状",                form.get("symptom", ""), height=60)
        form["maker_warranty_period"] = st.text_input("メーカー保証期間", form.get("maker_warranty_period", ""))
        form["install_type"]      = st.text_input("設置形態",           form.get("install_type", ""))
        form["extra_condition"]   = st.text_input("補足条件",           form.get("extra_condition", ""))

        st.session_state.form = form

    # ─── 右カラム: 通話中判定結果 ───
    with col_right:
        st.subheader("⚡ 通話中判定結果")
        form = st.session_state.form

        repair_type   = determine_repair_type(form)
        cost_estimate = determine_cost_estimate(form, repair_type)
        script_result = determine_script_route(form, repair_type)
        needs_data_erase = determine_data_erase_consent(form)
        req_questions = build_required_questions(form, repair_type, needs_data_erase)
        guidance_text = build_customer_cost_guidance(
            repair_type, cost_estimate, script_result["price_guidance_allowed"]
        )

        # --- スクリプト参照 (最重要) ---
        st.markdown("##### 📖 参照スクリプト")
        sheet = script_result["sheet_name"] or "─"
        part  = script_result["part"] or "─"
        st.markdown(
            f"""<div style="background:#1e3a5f;color:#fff;padding:12px 16px;
            border-radius:8px;font-size:1.1em;line-height:2;">
            <b>シート名:</b> {sheet}<br>
            <b>該当パート:</b> {part}
            </div>""",
            unsafe_allow_html=True,
        )
        st.text_input("シート名コピー用", sheet, key="copy_sheet", label_visibility="collapsed")

        st.divider()

        # --- 修理形態 ---
        repair_color = {"出張修理": "#2ecc71", "持込修理": "#3498db", "要確認": "#e67e22"}
        st.markdown("##### 🔧 修理形態")
        st.markdown(
            f'<div style="background:{repair_color.get(repair_type,"#95a5a6")};'
            f'color:white;padding:10px 16px;border-radius:8px;font-size:1.3em;'
            f'font-weight:bold;text-align:center;">{repair_type}</div>',
            unsafe_allow_html=True,
        )

        # --- 概算費用 ---
        st.markdown("##### 💴 保証対象外時の概算費用")
        cost_color = "#c0392b" if cost_estimate == "要確認" else "#27ae60"
        st.markdown(
            f'<div style="background:{cost_color};color:white;padding:10px 16px;'
            f'border-radius:8px;font-size:1.4em;font-weight:bold;text-align:center;">'
            f'{cost_estimate}</div>',
            unsafe_allow_html=True,
        )

        # --- 金額案内可否 ---
        if not script_result["price_guidance_allowed"]:
            st.error("🚫 金額案内不可（スクリプト・担当確認に従うこと）")
        else:
            st.success("✅ 金額案内可")

        # --- データ消去同意 ---
        if needs_data_erase:
            st.warning("⚠️ データ消去同意が必要な製品です")

        # --- エスカレーション ---
        if script_result["escalation_needed"]:
            st.error("🔺 エスカレーション必要 — SV/担当確認")

        st.divider()

        # --- 判定理由・注意事項 ---
        st.markdown("##### 📌 注意事項")
        notes = script_result.get("notes", [])
        if notes:
            for n in notes:
                st.markdown(f"- {n}")
        else:
            st.markdown("なし")

        st.markdown(f"*判定根拠: {script_result.get('reason', '─')}*")

        st.divider()

        # --- 次に確認する項目 ---
        st.markdown("##### ✅ 次に確認する項目")
        for i, q in enumerate(req_questions, 1):
            color = "#c0392b" if "必須" in q or "未入力" in q else "inherit"
            st.markdown(
                f'<span style="color:{color};">{i}. {q}</span>',
                unsafe_allow_html=True,
            )

        st.divider()

        # --- 修理拠点判定 ---
        st.markdown("##### 🏭 修理拠点判定")
        st.info("終話後処理タブで確定してください。")

    # ─── 下部: 補助文 + 履歴テンプレ ───
    st.divider()
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("##### 💬 お客様への概算案内補助文")
        st.caption("※ 正式スクリプト本文ではありません。概算案内の参考としてのみ使用してください。")
        st.text_area("概算案内補助文", guidance_text, height=110, key="guidance_display")

    with col_b:
        form = st.session_state.form
        repair_type   = determine_repair_type(form)
        cost_estimate = determine_cost_estimate(form, repair_type)
        script_result = determine_script_route(form, repair_type)
        vendor        = determine_vendor_candidate(form)
        history_tmpl  = build_history_template(form, repair_type, script_result,
                                               cost_estimate, vendor)
        st.markdown("##### 📄 対応履歴テンプレ")
        st.text_area("履歴テンプレ（コピーして使用）", history_tmpl, height=110, key="history_display")


# ============================================================
# タブ2: 終話後処理
# ============================================================
def render_tab_after_call():
    st.subheader("終話後処理")
    form = st.session_state.form
    repair_type   = determine_repair_type(form)
    cost_estimate = determine_cost_estimate(form, repair_type)
    script_result = determine_script_route(form, repair_type)
    vendor        = determine_vendor_candidate(form)
    history_tmpl  = build_history_template(form, repair_type, script_result,
                                           cost_estimate, vendor)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### 🏭 修理拠点候補")
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
    st.subheader("マスタ管理")
    st.info(
        "現在はダミーデータで動作しています。\n"
        "CSVファイルを配置することで、製品マスタ・概算費用マスタ・スクリプトルートマスタを差し替えられます。"
    )

    st.markdown("##### 製品マスタ（ダミー）")
    import pandas as pd
    df_product = pd.DataFrame({
        "シリーズ": ["ドライヤー・ヘアアイロン", "洗濯機", "冷蔵庫", "エアコン",
                   "パソコン", "プリンター", "カーナビ", "電子レンジ",
                   "食器洗い乾燥機", "給湯器", "温水便座"],
        "正規化製品名": ["ドライヤー", "洗濯機", "冷蔵庫", "エアコン",
                      "パソコン", "プリンター", "カーナビ", "電子レンジ",
                      "食器洗い乾燥機", "給湯器", "温水便座"],
        "修理形態": ["持込修理", "出張修理", "出張修理", "出張修理",
                  "持込修理", "持込修理", "持込修理", "要確認",
                  "出張修理", "出張修理", "出張修理"],
        "データ消去": ["×", "×", "×", "×", "○", "○", "○", "×", "×", "×", "×"],
    })
    st.dataframe(df_product, use_container_width=True)

    st.markdown("##### 概算費用マスタ（ダミー）")
    df_cost = pd.DataFrame({
        "条件": ["出張修理（一般）", "持込修理（一般）", "ダイキン家庭用エアコン",
                "ダイキン業務用エアコン", "アイリスオーヤマ出張", "エレクトロラックス洗濯機等",
                "エレクトロラックスIH", "ダイソン掃除機", "パソコン国内", "パソコン海外"],
        "概算費用": ["5,000円～7,000円前後", "2,000円～5,000円前後", "7,000円～16,000円前後",
                  "15,000円～22,000円前後", "15,000円前後", "45,000円前後",
                  "25,000円～30,000円前後", "10,000円前後", "2,000円～9,000円", "12,000円前後"],
    })
    st.dataframe(df_cost, use_container_width=True)

    st.markdown("##### スクリプトルートマスタ（ダミー）")
    df_script = pd.DataFrame({
        "条件": ["ビックカメラ/ソフマップ案件", "既築中古", "住設", "家電×出張修理",
                "家電×持込修理", "不明"],
        "シート名": ["⑩-1ビックカメラ・ソフマップ", "住設【既築／中古のみ】",
                   "住設【既築／中古のみ】", "家電出張・持込・新築住設",
                   "家電出張・持込・新築住設", "要確認"],
        "該当パート": ["案件別受付", "既築・中古住設受付", "住設受付",
                    "家電・出張修理", "家電・持込修理", "SV/担当確認"],
        "金額案内": ["不可", "可", "可", "可", "可", "─"],
    })
    st.dataframe(df_script, use_container_width=True)

    st.caption("※ CSV差し替え機能は次フェーズで実装予定。")


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
