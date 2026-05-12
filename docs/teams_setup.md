# Teamsチャット自動送信セットアップ

この手順は、WRT-helpr から既存の Teams チャットへ Microsoft Graph PowerShell 経由で報告文を送信するためのローカル設定です。本番の `chat_id` は環境ごとの秘密情報として扱い、Git へコミットしません。

## 1. 設定ファイルを作成する

```powershell
cd "$env:USERPROFILE\Documents\Projects\WRT-helpr"
Copy-Item .\config\teams_config.example.json .\config\teams_config.json
```

`config/teams_config.json` は `.gitignore` 対象です。送信先 PC や Teams チャットごとにローカルで編集してください。

## 2. chat_id を設定する

`config/teams_config.json` を開き、`chat_id` を実際の Teams チャット ID に置き換えます。初期状態では安全のため `enabled` は `false` です。

```json
{
  "enabled": true,
  "chat_id": "実際のTeamsチャットID",
  "chat_name": "WRT報告用チャット",
  "send_mode": "powershell_graph"
}
```

`send_mode` は現時点では `powershell_graph` のみ対応です。

## 3. Microsoft.Graph PowerShell を確認する

```powershell
cd "$env:USERPROFILE\Documents\Projects\WRT-helpr"
Get-Module Microsoft.Graph.Authentication -ListAvailable
Get-Module Microsoft.Graph.Teams -ListAvailable
```

未導入の場合は、ユーザー実機で管理者権限や社内ポリシーを確認したうえで導入してください。

```powershell
cd "$env:USERPROFILE\Documents\Projects\WRT-helpr"
Install-Module Microsoft.Graph -Scope CurrentUser
```

## 4. Microsoft Graph に接続する

```powershell
cd "$env:USERPROFILE\Documents\Projects\WRT-helpr"
Connect-MgGraph -Scopes "ChatMessage.Send"
Get-MgContext
```

初回はブラウザー認証が表示されることがあります。送信には `ChatMessage.Send` 権限が必要です。

## 5. send_teams_message.ps1 を単体テストする

まず一時ファイルに本文を作成し、設定済みの `chat_id` を指定して実行します。

```powershell
cd "$env:USERPROFILE\Documents\Projects\WRT-helpr"
$chatId = "実際のTeamsチャットID"
$messageFile = Join-Path $env:TEMP "wrt-teams-test-message.html"
Set-Content -LiteralPath $messageFile -Value "WRT-helpr Teams送信テスト" -Encoding UTF8
.\scripts\send_teams_message.ps1 -ChatId $chatId -MessageFile $messageFile
```

成功時は `SUCCESS <message id>` が標準出力に表示され、終了コードは `0` です。失敗時は `ERROR <理由>` が表示され、終了コードは `1` です。

## 6. Streamlit UI から送信テストする

```powershell
cd "$env:USERPROFILE\Documents\Projects\WRT-helpr"
streamlit run .\app.py
```

終話後処理タブで Teams 報告文を生成し、送信前チェックをすべて満たしてから `Teamsチャットへ送信` を押します。送信前に、送信先、報告文、楽テルNO、Teams報告アクション、PDF格納チェックが正しいことを確認してください。

## 7. 送信ログを確認する

```powershell
cd "$env:USERPROFILE\Documents\Projects\WRT-helpr"
Import-Csv .\logs\teams_send_log.csv | Select-Object -Last 10
```

`logs/teams_send_log.csv` には送信日時、楽テルNO、WRT No、送信先業者、Teams報告アクション、成功/失敗、エラー内容が記録されます。

## 8. よくあるエラー

- `Teams送信設定が未完了です`: `config/teams_config.json` がない、`enabled=false`、または `chat_id` が空です。
- `send_mode は powershell_graph を指定してください`: `send_mode` が未対応の値です。
- `PowerShell送信スクリプトが見つかりません`: `scripts/send_teams_message.ps1` が見つかりません。
- `Message body is empty`: Teams報告文が空です。
- `Connect-MgGraph` の認証画面が出る: 初回または認証期限切れです。ユーザー実機で認証してください。
- 権限エラー: `ChatMessage.Send` 権限、テナントの同意、対象チャットへの参加状態を確認してください。
- `New-MgChatMessage` の失敗: `chat_id` が誤っている、送信先チャットへアクセスできない、Graph 側の権限が不足している可能性があります。
