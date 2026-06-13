from __future__ import annotations

import csv
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


WHISPER_MODEL_SIZE = "small"
VOCAB_COLUMNS = (
    "display_name",
    "call_line",
    "call_line_code",
    "aliases",
    "product",
    "product_name",
    "vendor_name",
    "manufacturer",
    "group_name",
    "store_name",
    "template_code",
    "rule_name",
    "hearing_items",
    "title",
)


@dataclass(frozen=True)
class ConversationTurn:
    speaker: str
    start: float
    end: float
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


def _split_terms(value: str) -> list[str]:
    terms = []
    for part in re.split(r"[|,、/／\s]+", str(value or "")):
        term = part.strip()
        if 2 <= len(term) <= 30:
            terms.append(term)
    return terms


def row_is_enabled(row: dict) -> bool:
    enabled = str(row.get("enabled", "") or "").strip().lower()
    if enabled in {"0", "false", "disabled", "no", "off"}:
        return False
    active = str(row.get("active", "") or "").strip().lower()
    if active in {"0", "false", "disabled", "no", "off"}:
        return False
    return True


def load_master_vocabulary(data_dir: str | Path = "data", *, max_terms: int = 120) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for path in sorted(Path(data_dir).glob("master_*.csv")):
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not row_is_enabled(row):
                    continue
                for column in VOCAB_COLUMNS:
                    if column not in row:
                        continue
                    for term in _split_terms(row.get(column, "")):
                        key = term.casefold()
                        if key in seen:
                            continue
                        seen.add(key)
                        terms.append(term)
                        if len(terms) >= max_terms:
                            return terms
    return terms


def build_initial_prompt(vocabulary: Iterable[str] | None = None) -> str:
    terms = list(vocabulary if vocabulary is not None else load_master_vocabulary())
    if not terms:
        return "修理受付の通話です。日本語で書き起こしてください。"
    joined = "、".join(terms[:120])
    return (
        "修理受付の通話です。日本語で書き起こしてください。"
        "次の業務語彙を優先して認識してください: "
        f"{joined}"
    )


def load_whisper_model():
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:  # pragma: no cover - depends on optional runtime deps
        raise RuntimeError("faster-whisper が利用できません。requirements をインストールしてください。") from exc
    return WhisperModel(WHISPER_MODEL_SIZE, device="auto", compute_type="int8", local_files_only=True)


def transcribe_wav(
    wav_path: str | Path,
    *,
    speaker: str,
    model=None,
    initial_prompt: str | None = None,
) -> list[ConversationTurn]:
    active_model = model or load_whisper_model()
    prompt = initial_prompt if initial_prompt is not None else build_initial_prompt()
    segments, _info = active_model.transcribe(
        str(wav_path),
        language="ja",
        vad_filter=True,
        initial_prompt=prompt,
    )
    turns = []
    for segment in segments:
        text = str(segment.text or "").strip()
        if not text:
            continue
        turns.append(
            ConversationTurn(
                speaker=speaker,
                start=float(segment.start or 0.0),
                end=float(segment.end or 0.0),
                text=text,
            )
        )
    return turns


def merge_conversation_turns(*turn_groups: Iterable[ConversationTurn]) -> list[ConversationTurn]:
    turns: list[ConversationTurn] = []
    for group in turn_groups:
        turns.extend(group)
    return sorted(turns, key=lambda turn: (turn.start, turn.end, turn.speaker))


def transcribe_call(
    caller_wav: str | Path,
    operator_wav: str | Path,
) -> list[ConversationTurn]:
    model = load_whisper_model()
    prompt = build_initial_prompt()
    caller_turns = transcribe_wav(caller_wav, speaker="caller", model=model, initial_prompt=prompt)
    operator_turns = transcribe_wav(operator_wav, speaker="operator", model=model, initial_prompt=prompt)
    return merge_conversation_turns(caller_turns, operator_turns)


def conversation_to_dicts(turns: Iterable[ConversationTurn]) -> list[dict]:
    return [turn.to_dict() for turn in turns]
