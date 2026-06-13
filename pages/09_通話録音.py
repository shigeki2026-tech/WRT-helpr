from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

import app
from audio_devices import (
    TwoTrackRecorder,
    query_input_devices,
    recording_session_dir,
    resolve_recording_devices,
    wav_has_signal,
)
from transcribe import WHISPER_MODEL_SIZE, conversation_to_dicts, transcribe_call


def ensure_form() -> dict:
    if "form" not in st.session_state:
        st.session_state.form = app.empty_form()
    else:
        for key, value in app.empty_form().items():
            st.session_state.form.setdefault(key, value)
    return st.session_state.form


def device_index_options(devices) -> tuple[list[str], dict[str, int | None]]:
    labels = ["自動解決"]
    mapping: dict[str, int | None] = {"自動解決": None}
    for device in devices:
        labels.append(device.label)
        mapping[device.label] = device.index
    return labels, mapping


def append_to_symptom(text: str) -> None:
    form = ensure_form()
    current = form.get("symptom_detail") or st.session_state.get("call_hearing_symptom_detail") or ""
    updated = app.append_call_transcript_to_existing_text(current, text)
    form["symptom_detail"] = updated
    st.session_state["call_hearing_symptom_detail"] = updated
    st.session_state.form = form


def render_conversation(turns: list[dict]) -> None:
    if not turns:
        st.info("会話ログはまだありません。")
        return
    st.dataframe(pd.DataFrame(turns), use_container_width=True, hide_index=True)
    caller_turns = [
        turn for turn in turns
        if str(turn.get("speaker") or "") == "caller" and str(turn.get("text") or "").strip()
    ]
    if not caller_turns:
        st.info("先方発話はまだありません。")
        return
    labels = [
        f"{turn['start']:.1f}-{turn['end']:.1f}s: {turn['text']}"
        for turn in caller_turns
    ]
    selected = st.multiselect("症状欄へ追記する先方発話", labels, key="recording_selected_caller_turns")
    selected_texts = [
        caller_turns[labels.index(label)]["text"]
        for label in selected
        if label in labels
    ]
    if st.button("選択した先方発話を症状欄へ追記", disabled=not selected_texts, use_container_width=True):
        append_to_symptom("\n".join(selected_texts))
        st.success("先方発話を具体的な症状欄へ追記しました。終話後処理タブで再生成してください。")


def main() -> None:
    st.set_page_config(page_title="通話録音", page_icon="🎙️", layout="wide")
    ensure_form()
    st.title("🎙️ 通話録音")
    st.caption("ローカル録音とローカル書き起こしのみを行います。外部API連携は行いません。")

    try:
        devices = query_input_devices()
    except Exception as exc:
        st.error(str(exc))
        st.stop()

    labels, mapping = device_index_options(devices)
    auto_resolution = resolve_recording_devices()

    st.markdown("#### デバイス解決")
    device_cols = st.columns(2)
    with device_cols[0]:
        st.write("**オペレーター候補**")
        st.info(auto_resolution.operator.label if auto_resolution.operator else "未検出")
        st.caption(auto_resolution.operator_reason)
        operator_label = st.selectbox("オペレーター入力", labels, key="recording_operator_device")
    with device_cols[1]:
        st.write("**先方候補**")
        st.info(auto_resolution.caller.label if auto_resolution.caller else "未検出")
        st.caption(auto_resolution.caller_reason)
        caller_label = st.selectbox("先方入力", labels, key="recording_caller_device")

    resolution = resolve_recording_devices(
        operator_index=mapping.get(operator_label),
        caller_index=mapping.get(caller_label),
    )
    operator_device = resolution.operator
    caller_device = resolution.caller

    st.markdown("#### 録音操作")
    can_record = operator_device is not None and caller_device is not None
    if not can_record:
        st.warning("オペレーター/先方の入力デバイスを選択してください。")

    control_cols = st.columns([1, 1, 3])
    with control_cols[0]:
        if st.button("録音開始", disabled=(not bool(can_record)) or bool(st.session_state.get("local_recording_active", False)), use_container_width=True):
            session_dir = recording_session_dir()
            recorder = TwoTrackRecorder(
                operator_device_index=operator_device.index,
                caller_device_index=caller_device.index,
            )
            recorder.start()
            st.session_state["local_recording_active"] = True
            st.session_state["local_recording_dir"] = str(session_dir)
            st.session_state["local_recording_recorder"] = recorder
            st.rerun()
    with control_cols[1]:
        if st.button("録音停止", disabled=not st.session_state.get("local_recording_active"), use_container_width=True):
            recorder = st.session_state.get("local_recording_recorder")
            session_dir = Path(st.session_state.get("local_recording_dir") or recording_session_dir())
            paths = recorder.stop_and_save(session_dir)
            st.session_state["local_recording_active"] = False
            st.session_state["local_recording_paths"] = {k: str(v) for k, v in paths.items()}
            st.session_state["local_recording_recorder"] = None
            st.rerun()
    with control_cols[2]:
        if st.session_state.get("local_recording_active"):
            st.error("録音中です。終話後は録音停止を押してください。")
        else:
            st.info("停止中")

    paths = st.session_state.get("local_recording_paths") or {}
    if paths:
        st.markdown("#### 保存ファイル")
        for speaker, path in paths.items():
            has_signal = False
            try:
                has_signal = wav_has_signal(path)
            except Exception:
                pass
            st.write(f"- {speaker}: `{path}` / 有音: {'yes' if has_signal else 'no'}")

    st.markdown("#### ローカル書き起こし")
    st.caption(f"使用モデル: faster-whisper {WHISPER_MODEL_SIZE} / local_files_only=True")
    transcribe_disabled = not paths or not Path(paths.get("caller", "")).exists() or not Path(paths.get("operator", "")).exists()
    if st.button("caller/operator WAVを書き起こす", disabled=transcribe_disabled, use_container_width=True):
        with st.spinner("ローカルで書き起こしています..."):
            try:
                turns = transcribe_call(paths["caller"], paths["operator"])
            except Exception as exc:
                st.error(str(exc))
            else:
                st.session_state["local_recording_conversation"] = conversation_to_dicts(turns)
                st.success("書き起こしが完了しました。")

    render_conversation(st.session_state.get("local_recording_conversation") or [])


if __name__ == "__main__":
    main()
