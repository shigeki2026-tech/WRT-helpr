from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


OPERATOR_DEVICE_NAME_CANDIDATES = (
    "Jabra BIZ 1500 Mic",
    "Jabra BIZ 1500",
    "Jabra",
)

CALLER_DEVICE_NAME_CANDIDATES = (
    "CABLE Output",
    "Voicemeeter Out B1",
    "Voicemeeter Output",
    "Voicemeeter VAIO",
    "VoiceMeeter Aux Output",
)


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    max_input_channels: int
    default_samplerate: float
    hostapi: str = ""

    @property
    def label(self) -> str:
        host = f" / {self.hostapi}" if self.hostapi else ""
        return f"{self.index}: {self.name} ({self.max_input_channels}ch{host})"


@dataclass(frozen=True)
class DeviceResolution:
    operator: AudioDevice | None
    caller: AudioDevice | None
    operator_reason: str
    caller_reason: str
    input_devices: list[AudioDevice]


def _sounddevice():
    try:
        import sounddevice as sd
    except Exception as exc:  # pragma: no cover - depends on local audio runtime
        raise RuntimeError("sounddevice が利用できません。requirements をインストールしてください。") from exc
    return sd


def query_input_devices() -> list[AudioDevice]:
    sd = _sounddevice()
    hostapis = sd.query_hostapis()
    devices = []
    for index, info in enumerate(sd.query_devices()):
        input_channels = int(info.get("max_input_channels") or 0)
        if input_channels <= 0:
            continue
        hostapi_index = int(info.get("hostapi") or 0)
        hostapi = ""
        if 0 <= hostapi_index < len(hostapis):
            hostapi = str(hostapis[hostapi_index].get("name") or "")
        devices.append(
            AudioDevice(
                index=index,
                name=str(info.get("name") or ""),
                max_input_channels=input_channels,
                default_samplerate=float(info.get("default_samplerate") or 16000),
                hostapi=hostapi,
            )
        )
    return devices


def find_input_device_by_name(
    devices: Iterable[AudioDevice],
    candidates: Iterable[str],
) -> tuple[AudioDevice | None, str]:
    device_list = list(devices)
    for candidate in candidates:
        needle = candidate.casefold()
        for device in device_list:
            if needle in device.name.casefold():
                return device, f"デバイス名に '{candidate}' を含む入力デバイスを検出"
    return None, "候補名に一致する入力デバイスなし"


def device_by_index(devices: Iterable[AudioDevice], index: int | None) -> AudioDevice | None:
    if index is None:
        return None
    for device in devices:
        if device.index == index:
            return device
    return None


def resolve_recording_devices(
    operator_index: int | None = None,
    caller_index: int | None = None,
) -> DeviceResolution:
    devices = query_input_devices()
    operator = device_by_index(devices, operator_index)
    caller = device_by_index(devices, caller_index)
    operator_reason = "手動選択" if operator else ""
    caller_reason = "手動選択" if caller else ""
    if operator is None:
        operator, operator_reason = find_input_device_by_name(devices, OPERATOR_DEVICE_NAME_CANDIDATES)
    if caller is None:
        caller, caller_reason = find_input_device_by_name(devices, CALLER_DEVICE_NAME_CANDIDATES)
    return DeviceResolution(
        operator=operator,
        caller=caller,
        operator_reason=operator_reason,
        caller_reason=caller_reason,
        input_devices=devices,
    )


def recording_session_dir(base_dir: str | Path = "recordings") -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path(base_dir) / stamp
    path.mkdir(parents=True, exist_ok=True)
    return path


class TwoTrackRecorder:
    def __init__(
        self,
        operator_device_index: int,
        caller_device_index: int,
        *,
        sample_rate: int = 16000,
        channels: int = 1,
    ) -> None:
        self.operator_device_index = operator_device_index
        self.caller_device_index = caller_device_index
        self.sample_rate = sample_rate
        self.channels = channels
        self._operator_chunks = []
        self._caller_chunks = []
        self._operator_stream = None
        self._caller_stream = None
        self.started_at = datetime.now()

    @property
    def is_recording(self) -> bool:
        return self._operator_stream is not None or self._caller_stream is not None

    def _operator_callback(self, indata, frames, time, status) -> None:  # pragma: no cover - hardware callback
        self._operator_chunks.append(indata.copy())

    def _caller_callback(self, indata, frames, time, status) -> None:  # pragma: no cover - hardware callback
        self._caller_chunks.append(indata.copy())

    def start(self) -> None:
        sd = _sounddevice()
        self._operator_stream = sd.InputStream(
            device=self.operator_device_index,
            channels=self.channels,
            samplerate=self.sample_rate,
            dtype="float32",
            callback=self._operator_callback,
        )
        self._caller_stream = sd.InputStream(
            device=self.caller_device_index,
            channels=self.channels,
            samplerate=self.sample_rate,
            dtype="float32",
            callback=self._caller_callback,
        )
        self._operator_stream.start()
        self._caller_stream.start()

    def stop(self) -> None:
        for stream in (self._operator_stream, self._caller_stream):
            if stream is not None:
                stream.stop()
                stream.close()
        self._operator_stream = None
        self._caller_stream = None

    def save(self, directory: str | Path) -> dict[str, Path]:
        import numpy as np
        import soundfile as sf

        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        operator_audio = (
            np.concatenate(self._operator_chunks, axis=0)
            if self._operator_chunks
            else np.zeros((0, self.channels), dtype="float32")
        )
        caller_audio = (
            np.concatenate(self._caller_chunks, axis=0)
            if self._caller_chunks
            else np.zeros((0, self.channels), dtype="float32")
        )
        operator_path = path / "operator.wav"
        caller_path = path / "caller.wav"
        sf.write(operator_path, operator_audio, self.sample_rate)
        sf.write(caller_path, caller_audio, self.sample_rate)
        return {"operator": operator_path, "caller": caller_path}

    def stop_and_save(self, directory: str | Path) -> dict[str, Path]:
        self.stop()
        return self.save(directory)


def wav_has_signal(path: str | Path, *, threshold: float = 0.001) -> bool:
    import numpy as np
    import soundfile as sf

    audio, _sample_rate = sf.read(path, always_2d=True)
    if audio.size == 0:
        return False
    return bool(np.max(np.abs(audio)) > threshold)
