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
# 「情報・通信業」は IT と通信が混在するため、証券コード（4桁）で上書きする。必要に応じて追加。
SEC_CODE_OVERRIDE = {
    "9432": "3.通信",  # NTT
    "9433": "3.通信",  # KDDI
    "9434": "3.通信",  # ソフトバンク
    "9436": "3.通信",  # 沖縄セルラー電話
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
    out = df.dropna(subset=["industry"])[["edinet_code", "name", "industry", "sec_code4"]]
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
        "income": round(salary / 10000, 1) if salary is not None else None,  # 円 → 万円
        "age": age,
        "avg_tenure": tenure,
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

    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])


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
    args = ap.parse_args()

    load_dotenv_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    key = os.environ.get("EDINET_API_KEY")
    if not key:
        sys.exit("EDINET_API_KEY が設定されていません（環境変数か、このフォルダの .env に書いてください）")
    _SECRETS.append(key)
    if args.inspect:
        inspect(args.inspect, key)
        return

    end = date.fromisoformat(args.end) if args.end else date.today()
    start = date.fromisoformat(args.start) if args.start else end - timedelta(days=14)
    if start > end:
        sys.exit("--start が --end より後になっています")

    codes = load_codelist(args.codelist_file).set_index("edinet_code")
    client = None if args.dry_run else get_client()
    existing = {} if (args.dry_run or args.force) else fetch_existing(client)

    # 1) 対象日の有報を一覧化（同一企業は period_end が新しいものを採用）
    candidates: dict[str, dict] = {}
    day = start
    while day <= end:
        try:
            for d in list_yuho(day, key):
                code = d["edinetCode"]
                if code not in codes.index:
                    continue
                period_end = d.get("periodEnd") or ""
                if period_end and period_end <= existing.get(code, ""):
                    continue  # 取り込み済み
                if code not in candidates or period_end > (candidates[code].get("periodEnd") or ""):
                    candidates[code] = d
        except EdinetApiError as e:
            # キー不正などは何日分繰り返しても同じなので即終了
            sys.exit(redact(str(e)))
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
            row = {
                "source": "edinet",
                "edinet_code": code,
                "sec_code": codes.loc[code, "sec_code4"],
                "company_name": codes.loc[code, "name"],
                "industry": codes.loc[code, "industry"],
                "doc_id": d["docID"],
                "period_end": d.get("periodEnd") or None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                **metrics,
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


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        sys.exit(redact(traceback.format_exc()))  # エラー文に含まれるURLからキーを伏せる
