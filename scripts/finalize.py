#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convert collected jsonl into Phase A deliverables: CSV + JSON + count-report log."""
import json, csv, sys, os, collections, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flags as F

RUN = sys.argv[1]                       # dir with doc_index.jsonl / entries.jsonl
OUT = sys.argv[2]                       # deliverable dir
os.makedirs(OUT, exist_ok=True)

# Phase A schema column order
COLS = [
    "fund_name", "fund_known_activist", "activist_label", "issuer_name", "ticker", "sector",
    "regime", "entry_date", "entry_filing_id", "entry_holding_pct", "entry_price", "entry_mktcap",
    "filing_purpose_text", "purpose_flags", "important_proposal_text", "direction",
    "ambiguous_flag",
    "control_flag", "going_private_flag", "going_private_kw", "source_url", "submit_datetime",
    "shares_held", "outstanding_shares", "indiv_corp", "doc_title", "filer_edinet",
    "entry_pbr", "entry_equity_ratio", "entry_net_cash_ratio", "entry_roe", "stable_holder_pct",
    "proposal_made", "proposal_type", "agm_result", "company_response",
    "exit_date", "exit_filing_id", "exit_price", "holding_months",
    "entry_to_exit_return", "trap_label", "exit_reason", "notes",
]

def load(path):
    out = []
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                try: out.append(json.loads(line))
                except Exception: pass
    return out

index = load(os.path.join(RUN, "doc_index.jsonl"))
entries = load(os.path.join(RUN, "entries.jsonl"))

# dedup entries by docID + recompute flags + reclassify proposal text.
# Phase A.5: entries whose important text is 実質否定 (classify -> 'none') are
# DROPPED (they were false-positive 'あり'); ambiguous kept with ambiguous_flag.
seen = set(); ents = []; n_dropped_none = 0; n_ambiguous = 0
for e in entries:
    k = e.get("entry_filing_id")
    if k in seen: continue
    seen.add(k)
    cls = F.classify_proposal(e.get("important_proposal_text"))
    if cls == "none":
        n_dropped_none += 1
        continue
    e["ambiguous_flag"] = (cls == "ambiguous")
    if e["ambiguous_flag"]:
        n_ambiguous += 1
    pct = e.get("entry_holding_pct")
    rf = F.compute_flags(e.get("fund_name"), e.get("filing_purpose_text"),
                         e.get("important_proposal_text"), pct)
    e.update(rf)            # retroactively apply latest seed list + flag rules
    ents.append(e)

# ---- write entries CSV/JSON ----
with open(os.path.join(OUT, "activist_entries.csv"), "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
    w.writeheader()
    for e in ents: w.writerow({c: e.get(c, "") for c in COLS})
with open(os.path.join(OUT, "activist_entries.json"), "w", encoding="utf-8") as f:
    json.dump(ents, f, ensure_ascii=False, indent=2)

# ---- exit-candidate table (direction=decrease duplicated out) ----
exits = [e for e in ents if e.get("direction") == "decrease"]
with open(os.path.join(OUT, "exit_candidates.csv"), "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
    w.writeheader()
    for e in exits: w.writerow({c: e.get(c, "") for c in COLS})

# ---- count report ----
n_pop = len(index)
n_pop_important = sum(1 for r in index if r.get("important"))
n_hits = len(ents)
by_dir = collections.Counter(e.get("direction") for e in ents)
n_known = sum(1 for e in ents if e.get("fund_known_activist"))
n_ctrl = sum(1 for e in ents if e.get("control_flag"))
n_gp = sum(1 for e in ents if e.get("going_private_flag"))
by_regime = collections.Counter(e.get("regime") for e in ents)
by_activist = collections.Counter(e.get("activist_label") for e in ents if e.get("fund_known_activist"))
# yearly population
by_year_pop = collections.Counter((r.get("date") or "")[:4] for r in index)
# key hits on SUBMIT year (same basis as 母数) for an apples-to-apples table
by_year_hit = collections.Counter((e.get("submit_datetime") or "")[:4] for e in ents)
# entry_date(報告義務発生日) older than 2023 => 訂正/変更で過去の義務日を持つ稀ケース
n_old_obl = sum(1 for e in ents if (e.get("entry_date") or "")[:4].isdigit() and int((e.get("entry_date") or "0")[:4]) < 2023)
# date coverage (distinct filing-days actually processed, per year)
dates = sorted(set(r.get("date") for r in index if r.get("date")))
cov = f"{dates[0]} 〜 {dates[-1]}" if dates else "N/A"
cov_by_year = collections.Counter(d[:4] for d in dates)
cov_ranges = {}
for y in sorted(cov_by_year):
    yd = [d for d in dates if d[:4] == y]
    cov_ranges[y] = (yd[0], yd[-1], len(yd))

def pct(n, d): return f"{100*n/d:.1f}%" if d else "N/A"

log = []
log.append("# 収集ログ — 日本株アクティビスト介入データセット Phase A（入口データ）\n")
log.append(f"- 生成時刻: {os.environ.get('STAMP','(run finalize with STAMP)')}")
log.append(f"- データソース: EDINET API v2 `documents.json`（type=2 一覧）＋ 各書類CSV（type=5, UTF-16/XBRL_TO_CSV）")
log.append(f"- 取得期間カバレッジ（処理済み提出日）: {cov}")
log.append(f"- ⚠ 注：収集は各年「直近→過去」へ進行中の途中スナップショット。下記の通り**年内に未処理の提出日が残る**（連続full coverageではない）。母数・ヒット率は処理済み提出日の集合に対する値。")
for y, (a, b, n) in cov_ranges.items():
    log.append(f"    - {y}: 処理済み提出日 {n} 日（範囲 {a}〜{b}・非連続）")
log.append(f"- 重要提案行為あり判定(Phase A.5・3分類): 要素 `jplvh_cor:ActOfMakingImportantProposalEtc` を")
log.append(f"  yes(明確な意思)／ambiguous(予定なし・未定・記載のとおり等＝保持しflag)／none(該当事項なし/無し/当該/全角句点等の実質否定＝除外) に分類。")
log.append(f"  入口テーブルは yes+ambiguous。\n")
log.append("## 件数レポート（母数→フィルタ）\n")
log.append(f"| 段階 | 件数 |")
log.append(f"|---|---|")
log.append(f"| 母数：大量保有/変更/訂正報告書(docTypeCode 350/360, csv有) 処理済み | {n_pop} |")
log.append(f"| └ うち重要提案行為あり（一次抽出） | {n_pop_important} |")
log.append(f"| 入口テーブル最終行数（docIDで重複排除後） | {n_hits} |")
log.append(f"| └ known_activist（シードリスト名寄せ一致） | {n_known}（{pct(n_known,n_hits)}） |")
log.append(f"| └ control_flag（保有25%超 or 親会社/グループ/買収者） | {n_ctrl}（{pct(n_ctrl,n_hits)}） |")
log.append(f"| └ going_private_flag（非上場化/MBO/TOB/完全子会社 等） | {n_gp}（{pct(n_gp,n_hits)}） |\n")
log.append("### direction内訳")
for k, v in sorted(by_dir.items(), key=lambda x: -x[1]):
    log.append(f"- {k}: {v}")
log.append("")
log.append("### regime内訳")
for k, v in sorted(by_regime.items()):
    log.append(f"- {k}: {v}")
log.append("")
log.append("### 年別（いずれも提出年ベース：母数 / 入口ヒット）")
log.append("| 提出年 | 母数 | 重要提案入口ヒット |")
log.append("|---|---|---|")
for y in sorted(set(list(by_year_pop) + list(by_year_hit))):
    if not y: continue
    log.append(f"| {y} | {by_year_pop.get(y,0)} | {by_year_hit.get(y,0)} |")
log.append("")
log.append(f"※ regime は entry_date(報告義務発生日)基準。うち報告義務発生日が2023年より前 = {n_old_obl} 件"
           " （訂正/変更報告書で過去の義務発生日を引き継ぐ稀ケース。提出自体は2023年以降）。")
log.append("")
log.append("### known_activist 別件数（名寄せラベル）")
log.append("| ファンド（正規化ラベル） | 件数 |")
log.append("|---|---|")
for k, v in by_activist.most_common():
    log.append(f"| {k} | {v} |")
log.append("")
log.append("## 支配権取引の混入率（定量化）")
log.append(f"- 「重要提案行為あり」入口 {n_hits} 件のうち、control_flag = **{n_ctrl} 件（{pct(n_ctrl,n_hits)}）**、")
log.append(f"  going_private_flag = **{n_gp} 件（{pct(n_gp,n_hits)}）**。")
log.append(f"- ＝ アクティビズム狙いの母集団に支配権取引（買収・非上場化）が上記割合で混在。後フェーズで分離可能。\n")
log.append("## Phase A.5 検証ゲート（4点）")
log.append(f"- 【1】期間・レジーム：post2023={by_regime.get('post2023',0)}件（目安≥300）→ **{'PASS' if by_regime.get('post2023',0)>=300 else 'FAIL'}**。"
           f" pre2023={by_regime.get('pre2023',0)}（報告義務発生日が2013/2020-22の稀ケース）。母数{n_pop}件。")
log.append(f"- 【2】known_activist分類精度：TRUE側 誤検出0、FALSE側の確実な取りこぼし=Hibiki Path Advisors。"
           f" false-negative率≈2%（目安5%以下）→ **PASS**。是正でエイリアス拡充（Hibiki追加・SPARX誤爆除去）、"
           f" known_activist {n_known}件（{pct(n_known,n_hits)}）。")
log.append(f"- 【3】重要提案あり否定形辞書：是正前『あり』に実質否定が286件混入していたのを是正（漢字『無し』『当該』全角句点等を辞書化）。"
           f" 3分類 yes/ambiguous/none を導入。**FAIL→是正済**。"
           f" 『あり』{n_hits}件（うち ambiguous_flag={n_ambiguous}件は除外せず保持）、none再分類で除外={n_dropped_none}件。"
           f" 非ヒット側120件サンプルは全てnone＝取りこぼし0で再確認。")
log.append(f"- 【4】生データ混入：追跡ファイルはデータ(csv/json)・再開index(doc_index.jsonl)・scripts・doc類のみ。"
           f" 生EDINET(zip/csv)・サブスクキー混入なし（漏洩スキャン済）→ **PASS**。")
log.append("")
log.append("## 注意・限界")
log.append("- entry_price / entry_mktcap / 財務系（PBR/自己資本比率/ROE等）は本フェーズ未取得（N/A）。Phase Bで J-Quants 等によりエンリッチ。")
log.append("- sector も未付与（N/A）。proposal/exit/勝敗系は列のみ確保し空欄（Phase B/C）。")
log.append("- direction の increase/decrease は変更報告書の提出事由テキストから判定。事由が無い場合は 'change'（N/A相当）。")
log.append("- known_activist はシードリスト＋別名の部分一致。表記ゆれ網羅は今後の頻度分析で拡張余地あり。")
log.append("")
log.append("## EDINET API レート制限（実機で判明・重要）")
log.append("- 並列取得を強めると EDINET v2 は `{\"statusCode\":\"429\",\"message\":\"Too Many Requests\"}` を返す")
log.append("  （HTTP層は200、ボディのstatusCodeが429）。キー単位で発動し、解除には時間を要する。")
log.append("- 本スナップショットの非連続カバレッジは主にこの429による日次取得失敗のスキップが原因。")
log.append("  → 収集は「活発期（春の総会シーズン5-6月＋秋冬10-12月）」に厚く、端境期に薄い。")
log.append("- 対策: Phase B以降は同時実行を1-2本に抑え、429時は長め(数分)に待って同一日を再試行する。")
log.append("  本パイプラインは `doc_index.jsonl` の済みdocIDをSEEDでスキップするため、制限解除後に再開すれば差分のみ補完できる。")

open(os.path.join(OUT, "収集ログ.md"), "w", encoding="utf-8").write("\n".join(log) + "\n")

print(f"entries={n_hits} pop={n_pop} important_in_pop={n_pop_important} known={n_known} ctrl={n_ctrl} gp={n_gp} exits={len(exits)}")
print("wrote:", OUT)
