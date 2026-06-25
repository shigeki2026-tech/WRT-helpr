# WRT-helpr 最新引き継ぎ書

更新日：2026-06-25
対象リポジトリ：C:\Users\User\Documents\Projects\WRT-helpr

## 0. 現在の結論

WRT-helpr は今回の一連修正で、主要な widget 同期・終話後生成・CER/Drive運用注意の問題を修正済み。

現時点では、以下を確認済み。

- 全体 pytest：869 passed, 1 warning
- warning は .pytest_cache 書き込み権限で、テスト失敗ではない
- git status：clean
- origin/main 反映済み
- 最新HEAD：d1112a4 Clarify request PDF folder storage notice

今回の最終評価：

- 商品価格0円保持：OK
- CER優先判定：OK
- 岡山CER実機確認：OK
- 水栓系 product_original / manufacturer_original 保持：OK
- コーナン住設・住設（既築）保持：OK
- 終話後生成で多機能便座へ戻る問題：修正済み・実機OK
- CER/WRT Drive正規フォルダ注意文：実機OK
- ユナイト案件にDrive注意文が出ないこと：実機OK

残る未確認：

- 対象製品プルダウン経由の複数製品切替は、今回の貼付データでは対象製品プルダウンが出ず、完全な実機確認までは未完
- ただし、関連する回帰テストは追加済み
- 水栓系の修理形態・概算費用・拠点マスタは仕様未確定のため未整備

## 1. 最新commit

最新ログ：

d1112a4 Clarify request PDF folder storage notice
5647832 Preserve latest case fields for after-call regeneration
9a152ac Preserve product original for selected water fixtures
a42b968 Keep selected product item after widget sync
925243b Extract labeled case fields from pasted text
83ef14c Prioritize CER vendors before fallback
91180ae Preserve manual product price edits

## 2. 今回完了した修正

### 2-1. 商品価格0円保持

commit：
91180ae Preserve manual product price edits

内容：

- 商品価格 0円 がコピー情報取り込み後に消える問題を修正
- sync_global_case_basic_widget_state() で product_price を古い残骸扱いしないよう修正

確認：

- 商品価格 0円 が保持される
- 終話後処理でも 0円 が維持される

### 2-2. CER対象が No.7 fallback に吸われる問題

commit：
83ef14c Prioritize CER vendors before fallback

内容：

- No.7 fallback を即 return せず、特殊ルールを優先
- 岡山県など中国・四国のCER対象をユナイトより前に判定
- 非CER No.7 fallback と既存特殊ルールはテストで固定

確認：

岡山県 + 洗濯機 + パナソニック
→ CER候補（担当確認）

終話後処理：
- 修理拠点：CER候補（担当確認）
- 手配方法：依頼書PDF格納
- 依頼書PDF格納先：CER
- CER Google Driveリンク表示

### 2-3. ラベル抽出の強化

commit：
925243b Extract labeled case fields from pasted text

内容：

- 回線名、案件分類、都道府県、製品、メーカー、商品価格、販売店、保証プランなどをラベル抽出
- call_line / appliance_category / product / product_original 等へ反映

確認：

- 岡山CERテストで回線名・案件分類・都道府県・製品・商品価格が反映される

### 2-4. 複数製品選択後に古い製品へ戻る問題

commit：
a42b968 Keep selected product item after widget sync

内容：

- 対象製品選択時に case_basic_revision を更新
- 古い案件情報 widget 値から切り離して rerun
- 水栓系を多機能便座へ誤正規化しないガードを追加

### 2-5. 水栓系選択時の原文保持

commit：
9a152ac Preserve product original for selected water fixtures

内容：

- product_original の候補選択を専用化
- manufacturer_original は product_item["manufacturer"] 由来で保持
- メーカー値や「その他・要確認」を product_original に混入させない

実機確認：

京阪不動産 水栓系複数製品で確認。

期待結果：
- 製品：水栓
- メーカー：その他・要確認
- メーカー原文：国内メーカー
- 多機能便座へ戻らない

### 2-6. コーナン住設・住設（既築）保持

commit：
5647832 Preserve latest case fields for after-call regeneration

内容：

- normalize_appliance_category("", "住設", "既築") などを住設（既築）へ復元
- product_item 側の appliance_type / appliance_category / housing_phase が空なら既存フォーム値を保持
- 住設区分 / 住宅区分 / 建物区分 / 住居区分 を housing_phase として抽出
- 案件分類：住設 + 住設区分：既築 から 住設（既築）へ復元

実機確認：

コーナン住設テストで確認。

通話中：
- 回線名：コーナン住設
- 案件分類：住設（既築）
- 製品：システムキッチン
- メーカー：パナソニック
- 商品価格：0円
- 修理形態：出張修理
- 概算費用：5,000円〜7,000円
- 拠点：ユナイトサービス㈱

### 2-7. 終話後生成で多機能便座へ戻る問題

commit：
5647832 Preserve latest case fields for after-call regeneration

発生していた問題：

通話中ではシステムキッチンなのに、終話後処理で再生成しても以下が多機能便座になる。

- 修理依頼書メモ
- ラクテル用テキスト
- Teams報告文
- WRS引き継ぎ転記用

対応：

- 終話後処理タブ冒頭で共有の案件情報 widget state を session_state.form に同期してから判定・再生成
- 再生成 context に product_original / manufacturer_original / appliance_category / product_price も含めた
- 修理依頼書メモ再生成では古い attention_memo_current / memo_after_widget を最新 form 由来文面で上書き

実機確認：

通話中：
- 製品：システムキッチン
- メーカー：パナソニック
- 案件分類：住設（既築）

終話後：
- 修理依頼書メモ：システムキッチン / パナソニック
- ラクテル用テキスト：システムキッチン
- Teams報告文：コーナン住設 システムキッチン
- WRS引き継ぎ転記用：製品：システムキッチン

多機能便座戻りは解消。

### 2-8. CER/WRT Drive正規フォルダ注意文

commit：
d1112a4 Clarify request PDF folder storage notice

内容：

- request_pdf_folder_notice_text() を追加
- get_request_pdf_folder_info(vendor).required=True の案件のみ、終話後処理画面に正規Drive格納注意文を表示
- Teams本文、ラクテル文、修理依頼書メモ本文には混ぜない
- 既存PDF格納チェック、Teams送信前チェックは維持

CER表示確認：

- 依頼書PDF格納先：CER
- CER Google Drive を開く
- 注意文表示あり

注意文の趣旨：

- マイドライブではなく、このCER正規フォルダへ格納する
- Drive検索で見つかることと、正規フォルダ格納済みは別
- PDF格納後に「依頼書PDF格納済み」をチェックする

ユナイト確認：

- コーナン住設 / ユナイトサービス㈱案件ではDrive正規フォルダ注意文は出ない
- Teams報告文にもDrive URLや注意文は混入しない

## 3. 実機確認済みパス

### 3-1. 岡山CER

入力条件：

- 回線名：家電
- 案件分類：家電
- 都道府県：岡山県
- 製品：洗濯機
- メーカー：パナソニック
- 商品価格：0円
- 保証プラン：自然故障 10年保証

確認結果：

- 受付可否：保証期間内
- 修理形態：出張修理
- 概算費用：5,000円〜7,000円前後
- 拠点対応：CER候補（担当確認）
- 引継要否：必要
- 終話後処理にCER Driveリンク表示
- CER正規フォルダ注意文表示
- Teams文にDrive URLや注意文は混入なし

### 3-2. 京阪不動産 水栓系複数製品

確認結果：

- 製品：水栓
- メーカー：その他・要確認
- メーカー原文：国内メーカー
- 多機能便座へ戻らない

### 3-3. コーナン住設・既築・システムキッチン

入力条件：

- 回線名：コーナン住設
- 案件分類：住設
- 住設区分：既築
- 都道府県：大阪府
- 製品：システムキッチン
- メーカー：パナソニック
- 商品価格：0円
- 販売店：コーナン商事株式会社
- 保証プラン：コーナン住設 住宅設備機器【10年保証】

確認結果：

- 案件分類：住設（既築）
- 製品：システムキッチン
- メーカー：パナソニック
- 商品価格：0円
- 修理形態：出張修理
- 概算費用：5,000円〜7,000円
- 拠点：ユナイトサービス㈱
- 終話後処理でもシステムキッチンを維持
- Drive正規フォルダ注意文は出ない
- Teams文にDrive URLや注意文は混入なし

## 4. 未完・注意点

### 4-1. 対象製品プルダウン経由の複数製品切替

今回のコーナン住設テストデータでは、対象製品プルダウンが表示されなかった。
そのため、コーナン住設での複数製品切替実機確認は未完。

ただし、以下はテストで固定済み。

- product_item 側の案件分類系が空でも current_form の住設（既築）を保持
- 水栓選択後も product=水栓、manufacturer_original=国内メーカー、product_price=0円、appliance_category=住設（既築）を保持

次に実データで対象製品プルダウンが出た場合に、システムキッチン→水栓などの切替確認を行う。

### 4-2. 水栓系マスタ整備

水栓選択後の修理形態・費用・拠点マスタは未整備。

現状評価：

- 製品選択同期：OK
- 製品原文保持：OK
- メーカー原文保持：OK
- 水栓マスタ判定：未整備

次フェーズで仕様確認が必要：

1. 水栓 / 混合水栓 / トイレ水栓 / システムバス混合水栓は住設出張修理でよいか
2. メーカー「国内メーカー」をどう扱うか
3. 概算費用はいくらにするか
4. 京阪不動産案件の拠点・手配方法は何が正しいか
5. WRS引継ぎ要否との関係

仕様未確認のまま一律登録しないこと。

### 4-3. pytest cache warning

pytest 実行時に .pytest_cache 書き込み権限 warning が出る場合がある。
テスト本体は pass しているため、今回の完了判断では非ブロッキング。

## 5. 次チャットの推奨アクション

次にやるべきことは、追加バグ修正ではなく、仕様未確定タスクの整理。

優先順位：

1. 水栓系マスタ整備の業務仕様確認
2. 実データで対象製品プルダウンが出る複数製品案件の再確認
3. WRS引き継ぎ対象のマスタ整備
4. Teams送信設定の本番化

現時点で今すぐ触らないもの：

- CER判定ロジック
- No.7 fallback
- 終話後生成同期
- Drive注意文
- Teams送信本体
- 水栓マスタの一律追加

## 6. 次回作業開始時コマンド

次回はまずこれで状態確認。

cd "$env:USERPROFILE\Documents\Projects\WRT-helpr"

git status --short
git --no-pager log --oneline -7
python -m pytest -q

期待：

- git status --short：空
- log先頭：d1112a4 Clarify request PDF folder storage notice
- pytest：869 passed, 1 warning 程度

## 7. 進行ルール

禁止：

- git add .
- 部分テストだけで完了扱い
- 実機未確認なのに完了断定
- 仕様未確認のまま水栓マスタを確定登録
- 小分けコマンド提示
- 追加コピペ前提の検証データ提示

PowerShellを出す場合：

- 必ず cd から始める
- 1回コピペで完結
- 目的、期待結果、失敗時に貼るものを明記
- 対象ファイルを明示して git add する
