# WRT-helpr 最新引き継ぎ書

作成日: 2026-06-07

## 1. 現在の最新状態

- 最新commit: `aafb253 Add WRS handover false positive guards`
- pytest: `749 passed`
- git status: clean 前提
- Streamlit: 起動確認済み
- マスタ管理: 保存前プレビュー、重複警告、保存ボタンdisabledを実機確認済み
- Teams: self_test 送信成功済み
- Teams warranty: ローカル設定は有効化済み。本番送信は実案件待ちで未実施

直近で完了した主な内容:

- 京阪夜間・休日 / ビーバートザン対応
- Teams送信UI改善
- nested expander修正
- Teams設定 example / setup docs 追加
- Teams config BOM読み込み対応
- self_test Teams送信成功
- warranty送信先のローカル有効化
- マスタ編集UI安全化
- WRS引き継ぎ保留対象文書化
- WRS誤発火防止テスト追加

## 2. Teams送信運用ルール

現在の推奨運用:

- `default_destination` は `self_test` にしておく。
- 通常確認は自分宛てテストチャットで行う。
- 実運用時だけ送信先をワランティ報告用チャットへ切り替える。
- ワランティ本番送信テストは、実案件がある時だけ実施する。
- テスト文を本番ワランティチャットへ送らない。
- `config/teams_config.json` はGitに入れない。
- `chat_id` 実値をチャット、docs、README、Issue、PR本文に貼らない。

現在の確認済み:

- PowerShell単体 self_test 送信成功
- Streamlit UI self_test 送信成功
- warranty config はローカルで有効化済み
- warranty 本番送信は未確認

Teams関連ファイルの扱い:

- `config/teams_config.example.json`: Git管理対象のサンプル
- `config/teams_config.json`: ローカル秘密設定。Git管理外
- `scripts/send_teams_message.ps1`: 送信スクリプト。現状維持
- `logs/teams_send_log.csv`: 送信ログ。Git管理外

## 3. マスタ編集UI運用ルール

- いきなり保存しない。
- 保存前プレビューで、対象ファイル、追加/変更予定行数、主要キーを確認する。
- 重複警告が出たら保存しない。
- 保存前確認チェック後に保存する。
- 保存すると `backups/master_csv/` にバックアップが作成される。
- 保存すると `logs/master_edit_log.csv` に保存ログが作成される。
- 保存後はStreamlit cacheがクリアされるため、必要なら再判定する。
- 初回の実保存確認は、必要なマスタ追加が発生した時だけ行う。
- 本番CSVを汚すため、ダミー行の追加は避ける。

## 4. WRS引き継ぎルールの状態

追加・対応済み:

- Bosch
- 松﨑電機 / エアコンのマツ
- ビーバートザンをコーナン住設対象に追加
- 京阪夜間・休日対応

保留:

- 住設（賃貸・中古）
- 日新

監査済み:

- SKY
- 三城案件 / メガネ
- コジマ / CHIKYUJIN
- チャオ
- WM案件 / M停止
- コーナン / ビーバートザン
- Bosch
- 松﨑電機 / エアコンのマツ

注意事項:

- 既存ルールは削除していない。
- 誤発火防止テストでガードしている。
- `コジマ`、`メガネ`、`SKY`、`M停止` は今後の業務確認余地あり。
- WRSルール追加時は、対象が発火するテストだけでなく、通常案件に発火しない非発火テストも追加する。
- `docs/wrs_handover_pending.md` に保留理由と監査メモがあるため、WRSルールを増やす前に必ず確認する。

## 5. 残タスク

優先順:

1. warranty Teams本番送信確認
   - 実案件がある時のみ実施する。
   - テスト文を本番ワランティチャットへ送らない。
   - 実施後は `logs/teams_send_log.csv` を確認する。

2. マスタ編集UIの実保存確認
   - 必要なマスタ追加が出た時のみ実施する。
   - ダミー行は追加しない。
   - 実施後は `backups/master_csv/` と `logs/master_edit_log.csv` を確認する。

3. WRS広めルールの業務確認
   - `コジマ`
   - `メガネ`
   - `SKY`
   - `M停止`

4. 実運用後のログ確認
   - `logs/teams_send_log.csv`
   - `logs/master_edit_log.csv`

5. 必要ならREADME更新
   - 実運用確認後に、現場向けの状態説明だけを更新する。

## 6. 次回作業者への注意

- `git add .` は使わない。
- `config/teams_config.json` は絶対にcommitしない。
- `backups/` と `logs/` はGit管理外。
- PowerShellコマンドは必ず `cd "$env:USERPROFILE\Documents\Projects\WRT-helpr"` から始める。
- Teams本番送信は実案件時だけ行う。
- CSV本体を変更したら必ず `python -m pytest -v` を実行する。
- WRSルール追加時は非発火テストも追加する。
- `app.py` の判定ロジック変更は、CSV・テスト・docsだけで運用できない場合に限定する。

## 7. よく使う確認コマンド

```powershell
cd "$env:USERPROFILE\Documents\Projects\WRT-helpr"

git status --short
git log --oneline -6
python -m py_compile .\app.py
python -m pytest -v
git --no-pager diff --stat
```

`python` がPATHにない場合は、Codex同梱Pythonまたは既存 `.codex_test_deps` を使う。
