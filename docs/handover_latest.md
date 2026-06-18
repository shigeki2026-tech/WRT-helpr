# WRT-helpr 最新引き継ぎ書

更新日: 2026-06-18

## 1. 現在の最新状態

- 最新push済みcommit: `47dde26 Style main radio navigation as tabs`
- 最新pytest: `846 passed`
- `py_compile`: OK
- git status: clean
- 録音機能は戻していない
- Teams実送信本体、Graph認証、chat_id設定は触っていない

今回反映したcommit:

- `197c08a` Compact call line start UI
- `41a9672` Preserve case info while editing hearing fields
- `103832e` Sync call line and add product item selection
- `7404fa5` Avoid rewriting call line widget state
- `77a75f4` Preserve case fields on clipboard import
- `45084c8` Preserve active main tab across reruns
- `d5e9dc4` Use stable radio main navigation
- `47dde26` Style main radio navigation as tabs

## 2. 回線名の正本

回線名の正本は `form["call_line"]` に統一済み。

重要ルール:

- `case_basic_call_line_0` などのwidget keyは正本にしない
- widget描画後に `st.session_state[widget_key] = ...` で直接書き換えない
- ラクテル見出し、Teams文、通話開始エリア表示は `form["call_line"]` を参照する
- 回線名ボタン押下後も正本は `form["call_line"]`
- 手動選択済みの場合は `form["manual_call_line"] = True` として扱い、自動推定で不要に上書きしない

関連修正:

- `103832e`: 回線名同期と複数製品選択を追加
- `7404fa5`: widget key後書き換えを廃止

## 3. クリップボード貼付と案件情報保持

クリップボード貼付/再取込時は、解析結果の空値で既存 `form` を上書きしない。

保持対象の代表:

- `call_line`
- `manual_call_line`
- `appliance_category`
- `housing_phase`
- `case_category`
- `warranty_plan`
- `warranty_start`
- `warranty_end`
- `product`
- `series`
- `manufacturer`
- `model_number`
- `store_name`
- `operating_company`
- `product_items`
- `selected_product_item_index`

明確な非空値が解析できた場合のみ更新する。案件クリアだけが、回線名・案件分類・保証情報・製品情報・聴取内容・複数製品情報を明示的にリセットしてよい。

関連修正:

- `41a9672`: 聴取内容編集時に案件情報を保持
- `77a75f4`: クリップボード貼付で空値上書きを防止

## 4. 複数製品選択UI

複数製品候補を扱うUIを追加済み。

ポイント:

- `product_items` を保持する
- `selected_product_item_index` で対象製品を選択する
- 空の `product_items` で既存候補を消さない
- 対象製品選択、販売店入電ボタン、聴取内容入力で案件情報を巻き戻さない

関連修正:

- `103832e` Sync call line and add product item selection

## 5. 発生時期候補

発生時期候補は以下に修正済み。

- 本日（M/D）
- 昨日（M/D）
- 数日前から
- 1週間ほど前から
- 1か月ほど前から
- 不明

注意:

- 「本日（M/D）から」は使わない
- 「昨日から」だけの旧表記は使わない
- 月日ゼロ埋めはしない
- 「以前から」は追加しない

## 6. 販売店より修理依頼ボタン

終話後処理で相手区分が「販売店」の場合、販売店入電用ボタンを表示する。

ボタン:

- `販売店より修理依頼を追加`

押下時に修理依頼書メモへ追記:

```text
【{販売店名}より修理依頼】
```

販売店名の取得優先順位:

1. `form["store_name"]`
2. `form["store_original"]`
3. `form["store_company"]`
4. 終話後処理の相手名・担当者名入力

重複追記はしない。販売店名がどこにもない場合は、誤った `【より修理依頼】` を作らない。

## 7. メインナビとタブ保持

メインナビは `st.tabs` ではない。

現在の方式:

- 正本: `st.session_state["active_main_tab"]`
- 値: `during_call` / `after_call` / `master`
- 入力UI: `st.radio(horizontal=True)`
- 見た目: CSSでページタブ風UI

理由:

- `st.tabs` はStreamlit rerun後に選択タブをプログラム側で安定復元できない
- `st.button` 3個のナビはフォーカス/選択状態がズレ、赤表示や本文未切替が起きた
- `st.radio` は状態保持入力として安定している

現在の挙動:

- 終話後処理でラクテル用テキスト再生成をしても終話後処理に残る
- 相手区分変更、販売店より修理依頼追加、Teams文生成/更新でも終話後処理に残る
- 通話中判定の操作後は通話中判定に残る
- マスタ管理の操作後はマスタ管理に残る
- 案件クリア時は通話中判定へ戻る

見た目:

- radioの丸アイコンはCSSで非表示
- 選択中は淡い青背景、青枠、太字
- 非選択は白背景、薄いグレー枠
- 赤系色、danger、primary button依存は使わない

関連修正:

- `45084c8`: active tabをsession stateで保持
- `d5e9dc4`: `st.radio` ベースの安定ナビへ変更
- `47dde26`: radioをCSSでページタブ風に整形

## 8. 通話開始エリア

通話開始エリアはコンパクト化済み。

現在のポイント:

- 回線名ボタンは録音開始ボタンではない
- ボタン押下で `form["call_line"]` と `form["manual_call_line"]` を更新する
- `call_in_progress=True`
- 録音状態は `未開始 / 録音なし`
- 回線変更ボタンは復活させない
- 録音UIは復活させない

関連修正:

- `197c08a` Compact call line start UI

## 9. 録音の現状

録音機能は戻していない。

現在ないもの:

- 録音開始ボタン
- 録音停止ボタン
- 録音保存
- 文字起こしUI
- WRT本体から呼び出される録音処理

追加していない依存:

- `sounddevice`
- `soundfile`
- `faster-whisper`
- 録音/文字起こし目的の `numpy`

触っていないもの:

- 音声デバイス
- VB-CABLE
- Voicemeeter
- Jabra
- Windows既定デバイス

## 10. Teams実送信

Teams実送信本体は触っていない。

触っていないもの:

- Teams実送信本体
- Graph認証
- `chat_id` 設定
- 秘密値
- 送信先設定

Teams文生成側は `form["call_line"]` を参照する。実送信本体の調査・修正は別タスクで扱う。

## 11. 既存重要判定

維持している既存重要項目:

- WRS判定
- No.7 fallback
- なかやしき保証クロック
- appliance category / housing phase
- product_items
- Teams文
- 録音なしテスト

## 12. テスト状況

最新確認:

- `python -m py_compile .\app.py`: OK
- `python -m pytest -v`: `846 passed`
- `git status --short`: clean

環境メモ:

- このPCでは `python` がPATH上にない場合がある。
- Codexでは以下のように実行した。

```powershell
cd "$env:USERPROFILE\Documents\Projects\WRT-helpr"

$env:PYTHONPATH = "$PWD\.codex_test_deps"
& 'C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -v
```

## 13. 禁止事項

- `git add .`
- 録音機能の復活
- 録音開始/停止ボタンの追加
- 録音保存/文字起こしUIの追加
- `sounddevice` / `soundfile` / `faster-whisper` の追加
- 音声デバイス、VB-CABLE、Voicemeeter、Jabra、Windows既定デバイス変更
- Teams実送信本体、Graph認証、chat_id設定をついでに触る
- widget keyを描画後に `st.session_state` で直接書き換える
- `st.tabs` へ戻す
- `st.button` 3個のメインナビへ戻す

## 14. よく使う確認コマンド

通常環境:

```powershell
cd "$env:USERPROFILE\Documents\Projects\WRT-helpr"

python -m py_compile .\app.py
python -m pytest -v
git --no-pager diff --stat
git status --short
git --no-pager log --oneline -10
```

Codex同梱Pythonを使う場合:

```powershell
cd "$env:USERPROFILE\Documents\Projects\WRT-helpr"

$env:PYTHONPATH = "$PWD\.codex_test_deps"
& 'C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m py_compile .\app.py
& 'C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -v
git --no-pager diff --stat
git status --short
git --no-pager log --oneline -10
```
