# -*- coding: utf-8 -*-
"""
tests/test_decision_rules.py
4-layer CSV pipeline decision tests.

Run with:
    cd <project-root>
    python -m pytest tests/test_decision_rules.py -v

Or standalone:
    python tests/test_decision_rules.py
"""

import sys
import os

# プロジェクトルートを sys.path に追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Streamlit の st.cache_data をモック化してインポートを通す
import unittest.mock as mock

# st モジュール全体をモック
st_mock = mock.MagicMock()
st_mock.cache_data = lambda f: f          # デコレータを素通りさせる
sys.modules["streamlit"] = st_mock

import app  # noqa: E402

# ============================================================
# ヘルパー: run_decision 用フォームビルダー
# ============================================================

def make_form(
    product="", series="", manufacturer="", model_number="",
    prefecture="", case_type="", appliance_type="",
    extra_condition="", store_name="",
):
    form = app.empty_form()
    form.update(
        product=product,
        series=series,
        manufacturer=manufacturer,
        model_number=model_number,
        prefecture=prefecture,
        case_type=case_type,
        appliance_type=appliance_type,
        extra_condition=extra_condition,
        store_name=store_name,
    )
    return form


# ============================================================
# テストケース
# ============================================================

PASS = "PASS"
FAIL = "FAIL"
results = []


def check(label: str, actual, expected, *, contains: bool = False):
    """テスト結果を評価してリストに記録する。"""
    if contains:
        ok = expected in str(actual)
    else:
        ok = actual == expected
    status = PASS if ok else FAIL
    results.append((status, label, actual, expected))
    return ok


# ──────────────────────────────────────────────
# TC01: ドライヤー・ヘアアイロン → エイリアス正規化
# ──────────────────────────────────────────────
def test_tc01_dryer_alias():
    d = app.run_decision(make_form(series="ドライヤー・ヘアアイロン"))
    check("TC01 製品正規化 → ドライヤー",       d["normalized_product"], "ドライヤー")
    check("TC01 修理形態 → 持込修理",           d["repair_type"],        "持込修理")
    check("TC01 概算費用 → 2,000円～5,000円前後", d["cost_estimate"],      "2,000円～5,000円前後")


# ──────────────────────────────────────────────
# TC02: 洗濯機 → 出張修理
# ──────────────────────────────────────────────
def test_tc02_washer():
    d = app.run_decision(make_form(product="洗濯機"))
    check("TC02 修理形態 → 出張修理",           d["repair_type"],   "出張修理")
    check("TC02 概算費用 → 5,000円～7,000円前後", d["cost_estimate"], "5,000円～7,000円前後")


# ──────────────────────────────────────────────
# TC03: エレクトロラックス × 洗濯機 → 45,000円前後・escalation あり
# ──────────────────────────────────────────────
def test_tc03_electrolux_washer():
    d = app.run_decision(make_form(product="洗濯機", manufacturer="エレクトロラックス"))
    check("TC03 修理形態 → 出張修理",           d["repair_type"],                  "出張修理")
    check("TC03 概算費用 → 45,000円前後",       d["cost_estimate"],                "45,000円前後")
    check("TC03 escalation あり",               d["cost_result"]["needs_escalation"], True)


# ──────────────────────────────────────────────
# TC04: ダイキン家庭用エアコン → 出張修理 / 7,000円～16,000円前後
# ──────────────────────────────────────────────
def test_tc04_daikin_ac():
    d = app.run_decision(make_form(product="エアコン", manufacturer="ダイキン"))
    check("TC04 修理形態 → 出張修理",              d["repair_type"],   "出張修理")
    check("TC04 概算費用 → 7,000円～16,000円前後",  d["cost_estimate"], "7,000円～16,000円前後")


# ──────────────────────────────────────────────
# TC05: パソコン × 国内メーカー（富士通）→ 2,000円～9,000円
# ──────────────────────────────────────────────
def test_tc05_domestic_pc():
    d = app.run_decision(make_form(product="パソコン", manufacturer="富士通"))
    check("TC05 修理形態 → 持込修理",           d["repair_type"],   "持込修理")
    check("TC05 概算費用 → 2,000円～9,000円",    d["cost_estimate"], "2,000円～9,000円")


# ──────────────────────────────────────────────
# TC06: パソコン × 海外メーカー → 12,000円前後
# ──────────────────────────────────────────────
def test_tc06_foreign_pc():
    d = app.run_decision(make_form(product="パソコン", manufacturer="Dell"))
    check("TC06 修理形態 → 持込修理",       d["repair_type"],   "持込修理")
    check("TC06 概算費用 → 12,000円前後",   d["cost_estimate"], "12,000円前後")


# ──────────────────────────────────────────────
# TC07: 滋賀県 × 洗濯機 → ユナイトサービス㈱
# ──────────────────────────────────────────────
def test_tc07_shiga_washer():
    d = app.run_decision(make_form(product="洗濯機", prefecture="滋賀県"))
    check("TC07 修理拠点 → ユナイトサービス㈱", d["vendor"], "ユナイトサービス㈱")


# ──────────────────────────────────────────────
# TC08: 東京都 × 洗濯機 → WRT修理センター
# ──────────────────────────────────────────────
def test_tc08_tokyo_washer():
    d = app.run_decision(make_form(product="洗濯機", prefecture="東京都"))
    check("TC08 修理拠点 → WRT修理センター", d["vendor"], "WRT修理センター")


# ──────────────────────────────────────────────
# TC09: 沖縄県 → 宗建リノベーション
# ──────────────────────────────────────────────
def test_tc09_okinawa():
    d = app.run_decision(make_form(prefecture="沖縄県"))
    check("TC09 修理拠点 → 宗建リノベーション", d["vendor"], "宗建リノベーション")


# ──────────────────────────────────────────────
# TC10: ビックカメラ案件 → ソフマップ修理センター / 金額案内不可
# ──────────────────────────────────────────────
def test_tc10_bic_camera():
    d = app.run_decision(make_form(case_type="ビックカメラ案件"))
    check("TC10 修理拠点 → ソフマップ修理センター", d["vendor"], "ソフマップ修理センター")
    check("TC10 金額案内不可",
          d["script_result"]["price_guidance_allowed"], False)


# ============================================================
# テスト実行
# ============================================================

if __name__ == "__main__":
    test_tc01_dryer_alias()
    test_tc02_washer()
    test_tc03_electrolux_washer()
    test_tc04_daikin_ac()
    test_tc05_domestic_pc()
    test_tc06_foreign_pc()
    test_tc07_shiga_washer()
    test_tc08_tokyo_washer()
    test_tc09_okinawa()
    test_tc10_bic_camera()

    # ── サマリ ──
    total  = len(results)
    passed = sum(1 for r in results if r[0] == PASS)
    failed = total - passed
    print(f"\n{'='*60}")
    print(f"テスト結果: {passed}/{total} PASS  ({failed} FAIL)")
    print(f"{'='*60}")
    for status, label, actual, expected in results:
        mark = "OK" if status == PASS else "NG"
        print(f"  [{mark}] {label}")
        if status == FAIL:
            print(f"       期待: {expected!r}")
            print(f"       実際: {actual!r}")
    print()
    if failed:
        sys.exit(1)


# ============================================================
# pytest 互換
# ============================================================

class TestDecisionRules:
    def test_tc01(self): test_tc01_dryer_alias()
    def test_tc02(self): test_tc02_washer()
    def test_tc03(self): test_tc03_electrolux_washer()
    def test_tc04(self): test_tc04_daikin_ac()
    def test_tc05(self): test_tc05_domestic_pc()
    def test_tc06(self): test_tc06_foreign_pc()
    def test_tc07(self): test_tc07_shiga_washer()
    def test_tc08(self): test_tc08_tokyo_washer()
    def test_tc09(self): test_tc09_okinawa()
    def test_tc10(self): test_tc10_bic_camera()
