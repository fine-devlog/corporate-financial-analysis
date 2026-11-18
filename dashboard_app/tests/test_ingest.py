"""edinet_ingest.py のテスト（ネットワーク不要）。"""
import io
import logging
import types
import zipfile

import pandas as pd
import pytest

import edinet_ingest as E

P = "jpcrp_cor:"
S = E.SUFFIX_EMP
COLS = ["要素ID", "コンテキストID", "相対年度", "連結・個別", "値"]


def make_df(rows):
    return pd.DataFrame(rows, columns=COLS)


def make_csv_zip(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("XBRL_TO_CSV/jpaud-aar-cn-001_E00001.csv", "dummy".encode("utf-16"))
        z.writestr("XBRL_TO_CSV/jpcrp030000-asr-001_E00001.csv", df.to_csv(sep="\t", index=False).encode("utf-16"))
    return buf.getvalue()


# --------------------------------------------------------------------------
# 指標の抽出
# --------------------------------------------------------------------------
def test_employee_metrics_and_months():
    df = make_df([
        (P + "AverageAnnualSalary" + S, "CurrentYearInstant_NonConsolidatedMember", "当期末", "その他", "7512345"),
        (P + "AverageAgeYears" + S, "CurrentYearInstant_NonConsolidatedMember", "当期末", "その他", "41"),
        (P + "AverageAgeMonths" + S, "CurrentYearInstant_NonConsolidatedMember", "当期末", "その他", "6"),
        (P + "AverageLengthOfServiceYears" + S, "CurrentYearInstant_NonConsolidatedMember", "当期末", "その他", "15.3"),
    ])
    m = E.extract_metrics(df)
    assert m["income"] == 751.2  # 円 → 万円
    assert m["age"] == 41.5      # 41歳6ヶ月
    assert m["avg_tenure"] == 15.3


def test_summary_rows_marked_sonota_are_used():
    """実データでは「主要な経営指標等の推移」の行の連結・個別列が「その他」になっている（実際に起きたバグ）。"""
    df = make_df([
        (P + "NetSalesSummaryOfBusinessResults", "CurrentYearDuration", "当期", "その他", "2000"),
        (P + "NetSalesSummaryOfBusinessResults", "Prior1YearDuration", "前期", "その他", "1600"),
        ("jppfs_cor:OperatingIncome", "CurrentYearDuration", "当期", "連結", "200"),
        ("jppfs_cor:OperatingIncome", "Prior1YearDuration", "前期", "連結", "100"),
    ])
    m = E.extract_metrics(df)
    assert m["revenue_growth"] == 25.0
    assert m["operating_margin"] == 10.0
    assert m["operating_profit_growth"] == 100.0


def test_consolidated_and_nonconsolidated_are_not_mixed():
    """売上が連結で取れたら、営業利益も連結から取る（単体の値と混ぜない）。"""
    df = make_df([
        (P + "RevenueIFRSSummaryOfBusinessResults", "CurrentYearDuration", "当期", "その他", "1000000"),
        (P + "NetSalesSummaryOfBusinessResults", "CurrentYearDuration_NonConsolidatedMember", "当期", "その他", "100000"),
        ("jppfs_cor:OperatingIncome", "CurrentYearDuration_NonConsolidatedMember", "当期", "個別", "50000"),
    ])
    assert E.extract_metrics(df)["operating_margin"] is None


def test_nonconsolidated_only_company():
    df = make_df([
        (P + "NetSalesSummaryOfBusinessResults", "CurrentYearDuration_NonConsolidatedMember", "当期", "その他", "4884248000"),
        (P + "NetSalesSummaryOfBusinessResults", "Prior1YearDuration_NonConsolidatedMember", "前期", "その他", "4857640000"),
        ("jppfs_cor:OperatingIncome", "CurrentYearDuration_NonConsolidatedMember", "当期", "個別", "-53462000"),
        ("jppfs_cor:OperatingIncome", "Prior1YearDuration_NonConsolidatedMember", "前期", "個別", "-326171000"),
    ])
    m = E.extract_metrics(df)
    assert m["operating_margin"] == -1.1
    assert m["revenue_growth"] == 0.5
    assert m["operating_profit_growth"] is None  # 前期赤字からの成長率は意味がないので空欄


def test_segment_rows_are_ignored():
    df = make_df([
        (P + "NetSalesSummaryOfBusinessResults", "CurrentYearDuration", "当期", "その他", "1000"),
        (P + "CashFlowsFromUsedInOperatingActivitiesIFRSSummaryOfBusinessResults",
         "CurrentYearDuration_jpcrp030000-asr_E00001-000FooReportableSegmentMember", "当期", "その他", "999"),
        (P + "CashFlowsFromUsedInOperatingActivitiesIFRSSummaryOfBusinessResults", "CurrentYearDuration", "当期", "その他", "120"),
    ])
    assert E.extract_metrics(df)["operating_cf_margin"] == 12.0


@pytest.mark.parametrize("cur,prev,expected", [(120, 100, 20.0), (120, 0, None), (120, -10, None), (None, 100, None)])
def test_growth(cur, prev, expected):
    assert E._growth(cur, prev) == expected


def test_extract_texts_strips_html():
    df = make_df([
        (P + "DescriptionOfBusinessTextBlock", "FilingDateInstant", "提出日時点", "その他", "<p>自動車を製造。</p>\n\n\n販売も行う。"),
        (P + "BusinessRisksTextBlock", "FilingDateInstant", "提出日時点", "その他", "為替　　リスク"),
    ])
    t = E.extract_texts(df)
    assert "<p>" not in t["business_description"] and "\n\n" not in t["business_description"]
    assert t["business_risks"] == "為替 リスク"
    assert t["management_policy"] is None


def test_read_xbrl_csv_prefers_main_report():
    df = make_df([(P + "BusinessRisksTextBlock", "FilingDateInstant", "提出日時点", "その他", "x")])
    out = E.read_xbrl_csv(make_csv_zip(df))
    assert list(out["要素ID"]) == [P + "BusinessRisksTextBlock"]


# --------------------------------------------------------------------------
# API エラー・秘密情報
# --------------------------------------------------------------------------
def test_api_error_inside_http_200_is_detected():
    resp = types.SimpleNamespace(
        headers={"Content-Type": "application/json"},
        raise_for_status=lambda: None,
        json=lambda: {"StatusCode": 401, "message": "Access denied due to invalid subscription key."},
    )
    with pytest.raises(E.EdinetApiError):
        E._raise_if_api_error(resp)


def test_api_key_is_redacted_in_logs(caplog, monkeypatch):
    monkeypatch.setattr(E, "_SECRETS", ["SECRETKEY123"])
    logger = logging.getLogger("redact-test")
    handler = logging.StreamHandler(io.StringIO())
    handler.addFilter(E._RedactFilter())
    logger.addHandler(handler)
    logger.warning("failed: %s", "https://api.example/?Subscription-Key=SECRETKEY123")
    assert "SECRETKEY123" not in handler.stream.getvalue()
    assert "***" in handler.stream.getvalue()


def test_dotenv_inline_comment_and_quotes(tmp_path, monkeypatch):
    monkeypatch.delenv("T_A", raising=False)
    monkeypatch.delenv("T_B", raising=False)
    env = tmp_path / ".env"
    env.write_text('T_A=sb_secret_abc   # コメント\nT_B="quoted"\n# 無視\n', encoding="utf-8")
    E.load_dotenv_file(str(env))
    import os
    assert os.environ["T_A"] == "sb_secret_abc"
    assert os.environ["T_B"] == "quoted"


# --------------------------------------------------------------------------
# main() を通しで（EDINET API と Supabase は偽物）
# --------------------------------------------------------------------------
def make_codelist(path):
    header = "EDINETコード,提出種別,上場区分,連結の有無,資本金,決算日,提出者名,提出者名（英字）,提出者名（ヨミ）,所在地,提出者業種,証券コード,提出者法人番号"
    lines = [
        "ダウンロード実行日,2026年11月18日現在,件数,3件",
        header.replace("EDINET", "ＥＤＩＮＥＴ"),
        "E02144,内国法人・組合,上場,有,1,3月31日,トヨタ自動車株式会社,,,,輸送用機器,72030,",
        "E99998,内国法人・組合,上場,有,1,3月31日,倉庫会社,,,,倉庫・運輸関連,99980,",
        "E99997,内国法人・組合,非上場,有,1,3月31日,非上場会社,,,,輸送用機器,,",
    ]
    path.write_bytes("\n".join(lines).encode("cp932"))


def test_load_codelist_mapping(tmp_path):
    p = tmp_path / "codelist.csv"
    make_codelist(p)
    codes = E.load_codelist(str(p)).set_index("edinet_code")
    assert codes.loc["E02144", "industry"] == "9.輸送用機器"
    assert codes.loc["E99998", "industry"] == "16.サービス・運輸・レジャー"  # 実データの表記「倉庫・運輸関連」
    assert "E99997" not in codes.index  # 非上場は除外


def test_main_end_to_end(tmp_path, monkeypatch):
    codelist = tmp_path / "codelist.csv"
    make_codelist(codelist)
    df = make_df([
        (P + "AverageAnnualSalary" + S, "CurrentYearInstant_NonConsolidatedMember", "当期末", "その他", "9000000"),
        (P + "NetSalesSummaryOfBusinessResults", "CurrentYearDuration", "当期", "その他", "2000"),
        (P + "NetSalesSummaryOfBusinessResults", "Prior1YearDuration", "前期", "その他", "1600"),
        ("jppfs_cor:OperatingIncome", "CurrentYearDuration", "当期", "連結", "200"),
        (P + "BusinessRisksTextBlock", "FilingDateInstant", "提出日時点", "その他", "為替リスク"),
    ])
    zip_bytes = make_csv_zip(df)

    class Resp:
        def __init__(self, js=None, content=b""):
            self._js, self.content = js, content
            self.headers = {"Content-Type": "application/json" if js is not None else "application/octet-stream"}

        def raise_for_status(self):
            pass

        def json(self):
            return self._js

    base = {"docTypeCode": "120", "ordinanceCode": "010", "withdrawalStatus": "0", "csvFlag": "1", "periodEnd": "2026-03-31"}

    def fake_get(url, params=None, timeout=None):
        if url.endswith("documents.json"):
            if params["date"] != "2026-06-26":
                return Resp({"metadata": {"status": "200"}, "results": []})
            return Resp({"metadata": {"status": "200"}, "results": [
                {**base, "edinetCode": "E02144", "secCode": "72030", "docID": "S100NEW"},
                {**base, "edinetCode": "E02144", "secCode": "72030", "docID": "S100OLD", "periodEnd": "2025-03-31"},
                {**base, "edinetCode": "E00000", "secCode": "00000", "docID": "S100UNKNOWN"},  # コードリストにない
                {**base, "edinetCode": "E99998", "secCode": "99980", "docID": "S100NOCSV", "csvFlag": "0"},
                {**base, "docTypeCode": "130", "edinetCode": "E02144", "secCode": "72030", "docID": "S100FIX"},  # 訂正報告書
            ]})
        return Resp(content=zip_bytes)

    writes = {}

    class Table:
        def __init__(self, name):
            self.name = name

        def upsert(self, rows, on_conflict=None):
            writes.setdefault(self.name, []).extend(rows)
            return self

        def __getattr__(self, _):
            return lambda *a, **k: self

        def execute(self):
            return types.SimpleNamespace(data=[])

    monkeypatch.setattr(E.requests, "get", fake_get)
    monkeypatch.setattr(E, "SLEEP_SEC", 0)
    monkeypatch.setattr(E, "get_client", lambda: types.SimpleNamespace(table=Table))
    monkeypatch.setenv("EDINET_API_KEY", "dummy")
    monkeypatch.setattr("sys.argv", ["x", "--start", "2026-06-25", "--end", "2026-06-27", "--codelist-file", str(codelist)])

    E.main()

    assert [r["doc_id"] for r in writes["companies"]] == ["S100NEW"]
    row = writes["companies"][0]
    assert (row["income"], row["operating_margin"], row["revenue_growth"]) == (900.0, 10.0, 25.0)
    assert writes["company_texts"][0]["business_risks"] == "為替リスク"
