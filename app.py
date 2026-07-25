# -*- coding: utf-8 -*-
"""WRT-helpr runtime entrypoint.

The complete application source is preserved in ``app_source.py``. This file
applies the two approved hotfixes before executing that source.
"""

from pathlib import Path


_SOURCE_PATH = Path(__file__).with_name("app_source.py")
_source = _SOURCE_PATH.read_text(encoding="utf-8")


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one source anchor, found {count}")
    return source.replace(old, new, 1)


_source = _replace_once(
    _source,
    '''    if base_type == "住設":
        if phase == "賃貸":
            return "住設（賃貸）"
        if phase in ("新築", "新設"):
            return "住設（新築）"
        if phase in ("", "既築", "中古", "既築/中古"):
            return "住設（既築）"
    return ""
''',
    '''    if base_type == "住設":
        if phase == "賃貸":
            return "住設（賃貸）"
        if phase in ("新築", "新設"):
            return "住設（新築）"
        if phase in ("既築", "中古", "既築/中古"):
            return "住設（既築）"
    return ""
''',
    "案件分類の既築自動選択修正",
)

_source = _replace_once(
    _source,
    '''        except Exception as e:
            st.warning(f"コピーに失敗しました（{e}）。")


def sort_diagnostic_items(items: list) -> list:
''',
    '''        except Exception as e:
            st.warning(f"コピーに失敗しました（{e}）。")


def digits_only(value: str) -> str:
    """外部システム貼り付け用に半角数字だけを返す。"""
    translated = str(value or "").translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    return re.sub(r"[^0-9]", "", translated)


def build_after_call_field_copy_values(form: dict, decision: dict | None = None) -> dict:
    """終話後に各フィールドへ個別貼り付けする値を返す。"""
    decision = decision or {}
    return {
        "model_number": str(form.get("model_number") or "").strip(),
        "manufacturer": str(form.get("manufacturer") or "").strip(),
        "product": str(decision.get("normalized_product") or form.get("product") or "").strip(),
        "product_price": digits_only(form.get("product_price")),
    }


def sort_diagnostic_items(items: list) -> list:
''',
    "終話後コピー値ヘルパー追加",
)

_source = _replace_once(
    _source,
    '''    st.session_state.form = form

    # ── 修理依頼書メモ（備考欄反映）──
''',
    '''    st.session_state.form = form

    st.markdown("##### 📋 別システム貼り付け")
    st.caption("各ボタンは1項目だけをコピーします。商品金額は半角数字のみです。")
    copy_values = build_after_call_field_copy_values(form, decision)
    copy_columns = st.columns(4)
    copy_specs = (
        ("型番をコピー", "model_number", "copy_after_call_model_number"),
        ("メーカーをコピー", "manufacturer", "copy_after_call_manufacturer"),
        ("製品をコピー", "product", "copy_after_call_product"),
        ("商品金額をコピー", "product_price", "copy_after_call_product_price"),
    )
    for column, (label, field_name, key) in zip(copy_columns, copy_specs):
        with column:
            render_copy_button(label, copy_values[field_name], key)

    # ── 修理依頼書メモ（備考欄反映）──
''',
    "終話後個別コピーボタン追加",
)

exec(compile(_source, str(_SOURCE_PATH), "exec"), globals(), globals())
