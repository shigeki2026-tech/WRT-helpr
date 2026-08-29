# WRT_HELPER ver1.20 ボタン押下結果の永続表示

更新日: 2026-08-29

## 症状

取込・全文コピー・4項目コピー・通話メモコピーの押下後、処理自体が成功しても、ボタン表示が1200msで元に戻るため、Excelの画面再描画が遅い端末では「何も起きていない」ように見えた。

## 修正

- `SetButtonStateV120`でボタンの文字と色を即時更新する。
- 取込、全文コピー、4項目コピー、通話メモコピーは、処理開始時にオレンジの「処理中」を表示する。
- 成功時は緑色の「✓ ...済み」、失敗時は赤色の「✕ ...失敗」を表示する。
- 結果は時間で消さず、次の操作、案件クリア、または次回起動まで保持する。
- `WRT_Startup`で `gSilent=False` を明示し、表示抑止状態の残留を防ぐ。
- 案件クリア時に4ボタンを既定表示へ戻す。

## 必須Gate

`WRT_TestButtonFeedbackV120 = PASS`

ビルド中に以下の4図形についてCaptionとFillを実際に変更し、変更値を読み戻した後、元の状態へ復元する。

- `btnImport`
- `btnCopyOut`
- `btnCopy4History`
- `btnMemoCopy`

FAIL時は `WRT_HELPER-ver1.20.xlsm` を生成しない。

## 現行正本

- Module1 SHA-256: `66a27af0f11d98ee8bf39cfc6c6fd92a5c97bba37d8c1b05317da42683ad281a`
- ビルドパッケージ: `WRT_HELPER-ver1.20_BUILD_PACKAGE_FINAL.zip`
- パッケージ SHA-256: `3dac22e8588566912314a6b254e57c904cad27141dc803abc5d9eaa483510338`
- パッケージ bytes: `547798`
- VBA構造: Sub 157/157、Function 117/117、重複名0
- JScript: UTF-16LE BOM
- BAT: ASCII BOMなし
- ZIP CRC: PASS
- ZIP内SHA-256: 全ファイル一致

## 再生成

1. 旧 `WRT_HELPER-ver1.20_BUILD_PACKAGE_FINAL` フォルダを削除する。
2. 現行パッケージを新しいフォルダへ展開する。
3. Excelをすべて閉じる。
4. `RUN_BUILD.bat` を実行する。
5. `BUTTON FEEDBACK PASS`、既存の業務Gate、`PASS=200 FAIL=0`、最終クリーンがすべて通った場合だけ生成物を採用する。
