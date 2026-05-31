from pathlib import Path

import app


ROOT = Path(__file__).resolve().parents[1]


def _source() -> str:
    return (ROOT / "app.py").read_text(encoding="utf-8")


def _function_source(source: str, name: str) -> str:
    start = source.index(f"def {name}(")
    end = source.find("\ndef ", start + 1)
    return source[start:end if end != -1 else len(source)]


def test_inject_app_styles_exists_and_is_called_early():
    source = _source()
    main_source = _function_source(source, "main")

    assert hasattr(app, "inject_app_styles")
    assert "def inject_app_styles()" in source
    assert main_source.index("st.set_page_config(") < main_source.index("inject_app_styles()") < main_source.index("render_app_header()")


def test_dashboard_header_css_and_html_classes_exist():
    source = _source()

    assert "def render_app_header()" in source
    assert ".wrt-app-header" in source
    assert "wrt-app-header-title" in source
    assert "修理受付 支援ツール" in source
    assert "WRT-helpr MVP / ローカル判定補助" not in source
    assert "font-size: 1.5rem;" in source
    assert "font-weight: 800;" in source
    assert "line-height: 1.35;" in source


def test_top_dashboard_layout_css_classes_exist():
    source = _source()
    top_source = _function_source(source, "render_global_top_panels")

    assert "tags_col, memo_col = st.columns([2, 1], gap=\"medium\")" in top_source
    assert 'render_common_case_memo(form, "case_memo_global", height=125)' in top_source
    assert ".wrt-decision-tag" in source
    assert ".wrt-dashboard-card" not in source
    assert 'render_case_clear_controls("top_case_memo", use_container_width=True)' not in source


def test_decision_tag_basic_wording_is_not_changed_by_card_html():
    html = app._ui_v3_block(
        "受付可否",
        [("", "未判定"), ("", "不足：保証期間 / 保証プラン"), ("", "確認：要確認")],
        app.TAG_COLOR_MISSING,
    )

    assert "受付可否" in html
    assert "未判定" in html
    assert "不足：保証期間 / 保証プラン" in html
    assert "確認：要確認" in html
    assert "wrt-decision-tag neutral" in html
    assert "color:white" not in html


def test_decision_tag_color_meaning_comments_exist():
    source = _source()

    assert "灰：未判定" in source
    assert "緑：確定・OK" in source
    assert "黄：注意・要確認" in source
    assert "赤：受付不可・停止" in source
    assert "青：案内・参照" in source


def test_wrs_handover_simple_display_and_transfer_remain():
    source = _source()

    assert "def wrs_handover_call_summary_lines" in source
    assert "WRS引き継ぎ：あり" in source
    assert "WRS引き継ぎ：なし" in source
    assert "def render_wrs_handover_transfer_text" in source
    assert "##### WRS引き継ぎ表 転記用" in source
    assert 'render_copy_button("📋 コピー", transfer_text, "copy_wrs_handover_transfer")' in source


def test_generated_message_builders_do_not_depend_on_ui_style_cards():
    source = _source()
    builders = [
        "_build_teams_chat_message",
        "_build_rakutel_text",
        "_build_after_call_memo",
    ]

    for name in builders:
        body = _function_source(source, name)
        assert "inject_app_styles" not in body
        assert "wrt-decision-tag" not in body
        assert "wrt-section-gap" not in body
        assert "unsafe_allow_html" not in body


def test_no_unwanted_chinese_button_text():
    assert "\u6309\u94ae" not in _source()


def test_product_price_placeholder_is_empty():
    source = _source()
    case_basic_src = _function_source(source, "render_shared_case_basic_editor")

    assert 'placeholder=""' in case_basic_src
    assert 'placeholder="329,000"' not in case_basic_src


def test_app_title_is_larger_than_section_headings():
    source = _source()

    assert "font-size: 1.5rem;" in source
    assert "h3 { font-size: 1.18rem !important;" in source
    assert "h5 { font-size: 0.98rem !important;" in source


def test_heading_hierarchy_css_caps_h3_below_title():
    source = _source()
    styles_src = _function_source(source, "inject_app_styles")

    assert "h3 { font-size: 1.18rem !important;" in styles_src
    assert "h2 { font-size: 1.25rem !important;" in styles_src
