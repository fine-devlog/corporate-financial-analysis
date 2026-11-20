"""EDINET（有価証券報告書）→ Supabase 取り込みスクリプト

Streamlitアプリとは別に、手元 or GitHub Actions などで定期実行する。

必要な環境変数:
  EDINET_API_KEY             EDINET API v2 の Subscription-Key
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY  ※ Supabase の Secret key（sb_secret_...、旧 service_role キー）。Streamlit の secrets には入れないこと

事前準備:
  supabase_schema.sql を Supabase の SQL Editor で実行しておく
  （companies.edinet_code の UNIQUE 制約が無いと upsert が失敗する）

使い方:
  # 動作確認（DBには書かない）
  python edinet_ingest.py --start 2026-06-25 --end 2026-06-26 --dry-run

  # 初回バックフィル（3月決算の有報提出ピーク前後）
  python edinet_ingest.py --start 2026-06-15 --end 2026-07-05

  # 日次/週次の更新（引数なし＝直近14日）
  python edinet_ingest.py

  # 取り込み済みでも再取得して上書き（抽出ロジックを直したとき）
  python edinet_ingest.py --start 2026-06-15 --end 2026-07-05 --force

  # 要素IDの確認（XBRLタグが想定と合っているかを見る）
  python edinet_ingest.py --inspect S100XXXX

  # コードリストを手動ダウンロードした場合
  python edinet_ingest.py --codelist-file Edinetcode.zip

依存: pip install requests pandas supabase
"""
import argparse
import io
import logging
import os
import re
import sys
import time
import unicodedata
import zipfile
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import requests

API_BASE = "https://api.edinet-fsa.go.jp/api/v2"
CODELIST_URL = "https://disclosure2dl.edinet-fsa.go.jp/searchdocument/codelist/Edinetcode.zip"
SLEEP_SEC = 0.5  # APIへの負荷を抑える
DOC_TYPE_YUHO = "120"  # 有価証券報告書
ORDINANCE_CORPORATE = "010"  # 企業内容等の開示に関する内閣府令（＝事業会社。投信・外国会社などを除外）
UPSERT_BATCH = 50

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("edinet")

# --------------------------------------------------------------------------
# 業種マッピング（EDINETの「提出者業種」→ アプリの16業界）
# ※「その他製品」（任天堂・ヤマハ等）はどの業界にも当てはまらないため対象外にしている
# --------------------------------------------------------------------------
INDUSTRY_MAP = {
    "電気機器": "1.電機・電子機器",
    "精密機器": "1.電機・電子機器",
    "情報・通信業": "2.IT・ソフト・SI",
    "化学": "4.化学",
    "ゴム製品": "4.化学",
    "ガラス・土石製品": "4.化学",
    "パルプ・紙": "4.化学",
    "医薬品": "5.医薬・バイオ",
    "食料品": "6.食品",
    "水産・農林業": "6.食品",
    "繊維製品": "7.アパレル・繊維",
    "機械": "8.機械・重工業",
    "金属製品": "8.機械・重工業",
    "輸送用機器": "9.輸送用機器",
    "鉄鋼": "10.鉄鋼・非鉄金属",
    "非鉄金属": "10.鉄鋼・非鉄金属",
    "鉱業": "11.エネルギー・資源",
    "石油・石炭製品": "11.エネルギー・資源",
    "電気・ガス業": "11.エネルギー・資源",
    "卸売業": "12.商社",
    "銀行業": "13.金融",
    "証券、商品先物取引業": "13.金融",
    "保険業": "13.金融",
    "その他金融業": "13.金融",
    "建設業": "14.建設・不動産",
    "不動産業": "14.建設・不動産",
    "小売業": "15.小売",
    "サービス業": "16.サービス・運輸・レジャー",
    "陸運業": "16.サービス・運輸・レジャー",
    "海運業": "16.サービス・運輸・レジャー",
    "空運業": "16.サービス・運輸・レジャー",
    "倉庫・運輸関連": "16.サービス・運輸・レジャー",  # 【修正】コードリスト上の表記は「業」なし（実データで確認）
}
# 「情報・通信業」は IT と通信が混在する。基本は事業の内容の文章で判定し（classify_information_company）、
# 文章だけでは判定しにくい会社だけ証券コード（4桁）で指定する。
SEC_CODE_OVERRIDE = {
    "9432": "3.通信",  # NTT
    "9433": "3.通信",  # KDDI
    "9434": "3.通信",  # ソフトバンク
    "9436": "3.通信",  # 沖縄セルラー電話
    "9435": "3.通信",  # 光通信（通信回線・携帯の販売）
    "3843": "3.通信",  # フリービット（ISP・MVNO）
    "147A": "3.通信",  # ソラコム（IoT通信）
}

# --------------------------------------------------------------------------
# XBRL要素ID（CSV形式の「要素ID」列）。会計基準違いに備えて候補を複数並べる。
# ※ 想定と違う場合は --inspect で実際のIDを確認して追加すること。
#   存在しないIDを並べても「見つからない」だけで害はない。
# --------------------------------------------------------------------------
P = "jpcrp_cor:"
SUFFIX_EMP = "InformationAboutReportingCompanyInformationAboutEmployees"
SALARY_IDS = [P + "AverageAnnualSalary" + SUFFIX_EMP]
AGE_IDS = [P + "AverageAgeYears" + SUFFIX_EMP]
AGE_MONTHS_IDS = [P + "AverageAgeMonths" + SUFFIX_EMP]  # 「41歳3ヶ月」形式で開示する会社用
TENURE_IDS = [P + "AverageLengthOfServiceYears" + SUFFIX_EMP]
TENURE_MONTHS_IDS = [P + "AverageLengthOfServiceMonths" + SUFFIX_EMP]

REVENUE_IDS = [
    P + "NetSalesSummaryOfBusinessResults",
    P + "RevenueIFRSSummaryOfBusinessResults",
    P + "RevenuesUSGAAPSummaryOfBusinessResults",
    P + "OperatingRevenue1SummaryOfBusinessResults",
    P + "OperatingRevenue2SummaryOfBusinessResults",
    "jppfs_cor:NetSales",
    "jpigp_cor:RevenueIFRS",
]
OPERATING_INCOME_IDS = [
    "jppfs_cor:OperatingIncome",
    "jpigp_cor:OperatingProfitLossIFRS",
]
OPERATING_CF_IDS = [
    P + "NetCashProvidedByUsedInOperatingActivitiesSummaryOfBusinessResults",
    P + "CashFlowsFromUsedInOperatingActivitiesIFRSSummaryOfBusinessResults",
    P + "CashFlowsFromUsedInOperatingActivitiesUSGAAPSummaryOfBusinessResults",
    "jppfs_cor:NetCashProvidedByUsedInOperatingActivities",
    "jpigp_cor:NetCashProvidedByUsedInOperatingActivitiesIFRS",
]

# AI要約用の文章（テキストブロック）。company_texts テーブルに保存する。
TEXT_BLOCK_IDS = {
    "business_description": [P + "DescriptionOfBusinessTextBlock"],
    "management_policy": [P + "BusinessPolicyBusinessEnvironmentIssuesToAddressEtcTextBlock"],
    "business_risks": [P + "BusinessRisksTextBlock"],
}


# --------------------------------------------------------------------------
# EDINET コードリスト
# --------------------------------------------------------------------------
def load_codelist(path: str | None) -> pd.DataFrame:
    """上場企業の EDINETコード / 社名 / 業種 / 証券コード を返す。"""
    if path:
        with open(path, "rb") as f:
            raw = f.read()
    else:
        r = requests.get(CODELIST_URL, timeout=120)
        r.raise_for_status()
        raw = r.content
    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
            raw = z.read(name)

    # 1行目はダウンロード日などのメタ情報、2行目がヘッダー
    df = pd.read_csv(io.BytesIO(raw), encoding="cp932", skiprows=1, dtype=str)
    df.columns = [unicodedata.normalize("NFKC", c) for c in df.columns]  # ＥＤＩＮＥＴ → EDINET
    df = df[df["上場区分"] == "上場"].copy()
    df = df.rename(columns={"EDINETコード": "edinet_code", "提出者名": "name", "提出者業種": "edinet_industry"})
    df["sec_code4"] = df["証券コード"].fillna("").str[:4]
    df["industry"] = df.apply(
        lambda r: SEC_CODE_OVERRIDE.get(r["sec_code4"]) or INDUSTRY_MAP.get(r["edinet_industry"]), axis=1
    )
    unmapped = df[df["industry"].isna()]
    if len(unmapped):
        log.info(
            "業界マッピング対象外: %d社（例: %s）",
            len(unmapped), ", ".join(unmapped["edinet_industry"].dropna().unique()[:8]),
        )
    out = df.dropna(subset=["industry"])[["edinet_code", "name", "industry", "sec_code4", "edinet_industry"]]
    # 【修正】万一コードが重複していると codes.loc[...] が Series を返して壊れるので除去
    return out.drop_duplicates(subset=["edinet_code"])


# --------------------------------------------------------------------------
# EDINET API
# --------------------------------------------------------------------------
class EdinetApiError(RuntimeError):
    pass


def _raise_if_api_error(r: requests.Response):
    """【修正】EDINET は HTTP 200 のまま JSON でエラー（キー不正の 401 など）を返すことがあるので本文も確認する。"""
    r.raise_for_status()
    if "json" not in (r.headers.get("Content-Type") or "").lower():
        return
    try:
        body = r.json()
    except ValueError:
        return
    status = str(body.get("StatusCode") or body.get("statusCode") or (body.get("metadata") or {}).get("status") or "200")
    if status != "200":
        message = body.get("message") or (body.get("metadata") or {}).get("message") or body
        raise EdinetApiError(f"EDINET API エラー status={status}: {message}")


def list_yuho(day: date, key: str) -> list[dict]:
    r = requests.get(
        f"{API_BASE}/documents.json",
        params={"date": day.isoformat(), "type": 2, "Subscription-Key": key},
        timeout=60,
    )
    _raise_if_api_error(r)
    out = []
    for d in r.json().get("results") or []:
        if d.get("docTypeCode") != DOC_TYPE_YUHO:
            continue
        if d.get("ordinanceCode") not in (None, ORDINANCE_CORPORATE):
            continue
        if not d.get("secCode") or d.get("withdrawalStatus") != "0":
            continue
        if d.get("csvFlag") != "1":
            continue
        out.append(d)
    return out


def download_csv_zip(doc_id: str, key: str) -> bytes:
    r = requests.get(
        f"{API_BASE}/documents/{doc_id}",
        params={"type": 5, "Subscription-Key": key},  # 5 = XBRL to CSV
        timeout=180,
    )
    _raise_if_api_error(r)
    if r.content[:2] != b"PK":
        raise EdinetApiError(f"ZIPではない応答が返りました（先頭: {r.content[:80]!r}）")
    return r.content


def read_xbrl_csv(zip_bytes: bytes) -> pd.DataFrame | None:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        # 【修正】監査報告書(jpaud)を除き、本体(jpcrp...-asr)を優先
        names = sorted(
            (n for n in z.namelist() if n.lower().endswith(".csv") and "jpcrp" in n.lower()),
            key=lambda n: ("asr" not in n.lower(), n),
        )
        if not names:
            return None
        raw = z.read(names[0])
    return pd.read_csv(io.BytesIO(raw), encoding="utf-16", sep="\t", dtype=str)


# --------------------------------------------------------------------------
# 指標の抽出
# --------------------------------------------------------------------------
def _to_float(s):
    if s is None:
        return None
    s = str(s).replace(",", "").strip()
    if s in ("", "－", "-", "―", "nan"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _first_value(sub: pd.DataFrame):
    """コンテキストIDが短い行（＝セグメント等の軸が付いていない全体値）を優先して値を返す。"""
    if sub.empty:
        return None
    sub = sub.assign(_len=sub["コンテキストID"].fillna("").str.len()).sort_values("_len", kind="stable")
    for v in sub["値"]:
        f = _to_float(v)
        if f is not None:
            return f
    return None


def _scope_mask(context_ids: pd.Series, scope: str) -> pd.Series:
    """連結/個別をコンテキストIDで判定する。

    【修正】実データでは「主要な経営指標等の推移」(…SummaryOfBusinessResults) の行の「連結・個別」列が
    「その他」になっており、列で絞ると一致しなかった。コンテキストIDなら確実に分かる:
      連結 = 軸なし（例 CurrentYearDuration）／ 個別 = 個別軸のみ（例 CurrentYearDuration_NonConsolidatedMember）
    セグメント等の別の軸が付いた行は、どちらにも含めない（＝会社全体の値だけを使う）。
    """
    ctx = context_ids.fillna("")
    if scope == "個別":
        return ctx.str.fullmatch(r"[A-Za-z0-9]+_NonConsolidatedMember")
    return ~ctx.str.contains("_")


def pick(df: pd.DataFrame, element_ids, years=None, scope=None):
    for eid in element_ids:
        sub = df[df["要素ID"] == eid]
        if years:
            sub = sub[sub["相対年度"].isin(years)]
        if scope:
            sub = sub[_scope_mask(sub["コンテキストID"], scope)]
        v = _first_value(sub)
        if v is not None:
            return v
    return None


def _pct(numerator, denominator):
    # 【修正】売上がマイナス/0 のときは比率が意味を持たない
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return round(numerator / denominator * 100, 1)


def _growth(cur, prev):
    # 前期が0以下だと成長率が意味を持たないため「データなし」にする
    if cur is None or prev is None or prev <= 0:
        return None
    return round((cur - prev) / prev * 100, 1)


def _years_with_months(years, months):
    """「41歳3ヶ月」のように年と月が別要素で開示される場合に 41.25 にまとめる。"""
    if years is None:
        return None
    if months is not None and float(years).is_integer() and 0 <= months < 12:
        years = years + months / 12
    return round(years, 1)


PLAUSIBLE_SALARY_MAN = (100, 4000)   # これを外れたら単位の付け間違いを疑う
CORRECTED_SALARY_MAN = (200, 2500)   # 10の累乗で補正するときに収まるべき範囲


def normalize_salary_man(salary_yen):
    """平均年間給与（円）を万円にする。

    【修正】実データで「875,900万円」「0.5万円」のような値があった。XBRLで単位（千円/円）の
    付け方を誤った提出書類で、桁が10の累乗だけずれている。ありえない値のときは、
    10の累乗で割る/掛けて自然な範囲に入る最小の補正を採用し、どうしても入らなければ空欄にする。
    """
    if salary_yen is None:
        return None
    man = salary_yen / 10000
    low, high = PLAUSIBLE_SALARY_MAN
    if low <= man <= high:
        return round(man, 1)
    for k in sorted(range(-6, 7), key=abs):
        fixed = man * (10 ** k)
        if CORRECTED_SALARY_MAN[0] <= fixed <= CORRECTED_SALARY_MAN[1]:
            log.info("年収の単位補正: %s万円 → %s万円", round(man, 1), round(fixed, 1))
            return round(fixed, 1)
    return None


def extract_metrics(df: pd.DataFrame) -> dict:
    # 従業員の状況は提出会社（単体）の値。年・連結区分の指定なし
    salary = pick(df, SALARY_IDS)
    age = _years_with_months(pick(df, AGE_IDS), pick(df, AGE_MONTHS_IDS))
    tenure = _years_with_months(pick(df, TENURE_IDS), pick(df, TENURE_MONTHS_IDS))

    # 【修正】旧版は項目ごとに「連結→個別」とフォールバックしていたため、
    #   売上=連結・営業利益=個別 のような混在が起き、営業利益率が壊れることがあった。
    #   売上高が取れた区分（連結 or 個別）に固定して、他の財務項目も同じ区分から取る。
    rev = rev_prev = op = op_prev = cfo = None
    for scope in ("連結", "個別"):
        rev = pick(df, REVENUE_IDS, years=("当期",), scope=scope)
        if rev is None:
            continue
        rev_prev = pick(df, REVENUE_IDS, years=("前期",), scope=scope)
        op = pick(df, OPERATING_INCOME_IDS, years=("当期",), scope=scope)
        op_prev = pick(df, OPERATING_INCOME_IDS, years=("前期",), scope=scope)
        cfo = pick(df, OPERATING_CF_IDS, years=("当期",), scope=scope)
        break

    return {
        "income": normalize_salary_man(salary),  # 円 → 万円（単位の付け間違いを補正）
        "age": age if age is not None and 18 <= age <= 75 else None,
        "avg_tenure": tenure if tenure is not None and 0 <= tenure <= 50 else None,
        "operating_margin": _pct(op, rev),
        "revenue_growth": _growth(rev, rev_prev),
        "operating_profit_growth": _growth(op, op_prev),
        "operating_cf_margin": _pct(cfo, rev),
        # EDINETの標準タグだけでは取れない項目（四季報固有/非構造化。データなし＝評価対象外）
        "overseas_ratio": None,
        "founding_year": None,
        "next_year_growth_forecast": None,
        "segment_concentration": None,
    }


# --------------------------------------------------------------------------
# セグメント情報と業界の分類
# --------------------------------------------------------------------------
SEGMENT_REVENUE_IDS = [
    "jpigp_cor:RevenueFromExternalCustomersIFRS",  # IFRS
    P + "RevenuesFromExternalCustomers",           # 日本基準
]
SEGMENT_PROFIT_IDS = ["jpigp_cor:OperatingProfitLossIFRS", "jppfs_cor:OperatingIncome"]
# 例: CurrentYearDuration_jpcrp030000-asr_E25165-000EnergyReportableSegmentsMember
_SEGMENT_CONTEXT = re.compile(r"^CurrentYearDuration_.*-\d{3}([A-Za-z0-9]+?)ReportableSegments?Member$")

MULTI_INDUSTRY_SHARE = 0.30  # 売上の3割以上を占める事業があれば、その業界にも表示する

# セグメント名（企業が付けた英語のID）に含まれる語 → 業界。上から順に判定し、最初に当たったものを採用。
# 例: FinancialITSolutions は「IT」が先に当たるので金融ではなくIT
SEGMENT_KEYWORDS = [
    # 「Communication(s)」単独はPR・広告会社でも使われ、「Mobile」単独はモバイルコンテンツでも使われるため、
    # 通信と分かる組み合わせだけにした（実データでプラップジャパン等が誤って通信になった）
    # 「MobilePhone」単独も携帯向けコンテンツ（エムアップ）で使われていたため外した
    ("3.通信", ["telecom", "informationcommunication", "mobilecommunication", "mobileline",
               "broadband", "catv", "cabletelevision", "satellite", "internetconnection"]),
    ("2.IT・ソフト・SI", ["software", "saas", "cloud", "systemintegration", "systemdevelopment",
                         "informationtechnology", "informationservice", "game", "it", "ict", "dx"]),
    ("5.医薬・バイオ", ["pharma", "drug", "biotech", "medicine"]),
    ("9.輸送用機器", ["automotive", "automobile", "vehicle", "motorcycle", "aircraft", "aerospace",
                     "shipbuilding", "autoparts"]),
    ("10.鉄鋼・非鉄金属", ["steel", "metal", "iron", "aluminum", "aluminium", "copper", "nonferrous", "smelting"]),
    ("11.エネルギー・資源", ["energy", "gas", "electricpower", "petroleum", "oil", "fuel", "lpg", "mining",
                          "resource", "coal", "renewable", "solar"]),
    ("16.サービス・運輸・レジャー", ["foodservice", "restaurant", "logistic", "transport", "railway", "bus",
                                 "taxi", "airline", "shipping", "warehous", "travel", "tourism", "hotel",
                                 "leisure", "amusement", "consult", "staffing", "humanresource", "education",
                                 "temporaryemployee", "placement", "dispatch", "recruit",
                                 "nursing", "care", "advertis", "broadcast", "publish", "media", "security",
                                 "fitness", "wedding", "funeral", "outsourc"]),
    ("6.食品", ["food", "beverage", "drink", "dairy", "meat", "confection", "seafood", "brew", "beer",
               "flour", "sugar", "noodle", "agricultur"]),
    ("7.アパレル・繊維", ["apparel", "fashion", "textile", "fiber", "fibre", "clothing"]),
    ("4.化学", ["chemical", "plastic", "resin", "polymer", "rubber", "glass", "cement", "paper", "pulp",
               "coating", "paint", "cosmetic"]),
    ("1.電機・電子機器", ["electronic", "electrical", "device", "semiconductor", "component", "precision", "instrument",
                       "optical", "camera", "imaging", "display", "battery", "appliance"]),
    ("8.機械・重工業", ["machinery", "machine", "robot", "engine"]),
    ("14.建設・不動産", ["realestate", "property", "properties", "construction", "building", "housing",
                       "house", "civil", "architect"]),
    ("15.小売", ["retail", "store", "shop", "supermarket", "drugstore", "ecommerce", "mailorder"]),
    ("13.金融", ["bank", "securities", "insurance", "leasing", "lease", "credit", "loan", "finance",
                "financial", "assetmanagement", "investment", "payment"]),
    ("12.商社", ["trading", "wholesale"]),
]
# 単語として一致したときだけ当てる語（部分一致だと Automobile→mobile、Environment→iron、
# Engineering→engine のように誤爆するもの）
_SHORT_TOKENS = {"it", "ict", "dx", "catv", "lpg", "gas", "oil", "bus", "care", "game",
                 "mobile", "iron", "engine", "media", "store", "cement"}  # cement: Placement に当たらないように


def _split_camel(name: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z]+|[a-z]+|\d+", name)]


def classify_segment(name: str):
    """セグメント名から業界を推定する。分からなければ None。"""
    tokens = _split_camel(name)
    joined = "".join(tokens)
    # 通信「機器」の製造・販売や電気・通信インフラ機器は、通信サービスではなく電機（日東工業・萬世電機の実例）
    joined = re.sub(r"telecommunications?(apparatus|equipment|device)", r"commsdevice", joined)
    joined = re.sub(r"^electricalandtelecommunications?", "electricalequipment", joined)
    joined = (joined
              .replace("humanresource", "staffing")   # HumanResources → エネルギーの resource と区別
              .replace("pharmacy", "retailshop")      # 調剤薬局・ドラッグストアは医薬品メーカーではなく小売
              .replace("drugstore", "retailshop"))    # （「drug」で医薬に当たらないよう先に置き換える）
    for industry, words in SEGMENT_KEYWORDS:
        for w in words:
            if w in _SHORT_TOKENS:
                if w in tokens or (w + "s") in tokens:
                    return industry
            elif w in joined:
                return industry
    return None


def extract_segments(df: pd.DataFrame) -> list[dict]:
    """当期の報告セグメントごとの外部顧客への売上高と営業利益。"""
    sub = df[df["相対年度"] == "当期"]
    segments: dict[str, dict] = {}
    for kind, ids in (("revenue", SEGMENT_REVENUE_IDS), ("profit", SEGMENT_PROFIT_IDS)):
        for eid in ids:
            rows = sub[sub["要素ID"] == eid]
            found = False
            for ctx, value in zip(rows["コンテキストID"].fillna(""), rows["値"]):
                m = _SEGMENT_CONTEXT.match(ctx)
                v = _to_float(value)
                if m and v is not None:
                    segments.setdefault(m.group(1), {"name": m.group(1)})[kind] = v
                    found = True
            if found:
                break
    return [s for s in segments.values() if s.get("revenue") is not None]


def segment_concentration(segments: list[dict]):
    """主力セグメント利益集中度（％）：黒字セグメントの営業利益のうち、最大のセグメントが占める割合。"""
    profits = [s["profit"] for s in segments if s.get("profit") is not None and s["profit"] > 0]
    if len(profits) < 2:
        return None
    return round(max(profits) / sum(profits) * 100, 1)


TELECOM_TEXT_WORDS = ["電気通信", "移動体通信", "携帯電話", "モバイル通信", "固定通信", "光回線", "光ファイバ",
                      "ブロードバンド", "インターネット接続", "MVNO", "ＭＶＮＯ", "通信回線", "通信サービス",
                      "データセンター", "ケーブルテレビ", "衛星通信", "基地局", "通信事業", "プロバイダ"]
IT_TEXT_WORDS = ["ソフトウェア", "システム開発", "システムインテグレーション", "受託開発", "ＳａａＳ", "SaaS",
                 "パッケージ", "情報処理", "アプリ", "ゲーム", "コンサルティング", "ＤＸ", "DX", "Ｗｅｂ", "Web",
                 "プラットフォーム", "クラウドサービス", "ITサービス", "ＩＴサービス"]


def classify_information_company(text: str | None) -> str:
    """EDINETの「情報・通信業」はITと通信が混ざっているので、事業の内容の文章で通信会社を見分ける。"""
    if not isinstance(text, str) or not text:
        return "2.IT・ソフト・SI"
    head = text[:4000]
    telecom = sum(head.count(w) for w in TELECOM_TEXT_WORDS)
    it = sum(head.count(w) for w in IT_TEXT_WORDS)
    # しきい値は実データ（情報・通信業 609社）で確認して決めた。3語だと LINEヤフー 等が誤って通信になった
    return "3.通信" if telecom >= 5 and telecom > it else "2.IT・ソフト・SI"


def decide_industries(primary: str, edinet_industry: str | None, segments: list[dict], texts: dict) -> dict:
    """主業種と、売上の3割以上を占める兼業の業界を決める。"""
    shares: dict[str, float] = {}
    total = sum(s["revenue"] for s in segments if s["revenue"] > 0)
    if total > 0:
        for s in segments:
            industry = classify_segment(s["name"])
            if industry and s["revenue"] > 0:
                shares[industry] = shares.get(industry, 0) + s["revenue"] / total
    if edinet_industry == "情報・通信業" and primary == "2.IT・ソフト・SI":
        # IT か通信か：セグメントで売上の過半が説明できるならそれを優先し、できなければ事業の内容の文章で判定
        # （例：ソフィアHDは文章に通信の語が多いが、売上の8割は調剤薬局で通信は3%）
        if shares.get("3.通信", 0) >= 0.5:
            primary = "3.通信"
        elif not shares or max(shares.values()) < 0.5:
            primary = classify_information_company(texts.get("business_description"))
    industries = [primary] + sorted(i for i, v in shares.items() if v >= MULTI_INDUSTRY_SHARE and i != primary)
    return {
        "industry": primary,
        "industries": industries,
        "industry_shares": {i: round(v, 3) for i, v in shares.items()} or None,
    }


def _clean_text_block(s) -> str | None:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    s = re.sub(r"<[^>]+>", " ", str(s))  # CSVにHTMLが残っている場合に備える
    s = re.sub(r"[ \t　]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s).strip()
    return s or None


def extract_texts(df: pd.DataFrame) -> dict:
    """有報の文章セクションを取り出す（見つからなければ None）。"""
    out = {}
    for field, ids in TEXT_BLOCK_IDS.items():
        out[field] = None
        for eid in ids:
            sub = df[df["要素ID"] == eid]
            if sub.empty:
                continue
            # 同じ要素が複数ある場合は、軸の付いていない（コンテキストIDが短い）ものを優先
            sub = sub.assign(_len=sub["コンテキストID"].fillna("").str.len()).sort_values("_len", kind="stable")
            for v in sub["値"]:
                text = _clean_text_block(v)
                if text:
                    out[field] = text
                    break
            if out[field]:
                break
    return out


# --------------------------------------------------------------------------
# Supabase
# --------------------------------------------------------------------------
def get_client():
    from supabase import create_client

    url, key = _env("SUPABASE_URL"), _env("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        fail("SUPABASE_URL と SUPABASE_SERVICE_ROLE_KEY を設定してください（DBに書き込まない確認だけなら --dry-run）")
    return create_client(url.rstrip("/"), key)


def fetch_existing(client) -> dict:
    """{edinet_code: 取り込み済みの period_end(str)}"""
    existing, start = {}, 0
    while True:
        rows = (
            client.table("companies")
            .select("id,edinet_code,period_end")
            .eq("source", "edinet")
            .order("id")  # 【修正】順序指定がないとページングで行が重複/欠落しうる
            .range(start, start + 999)
            .execute()
            .data
        )
        for r in rows:
            existing[r["edinet_code"]] = r.get("period_end") or ""
        if len(rows) < 1000:
            return existing
        start += 1000


def upsert_rows(client, rows: list[dict], table: str = "companies") -> bool:
    if not rows:
        return True
    try:
        client.table(table).upsert(rows, on_conflict="edinet_code").execute()
        return True
    except Exception as e:  # 【修正】1バッチの失敗で全体が止まらないようにする
        log.error("%s へのupsert失敗（%d件）: %s", table, len(rows), e)
        return False


# --------------------------------------------------------------------------
# 要素ID確認用
# --------------------------------------------------------------------------
def inspect(doc_id: str, key: str):
    df = read_xbrl_csv(download_csv_zip(doc_id, key))
    if df is None:
        print("jpcrp のCSVが見つかりません")
        return
    pat = "Average|Salary|OperatingIncome|OperatingProfit|NetSales|Revenue|OperatingActivities"
    sub = df[df["要素ID"].str.contains(pat, regex=True, na=False)]
    cols = ["要素ID", "項目名", "コンテキストID", "相対年度", "連結・個別", "単位", "値"]
    with pd.option_context("display.max_rows", 300, "display.max_colwidth", 70, "display.width", 250):
        print(sub[cols].to_string(index=False))
    print("\n--- 抽出結果 ---")
    print(extract_metrics(df))
    print("\n--- 文章セクション（先頭200字）---")
    for field, text in extract_texts(df).items():
        print(f"[{field}] {len(text) if text else 0}字: {(text or 'なし')[:200]!r}")


# --------------------------------------------------------------------------
# 秘密情報の扱い
# --------------------------------------------------------------------------
_SECRETS: list[str] = []


def redact(text: str) -> str:
    """APIキーはURLのクエリに入るため、requests のエラー文にそのまま出る。ログに残さないよう伏せる。"""
    for s in _SECRETS:
        if s:
            text = text.replace(s, "***")
    return text


class _RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        safe = redact(msg)
        if safe != msg:
            record.msg, record.args = safe, ()
        return True


for _h in logging.getLogger().handlers:
    _h.addFilter(_RedactFilter())


def load_dotenv_file(path: str):
    """KEY=VALUE 形式の .env を読む（既に環境変数がある場合はそちらを優先）。"""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            value = re.split(r"\s+#", value, maxsplit=1)[0]  # 行末の「  # コメント」を除く
            name, value = name.strip(), value.strip().strip('"').strip("'")
            if name and value and not os.environ.get(name):
                os.environ[name] = value
    for name in ("SUPABASE_SERVICE_ROLE_KEY",):
        if os.environ.get(name):
            _SECRETS.append(os.environ[name])


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--codelist-file")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="取り込み済みの書類も再取得して上書きする")
    ap.add_argument("--inspect", metavar="DOC_ID")
    ap.add_argument("--limit", type=int, help="取り込む企業数の上限（お試し用）")
    ap.add_argument("--only-codes", help="この EDINETコード（カンマ区切り）の企業だけ処理する")
    args = ap.parse_args()

    load_dotenv_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    key = _env("EDINET_API_KEY")
    if not key:
        fail("EDINET_API_KEY が設定されていません（環境変数か、このフォルダの .env に書いてください）")
    _SECRETS.append(key)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        # 値そのものは出さず、形式だけを確認して表示する（Secrets の貼り間違いを見つけやすくする）
        url, sk = _env("SUPABASE_URL"), _env("SUPABASE_SERVICE_ROLE_KEY")
        print("::notice title=設定の形式チェック::"
              f"EDINET_API_KEY {len(key)}文字 / "
              f"SUPABASE_URL {'OK' if url.startswith('https://') and '.supabase.co' in url else '形式が違う'} / "
              f"SUPABASE_SERVICE_ROLE_KEY {'OK' if sk.startswith('sb_secret_') or sk.count('.') == 2 else '形式が違う（Secret key を入れてください）'}")
    if args.inspect:
        inspect(args.inspect, key)
        return

    end = date.fromisoformat(args.end) if args.end else date.today()
    start = date.fromisoformat(args.start) if args.start else end - timedelta(days=14)
    if start > end:
        fail("--start が --end より後になっています")

    codes = load_codelist(args.codelist_file).set_index("edinet_code")
    client = None if args.dry_run else get_client()
    existing = {} if (args.dry_run or args.force) else fetch_existing(client)
    only_codes = {c.strip() for c in args.only_codes.split(",") if c.strip()} if args.only_codes else None

    # 1) 対象日の有報を一覧化（同一企業は period_end が新しいものを採用）
    candidates: dict[str, dict] = {}
    day = start
    while day <= end:
        try:
            for d in list_yuho(day, key):
                code = d["edinetCode"]
                if code not in codes.index or (only_codes and code not in only_codes):
                    continue
                period_end = d.get("periodEnd") or ""
                if period_end and period_end <= existing.get(code, ""):
                    continue  # 取り込み済み
                if code not in candidates or period_end > (candidates[code].get("periodEnd") or ""):
                    candidates[code] = d
        except EdinetApiError as e:
            # キー不正などは何日分繰り返しても同じなので即終了
            fail(str(e))
        except requests.RequestException as e:
            log.warning("%s の一覧取得に失敗: %s", day, e)
        time.sleep(SLEEP_SEC)
        day += timedelta(days=1)
    log.info("取り込み対象: %d社", len(candidates))
    if args.limit is not None and len(candidates) > args.limit:
        candidates = dict(list(candidates.items())[: args.limit])
        log.info("--limit により %d社だけ処理します", args.limit)

    # 2) 書類(CSV)を取得して指標を抽出
    batch, text_batch, done, failed = [], [], 0, 0
    for code, d in candidates.items():
        try:
            df = read_xbrl_csv(download_csv_zip(d["docID"], key))
            if df is None:
                raise ValueError("jpcrp CSVなし")
            metrics = extract_metrics(df)
            texts = extract_texts(df)
            text_row = {
                "edinet_code": code,
                "doc_id": d["docID"],
                "period_end": d.get("periodEnd") or None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                **texts,
            }
            segments = extract_segments(df)
            metrics["segment_concentration"] = segment_concentration(segments)
            row = {
                "source": "edinet",
                "edinet_code": code,
                "sec_code": codes.loc[code, "sec_code4"],
                "company_name": codes.loc[code, "name"],
                "doc_id": d["docID"],
                "period_end": d.get("periodEnd") or None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                **metrics,
                **decide_industries(codes.loc[code, "industry"], codes.loc[code, "edinet_industry"], segments, texts),
            }
            if args.dry_run:
                log.info("%s", row)
                log.info("文章: %s", {k: (len(v) if v else 0) for k, v in texts.items()})
            else:
                batch.append(row)
                text_batch.append(text_row)
            done += 1
        except Exception as e:
            failed += 1
            log.warning("%s(%s) 失敗: %s", d.get("filerName"), d.get("docID"), e)
        time.sleep(SLEEP_SEC)
        if len(batch) >= UPSERT_BATCH:
            done, failed = _flush(client, batch, text_batch, done, failed)
            batch, text_batch = [], []
    if batch:
        done, failed = _flush(client, batch, text_batch, done, failed)
    log.info("完了: 成功%d / 失敗%d", done, failed)


def _flush(client, batch, text_batch, done, failed):
    if not upsert_rows(client, batch):
        return done - len(batch), failed + len(batch)
    # 文章は数値データの後に書く。1件あたり数万字になるので小分けにして送る
    for i in range(0, len(text_batch), 10):
        upsert_rows(client, text_batch[i:i + 10], table="company_texts")
    return done, failed


def _env(name: str) -> str:
    """環境変数を読む。Secrets に貼るときに紛れ込みやすい前後の空白・引用符を取り除く。"""
    return (os.environ.get(name) or "").strip().strip('"').strip("'").strip()


def fail(message: str):
    """エラー終了する。GitHub Actions では、ログインしなくても見える「注釈」にもエラーを出す。"""
    message = redact(message)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        tail = "\n".join(message.strip().splitlines()[-12:])  # トレースバックは末尾が要点
        escaped = tail.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::error title=EDINET取り込み失敗::{escaped}", flush=True)
    sys.exit(message)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        fail(traceback.format_exc())  # エラー文に含まれるURLからキーを伏せる
