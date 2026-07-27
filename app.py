# -*- coding: utf-8 -*-
# WRT-helpr runtime entrypoint.
#
# The complete application source is preserved in app_source.py. This file
# applies the approved hotfixes before executing that source.

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
    # 外部システム貼り付け用に半角数字だけを返す。
    translated = str(value or "").translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    return re.sub(r"[^0-9]", "", translated)


AFTER_CALL_CLIPBOARD_FIELDS = (
    ("model_number", "型番"),
    ("manufacturer", "メーカー"),
    ("product", "製品"),
    ("product_price", "商品金額"),
)


def build_after_call_field_copy_values(form: dict, decision: dict | None = None) -> dict:
    # 終話後に各フィールドへ貼り付ける値を返す。
    decision = decision or {}
    return {
        "model_number": str(form.get("model_number") or "").strip(),
        "manufacturer": str(form.get("manufacturer") or "").strip(),
        "product": str(decision.get("normalized_product") or form.get("product") or "").strip(),
        "product_price": digits_only(form.get("product_price")),
    }


def build_after_call_clipboard_history_items(
    form: dict,
    decision: dict | None = None,
) -> list[tuple[str, str]]:
    # Windowsクリップボード履歴へ登録する項目を画面表示順で返す。
    values = build_after_call_field_copy_values(form, decision)
    return [
        (label, values[field_name])
        for field_name, label in AFTER_CALL_CLIPBOARD_FIELDS
        if values[field_name]
    ]


def copy_after_call_fields_to_clipboard_history(
    form: dict,
    decision: dict | None = None,
    delay_seconds: float = 0.45,
) -> list[str]:
    # 4項目を別々のWindowsクリップボード履歴として登録する。
    if not _PYPERCLIP_AVAILABLE:
        raise RuntimeError("クリップボード操作が使えません。")

    items = build_after_call_clipboard_history_items(form, decision)
    for _label, value in reversed(items):
        pyperclip.copy(value)
        time.sleep(delay_seconds)
    return [label for label, _value in items]


def sort_diagnostic_items(items: list) -> list:
''',
    "終話後クリップボード履歴ヘルパー追加",
)

_source = _replace_once(
    _source,
    '''    st.session_state.form = form

    # ── 修理依頼書メモ（備考欄反映）──
''',
    '''    st.session_state.form = form

    st.markdown("##### 📋 別システム用クリップボード")
    st.caption(
        "1回の操作で、型番・メーカー・製品・商品金額を別々の履歴として保存します。"
        "別システムでは Windowsキー＋V から各項目を選んで貼り付けてください。"
    )
    copy_values = build_after_call_field_copy_values(form, decision)
    copy_items = build_after_call_clipboard_history_items(form, decision)
    missing_copy_labels = [
        label
        for field_name, label in AFTER_CALL_CLIPBOARD_FIELDS
        if not copy_values[field_name]
    ]
    if not _PYPERCLIP_AVAILABLE:
        st.button(
            "4項目をクリップボード履歴へコピー",
            key="copy_after_call_fields_to_history",
            disabled=True,
            use_container_width=True,
        )
        st.caption("クリップボード操作が使えません。")
    elif st.button(
        "4項目をクリップボード履歴へコピー",
        key="copy_after_call_fields_to_history",
        disabled=not bool(copy_items),
        use_container_width=True,
    ):
        try:
            copied_labels = copy_after_call_fields_to_clipboard_history(form, decision)
            st.success(
                f"{'・'.join(copied_labels)}をそれぞれクリップボード履歴へコピーしました。"
                "Windowsキー＋Vで選択できます。"
            )
            if missing_copy_labels:
                st.warning(f"未入力のためコピーしていない項目：{'・'.join(missing_copy_labels)}")
        except Exception as e:
            st.warning(f"クリップボード履歴へのコピーに失敗しました（{e}）。")

    # ── 修理依頼書メモ（備考欄反映）──
''',
    "終話後クリップボード履歴ボタン追加",
)

exec(compile(_source, str(_SOURCE_PATH), "exec"), globals(), globals())
