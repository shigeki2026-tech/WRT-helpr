# Teams送信 初回設定手順

## 目的

WRT-helpr から Microsoft Teams へ報告文を送信するための初回設定と手動確認手順を整理する。本番 `chat_id` は Git に入れず、実送信テストは担当者が手動で実施する。

## 前提

- Teams送信は Microsoft Graph PowerShell を使う。
- 送信スクリプトは `scripts/send_teams_message.ps1`。
- アプリ側の送信方式は `powershell_graph`。
- 本文は一時ファイル経由で PowerShell に渡される。
- PowerShell スクリプトは `SUCCESS <message_id>` を stdout に出して終了コード 0、失敗時は `ERROR <reason>` を stdout に出して終了コード 1 を返す。
- 本番Teams送信テストは自動テストでは行わない。

## 設定ファイル

設定ファイルの場所:

- example: `config/teams_config.example.json`
- 本番用: `config/teams_config.json`

`config/teams_config.json` は Git 管理対象外にする。本番 `chat_id`、個人向けテスト `chat_id`、ワランティ送信先 `chat_id` はコミットしない。

## 初回設定

```powershell
cd "$env:USERPROFILE\Documents\Projects\WRT-helpr"
Copy-Item -LiteralPath .\config\teams_config.example.json -Destination .\config\teams_config.json
```

`config/teams_config.json` を開き、必要な送信先だけ `chat_id` を設定する。初回編集時点では `enabled=false` のままにする。

主な項目:

- `enabled`: 通常送信/送信機能全体を有効化するか。
- `chat_id`: 旧形式の通常送信先。新しい送信先設定を使う場合は空欄でもよい。
- `chat_name`: ログや画面表示用の送信先名。
- `send_mode`: `powershell_graph` を指定する。
- `warranty_chat_id`: 旧形式のワランティ送信先。
- `destinations.warranty.chat_id`: ワランティ送信先。
- `destinations.self_test.chat_id`: 自分宛てテスト送信先。

`enabled=true` にするタイミング:

- Microsoft Graph PowerShell のモジュール確認が済んでいる。
- Teams の送信先 `chat_id` が確定している。
- 自分宛て、または検証用チャットで PowerShell 単体送信テストを行う準備ができている。

## Microsoft Graph PowerShell 確認

モジュール確認:

```powershell
cd "$env:USERPROFILE\Documents\Projects\WRT-helpr"
Get-Module Microsoft.Graph.Authentication -ListAvailable
Get-Module Microsoft.Graph.Teams -ListAvailable
```

未導入の場合は、組織の運用ルールに従って Microsoft Graph PowerShell SDK を導入する。

認証:

```powershell
cd "$env:USERPROFILE\Documents\Projects\WRT-helpr"
Connect-MgGraph -Scopes "ChatMessage.Send"
Get-MgContext
```

## PowerShell単体送信テスト

本番チャットではなく、自分宛てまたは検証用チャットで実施する。

```powershell
cd "$env:USERPROFILE\Documents\Projects\WRT-helpr"
$messagePath = Join-Path $env:TEMP "wrt-teams-test-message.html"
Set-Content -LiteralPath $messagePath -Encoding UTF8 -Value "<b>WRT-helpr Teams送信テスト</b><br>手動テストです。"
.\scripts\send_teams_message.ps1 -ChatId "<検証用chat_id>" -MessageFile $messagePath
```

成功時は stdout に `SUCCESS <message_id>` が出る。失敗時は `ERROR <reason>` が出るため、理由を確認する。

## Streamlit UIからの確認

1. `config/teams_config.json` に検証用 `chat_id` を設定する。
2. 検証用送信先のみ有効化する。
3. `enabled=true` にする。
4. WRT-helpr を起動し、Teams報告文を生成する。
5. 送信先が検証用チャットであることを確認する。
6. 送信ボタンを押す。
7. UI に「Teamsへ送信しました。」と送信日時が表示されることを確認する。
8. `logs/teams_send_log.csv` に成功/失敗ログが残ることを確認する。

## 失敗時の切り分け

- `send_mode` が `powershell_graph` か確認する。
- `chat_id` が空欄ではないか確認する。
- `enabled=true` になっているか確認する。
- Microsoft Graph PowerShell モジュールが導入済みか確認する。
- `Connect-MgGraph -Scopes "ChatMessage.Send"` 済みか確認する。
- PowerShell 単体送信で `SUCCESS` が出るか確認する。
- `ERROR MessageFile not found` の場合は本文ファイルのパスを確認する。
- `ERROR Message body is empty` の場合は本文ファイルの中身を確認する。
- Graph 権限や組織ポリシーで送信が拒否されていないか確認する。
- Streamlit UI の送信ログと `logs/teams_send_log.csv` を確認する。

## Git管理方針

- `config/teams_config.example.json` は Git 管理する。
- `config/teams_config.json` は Git 管理しない。
- `logs/` は Git 管理しない。
- 本番 `chat_id`、Graph 認証情報、送信本文の一時ファイルは Git に入れない。
- 本番Teams送信テストは自動化せず、担当者が手動で実施する。
