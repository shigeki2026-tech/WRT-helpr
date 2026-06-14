# WRT-helpr 最新引き継ぎ書

更新日: 2026-06-14

## 1. 現在の最新状態

- 最新commit: `0564c1f Make call line buttons commit selection state`
- 最新pytest: `822 passed, 1 warning`
- warning: `.pytest_cache` 書き込み権限の警告のみ
- `py_compile`: OK
- git status: clean
- `python` がPATH上にない環境では、Codex同梱Pythonに `.codex_test_deps` を `PYTHONPATH` 追加して検証した

重要commit:

- `c1e148f` Add WRS handover vendor rules
- `4674bdb` Add call line start buttons without recording
- `571ad66` Clarify WRS handover before No7 fallback
- `f821a96` Guard Nakayashiki warranty clock routing
- `51716e8` Align appliance category template routing
- `46cd24a` Document audio readonly probe plan
- `0564c1f` Make call line buttons commit selection state

## 2. 回線名ボタンの現状

通話開始エリアに回線名ボタンがある。ボタンは録音開始ボタンではない。

ボタン押下時に確定する状態:

- `form["call_line"]`
- `form["manual_call_line"]`
- `session_state["call_selected_line"]`
- `call_in_progress=True`
- `call_audio_status="未開始 / 録音なし"`

出力反映:

- ラクテル見出しへ即反映される。
- 例: `【住設回線へ入電】`
- 例: `【家電回線へ入電】`
- Teams文の回線名へ即反映される。

運用上の注意:

- 回線名ボタンをクリックしただけで、別のセレクトボックス操作なしに回線選択は完了する。
- 住設補正など自動判定があっても、ボタンで明示選択した回線名は手動指定扱いとして優先する。
- 案件クリアで `call_line` / `manual_call_line` / `call_in_progress` / `call_selected_line` はリセットされる。
- 録音状態は常に `未開始 / 録音なし` のまま。

関連テスト:

- `test_call_start_line_helper_sets_line_and_call_state_without_recording`
- `test_call_start_line_selection_updates_rakutel_heading_and_teams_line`
- `test_call_start_line_manual_selection_survives_residential_inference`
- `test_case_clear_resets_call_start_state_and_removes_stale_recording_key`

## 3. 録音の現状

録音機能はrevert済みのまま。WRT-helpr本体へ録音機能は戻していない。

現在ないもの:

- 録音開始ボタン
- 録音停止ボタン
- 録音保存
- 文字起こしUI
- WRT本体から呼び出される録音処理

依存関係:

- `sounddevice` は追加していない。
- `soundfile` は追加していない。
- `faster-whisper` は追加していない。
- `numpy` など録音・文字起こし目的の依存は追加していない。

音声経路:

- 音声デバイスは変更していない。
- VB-CABLEは変更していない。
- Voicemeeterは変更していない。
- Jabraは変更していない。
- Windows既定デバイスは変更していない。

検証計画:

- `docs/audio_recording_probe_plan.md` に読み取り専用録音の非干渉検証計画だけ作成済み。
- WRT本体から検証スクリプトは呼び出されない。
- 録音再開は、非干渉検証が通ってから判断する。
- 本番通話中に検証を実行しない。

## 4. WRS判定の現状

- WRS引き継ぎルール40件を追加済み。
- WRS対象は No.7 fallback より前に判定する。
- WRS対象のみ、画面に以下の補足表示を出す。

表示文言:

```text
WRS引き継ぎ対象として No.7 fallback より前に判定済み
```

ガード:

- No.7 fallback の通常ユナイト案件ではWRS表示を出さない。
- 通常メーカーがWRS表示になるfalse positiveを防ぐテストがある。
- 既存のWRS判定理由表示は維持している。

## 5. なかやしき保証クロック

なかやしき案件はCSV拠点ルールより前に専用分岐する。

現行ルール:

- 保証期間内: なかやしき工務
- 保証終了後: ベルホームふくおか
- 保証未確認: 担当エスカ（要確認）
- 保証開始日前 / 終了後 / 未確認では `arrangement_blocked=True`
- 保証終了後のベルホームふくおか候補は維持しつつ `needs_escalation=True`
- 画面に `なかやしき保証クロック：...` の理由表示あり
- 日付未入力は今日の日付で補完しない

目的:

- なかやしき案件の保証開始日、保証終了日、保証状態、受付可否、修理手配判定が、通常案件や他販売店に引きずられて誤判定されないようにする。

## 6. appliance category / template routing

現行の分類実態:

- 内部 `appliance_type` は主に `家電` / `住設` の2値。
- 4区分は `appliance_category` と `housing_phase` で表現する。

実表記:

- 家電
- 住設（新築）
- 住設（既築）
- 住設（賃貸）

整合状況:

- `determine_script_route` は既に4区分を参照している。
- テンプレート自動選択側の分類ズレを修正済み。
- 住設（既築）は `0044【中古・既築】` を優先する。
- 住設（賃貸）は賃貸依頼テンプレートを優先する。
- 家電、住設（新築）、未分類は既存フォールバックを維持する。
- 販売店ルールは最優先なので、アイ工務店 `0058` は維持する。

注意:

- 表示名、ラクテル回線名、内部 `appliance_type` を混同しない。
- 回線名手動指定の優先仕様を壊さない。

## 7. テスト状況

最新確認:

- `python -m py_compile .\app.py`: OK
- `python -m pytest -v`: `822 passed, 1 warning`
- warningは `.pytest_cache` 書き込み権限のみ
- `git status --short`: clean

環境メモ:

- このPCでは `python` がPATH上にない場合がある。
- Codexでは以下のように実行した。

```powershell
$env:PYTHONPATH = "$PWD\.codex_test_deps"
& 'C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -v
```

## 8. 残タスク

優先順:

### A. GitHub push

- ローカルcommitが積み上がっている。
- GitHub認証で詰まる可能性がある。
- 業務中や疲れている時はやらない。
- `gh` / GitHub CLI を急に前提化しない。

### B. Teams 45秒同期ブロック

- `Microsoft.Graph` import 起因の同期ブロック疑いがある。
- Teams実送信本体を触る場合は別タスクにする。
- `chat_id` / Graph認証 / config が絡むため環境依存。
- 調査時も秘密値をdocs、README、Issue、PR本文へ貼らない。

### C. 録音非干渉検証

- まだ実行しない。
- 本番通話中にやらない。
- WRT本体へ組み込まない。
- `docs/audio_recording_probe_plan.md` の計画に従う。

### D. 実機UI確認

- 回線ボタン押下
- ラクテル見出し反映
- Teams文反映
- 案件クリア
- 録音UIが出ないこと

## 9. 禁止事項

- `git add .`
- 旧録音実装 commit `37a5485` の復活
- `sounddevice` / `faster-whisper` の安易な追加
- 録音保存、録音UI、文字起こしUIの復活
- 音声デバイス変更
- Voicemeeter / VB-CABLE / Jabra 設定変更
- Windows既定デバイス変更
- Teams Graph 認証に急に入る
- `gh auth login` に急に入る
- 確認コマンドだけで終わる作業
- 差し替え箇所をユーザーに探させる
- Teams実送信、Graph、Push認証を別目的の作業でついでに触る

## 10. よく使う確認コマンド

通常環境:

```powershell
cd "$env:USERPROFILE\Documents\Projects\WRT-helpr"

python -m pytest -q
git --no-pager log --oneline -10
git status --short
```

Codex同梱Pythonを使う場合:

```powershell
cd "$env:USERPROFILE\Documents\Projects\WRT-helpr"

$env:PYTHONPATH = "$PWD\.codex_test_deps"
& 'C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q
git --no-pager log --oneline -10
git status --short
```
