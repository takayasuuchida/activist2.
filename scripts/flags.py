# -*- coding: utf-8 -*-
"""Shared flag/normalization logic. Recomputed at finalize time so the seed
list can be expanded retroactively over already-collected raw data."""
import unicodedata, re

# Known activist / engagement funds active in Japan.
# Seed list (task) + frequency-grown additions. Substring match on NFKC-casefold.
ACTIVIST_ALIASES = {
    "AVI/AssetValueInvestors": ["asset value investors", "ＡＶＩ", "avi japan", "avi global"],
    "Oasis": ["oasis management", "オアシス", "oasis investments", "oasis japan"],
    "Effissimo": ["effissimo", "エフィッシモ"],
    "3D Investment": ["3d investment", "3d opportunity", "スリーディー", "3dインベストメント", "３Ｄインベストメント"],
    "Dalton/NipponActiveValue": ["dalton", "ダルトン", "nippon active value", "ニッポン・アクティブ・バリュー", "navf"],
    "Kaname Capital": ["kaname", "カナメ・キャピタル", "カナメキャピタル"],
    "Strategic Capital": ["strategic capital", "ストラテジックキャピタル", "ストラテジック・キャピタル", "ストラテジックキヤピタル"],
    "Murakami(CityIndex/Reno)": ["シティインデックスイレブンス", "city index", "レノ", "reno", "エスグラント",
                                  "南青山不動産", "野村絢", "村上世彰", "村上絢", "オフィスサポート", "リビモ", "ＲＥＮＯ"],
    "ValueAct": ["valueact", "バリューアクト"],
    "Elliott": ["elliott", "エリオット"],
    "Taiyo": ["taiyo pacific", "タイヨウ", "taiyo fund"],
    "Silchester": ["silchester", "シルチェスター"],
    "Farallon": ["farallon", "ファラロン"],
    "Palliser": ["palliser", "パリサー"],
    # --- frequency-grown additions (Japan engagement/activist funds) ---
    "Valex Partners": ["ヴァレックス", "valex"],
    "Symphony Financial": ["シンフォニー・フィナンシャル", "シンフォニーフィナンシャル", "symphony financial"],
    "Epic Partners": ["エピック・パートナーズ", "エピックパートナーズ", "epic partners"],
    "Misaki Capital": ["みさき", "misaki"],
    "Ichigo Asset": ["いちごアセット", "ichigo asset", "ichigo trust"],
    "LIM Advisors": ["リム・アドバイザーズ", "lim advisors"],
    "Pilgrim/NipponValueInvestors": ["pilgrim partners", "ピルグリム・パートナーズ"],
    "Hibiki Path Advisors": ["ひびき・パース", "ひびきパース", "hibiki path"],
}

def norm(s):
    return unicodedata.normalize("NFKC", s or "").casefold()

# ---- 重要提案行為テキストの3分類: none(実質否定) / ambiguous(曖昧) / yes(あり) ----
def _strip_punct(t):
    t = unicodedata.normalize("NFKC", t or "")
    return re.sub(r"[\s。、，．\.,；;：:｡､・　]", "", t)

_NEG_RE = [
    r"^(該当|当該)\S{0,6}(ありません|ございません|有りません|なし|無し|無)$",
    r"^(記載事項|特記事項|重要事項|重要な事項)\S{0,4}(ありません|ございません|なし|無し|無)$",
    r"^特に(ありません|ございません|なし|無し)$",
    r"^(なし|無し|無|非該当|該当なし|特記なし|なし\.)$",
    r"^重要提案行為\S{0,8}(ありません|ございません)$",
    r"^[ー－—―\-]+$",
]
# affirmative intent markers -> genuine "yes" (override ambiguous cross-refs)
_AFFIRM_KW = ["行う可能性", "可能性がある", "可能性あり", "可能性有", "行うことがある", "行うことがあり",
              "行うことがあります", "行う場合がある", "行うこともあり", "行う予定である", "行うことを予定",
              "指名提案", "選任を求", "解任を求", "株主提案", "提案を行", "を求めてまいり", "を求めていく"]
_AMBIG_KW = ["予定はありません", "予定はございません", "予定はない", "予定なし",
             "計画はありません", "計画はない", "計画はございません", "具体的な計画", "具体的計画",
             "未定", "検討中", "検討しており", "記載のとおり", "記載の通り", "上記のとおり",
             "上記の通り", "下記のとおり", "保有目的に記載", "上記（", "上記(2", "上記２", "上記２）"]

def classify_proposal(text):
    """Return 'none' | 'ambiguous' | 'yes' for an ActOfMakingImportantProposalEtc value.
    Order: empty->none; affirmative intent->yes; undecided/cross-ref->ambiguous;
    pure-negation pattern->none; else yes."""
    if text is None:
        return "none"
    nt = unicodedata.normalize("NFKC", text)
    s = _strip_punct(text)
    if not s:
        return "none"
    if any(k in nt for k in _AFFIRM_KW):
        return "yes"
    if any(k in nt for k in _AMBIG_KW):
        return "ambiguous"
    for p in _NEG_RE:
        if re.match(p, s):
            return "none"
    return "yes"

def known_activist(fund_name):
    n = norm(fund_name)
    for label, aliases in ACTIVIST_ALIASES.items():
        for a in aliases:
            if a and norm(a) in n:
                return label
    return ""

GP_KW = ["非上場化", "非公開化", "上場廃止", "ＭＢＯ", "mbo", "株式併合", "スクイーズアウト", "スクイズアウト",
         "公開買付", "公開買付け", "ＴＯＢ", "完全子会社", "完全子会社化"]
CTRL_KW = ["完全子会社", "子会社化", "グループ会社", "親会社", "買収", "ＳＰＣ", "特別目的会社", "持分法適用"]

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

def compute_flags(fund_name, purpose, important_text, holding_pct):
    """Return dict of recomputed flags from raw fields."""
    combo = (purpose or "") + " " + (important_text or "")
    ka = known_activist(fund_name)
    pf = purpose_flags(combo)
    gp = kw_hit(combo, GP_KW)
    try:
        ctrl = isinstance(holding_pct, (int, float)) and holding_pct >= 25.0
    except Exception:
        ctrl = False
    ctrl = bool(ctrl or kw_hit(combo, CTRL_KW))
    return {
        "fund_known_activist": bool(ka),
        "activist_label": ka or "",
        "purpose_flags": "|".join(pf),
        "going_private_flag": bool(gp),
        "going_private_kw": "|".join(gp),
        "control_flag": ctrl,
    }
