#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EDINET 大量保有報告書 入口データ収集 (Phase A).
Key is read from env EDINET_KEY (never hard-coded).
Outputs append incrementally so long runs survive interruption.
"""
import os, sys, json, csv, io, time, zipfile, urllib.request, urllib.error, unicodedata, datetime, re

KEY = os.environ["EDINET_KEY"]
BASE = "https://api.edinet-fsa.go.jp/api/v2"
OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/out"
os.makedirs(OUT, exist_ok=True)
INDEX_PATH = os.path.join(OUT, "doc_index.jsonl")      # every 350/360 doc seen (母数)
ENTRIES_PATH = os.path.join(OUT, "entries.jsonl")      # important-proposal hits (full rows)

DOCTYPES = {"350", "360"}  # 350=大量保有/変更, 360=訂正

def http_get(url, retries=4):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "phaseA/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise last

def list_day(date, retries=6):
    """Return results list on success, [] on genuinely-empty 200, None if the
    day could not be fetched (non-200 / throttle) after retries."""
    url = f"{BASE}/documents.json?date={date}&type=2&Subscription-Key={KEY}"
    last_status = None
    for i in range(retries):
        try:
            d = json.loads(http_get(url, retries=2).decode("utf-8"))
        except Exception:
            time.sleep(3 * (i + 1)); continue
        st = d.get("metadata", {}).get("status")
        last_status = st
        if st == "200":
            return d.get("results", [])
        # non-200 (often throttle) -> back off and retry
        time.sleep(3 * (i + 1))
    print(f"[FAIL] {date} list_day status={last_status} after {retries} tries", flush=True)
    return None

def fetch_csv_rows(docID):
    url = f"{BASE}/documents/{docID}?type=5&Subscription-Key={KEY}"
    raw = http_get(url)
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        return None
    names = [n for n in zf.namelist() if n.upper().endswith(".CSV") and "XBRL_TO_CSV" in n.upper()]
    if not names:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    if not names:
        return None
    data = zf.read(names[0])
    text = data.decode("utf-16")
    return list(csv.reader(io.StringIO(text), delimiter="\t"))

def build_map(rows):
    """element_id -> list of values (in order)."""
    m = {}
    for r in rows[1:]:
        if len(r) >= 9:
            m.setdefault(r[0], []).append(r[8])
    return m

def first(m, key, default="N/A"):
    vals = m.get(key)
    if not vals:
        return default
    for v in vals:
        if v is not None and v.strip() not in ("", "－", "-"):
            return v.strip()
    return vals[0].strip() if vals[0] else default

def is_na_text(v):
    """True if the value is an empty / 'not applicable' style placeholder."""
    s = re.sub(r"\s", "", v or "")
    if s in ("", "－", "-", "―", "—"):
        return True
    # 該当事項なし / 該当事項はありません / 該当事項はございません / 該当なし / 特になし / ありません
    if re.match(r"^該当(事項)?(は)?(あり|ござい)?ま?せん。?$", s):
        return True
    if s in ("該当なし", "該当なし。", "なし", "特になし", "特になし。", "該当事項なし", "該当事項なし。"):
        return True
    return False

def has_important_proposal(m):
    """A doc is an 'あり' candidate when the ActOfMakingImportantProposalEtc value
    classifies as yes or ambiguous (not a 実質否定). Uses flags.classify_proposal."""
    import flags as _F
    vals = m.get("jplvh_cor:ActOfMakingImportantProposalEtc", [])
    best = ""
    for v in vals:
        s = (v or "").strip()
        cls = _F.classify_proposal(s)
        if cls in ("yes", "ambiguous"):
            return True, s
        if s and not best:
            best = s
    return False, best

# ---- activist seed list (aliases, NFKC-normalized, casefolded substring match) ----
ACTIVIST_ALIASES = {
    "AVI/AssetValueInvestors": ["asset value investors", "ＡＶＩ", "avi japan", "aviジャパン", "avi global"],
    "Oasis": ["oasis management", "オアシス", "oasis investments", "oasis japan"],
    "Effissimo": ["effissimo", "エフィッシモ"],
    "3D Investment": ["3d investment", "3d opportunity", "スリーディー", "3dインベストメント"],
    "Dalton/NipponActiveValue": ["dalton", "ダルトン", "nippon active value", "ニッポン・アクティブ・バリュー", "navf"],
    "Kaname Capital": ["kaname", "カナメ"],
    "Strategic Capital": ["strategic capital", "ストラテジックキャピタル", "ストラテジック・キャピタル", "ストラテジックキヤピタル"],
    "Murakami(CityIndex/Reno)": ["シティインデックスイレブンス", "city index", "レノ", "reno", "エスグラント", "南青山不動産", "野村絢", "村上世彰", "村上絢", "オフィスサポート", "リビモ", "ＲＥＮＯ"],
    "ValueAct": ["valueact", "バリューアクト"],
    "Elliott": ["elliott", "エリオット"],
    "Taiyo": ["taiyo pacific", "タイヨウ", "taiyo fund"],
    "Silchester": ["silchester", "シルチェスター"],
    "Farallon": ["farallon", "ファラロン"],
    "RMB/PalliserMisc": ["palliser", "パリサー"],
    "Tokio/MISC": [],
}

def norm(s):
    return unicodedata.normalize("NFKC", s or "").casefold()

def known_activist(fund_name):
    n = norm(fund_name)
    for label, aliases in ACTIVIST_ALIASES.items():
        for a in aliases:
            if a and norm(a) in n:
                return label
    return ""

GP_KW = ["非上場化", "非公開化", "上場廃止", "ＭＢＯ", "mbo", "株式併合", "スクイーズアウト", "スクイズアウト",
         "公開買付", "公開買付け", "ＴＯＢ", "完全子会社", "完全子会社化"]
def kw_hit(text, kws):
    t = norm(text)
    return [k for k in kws if norm(k) in t]

def purpose_flags(text):
    t = norm(text)
    flags = []
    if any(norm(k) in t for k in ["増配", "配当", "株主還元", "減配"]): flags.append("増配")
    if any(norm(k) in t for k in ["自己株式", "自社株", "自己株式取得", "自社株買"]): flags.append("自社株")
    if any(norm(k) in t for k in ["取締役", "役員", "選任", "取締役会", "監査役"]): flags.append("取締役選任")
    if any(norm(k) in t for k in ["事業売却", "譲渡", "事業分割", "資産売却", "事業の売却"]): flags.append("事業売却")
    if kw_hit(text, GP_KW): flags.append("非上場化")
    return flags

def to_pct(v):
    try:
        return round(float(v) * 100, 4)
    except Exception:
        return "N/A"

def norm_ticker(code):
    c = (code or "").strip()
    if not c or c in ("－", "-"):
        return "N/A"
    c = unicodedata.normalize("NFKC", c)
    if len(c) == 5 and c.endswith("0"):
        return c[:4]
    return c

def direction_of(title, change_reason):
    t = title or ""
    if "訂正" in t:
        return "amend"
    if "変更報告書" in t:
        r = change_reason or ""
        if "減少" in r: return "decrease"
        if "増加" in r: return "increase"
        return "change"
    if "大量保有報告書" in t:
        return "new"
    return "N/A"

def process(meta):
    docID = meta["docID"]
    rows = fetch_csv_rows(docID)
    if rows is None:
        return None
    m = build_map(rows)
    has_imp, imp_text = has_important_proposal(m)

    fund = first(m, "jplvh_cor:Name", first(m, "jpdei_cor:FilerNameInJapaneseDEI"))
    issuer = first(m, "jplvh_cor:NameOfIssuer")
    ticker = norm_ticker(first(m, "jplvh_cor:SecurityCodeOfIssuer", ""))
    pct = to_pct(first(m, "jplvh_cor:HoldingRatioOfShareCertificatesEtc", ""))
    entry_date = first(m, "jplvh_cor:DateWhenFilingRequirementAroseCoverPage")
    filing_date = first(m, "jplvh_cor:FilingDateCoverPage")
    title = first(m, "jplvh_cor:DocumentTitleCoverPage")
    purpose = first(m, "jplvh_cor:PurposeOfHolding")
    change_reason = first(m, "jplvh_cor:ReasonForFilingChangeReportCoverPage", "")
    shares = first(m, "jplvh_cor:TotalNumberOfStocksEtcHeld", "N/A")
    outstanding = first(m, "jplvh_cor:TotalNumberOfOutstandingStocksEtc", "N/A")
    indiv = first(m, "jplvh_cor:IndividualOrCorporation", "N/A")
    edinet_code = first(m, "jpdei_cor:EDINETCodeDEI", meta.get("edinetCode") or "N/A")

    rec = {
        "docID": docID, "docTypeCode": meta.get("docTypeCode"),
        "formCode": meta.get("formCode"), "ordinanceCode": meta.get("ordinanceCode"),
        "submitDateTime": meta.get("submitDateTime"),
        "fund_name": fund, "filer_edinet": edinet_code, "issuer_name": issuer, "ticker": ticker,
        "entry_date": entry_date, "filing_date": filing_date, "doc_title": title,
        "entry_holding_pct": pct, "shares_held": shares, "outstanding": outstanding,
        "indiv_corp": indiv, "purpose": purpose, "change_reason": change_reason,
        "important_proposal": has_imp, "important_text": imp_text,
    }
    return rec

def to_entry_row(rec):
    """Map a parsed rec to the Phase A schema (entry columns filled, later blank)."""
    fund = rec["fund_name"]
    ka = known_activist(fund)
    purpose = rec["purpose"]
    imp = rec["important_text"]
    combo = (purpose or "") + " " + (imp or "")
    pf = purpose_flags(combo)
    gp = kw_hit(combo, GP_KW)
    pct = rec["entry_holding_pct"]
    try:
        ctrl = (isinstance(pct, (int, float)) and pct >= 25.0)
    except Exception:
        ctrl = False
    ctrl = ctrl or bool(kw_hit(combo, ["完全子会社", "子会社化", "グループ会社", "親会社", "買収", "ＳＰＣ", "特別目的会社"]))
    ed = rec["entry_date"]
    regime = "pre2023"
    try:
        regime = "pre2023" if int(ed[:4]) < 2023 else "post2023"
    except Exception:
        pass
    direction = direction_of(rec["doc_title"], rec["change_reason"])
    docID = rec["docID"]
    return {
        "fund_name": fund,
        "fund_known_activist": bool(ka),
        "activist_label": ka or "",
        "issuer_name": rec["issuer_name"],
        "ticker": rec["ticker"],
        "sector": "N/A",
        "regime": regime,
        "entry_date": ed,
        "entry_filing_id": docID,
        "entry_holding_pct": pct,
        "entry_price": "N/A",
        "entry_mktcap": "N/A",
        "filing_purpose_text": purpose,
        "purpose_flags": "|".join(pf),
        "important_proposal_text": imp,
        "direction": direction,
        "control_flag": bool(ctrl),
        "going_private_flag": bool(gp),
        "going_private_kw": "|".join(gp),
        "source_url": f"https://api.edinet-fsa.go.jp/api/v2/documents/{docID}?type=2",
        "submit_datetime": rec["submitDateTime"],
        "shares_held": rec["shares_held"],
        "outstanding_shares": rec["outstanding"],
        "indiv_corp": rec["indiv_corp"],
        "doc_title": rec["doc_title"],
        "filer_edinet": rec["filer_edinet"],
        # later-phase blanks
        "entry_pbr": "", "entry_equity_ratio": "", "entry_net_cash_ratio": "", "entry_roe": "", "stable_holder_pct": "",
        "proposal_made": "", "proposal_type": "", "agm_result": "", "company_response": "",
        "exit_date": "", "exit_filing_id": "", "exit_price": "", "holding_months": "",
        "entry_to_exit_return": "", "trap_label": "", "exit_reason": "",
        "notes": "",
    }

def daterange(start, end):
    d = start
    one = datetime.timedelta(days=1)
    while d <= end:
        yield d
        d += one

def load_done():
    """Done docIDs from this run's index + any SEED index files (glob/space-sep)."""
    import glob as _glob
    done = set()
    paths = [INDEX_PATH]
    seed = os.environ.get("SEED", "")
    for pat in seed.split():
        paths.extend(_glob.glob(pat))
    for p in paths:
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                try:
                    done.add(json.loads(line)["docID"])
                except Exception:
                    pass
    return done

def main():
    start = datetime.date.fromisoformat(os.environ.get("START", "2025-01-01"))
    end = datetime.date.fromisoformat(os.environ.get("END", "2025-12-31"))
    # iterate most-recent first
    days = list(daterange(start, end))[::-1]
    done = load_done()
    idx_f = open(INDEX_PATH, "a", encoding="utf-8")
    ent_f = open(ENTRIES_PATH, "a", encoding="utf-8")
    n_docs = n_hits = 0
    for d in days:
        ds = d.isoformat()
        try:
            results = list_day(ds)
        except Exception as e:
            print(f"[WARN] {ds} list failed: {e}", flush=True)
            continue
        if not results:
            continue
        targets = [r for r in results if r.get("docTypeCode") in DOCTYPES and r.get("csvFlag") == "1"]
        for meta in targets:
            if meta["docID"] in done:
                continue
            try:
                rec = process(meta)
            except Exception as e:
                print(f"[WARN] {meta['docID']} process failed: {e}", flush=True)
                continue
            if rec is None:
                continue
            done.add(meta["docID"])
            idx_f.write(json.dumps({"docID": rec["docID"], "docTypeCode": rec["docTypeCode"],
                                    "important": rec["important_proposal"], "date": ds,
                                    "fund": rec["fund_name"], "issuer": rec["issuer_name"]}, ensure_ascii=False) + "\n")
            n_docs += 1
            if rec["important_proposal"]:
                ent_f.write(json.dumps(to_entry_row(rec), ensure_ascii=False) + "\n")
                n_hits += 1
            time.sleep(0.12)
        idx_f.flush(); ent_f.flush()
        print(f"[{ds}] cum_docs={n_docs} cum_hits={n_hits}", flush=True)
    idx_f.close(); ent_f.close()
    print(f"DONE docs={n_docs} hits={n_hits}", flush=True)

if __name__ == "__main__":
    main()
