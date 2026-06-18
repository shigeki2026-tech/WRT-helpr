"""List audio-related devices without opening or changing them.

This standalone probe is intentionally disconnected from WRT-helpr. It uses
only Python's standard library and read-only PowerShell queries.
"""

from __future__ import annotations

import csv
import io
import platform
import subprocess
import sys
from dataclasses import dataclass


POWERSHELL = "powershell.exe"


@dataclass(frozen=True)
class AudioDevice:
    source: str
    name: str
    status: str = ""
    device_id: str = ""


def _run_powershell(command: str) -> str:
    completed = subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(message or f"PowerShell exited with {completed.returncode}")
    return completed.stdout


def _parse_csv_rows(text: str, source: str) -> list[AudioDevice]:
    devices: list[AudioDevice] = []
    for row in csv.DictReader(io.StringIO(text)):
        name = (row.get("Name") or row.get("FriendlyName") or "").strip()
        if not name:
            continue
        devices.append(
            AudioDevice(
                source=source,
                name=name,
                status=(row.get("Status") or "").strip(),
                device_id=(row.get("DeviceID") or row.get("InstanceId") or "").strip(),
            )
        )
    return devices


def list_windows_audio_devices() -> list[AudioDevice]:
    """Return audio-related Windows devices using read-only system queries."""

    commands = [
        (
            "Win32_SoundDevice",
            "Get-CimInstance Win32_SoundDevice | "
            "Select-Object Name,Status,DeviceID | ConvertTo-Csv -NoTypeInformation",
        ),
        (
            "Get-PnpDevice",
            "Get-PnpDevice -Class AudioEndpoint,MEDIA -PresentOnly | "
            "Select-Object FriendlyName,Status,InstanceId | ConvertTo-Csv -NoTypeInformation",
        ),
    ]

    devices: list[AudioDevice] = []
    for source, command in commands:
        try:
            devices.extend(_parse_csv_rows(_run_powershell(command), source))
        except Exception as exc:
            devices.append(AudioDevice(source=source, name=f"取得不可: {exc}"))
    return devices


def print_devices(devices: list[AudioDevice]) -> None:
    if not devices:
        print("音声関連デバイスを取得できませんでした。docs/audio_recording_probe_plan.md の手動確認手順を使ってください。")
        return

    print("音声関連デバイス一覧（読み取り専用）")
    print("このスクリプトは録音せず、デバイスを開かず、既定デバイスやOS設定を変更しません。")
    for index, device in enumerate(devices, start=1):
        status = f" / status={device.status}" if device.status else ""
        device_id = f" / id={device.device_id}" if device.device_id else ""
        print(f"{index}. [{device.source}] {device.name}{status}{device_id}")


def main() -> int:
    if platform.system() != "Windows":
        print("Windows以外では自動取得しません。docs/audio_recording_probe_plan.md の手動確認手順を使ってください。")
        return 0

    print_devices(list_windows_audio_devices())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
