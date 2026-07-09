# 収集ログ — 日本株アクティビスト介入データセット Phase A（入口データ）

- 生成時刻: 2026-06-24 (Phase A 全期間カバレッジ完走)
- データソース: EDINET API v2 `documents.json`（type=2 一覧）＋ 各書類CSV（type=5, UTF-16/XBRL_TO_CSV）
- 取得期間カバレッジ（処理済み提出日）: 2023-01-04 〜 2026-06-24
- ⚠ 注：収集は各年「直近→過去」へ進行中の途中スナップショット。下記の通り**年内に未処理の提出日が残る**（連続full coverageではない）。母数・ヒット率は処理済み提出日の集合に対する値。
    - 2023: 処理済み提出日 245 日（範囲 2023-01-04〜2023-12-28・非連続）
    - 2024: 処理済み提出日 244 日（範囲 2024-01-04〜2024-12-27・非連続）
    - 2025: 処理済み提出日 237 日（範囲 2025-01-06〜2025-12-26・非連続）
    - 2026: 処理済み提出日 115 日（範囲 2026-01-05〜2026-06-24・非連続）
- 重要提案行為あり判定(Phase A.5・3分類): 要素 `jplvh_cor:ActOfMakingImportantProposalEtc` を
  yes(明確な意思)／ambiguous(予定なし・未定・記載のとおり等＝保持しflag)／none(該当事項なし/無し/当該/全角句点等の実質否定＝除外) に分類。
  入口テーブルは yes+ambiguous。

## 件数レポート（母数→フィルタ）

| 段階 | 件数 |
|---|---|
| 母数：大量保有/変更/訂正報告書(docTypeCode 350/360, csv有) 処理済み | 52277 |
| └ うち重要提案行為あり（一次抽出） | 1898 |
| 入口テーブル最終行数（docIDで重複排除後） | 1610 |
| └ known_activist（シードリスト名寄せ一致） | 1158（71.9%） |
| └ control_flag（保有25%超 or 親会社/グループ/買収者） | 112（7.0%） |
| └ going_private_flag（非上場化/MBO/TOB/完全子会社 等） | 54（3.4%） |

### direction内訳
- increase: 758
- decrease: 268
- change: 254
- new: 198
- amend: 125
- N/A: 7

### regime内訳
- post2023: 1600
- pre2023: 10

### 年別（いずれも提出年ベース：母数 / 入口ヒット）
| 提出年 | 母数 | 重要提案入口ヒット |
|---|---|---|
| 2023 | 13495 | 263 |
| 2024 | 14326 | 495 |
| 2025 | 15372 | 516 |
| 2026 | 9084 | 336 |

※ regime は entry_date(報告義務発生日)基準。うち報告義務発生日が2023年より前 = 10 件 （訂正/変更報告書で過去の義務発生日を引き継ぐ稀ケース。提出自体は2023年以降）。

### known_activist 別件数（名寄せラベル）
| ファンド（正規化ラベル） | 件数 |
|---|---|
| Dalton/NipponActiveValue | 334 |
| AVI/AssetValueInvestors | 190 |
| Oasis | 149 |
| 3D Investment | 85 |
| Valex Partners | 76 |
| Symphony Financial | 57 |
| Taiyo | 56 |
| Kaname Capital | 55 |
| Ichigo Asset | 45 |
| Effissimo | 33 |
| Hibiki Path Advisors | 32 |
| Misaki Capital | 17 |
| Pilgrim/NipponValueInvestors | 12 |
| Epic Partners | 8 |
| LIM Advisors | 8 |
| Elliott | 1 |

## 支配権取引の混入率（定量化）
- 「重要提案行為あり」入口 1610 件のうち、control_flag = **112 件（7.0%）**、
  going_private_flag = **54 件（3.4%）**。
- ＝ アクティビズム狙いの母集団に支配権取引（買収・非上場化）が上記割合で混在。後フェーズで分離可能。

## Phase A.5 検証ゲート（4点）
- 【1】期間・レジーム：post2023=1600件（目安≥300）→ **PASS**。 pre2023=10（報告義務発生日が2013/2020-22の稀ケース）。母数52277件。
- 【2】known_activist分類精度：TRUE側 誤検出0、FALSE側の確実な取りこぼし=Hibiki Path Advisors。 false-negative率≈2%（目安5%以下）→ **PASS**。是正でエイリアス拡充（Hibiki追加・SPARX誤爆除去）、 known_activist 1158件（71.9%）。
- 【3】重要提案あり否定形辞書：是正前『あり』に実質否定が286件混入していたのを是正（漢字『無し』『当該』全角句点等を辞書化）。 3分類 yes/ambiguous/none を導入。**FAIL→是正済**。 『あり』1610件（うち ambiguous_flag=29件は除外せず保持）、none再分類で除外=286件。 非ヒット側120件サンプルは全てnone＝取りこぼし0で再確認。
- 【4】生データ混入：追跡ファイルはデータ(csv/json)・再開index(doc_index.jsonl)・scripts・doc類のみ。 生EDINET(zip/csv)・サブスクキー混入なし（漏洩スキャン済）→ **PASS**。

## 注意・限界
- entry_price / entry_mktcap / 財務系（PBR/自己資本比率/ROE等）は本フェーズ未取得（N/A）。Phase Bで J-Quants 等によりエンリッチ。
- sector も未付与（N/A）。proposal/exit/勝敗系は列のみ確保し空欄（Phase B/C）。
- direction の increase/decrease は変更報告書の提出事由テキストから判定。事由が無い場合は 'change'（N/A相当）。
- known_activist はシードリスト＋別名の部分一致。表記ゆれ網羅は今後の頻度分析で拡張余地あり。

## EDINET API レート制限（実機で判明・重要）
- 並列取得を強めると EDINET v2 は `{"statusCode":"429","message":"Too Many Requests"}` を返す
  （HTTP層は200、ボディのstatusCodeが429）。キー単位で発動し、解除には時間を要する。
- 本スナップショットの非連続カバレッジは主にこの429による日次取得失敗のスキップが原因。
  → 収集は「活発期（春の総会シーズン5-6月＋秋冬10-12月）」に厚く、端境期に薄い。
- 対策: Phase B以降は同時実行を1-2本に抑え、429時は長め(数分)に待って同一日を再試行する。
  本パイプラインは `doc_index.jsonl` の済みdocIDをSEEDでスキップするため、制限解除後に再開すれば差分のみ補完できる。
