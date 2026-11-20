import hmac
import random
import unicodedata
from datetime import datetime, timezone
from io import BytesIO

import altair as alt
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from supabase import create_client, Client

import ai_summary
import company_names
import shikiho_guide

st.set_page_config(
    page_title="就活生のための企業データ分析ツール",
    layout="wide",
    # 【修正】"expanded" だとスマホでもサイドバーが開いた状態で画面をふさぐ。
    #   "auto" はパソコンでは開き、スマホなど狭い画面では閉じた状態で始まる
    initial_sidebar_state="auto",
)

# matplotlib の日本語フォント（入っているものを順に使う。無ければ豆腐になる）
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = [
    "IPAexGothic", "IPAGothic", "Noto Sans CJK JP", "Noto Sans JP",
    "Yu Gothic", "Meiryo", "Hiragino Sans", "TakaoGothic", "DejaVu Sans",
]

CURRENT_YEAR = datetime.now().year


# ---------------------------------------------------------------------------
# Supabase クライアント
# ---------------------------------------------------------------------------
# @st.cache_resource で共有するとログイン状態(JWT)が全ユーザーで混ざるため、
# セッションごとにクライアントを作る。
def get_supabase() -> Client:
    if "supabase" not in st.session_state:
        st.session_state["supabase"] = create_client(
            st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"]
        )
    return st.session_state["supabase"]


# 【修正】secrets に無いとアプリ全体が起動しないので、無ければ管理者認証を無効化する
ADMIN_PASSCODE = st.secrets.get("ADMIN_PASSCODE")
MAX_ADMIN_ATTEMPTS = 5


def init_session_state():
    defaults = {
        "page": "title",
        "prev_page": "title",
        "auth_user": None,
        "selected_industry": None,
        "selected_company": None,
        "reporter_headline": "",
        "market_ranking": [""] * 15,
        "market_sentiment_skipped": False,
        "comparison_result": {},
        "company_score_pct": 0.0,
        "reporter_score_pct": 0.0,
        "reporter_weight": 0.0,
        "reporter_level": "",
        "reporter_detail": None,
        "segment_note": None,
        "search_candidates": [],
        "other_industry_hits": [],
        "search_not_found": False,
        "skip_save": False,
        "manual_confirmed": False,
        "is_admin_authed": False,
        "admin_attempts": 0,
        "selected_edinet_code": None,
        "ai_summaries": {},
        "ai_calls": 0,  # AI要約のAPI呼び出し回数（セッション内の上限管理用。分析リセットでは戻さない）
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_session_state()


def goto(page_name: str):
    st.session_state["prev_page"] = st.session_state["page"]
    st.session_state["page"] = page_name
    st.rerun()


ANALYSIS_KEYS = [
    "selected_company", "reporter_headline",
    "market_ranking", "market_sentiment_skipped", "comparison_result",
    "company_score_pct", "reporter_score_pct", "reporter_weight",
    "reporter_level", "reporter_detail", "segment_note",
    "search_candidates", "search_not_found", "skip_save", "manual_confirmed",
    "selected_edinet_code", "other_industry_hits",
]
# 【修正】ウィジェットの入力値も残っていると、次の分析で前回の入力が表示されてしまう
WIDGET_KEYS_TO_CLEAR = ["company_search_input", "candidate_select"] + [f"rank_{i}" for i in range(15)]


def reset_analysis_state():
    """分析結果だけをリセットする（業界変更時・終了時に使用）。"""
    for k in ANALYSIS_KEYS + WIDGET_KEYS_TO_CLEAR:
        st.session_state.pop(k, None)
    init_session_state()


def reset_all_and_goto_title():
    reset_analysis_state()
    st.session_state.pop("selected_industry", None)
    init_session_state()
    st.session_state["page"] = "title"
    st.rerun()


INDUSTRIES = [
    "1.電機・電子機器", "2.IT・ソフト・SI", "3.通信", "4.化学",
    "5.医薬・バイオ", "6.食品", "7.アパレル・繊維", "8.機械・重工業",
    "9.輸送用機器", "10.鉄鋼・非鉄金属", "11.エネルギー・資源", "12.商社",
    "13.金融", "14.建設・不動産", "15.小売", "16.サービス・運輸・レジャー",
]

METRIC_COLUMNS = [
    "平均年収（万）", "平均年齢（歳）", "海外売上比率（％）",
    "営業利益率（％）", "売上高成長率（％）", "営業利益成長率（％）",
    "平均勤続年数（年）", "来期成長率予想（％）", "営業CFマージン（％）",
]
INFO_ONLY_COLUMNS = ["主力セグメント利益集中度（％）"]
ALL_DATA_COLUMNS = METRIC_COLUMNS + ["創業年"] + INFO_ONLY_COLUMNS
META_COLUMNS = ["区分", "証券コード", "決算期", "出典", "EDINETコード", "主業種", "業界別売上比率"]
HIDDEN_COLUMNS = ["EDINETコード", "主業種", "業界別売上比率"]  # 内部用（一覧表には出さない）
DISPLAY_COLUMNS = ["企業名", *ALL_DATA_COLUMNS, *META_COLUMNS]

SOURCE_LABELS = {"edinet": "EDINET", "user": "手入力", "sample": "サンプル"}

# ---------------------------------------------------------------------------
# サンプル（架空）データ：EDINETデータがまだ無い業界でだけ使う
# ---------------------------------------------------------------------------
COMPANY_DATA_BY_INDUSTRY = {
    "1.電機・電子機器": {
        "企業名": ["ネクサスエレクトロ", "アステックデバイス", "東洋マイクロ", "グローバルセミコン", "オービット電機"],
        "平均年収（万）": [680, 590, 540, 750, 620],
        "平均年齢（歳）": [38, 40, 42, 36, 39],
        "海外売上比率（％）": [55, 45, 35, 70, 60],
    },
    "2.IT・ソフト・SI": {
        "企業名": ["クラウドネクサス", "コードウェーブ", "データブリッジ", "スマートロジック", "バイトフォース"],
        "平均年収（万）": [520, 460, 430, 610, 400],
        "平均年齢（歳）": [34, 37, 40, 33, 42],
        "海外売上比率（％）": [25, 15, 45, 60, 10],
    },
    "3.通信": {
        "企業名": ["ネクストコミュニケーションズ", "オービットネット", "リンクフロンティア", "グローバルコネクト", "デジタルウェーブ"],
        "平均年収（万）": [650, 580, 520, 720, 490],
        "平均年齢（歳）": [38, 40, 42, 36, 43],
        "海外売上比率（％）": [30, 25, 20, 55, 15],
    },
    "4.化学": {
        "企業名": ["アークケミカル", "ネオマテリアルズ", "東亜ファインケム", "グリーンポリマー", "フロンティア化成"],
        "平均年収（万）": [720, 680, 610, 650, 570],
        "平均年齢（歳）": [41, 39, 43, 40, 44],
        "海外売上比率（％）": [60, 55, 35, 50, 30],
    },
    "5.医薬・バイオ": {
        "企業名": ["ライフセルファーマ", "ネクストバイオ", "メディアーク製薬", "セルゲノム", "フロンティアファーマ"],
        "平均年収（万）": [820, 760, 690, 880, 640],
        "平均年齢（歳）": [39, 37, 42, 36, 44],
        "海外売上比率（％）": [65, 50, 45, 75, 35],
    },
    "6.食品": {
        "企業名": ["グリーンフーズ", "ナチュラルテーブル", "東洋フードリンク", "ワールドデリカ", "フレッシュパレット"],
        "平均年収（万）": [520, 480, 560, 610, 450],
        "平均年齢（歳）": [41, 39, 43, 38, 42],
        "海外売上比率（％）": [25, 20, 30, 45, 15],
    },
    "7.アパレル・繊維": {
        "企業名": ["モードリンク", "ファブリックワークス", "アーバンテキスタイル", "グローバルアパレル", "ネクストファッション"],
        "平均年収（万）": [470, 430, 510, 580, 450],
        "平均年齢（歳）": [38, 42, 40, 36, 39],
        "海外売上比率（％）": [40, 25, 35, 65, 30],
    },
    "8.機械・重工業": {
        "企業名": ["アトラスマシナリー", "東洋メカニクス", "グローバルエンジン", "ネクストインダストリー", "オメガ重工"],
        "平均年収（万）": [700, 650, 730, 610, 780],
        "平均年齢（歳）": [42, 44, 40, 43, 45],
        "海外売上比率（％）": [60, 50, 70, 40, 65],
    },
    "9.輸送用機器": {
        "企業名": ["フロンティアモーターズ", "ネクストビークル", "東亜モビリティ", "グローバルオートテック", "アークトランスポート"],
        "平均年収（万）": [690, 620, 650, 760, 580],
        "平均年齢（歳）": [41, 39, 43, 38, 44],
        "海外売上比率（％）": [70, 55, 60, 80, 45],
    },
    "10.鉄鋼・非鉄金属": {
        "企業名": ["東洋スチール", "ネオメタル工業", "グローバルメタルズ", "アークスチール", "フロンティア非鉄"],
        "平均年収（万）": [680, 620, 720, 590, 650],
        "平均年齢（歳）": [43, 45, 41, 44, 42],
        "海外売上比率（％）": [45, 35, 60, 30, 50],
    },
    "11.エネルギー・資源": {
        "企業名": ["ネクストエナジー", "グローバルリソース", "東洋エネルギー開発", "フロンティア資源", "アースパワー"],
        "平均年収（万）": [780, 850, 720, 810, 690],
        "平均年齢（歳）": [43, 45, 44, 42, 46],
        "海外売上比率（％）": [40, 70, 35, 65, 25],
    },
    "12.商社": {
        "企業名": ["グローバルリンク商事", "ネクストトレード", "東洋ビジネスパートナーズ", "フロンティア商事", "ワールドゲート"],
        "平均年収（万）": [850, 720, 920, 680, 790],
        "平均年齢（歳）": [39, 41, 38, 43, 40],
        "海外売上比率（％）": [70, 55, 80, 45, 65],
    },
    "13.金融": {
        "企業名": ["ネクストフィナンシャル", "アーク銀行ホールディングス", "グローバルキャピタル", "東洋ファイナンス", "フロンティアアセット"],
        "平均年収（万）": [780, 690, 920, 620, 850],
        "平均年齢（歳）": [39, 42, 37, 44, 40],
        "海外売上比率（％）": [35, 20, 60, 15, 45],
    },
    "14.建設・不動産": {
        "企業名": ["アーバンビルド", "ネクストディベロップ", "東都建設パートナーズ", "グローバルプロパティ", "フロンティア都市開発"],
        "平均年収（万）": [650, 610, 720, 680, 590],
        "平均年齢（歳）": [42, 40, 44, 39, 43],
        "海外売上比率（％）": [20, 15, 10, 35, 25],
    },
    "15.小売": {
        "企業名": ["ネクストリテール", "スマートマーケット", "グローバルストアーズ", "ライフスタイルマート", "フレッシュリテール"],
        "平均年収（万）": [480, 450, 520, 430, 460],
        "平均年齢（歳）": [38, 36, 40, 42, 39],
        "海外売上比率（％）": [20, 15, 35, 10, 25],
    },
    "16.サービス・運輸・レジャー": {
        "企業名": ["ネクストトラベル", "グローバルロジスティクス", "アーバンレジャー", "フロンティアサービス", "スマートトランスポート"],
        "平均年収（万）": [470, 540, 430, 500, 510],
        "平均年齢（歳）": [38, 42, 36, 40, 43],
        "海外売上比率（％）": [30, 40, 25, 20, 35],
    },
}

_founding_year_rng = random.Random(42)
for _industry, _data in COMPANY_DATA_BY_INDUSTRY.items():
    _data["創業年"] = [_founding_year_rng.randint(1955, 2020) for _ in _data["企業名"]]

_extra_metrics_rng = random.Random(99)
for _industry, _data in COMPANY_DATA_BY_INDUSTRY.items():
    n = len(_data["企業名"])
    _data["営業利益率（％）"] = [round(_extra_metrics_rng.uniform(2, 25), 1) for _ in range(n)]
    _data["売上高成長率（％）"] = [round(_extra_metrics_rng.uniform(-10, 20), 1) for _ in range(n)]
    _data["営業利益成長率（％）"] = [round(_extra_metrics_rng.uniform(-20, 30), 1) for _ in range(n)]
    _data["平均勤続年数（年）"] = [round(_extra_metrics_rng.uniform(3, 20), 1) for _ in range(n)]
    _data["来期成長率予想（％）"] = [round(_extra_metrics_rng.uniform(-5, 15), 1) for _ in range(n)]
    _data["営業CFマージン（％）"] = [round(_extra_metrics_rng.uniform(-5, 20), 1) for _ in range(n)]
    _data["主力セグメント利益集中度（％）"] = [round(_extra_metrics_rng.uniform(35, 95), 1) for _ in range(n)]


DB_COLUMN_RENAME = {
    "company_name": "企業名",
    "income": "平均年収（万）",
    "age": "平均年齢（歳）",
    "overseas_ratio": "海外売上比率（％）",
    "founding_year": "創業年",
    "operating_margin": "営業利益率（％）",
    "revenue_growth": "売上高成長率（％）",
    "operating_profit_growth": "営業利益成長率（％）",
    "avg_tenure": "平均勤続年数（年）",
    "next_year_growth_forecast": "来期成長率予想（％）",
    "operating_cf_margin": "営業CFマージン（％）",
    "segment_concentration": "主力セグメント利益集中度（％）",
    "sec_code": "証券コード",
    "period_end": "決算期",
    "source": "出典",
    "edinet_code": "EDINETコード",
    "industry": "主業種",
    "industry_shares": "業界別売上比率",
}
DB_SELECT = ",".join(["id", *DB_COLUMN_RENAME.keys()])
# industries / industry_shares 列を追加する前のDBでも動くよう、旧形式の問い合わせも用意しておく
DB_SELECT_LEGACY = ",".join(["id", *(c for c in DB_COLUMN_RENAME if c != "industry_shares")])
PAGE_SIZE = 1000  # Supabase(PostgREST) の1リクエストあたりの既定上限

SCHEMA_HINT = (
    "Supabase の `companies` テーブルに必要な列・権限が無いようです。"
    "同梱の `supabase_schema.sql` を Supabase の SQL Editor で実行してください。"
)


# 企業データは全員共通の公開情報という前提で、ユーザーをまたいでキャッシュする（_client はハッシュ対象外）
def _fetch_pages(client: Client, industry: str, multi_industry: bool) -> list:
    rows, start = [], 0
    # 【修正】EDINET取り込み後は1業界で数百社になるため、1000件上限を超えてもページングで全件取る
    while True:
        query = client.table("companies").select(DB_SELECT if multi_industry else DB_SELECT_LEGACY)
        # 【追加】売上の3割以上を占める事業がある企業は、複数の業界（industries 列）に表示する
        query = query.contains("industries", [industry]) if multi_industry else query.eq("industry", industry)
        batch = query.order("id").range(start, start + PAGE_SIZE - 1).execute().data
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            return rows
        start += PAGE_SIZE


@st.cache_data(ttl=600, show_spinner="企業データを読み込み中…")
def fetch_companies_from_db(industry: str, _client: Client):
    """戻り値: (DataFrame, エラーメッセージ or None)"""
    try:
        try:
            rows = _fetch_pages(_client, industry, multi_industry=True)
        except Exception as e:
            if "industr" not in str(e):
                raise
            rows = _fetch_pages(_client, industry, multi_industry=False)  # 列の追加前のDB
    except Exception as e:
        return pd.DataFrame(columns=DISPLAY_COLUMNS), str(e)
    if not rows:
        return pd.DataFrame(columns=DISPLAY_COLUMNS), None
    df = pd.DataFrame(rows).rename(columns=DB_COLUMN_RENAME)
    df["出典"] = df["出典"].where(df["出典"].notna(), "user")  # source列追加前の旧データは手入力扱い
    for col in ALL_DATA_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.reindex(columns=DISPLAY_COLUMNS), None


def get_industry_data(industry: str) -> dict:
    """【EDINET対応】業界のデータを返す。

    - stats:   業界基準値の計算に使う行。EDINETデータがあればEDINETのみ、無ければサンプル（架空）
    - display: 一覧・検索・グラフ用（stats ＋ 利用者の手入力）
    - kind:    "edinet" / "sample" / "none"

    【修正】旧版はサンプル（架空）・手入力・DBを全部混ぜて平均を出していたため、
    実データと架空データ、誰かの入力ミスが業界基準値に混ざっていた。
    """
    db_df, error = fetch_companies_from_db(industry, get_supabase())
    edinet_df = db_df[db_df["出典"] == "edinet"]
    user_df = db_df[db_df["出典"] != "edinet"]

    if not edinet_df.empty:
        stats_df, kind = edinet_df, "edinet"
    elif industry in COMPANY_DATA_BY_INDUSTRY:
        stats_df = pd.DataFrame(COMPANY_DATA_BY_INDUSTRY[industry]).assign(出典="sample")
        stats_df = stats_df.reindex(columns=DISPLAY_COLUMNS)
        kind = "sample"
    else:
        stats_df, kind = pd.DataFrame(columns=DISPLAY_COLUMNS), "none"

    frames = [f for f in (stats_df, user_df) if not f.empty]
    display_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=DISPLAY_COLUMNS)
    if not display_df.empty:
        display_df["区分"] = [listing_reason(row, industry) for _, row in display_df.iterrows()]
    return {"stats": stats_df, "display": display_df, "kind": kind, "error": error}


def listing_reason(row, industry: str) -> str:
    """この業界に表示されている理由（主業種か、売上の3割以上を占める兼業か）。"""
    main = row.get("主業種")
    if is_missing(main) or main == industry:
        return "主業種"
    shares = row.get("業界別売上比率")
    share = shares.get(industry) if isinstance(shares, dict) else None
    return f"兼業（売上の{share:.0%}）" if share else "兼業"


def clean_row(series) -> dict:
    """DB由来のNaNをNone（＝データなし）に変換する。"""
    return {k: (None if is_missing(v) else v) for k, v in series.to_dict().items()}


MIN_SAMPLES_FOR_BASELINE = 3


def calculate_industry_threshold(industry: str) -> dict:
    """業界基準値（中央値）。

    【修正】実データは「営業利益成長率 +800%」のような外れ値が混ざり、平均だと基準値が大きく歪む。
    就活生向けの「業界の標準的な水準」として中央値を使う。
    データ数が少なすぎる指標は基準値なし（＝評価対象外）にする。
    """
    stats_df = get_industry_data(industry)["stats"]
    result = {}
    for metric in METRIC_COLUMNS + INFO_ONLY_COLUMNS:
        values = pd.to_numeric(stats_df.get(metric), errors="coerce").dropna() if metric in stats_df else pd.Series(dtype=float)
        if len(values) < MIN_SAMPLES_FOR_BASELINE:
            result[metric] = None
        else:
            result[metric] = round(float(values.median()), 1)
    return result


def is_missing(value) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


# 【修正】旧版は全指標を「(値-基準)/基準」の比率で比べていたが、
#   成長率のように基準値がマイナス/ゼロ付近になる指標では符号が逆転する
#   （例：業界 -2%、対象 +5% → 比率 -350% → 「業界平均より低い」と判定されていた）。
#   ％で表す指標は「ポイント差」で比べる。値は「何の差で満点(±30)になるか」。
METRIC_SCALE = {
    "平均年収（万）": ("relative", 30),        # 30%差で±30
    "平均勤続年数（年）": ("relative", 30),
    "海外売上比率（％）": ("point", 30),        # 30ポイント差で±30
    "営業利益率（％）": ("point", 10),
    "売上高成長率（％）": ("point", 15),
    "営業利益成長率（％）": ("point", 30),
    "来期成長率予想（％）": ("point", 10),
    "営業CFマージン（％）": ("point", 10),
    "平均年齢（歳）": ("relative", 30),
}
MAX_METRIC_SCORE = 30.0


def evaluate_metric_diff(metric: str, value: float, base_value: float) -> float:
    mode, saturation = METRIC_SCALE.get(metric, ("relative", 30))
    if mode == "relative":
        if base_value <= 0:
            return 0.0
        diff = (value - base_value) / base_value * 100
    else:
        diff = value - base_value
    score = diff / saturation * MAX_METRIC_SCORE
    return max(-MAX_METRIC_SCORE, min(MAX_METRIC_SCORE, score))


AGE_MAX_ABS_SCORE = 15.0


def evaluate_age_with_tenure(avg_age, industry_avg_age, founding_year):
    """【修正】年齢は「高い＝良い」とは限らないので、平均年齢そのものはスコアに入れない。
    スコアに入れるのは「創業年に対して若すぎる/定着している」という定着度の手がかりだけ。
    創業年が分からない（EDINETデータなど）場合はスコア対象外（None）。
    """
    position = evaluate_metric_diff("平均年齢（歳）", avg_age, industry_avg_age)
    if position >= 10:
        judgement = "平均年齢は業界中央値より高め"
    elif position <= -10:
        judgement = "平均年齢は業界中央値より低め"
    else:
        judgement = "平均年齢は業界中央値並み"

    if is_missing(founding_year):
        return None, judgement + "（創業年が不明のためスコア対象外）"

    company_age_years = CURRENT_YEAR - int(founding_year)
    if company_age_years >= 15 and avg_age < 35:
        return -15.0, judgement + f"（懸念：創業{company_age_years}年に対し平均年齢が若く、早期離職の可能性）"
    if company_age_years >= 15 and avg_age >= 40:
        return 5.0, judgement + f"（好材料：創業{company_age_years}年で平均年齢も高く、定着率の良さがうかがえます）"
    return 0.0, judgement


def evaluate_against_industry(company_row: dict, industry: str) -> dict:
    thresholds = calculate_industry_threshold(industry)
    result = {}
    for metric in METRIC_COLUMNS:
        base_value = thresholds.get(metric)
        company_value = company_row.get(metric)
        # NaNも「データなし」として扱う
        if is_missing(company_value):
            result[metric] = {"score": None, "judgement": "データなし"}
            continue
        if base_value is None:
            result[metric] = {"score": None, "judgement": "業界の比較データが不足しているため評価対象外"}
            continue
        company_value = float(company_value)
        if metric == "平均年齢（歳）":
            score, judgement = evaluate_age_with_tenure(company_value, base_value, company_row.get("創業年"))
        else:
            score = evaluate_metric_diff(metric, company_value, base_value)
            if score >= 10:
                judgement = "業界中央値より高い"
            elif score <= -10:
                judgement = "業界中央値より低い"
            else:
                judgement = "業界中央値並み"
            judgement += f"（{company_value:g} / 業界中央値 {base_value:g}）"
        result[metric] = {"score": score, "judgement": judgement}
    return result


def calculate_company_score_pct(comparison: dict) -> float:
    total = 0.0
    max_possible = 0.0
    for metric, info in comparison.items():
        if info["score"] is None:
            continue
        # 【修正】旧版は年齢の重みが45なのに実際の点数幅は-45〜+35で、満点の基準がずれていた
        weight = AGE_MAX_ABS_SCORE if metric == "平均年齢（歳）" else MAX_METRIC_SCORE
        total += info["score"]
        max_possible += weight
    if max_possible == 0:
        return 0.0
    return max(-100.0, min(100.0, total / max_possible * 100))


def describe_segment_concentration(company_value, industry_avg):
    if is_missing(company_value) or industry_avg is None:
        return None
    diff = company_value - industry_avg
    if diff >= 15:
        note = "特定事業への依存度が業界中央値より高めです（1事業に利益が偏っています）"
    elif diff <= -15:
        note = "事業が業界中央値より分散されており、特定事業への依存は低めです"
    else:
        note = "業界中央値並みの事業構成です"
    return f"主力セグメント利益集中度：{company_value:.0f}%（業界中央値{industry_avg:.0f}%）→ {note}"


def apply_comparison(company_name: str, company_row: dict, industry: str):
    """検索・手入力どちらからでも同じ手順で比較結果を session_state に入れる。"""
    thresholds = calculate_industry_threshold(industry)
    comparison = evaluate_against_industry(company_row, industry)
    st.session_state["selected_company"] = company_name
    st.session_state["selected_edinet_code"] = company_row.get("EDINETコード")  # 手入力・サンプルは None
    st.session_state["comparison_result"] = comparison
    st.session_state["company_score_pct"] = calculate_company_score_pct(comparison)
    st.session_state["segment_note"] = describe_segment_concentration(
        company_row.get("主力セグメント利益集中度（％）"), thresholds.get("主力セグメント利益集中度（％）")
    )


_HEADLINE_RAW = [
    ("連続最高益", 5, "利益", "利益", "最高益継続", 85),
    ("最高益更新", 5, "利益", "利益", "過去最高更新", 36),
    ("最高純益", 5, "利益", "純利益", "過去最高", 0),
    ("最高益", 5, "利益", "利益", "過去最高", 110),
    ("最高益圏", 4, "利益", "利益", "高水準", 7),
    ("続伸", 3, "成長", "売上・利益等", "増加継続", 222),
    ("増勢", 3, "成長", "売上・利益等", "増加傾向", 68),
    ("成長続く", 4, "成長", "業績・事業", "成長継続", 1),
    ("連続増益", 4, "利益", "利益", "増益継続", 92),
    ("増益続く", 4, "利益", "利益", "増益継続", 85),
    ("絶好調", 5, "業績モメンタム", "業績全般", "非常に好調", 8),
    ("好調", 3, "業績モメンタム", "業績全般", "好調", 48),
    ("大幅増益", 4, "利益", "利益", "大幅増加", 73),
    ("高水準", 2, "業績水準", "売上・利益等", "高水準", 24),
    ("連続増配", 4, "株主還元", "配当", "増配継続", 214),
    ("快走", 4, "業績モメンタム", "業績全般", "強い進捗", 64),
    ("加速", 4, "成長", "成長率・利益等", "成長加速", 9),
    ("好発進", 3, "業績モメンタム", "業績進捗", "好スタート", 2),
    ("増益基調", 3, "利益", "利益", "増益傾向", 12),
    ("着実増", 3, "成長", "売上・利益等", "着実な増加", 16),
    ("着実", 2, "業績モメンタム", "業績全般", "安定・順調", 17),
    ("順調", 2, "業績モメンタム", "業績全般", "順調", 29),
    ("堅調", 2, "業績モメンタム", "業績全般", "安定・堅調", 56),
    ("前進", 2, "業績モメンタム", "業績全般", "改善", 3),
    ("伸長", 3, "成長", "売上・事業規模等", "増加", 29),
    ("小幅増益", 2, "利益", "利益", "小幅増加", 70),
    ("小幅増益圏", 1, "利益", "利益", "小幅増益", 1),
    ("営業増益", 2, "利益", "営業利益", "増加", 2),
    ("微増益", 1, "利益", "利益", "微増", 27),
    ("微増益圏", 1, "利益", "利益", "微増", 6),
    ("回復軌道", 3, "回復", "業績全般", "回復継続", 1),
    ("好転", 3, "回復", "業績全般", "改善", 121),
    ("上向く", 3, "回復", "業績全般", "改善", 147),
    ("急改善", 4, "回復", "業績全般・利益", "大幅改善", 17),
    ("Ｖ字回復", 4, "回復", "業績全般", "急回復", 8),
    ("急回復", 4, "回復", "業績全般", "急速回復", 16),
    ("急浮上", 4, "回復", "業績全般", "急改善", 4),
    ("回復", 3, "回復", "業績全般", "改善", 10),
    ("急反発", 4, "回復", "業績・利益等", "急改善", 29),
    ("好反発", 3, "回復", "業績全般", "強い回復", 10),
    ("反発", 2, "回復", "業績全般", "回復", 71),
    ("反転増", 3, "回復", "利益等", "減少→増加", 22),
    ("復調", 3, "回復", "業績全般", "回復", 37),
    ("改善", 2, "回復", "業績全般", "改善", 32),
    ("小反発", 1, "回復", "業績全般", "小幅回復", 26),
    ("持ち直す", 1, "回復", "業績全般", "悪化→改善", 9),
    ("底打ち", 1, "回復", "業績全般", "悪化停止", 5),
    ("底入れ", 1, "回復", "業績全般", "悪化停止", 11),
    ("底離れ", 2, "回復", "業績全般", "底→上昇", 0),
    ("戻り歩調", 1, "回復", "業績全般", "回復", 4),
    ("回復基調", 2, "回復", "業績全般", "回復傾向", 9),
    ("改善基調", 2, "回復", "業績全般", "改善傾向", 5),
    ("浮上", 2, "回復", "業績全般", "改善", 51),
    ("赤字縮小", 2, "損益状態", "赤字", "赤字改善", 7),
    ("黒字化", 4, "損益状態", "利益", "赤字→黒字", 61),
    ("黒字復帰", 4, "損益状態", "利益", "赤字→黒字", 37),
    ("復配", 3, "株主還元", "配当", "無配→配当", 9),
    ("増配", 4, "株主還元", "配当", "増額", 174),
    ("増益幅拡大", 4, "利益", "利益", "増益加速", 3),
    ("大幅増額", 4, "業績予想修正", "業績予想", "上方修正", 0),
    ("独自増額", 5, "業績予想修正", "四季報予想", "上方修正", 29),
    ("減益幅縮小", 2, "利益", "利益", "減益改善", 19),
    ("上振れ", 4, "業績予想修正", "業績・利益等", "予想超過", 34),
    ("再増額", 5, "業績予想修正", "業績予想", "再上方修正", 1),
    ("一転増益", 4, "利益", "利益", "減益→増益", 4),
    ("一転黒字", 4, "損益状態", "利益", "赤字→黒字", 0),
    ("増額", 4, "業績予想修正", "業績予想", "上方修正", 51),
    ("赤字幅縮小", 2, "損益状態", "赤字", "赤字改善", 4),
    ("後半挽回", 1, "業績モメンタム", "業績進捗", "後半改善", 1),
    ("大幅赤字", -5, "損益状態", "赤字", "大幅悪化", 2),
    ("赤字転落", -4, "損益状態", "利益", "黒字→赤字", 7),
    ("連続赤字", -5, "損益状態", "赤字", "赤字継続", 10),
    ("続落", -3, "成長", "売上・利益等", "減少継続", 53),
    ("苦戦続く", -4, "業績モメンタム", "業績全般", "不振継続", 0),
    ("連続減益", -4, "利益", "利益", "減益継続", 22),
    ("減益続く", -4, "利益", "利益", "減益継続", 21),
    ("大赤字", -5, "損益状態", "赤字", "大幅赤字", 0),
    ("赤字続く", -5, "損益状態", "赤字", "赤字継続", 21),
    ("赤字継続", -5, "損益状態", "赤字", "赤字継続", 5),
    ("大幅減益", -4, "利益", "利益", "大幅減少", 34),
    ("赤字", -4, "損益状態", "利益", "赤字", 12),
    ("急降下", -4, "業績モメンタム", "業績全般", "急悪化", 4),
    ("赤字拡大", -5, "損益状態", "赤字", "赤字悪化", 7),
    ("後退", -3, "業績モメンタム", "業績全般", "悪化", 28),
    ("低迷", -3, "業績モメンタム", "業績全般", "低調", 2),
    ("急反落", -4, "業績モメンタム", "業績・利益等", "急悪化", 19),
    ("水面下", -3, "損益状態", "利益", "赤字圏", 27),
    ("一歩後退", -2, "業績モメンタム", "業績全般", "小幅悪化", 14),
    ("赤字残る", -3, "損益状態", "赤字", "赤字継続", 14),
    ("底ばい", -2, "業績モメンタム", "業績全般", "低水準停滞", 3),
    ("ゼロ圏", -1, "損益状態", "利益", "ほぼゼロ", 6),
    ("小幅減益", -2, "利益", "利益", "小幅減少", 47),
    ("小幅赤字", -2, "損益状態", "赤字", "小幅赤字", 5),
    ("微減益", -1, "利益", "利益", "微減", 11),
    ("均衡圏", 0, "損益状態", "損益", "±0付近", 18),
    ("停滞", -2, "業績モメンタム", "業績全般", "成長停止", 9),
    ("反落", -3, "業績モメンタム", "業績・利益等", "増加→減少", 185),
    ("急落", -4, "業績モメンタム", "業績等", "急減少", 25),
    ("急減速", -4, "成長", "成長率・利益等", "急鈍化", 0),
    ("急悪化", -5, "業績モメンタム", "業績全般", "急激悪化", 0),
    ("下降", -3, "業績モメンタム", "業績等", "下降", 0),
    ("反動減", -2, "成長", "売上・利益等", "一時的減少", 5),
    ("横ばい", 0, "業績水準", "売上・利益等", "変化なし", 86),
    ("横ばい圏", 0, "業績水準", "売上・利益等", "ほぼ変化なし", 61),
    ("軟調", -2, "業績モメンタム", "業績全般", "弱含み", 30),
    ("低調", -3, "業績モメンタム", "業績全般", "低調", 7),
    ("低水準", -2, "業績水準", "売上・利益等", "低水準", 4),
    ("苦戦", -3, "業績モメンタム", "業績全般", "不振", 4),
    ("不透明", -1, "見通し", "業績見通し", "不確実", 2),
    ("回復途上", 1, "回復", "業績全般", "回復中", 3),
    ("回復鈍い", -1, "回復", "業績全般", "回復弱い", 0),
    ("足踏み", -1, "業績モメンタム", "業績全般", "改善停滞", 43),
    ("一服", -1, "業績モメンタム", "成長・業績", "一時鈍化", 25),
    ("頭打ち", -2, "成長", "成長・業績", "成長限界", 1),
    ("踊り場", -1, "業績モメンタム", "業績全般", "一時停滞", 16),
    ("費用先行", -1, "コスト", "利益・費用", "費用先行", 4),
    ("先行投資", 0, "投資", "費用・成長投資", "短期負担", 6),
    ("費用増", -2, "コスト", "費用", "コスト増加", 19),
    ("特需剥落", -3, "外部要因", "売上・利益", "特需消失", 3),
    ("剥落", -3, "外部要因", "売上・利益等", "追い風消失", 2),
    ("無配", -4, "株主還元", "配当", "配当なし", 2),
    ("減配", -4, "株主還元", "配当", "減額", 24),
    ("減益幅拡大", -4, "利益", "利益", "悪化加速", 4),
    ("大幅減額", -5, "業績予想修正", "業績予想", "大幅下方修正", 1),
    ("赤字幅拡大", -5, "損益状態", "赤字", "赤字悪化", 5),
    ("増益幅縮小", -2, "利益", "利益", "増益鈍化", 8),
    ("下振れ", -4, "業績予想修正", "業績・利益等", "予想未達", 14),
    ("再減額", -5, "業績予想修正", "業績予想", "再下方修正", 0),
    ("一転減益", -4, "利益", "利益", "増益→減益", 8),
    ("一転赤字", -5, "損益状態", "利益", "黒字→赤字", 1),
    ("減額", -4, "業績予想修正", "業績予想", "下方修正", 8),
    ("減速", -3, "成長", "成長率・利益等", "鈍化", 4),
    ("後半減速", -2, "成長", "業績進捗", "後半鈍化", 0),
]

HEADLINE_DICTIONARY = {
    row[0]: {"score": row[1], "category": row[2], "target": row[3], "direction": row[4], "frequency": row[5]}
    for row in _HEADLINE_RAW
}


def normalize_text(text: str) -> str:
    """全角/半角の揺れ（Ｖ字回復 / V字回復 など）を吸収する。"""
    return unicodedata.normalize("NFKC", text).replace(" ", "").replace("　", "")


# (正規化後キー, 元のキー) を長い順に並べ、長い語から先にマッチさせる
_NORMALIZED_HEADLINE_KEYS = sorted(
    ((normalize_text(k), k) for k in HEADLINE_DICTIONARY.keys()),
    key=lambda x: len(x[0]),
    reverse=True,
)

EXPECTED_HEADLINE_COUNT = 133
# 見出し語と出現数の出典（スコア等は独自に付与）
HEADLINE_SOURCE_NAME = "会社四季報オンライン（東洋経済新報社）"
HEADLINE_SOURCE_URL = "https://shikiho.toyokeizai.net/headwords"


def validate_headline_dictionary():
    errors = []
    warnings = []
    # 【修正】同じ見出し語を2回書くと dict で上書きされて黙って消えるので、元リストで重複を検出する
    seen = set()
    for row in _HEADLINE_RAW:
        if row[0] in seen:
            errors.append(f"「{row[0]}」が重複登録されています（後の行で上書きされます）")
        seen.add(row[0])
    if len(HEADLINE_DICTIONARY) != EXPECTED_HEADLINE_COUNT:
        errors.append(f"登録語数が{EXPECTED_HEADLINE_COUNT}語ではありません：{len(HEADLINE_DICTIONARY)}語")

    required_fields = {"score", "category", "target", "direction", "frequency"}
    for key, info in HEADLINE_DICTIONARY.items():
        if not key:
            errors.append("空の見出し語があります")
            continue
        missing = required_fields - set(info.keys())
        if missing:
            errors.append(f"「{key}」: 必須項目が不足しています → {missing}")

    keys = list(HEADLINE_DICTIONARY.keys())
    for short in keys:
        for long in keys:
            if short == long or len(short) >= len(long):
                continue
            if short in long:
                short_score = HEADLINE_DICTIONARY[short]["score"]
                long_score = HEADLINE_DICTIONARY[long]["score"]
                if (short_score > 0) != (long_score > 0) and short_score != 0 and long_score != 0:
                    warnings.append(
                        f"「{short}」({short_score:+d})が「{long}」({long_score:+d})に含まれており、"
                        "符号が逆です（長い語から先にマッチさせる設計で対応済み）"
                    )
    return errors, warnings


HEADLINE_DICTIONARY_ERRORS, HEADLINE_DICTIONARY_WARNINGS = validate_headline_dictionary()


def match_headline(text: str):
    if not text:
        return None
    normalized = normalize_text(text)
    for norm_key, key in _NORMALIZED_HEADLINE_KEYS:
        if norm_key in normalized:
            return key, HEADLINE_DICTIONARY[key]
    return None


def rank_weight(rank: int, total: int = 15) -> float:
    if total <= 1:
        return 1.0
    return 1.00 - (rank - 1) / (total - 1) * 0.70


def calculate_market_sentiment(rankings: list) -> dict:
    weighted_sum = 0.0
    weight_sum = 0.0
    category_counts = {}
    details = []
    total = len(rankings)
    for i, text in enumerate(rankings):
        rank = i + 1
        if not text.strip():
            continue
        match = match_headline(text)
        w = rank_weight(rank, total)
        if match:
            key, info = match
            weighted_sum += info["score"] * w
            weight_sum += w
            category_counts[info["category"]] = category_counts.get(info["category"], 0) + 1
            details.append({"rank": rank, "text": text, "keyword": key, "score": info["score"]})
        else:
            details.append({"rank": rank, "text": text, "keyword": None, "score": None})
    sentiment = weighted_sum / weight_sum if weight_sum > 0 else None
    return {"sentiment": sentiment, "category_breakdown": category_counts, "details": details}


def calculate_company_headline_score(headline_text: str):
    match = match_headline(headline_text)
    if not match:
        return None
    key, info = match
    return {
        "keyword": key,
        "score": info["score"],
        "category": info["category"],
        "direction": info["direction"],
        "frequency": info["frequency"],
        "is_rare": info["frequency"] <= 5,
    }


def calculate_reporter_component(headline_text: str, rankings: list):
    market_result = calculate_market_sentiment(rankings)
    market_sentiment = market_result["sentiment"]
    company_result = calculate_company_headline_score(headline_text)

    # 【修正】旧版は「入力欄が埋まっている数」で重みを決めていたため、辞書に無い語（評価に使われない語）
    #   を並べても重みが最大60になっていた。実際にセンチメント計算に使えた件数で判定する。
    matched_rankings_count = sum(1 for d in market_result["details"] if d["keyword"] is not None)
    filled_rankings_count = sum(1 for r in rankings if r.strip())
    headline_filled = bool(headline_text.strip())

    if not headline_filled and filled_rankings_count == 0:
        return 0.0, 0.0, "スキップ（企業データのみで評価）", None

    company_abs = company_result["score"] if company_result else None
    relative = None
    if company_abs is not None and market_sentiment is not None:
        relative = company_abs - market_sentiment

    detail = {
        "company": company_result,
        "market_sentiment": market_sentiment,
        "relative": relative,
        "market_category_breakdown": market_result["category_breakdown"],
        "market_details": market_result["details"],
    }

    # 対象企業の見出しが評価できない場合、市場センチメントは「企業自身の評価」ではないので重み0
    if company_abs is None:
        if headline_filled:
            level = "対象企業の見出しが辞書に一致しないため、企業データのみで評価"
        else:
            level = "対象企業の見出しが未入力のため、企業データのみで評価（市場ランキングは参考表示）"
        return 0.0, 0.0, level, detail

    if relative is not None:
        blended = company_abs * 0.6 + relative * 0.4
        reporter_score_pct = max(-100.0, min(100.0, blended / 8 * 100))
    else:
        reporter_score_pct = max(-100.0, min(100.0, company_abs / 5 * 100))

    if matched_rankings_count >= 12:
        weight = 60.0
        level = "市場全体ランキング（ほぼ全件入力・最重視）"
    elif matched_rankings_count < 3:
        weight = 25.0
        level = "対象企業の記者コメントのみ"
    else:
        weight = min(60.0, 25.0 + matched_rankings_count * 2.5)
        level = f"ランキング一部入力（辞書一致{matched_rankings_count}件）"
    if filled_rankings_count > matched_rankings_count:
        level += f"／辞書に一致しない語{filled_rankings_count - matched_rankings_count}件は除外"

    return reporter_score_pct, weight, level, detail


COMPANY_WEIGHT = 40.0


def calculate_final_score(company_score_pct: float, reporter_score_pct: float, reporter_weight: float) -> float:
    total_weight = COMPANY_WEIGHT + reporter_weight
    if total_weight == 0:
        return 0.0
    return (company_score_pct * COMPANY_WEIGHT + reporter_score_pct * reporter_weight) / total_weight


EXPECTED_TYPICAL_MAX = {
    "平均年収（万）": 1500,
    "平均年齢（歳）": 65,
    "海外売上比率（％）": 100,
    "営業利益率（％）": 40,
    "売上高成長率（％）": 50,
    "営業利益成長率（％）": 80,
    "平均勤続年数（年）": 40,
    "来期成長率予想（％）": 50,
    "営業CFマージン（％）": 40,
    "主力セグメント利益集中度（％）": 100,
}
POSITIVE_ONLY_METRICS = {
    "平均年収（万）", "平均年齢（歳）", "海外売上比率（％）",
    "平均勤続年数（年）", "主力セグメント利益集中度（％）",
}
SIGNED_METRICS = {
    "営業利益率（％）", "売上高成長率（％）", "営業利益成長率（％）",
    "来期成長率予想（％）", "営業CFマージン（％）",
}


def validate_metrics(values: dict):
    has_negative_error = False
    needs_confirmation = False
    is_extreme_outlier = False
    messages = []

    for metric, value in values.items():
        if value is None:
            continue

        if metric in POSITIVE_ONLY_METRICS and value < 0:
            has_negative_error = True
            messages.append(f"❌「{metric}」はマイナスの値を取りえません。修正してください。（入力値：{value}）")
            continue

        if metric in ("海外売上比率（％）", "主力セグメント利益集中度（％）"):
            if value > 100:
                needs_confirmation = True
                messages.append(f"⚠️「{metric}」が100％を超えています。入力に誤りがないかご確認ください。")
            continue

        typical_max = EXPECTED_TYPICAL_MAX.get(metric)
        if typical_max is None:
            continue

        check_value = abs(value) if metric in SIGNED_METRICS else value

        if check_value >= typical_max * 10:
            is_extreme_outlier = True
            messages.append(
                f"🚨「{metric}」が想定の10倍程度（絶対値{typical_max * 10}以上）です。"
                "異常値と判断し、この結果はデータベースには保存されません。"
            )
        elif check_value >= typical_max * 3:
            needs_confirmation = True
            messages.append(
                f"⚠️「{metric}」が想定範囲の3倍近く（絶対値{typical_max * 3}以上）です。"
                "入力に間違いがないかご確認の上、チェックしてください。"
            )

    return has_negative_error, needs_confirmation, is_extreme_outlier, messages


def validate_founding_year(founding_year):
    if founding_year is None:
        return True, ""
    if not float(founding_year).is_integer():
        return False, f"❌「創業年」は西暦の整数で入力してください（入力値：{founding_year}）。"
    if founding_year > CURRENT_YEAR:
        return False, f"❌「創業年」が未来の年になっています（入力値：{founding_year:.0f}）。修正してください。"
    if founding_year < 1850:
        return False, f"⚠️「創業年」が古すぎます（入力値：{founding_year:.0f}）。入力に誤りがないかご確認ください。"
    return True, ""


SKIP_INPUT_SYMBOLS = {"", ",", "、", "，", "-", "ー", "－", "‐", "―", "なし", "N/A", "n/a"}


def parse_optional_metric(raw_value: str):
    """未入力や「,」などは「データなし」(None, None)。数値でなければ (None, エラー文)。"""
    text = (raw_value or "").strip()
    if text in SKIP_INPUT_SYMBOLS:
        return None, None
    # 【修正】全角数字・全角マイナス（「１２．５」「－３」）も受け付ける
    normalized = unicodedata.normalize("NFKC", text).replace("−", "-").replace("ー", "-")
    normalized = normalized.replace(",", "").replace("%", "")
    try:
        return float(normalized), None
    except ValueError:
        return None, (
            f"「{raw_value}」を数値として認識できません。"
            "数値を入力するか、データが無い場合は空欄または「,」にしてスキップしてください。"
        )


def calculate_operating_margin(operating_profit, revenue):
    # 【修正】売上高がマイナスだと率が意味を持たないので除外
    if operating_profit is None or revenue is None or revenue <= 0:
        return None
    return round(operating_profit / revenue * 100, 1)


def normalize_company_name(name) -> str:
    """【EDINET対応】「トヨタ」で「トヨタ自動車株式会社」が引けるよう、表記揺れを吸収する。"""
    s = unicodedata.normalize("NFKC", str(name or ""))  # ㈱ → (株)、全角英数 → 半角
    for token in ("株式会社", "(株)", "有限会社", "合同会社", " ", "　", "・"):
        s = s.replace(token, "")
    return s.lower()


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def get_name_table() -> pd.DataFrame:
    """EDINET コードリスト（社名・英語名・読み仮名）。取得できなければ空の表（別名検索なしで動く）。"""
    try:
        return company_names.load_name_table()
    except Exception:
        return pd.DataFrame(columns=["edinet_code", "name", "name_en", "name_kana", "sec_code"])


def search_companies(df: pd.DataFrame, query: str) -> list:
    """一致した行の index を一致の強い順に返す。

    【追加】正式名の一部だけでなく、証券コード・英語名の頭文字（NRI）・英語名（nomura）・
    読み仮名（のむら）・略称（野村総研）でも引けるようにした（EDINET のコードリストを利用、LLMは不使用）。
    """
    q = unicodedata.normalize("NFKC", query or "").strip()
    if not q:
        return []
    names = get_name_table().set_index("edinet_code")
    ranked = []
    for idx, row in df.iterrows():
        code = row.get("EDINETコード")
        alias = names.loc[code] if isinstance(code, str) and code in names.index else None
        if str(row.get("証券コード") or "") == q:
            rank = company_names.EXACT
        else:
            rank = company_names.match_rank(
                q, row["企業名"],
                alias["name_en"] if alias is not None else None,
                alias["name_kana"] if alias is not None else None,
            )
        if rank is not None:
            ranked.append((rank, idx))
    return [idx for _, idx in sorted(ranked, key=lambda x: x[0])]


def find_in_other_industries(query: str, current_industry: str) -> list:
    """選んだ業界に見つからないとき、上場企業全体から探して、どの業界のデータにあるかを返す。"""
    hits = company_names.search_names(query, get_name_table(), limit=5)
    if hits.empty:
        return []
    try:
        rows = (get_supabase().table("companies").select("edinet_code,company_name,industry,industries")
                .in_("edinet_code", hits["edinet_code"].tolist()).execute().data)
    except Exception:
        rows = []
    in_db = {r["edinet_code"]: r for r in rows}
    results = []
    for _, h in hits.iterrows():
        r = in_db.get(h["edinet_code"])
        industries = (r.get("industries") or [r.get("industry")]) if r else []
        results.append({
            "name": h["name"],
            "industries": [i for i in industries if i and i != current_industry],
            "in_current": bool(r) and current_industry in industries,
            "has_data": bool(r),
        })
    return results


def switch_industry_and_search(industry: str, company_name: str):
    """別の業界に切り替えて、その企業を検索した状態にする（ボタンのコールバック）。"""
    reset_analysis_state()
    st.session_state["selected_industry"] = industry
    st.session_state["company_search_input"] = company_name
    st.session_state["pending_search"] = True


def get_user_role(user) -> str:
    # user_metadata は本人が書き換え可能。サーバー側でのみ変更できる app_metadata を使う。
    try:
        return (getattr(user, "app_metadata", None) or {}).get("role", "user")
    except Exception:
        return "user"


BASELINE_HEADLINE = [
    ("平均年収（万）", "平均年収", "万円"),
    ("平均年齢（歳）", "平均年齢", "歳"),
    ("海外売上比率（％）", "海外売上比率", "％"),
]
BASELINE_DETAIL = [
    ("営業利益率（％）", "営業利益率", "％"),
    ("売上高成長率（％）", "売上高成長率", "％"),
    ("営業利益成長率（％）", "営業利益成長率", "％"),
    ("平均勤続年数（年）", "平均勤続年数", "年"),
    ("来期成長率予想（％）", "来期成長率予想", "％"),
    ("営業CFマージン（％）", "営業CFマージン", "％"),
    ("主力セグメント利益集中度（％）", "主力セグメント利益集中度（参考情報・スコア対象外）", "％"),
]


def fmt_threshold(value, unit: str = "") -> str:
    return "データなし" if value is None else f"{value}{unit}"


def threshold_placeholder(value) -> str:
    return "" if value is None else f"業界中央値 {value}"


def _json_safe(value):
    """pandas/numpy の値を Supabase に送れる形にする（NaN → None、numpy型 → Python型）。"""
    if is_missing(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def describe_auth_error(error: Exception, action: str) -> str:
    """Supabase Auth のエラーを、利用者が次に何をすればよいか分かる日本語にする。"""
    text = str(error).lower()
    if "email not confirmed" in text:
        return "メールアドレスの確認が済んでいません。届いた確認メールのリンクを開いてから、ログインしてください。"
    if "not authorized" in text:
        # Supabase 標準のメール送信は、プロジェクトのチームメンバー宛てにしか送れない
        return ("確認メールを送れなかったため、登録できませんでした。"
                "（管理者向け：Supabase の確認メール設定か SMTP 設定を見直してください）")
    if "rate limit" in text:
        return "短時間に操作が集中しています。しばらく時間をおいてから、もう一度お試しください。"
    if "already registered" in text or "already exists" in text:
        return "このメールアドレスは登録済みです。「ログイン」タブからログインしてください。"
    if "invalid login credentials" in text:
        return "メールアドレスまたはパスワードが正しくありません。"
    if "password" in text and ("weak" in text or "at least" in text):
        return "パスワードが条件を満たしていません。より長い、推測されにくいパスワードにしてください。"
    if "email" in text and "invalid" in text:
        return "メールアドレスの形式が正しくありません。"
    return f"{action}に失敗しました：{error}"


def page_login():
    st.title("🔐 ログイン")
    st.write("本ツールの利用にはログインが必要です")
    tab_login, tab_signup = st.tabs(["ログイン", "新規登録"])
    with tab_login:
        email = st.text_input("メールアドレス", key="login_email")
        password = st.text_input("パスワード", type="password", key="login_password")
        if st.button("ログイン", type="primary"):
            try:
                res = get_supabase().auth.sign_in_with_password({"email": email.strip(), "password": password})
                st.session_state["auth_user"] = res.user
                st.session_state.pop("login_password", None)
                st.rerun()
            except Exception as e:
                # 【修正】旧版は何のエラーでも「パスワードが違う」と表示していた（メール未確認でも）
                st.error(describe_auth_error(e, "ログイン"))
    with tab_signup:
        new_email = st.text_input("メールアドレス", key="signup_email")
        new_password = st.text_input("パスワード（8文字以上）", type="password", key="signup_password")
        if st.button("登録する"):
            if len(new_password) < 8:
                st.error("パスワードは8文字以上にしてください。")
            else:
                try:
                    res = get_supabase().auth.sign_up({"email": new_email.strip(), "password": new_password})
                except Exception as e:
                    st.error(describe_auth_error(e, "登録"))
                else:
                    if res.session is not None:
                        # Supabase で「メール確認」をオフにしている場合は、その場でログインできる
                        st.session_state["auth_user"] = res.user
                        st.rerun()
                    st.success(
                        "確認メールを送信しました。メール内のリンクを開いてから、ログインしてください。"
                        "（届かない場合は迷惑メールフォルダも確認してください）"
                    )


def page_title():
    st.title("📊 就活生のための企業データ分析ツール")
    st.write("有価証券報告書（EDINET）の実データと、四季報の見出し語から企業の傾向を多角的に分析します。")
    user = st.session_state["auth_user"]
    st.caption(f"ログイン中：{user.email}")
    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("始める", type="primary"):
            goto("disclaimer")
    with col2:
        if st.button("ログアウト"):
            try:
                get_supabase().auth.sign_out()
            except Exception:
                pass
            # クライアントごと破棄し、管理者認証状態もリセットする
            for k in ["supabase", "auth_user", "is_admin_authed", "admin_attempts"]:
                st.session_state.pop(k, None)
            reset_analysis_state()
            st.session_state["page"] = "title"
            st.rerun()
    if get_user_role(user) == "admin":
        st.write("---")
        if st.button("🔒 管理者ページへ"):
            goto("admin")


def page_disclaimer():
    st.title("⚖️ ご利用前の確認と同意")
    st.write("本システムを安全にご利用いただくため、以下の内容への同意が必要です。")
    with st.container(border=True):
        st.subheader("企業分析ツール　ご利用にあたって")
        st.markdown("""
第一条（目的）
本プログラムは、EDINETで公開されている有価証券報告書等の公開情報をもとにした財務指標・人材指標、
および四季報の見出し語等により、業界内での企業の傾向を把握するための参考情報提供ツールです。

第二条（断定的表現の排除）
本ツールが示す評価スコアは機械的な計算結果であり、
対象企業への入社の可否や優劣を断定するものではありません。

第三条（業界差の考慮）
指標の基準は業界によって大きく異なります。単一の指標のみで
企業の良し悪しを判断しないようご注意ください。

第四条（データの限界）
自動取得したデータには、会計基準の違いや開示様式の違いによる抽出漏れ・誤りが含まれる可能性があります。
重要な判断の前には、必ず原本（有価証券報告書）を確認してください。
AIによる要約は、事実と異なる内容や重要な情報の抜け落ちを含む可能性があります。

第五条（免責事項）
利用者は本ツールの情報を参考情報として扱い、就職活動における最終的な
判断は自己の責任において行うものとします。
        """)
    st.write("---")
    if st.button("理解した"):
        goto("industry_select")
    else:
        st.write("「理解した」ボタンを押してください。")


def page_industry_select():
    st.title("業界を選択してください")
    current = st.session_state.get("selected_industry")
    index = INDUSTRIES.index(current) if current in INDUSTRIES else None
    industry = st.selectbox("業界", INDUSTRIES, index=index, placeholder="選択してください")
    if st.button("次へ", disabled=(industry is None)):
        # 業界が変わったら前の比較結果などをクリアする
        if industry != current:
            reset_analysis_state()
        st.session_state["selected_industry"] = industry
        goto("company_data")


def render_data_source_notice(data: dict):
    if data["error"]:
        st.error(f"企業データベースの読み込みに失敗しました：{data['error']}")
        st.info(SCHEMA_HINT)
    if data["kind"] == "edinet":
        stats = data["stats"]
        latest = pd.to_datetime(stats["決算期"], errors="coerce").max()
        latest_text = latest.strftime("%Y年%m月期") if not pd.isna(latest) else "不明"
        st.info(
            f"📑 業界基準値は **EDINET（有価証券報告書）の実データ {len(stats)}社** から計算しています"
            f"（最新の決算期：{latest_text}）。\n\n"
            "・平均年収・平均年齢・平均勤続年数は「提出会社（単体）」の値です。"
            "持株会社は従業員が少なく、年収が高めに出ることがあります。\n\n"
            "・海外売上比率・創業年・来期成長率予想・主力セグメント集中度は有報の標準データから"
            "自動取得できないため「データなし」になります（四季報で確認してください）。"
        )
    elif data["kind"] == "sample":
        st.warning(
            "⚠️ この業界はまだ実データ（EDINET）が取り込まれていないため、"
            "**サンプル（架空）データ** を表示しています。"
            "実在企業の判断材料としては使わず、ツールの使い方の確認用としてご利用ください。"
        )
    if (data["display"]["出典"] == "user").any():
        st.caption("※「出典：手入力」の行は利用者が入力したデータです。業界基準値の計算には使っていません。")


def render_manual_input_form(industry: str, thresholds: dict, display_df: pd.DataFrame):
    st.warning("該当企業が見つかりません。データを直接入力してください。")
    render_location_popover(shikiho_guide.LOCATIONS_FOR_MANUAL_INPUT)
    st.caption(
        "四季報・有報に載っていない・わからない項目は、空欄のままか「,」などの記号を入力すると"
        "「データなし」としてスキップされます（業界基準値で穴埋めせず、評価からも除外されます）。"
    )
    default_name = st.session_state.get("company_search_input") or "マイカンパニー"
    my_company = st.text_input("企業名", value=default_name, key="manual_company").strip()
    my_income = st.number_input("平均年収（万）", value=400, key="manual_income")
    my_age = st.number_input("平均年齢（歳）", value=40, key="manual_age")
    my_overseas_raw = st.text_input(
        "海外売上比率（％）　※不明なら空欄または「,」でスキップ可",
        value="",
        placeholder=threshold_placeholder(thresholds.get("海外売上比率（％）")),
        key="manual_overseas",
    )
    # 【修正】旧版は創業年が必須（初期値2010）で、知らない人も2010年創業扱いになり年齢評価が歪んでいた
    my_founding_year_raw = st.text_input(
        "創業年（西暦）　※不明なら空欄でスキップ可", value="", key="manual_founding_year"
    )

    with st.expander("詳細指標を入力（任意・不明な項目はスキップ可）", expanded=True):
        st.caption(
            "営業利益率は自動計算されます。四季報に記載されている「営業利益」と「売上高」の"
            "数値をそのまま入力してください（単位は百万円・億円などどちらでも構いませんが、"
            "2つの単位は揃えてください）。"
        )
        my_operating_profit_raw = st.text_input(
            "営業利益　※不明なら空欄でスキップ可", value="", key="manual_operating_profit"
        )
        my_revenue_raw = st.text_input(
            "売上高（営業利益と同じ単位）　※不明なら空欄でスキップ可", value="", key="manual_revenue"
        )
        my_operating_profit, op_profit_error = parse_optional_metric(my_operating_profit_raw)
        my_revenue, revenue_error = parse_optional_metric(my_revenue_raw)
        my_op_margin = calculate_operating_margin(my_operating_profit, my_revenue)
        if my_op_margin is not None:
            st.caption(f"→ 自動計算された営業利益率：{my_op_margin:.1f}％")
        elif my_operating_profit is not None or my_revenue is not None:
            st.caption(
                "→ 営業利益・売上高のどちらか一方しか入力されていない（または売上高が0以下の）ため、"
                "営業利益率は「データなし」として扱われます。"
            )

        raw_inputs = {}
        for metric, key in [
            ("売上高成長率（％）", "manual_rev_growth"),
            ("営業利益成長率（％）", "manual_op_growth"),
            ("平均勤続年数（年）", "manual_tenure"),
            ("来期成長率予想（％）", "manual_forecast"),
            ("営業CFマージン（％）", "manual_cf_margin"),
            ("主力セグメント利益集中度（％）", "manual_seg_concentration"),
        ]:
            label = metric if metric not in INFO_ONLY_COLUMNS else metric.replace("（％）", "（％・参考情報）")
            raw_inputs[metric] = st.text_input(
                f"{label}　※不明なら空欄または「,」でスキップ可",
                value="",
                placeholder=threshold_placeholder(thresholds.get(metric)),
                key=key,
            )

    my_overseas, overseas_error = parse_optional_metric(my_overseas_raw)
    my_founding_year, founding_error = parse_optional_metric(my_founding_year_raw)
    parsed = {m: parse_optional_metric(raw) for m, raw in raw_inputs.items()}

    parse_errors = [
        msg for msg in [op_profit_error, revenue_error, overseas_error, founding_error, *(e for _, e in parsed.values())]
        if msg
    ]
    for msg in parse_errors:
        st.write(f"❌ {msg}")

    values = {
        "平均年収（万）": float(my_income),
        "平均年齢（歳）": float(my_age),
        "海外売上比率（％）": my_overseas,
        "営業利益率（％）": my_op_margin,
        **{m: v for m, (v, _) in parsed.items()},
    }
    has_negative_error, needs_confirmation, is_extreme_outlier, messages = validate_metrics(values)
    year_ok, year_message = validate_founding_year(my_founding_year)
    if not year_ok:
        messages.append(year_message)
    for msg in messages:
        st.write(msg)

    confirmed = True
    if needs_confirmation:
        confirmed = st.checkbox("入力内容に間違いがないことを確認しました", key="manual_confirm_checkbox")

    submit_disabled = (
        not my_company
        or has_negative_error
        or (not year_ok)
        or (needs_confirmation and not confirmed)
        or bool(parse_errors)
    )

    if st.button("この内容で比較する", disabled=submit_disabled):
        founding_year_int = int(my_founding_year) if my_founding_year is not None else None
        company_row = {"企業名": my_company, "創業年": founding_year_int, **values}
        apply_comparison(my_company, company_row, industry)
        st.session_state["skip_save"] = is_extreme_outlier
        st.session_state["search_not_found"] = False

        existing_names = set(display_df["企業名"].map(normalize_company_name))
        if is_extreme_outlier:
            st.success(f"「{my_company}」のデータを比較しました（異常値のため企業データベースには登録しません）")
        elif normalize_company_name(my_company) in existing_names:
            # 同名企業は重複登録しない
            st.success(f"「{my_company}」のデータを比較しました（同名の企業が既にあるため、新規登録はしていません）")
        else:
            insert_payload = {
                "source": "user",
                "industry": industry,
                "industries": [industry],
                "company_name": my_company,
                "income": values["平均年収（万）"],
                "age": values["平均年齢（歳）"],
                "founding_year": founding_year_int,
                "overseas_ratio": my_overseas,
                "operating_margin": my_op_margin,
                "revenue_growth": values["売上高成長率（％）"],
                "operating_profit_growth": values["営業利益成長率（％）"],
                "avg_tenure": values["平均勤続年数（年）"],
                "next_year_growth_forecast": values["来期成長率予想（％）"],
                "operating_cf_margin": values["営業CFマージン（％）"],
                "segment_concentration": values["主力セグメント利益集中度（％）"],
            }
            try:
                get_supabase().table("companies").insert(insert_payload).execute()
                fetch_companies_from_db.clear()
                st.success(f"「{my_company}」のデータを比較し、企業データベースにも登録しました（手入力データとして）")
            except Exception as e:
                st.warning(f"比較はできましたが、企業データベースへの登録に失敗しました：{e}")
                st.info(SCHEMA_HINT)


MIN_CHART_COVERAGE = 0.2  # 業界の2割以上の企業に値がある指標だけをグラフの選択肢に出す


def chartable_metrics(display_df: pd.DataFrame) -> tuple[list, list]:
    """【修正】海外売上比率のように EDINET から取れずほぼ空の指標は、グラフにしても意味がないので除く。"""
    usable, skipped = [], []
    for metric in METRIC_COLUMNS:
        count = pd.to_numeric(display_df[metric], errors="coerce").notna().sum()
        if count >= max(MIN_SAMPLES_FOR_BASELINE, len(display_df) * MIN_CHART_COVERAGE):
            usable.append(metric)
        else:
            skipped.append(metric)
    return usable, skipped


def render_metric_chart(display_df: pd.DataFrame, thresholds: dict):
    st.subheader("指標比較グラフ")
    usable, skipped = chartable_metrics(display_df)
    if not usable:
        st.caption("グラフにできる指標がありません。")
        return
    metric_to_plot = st.selectbox("表示する指標", usable)
    if skipped:
        names = "、".join(m.split("（")[0] for m in skipped)
        st.caption(f"※ {names} はデータのある企業が少ないため、グラフの選択肢から外しています（四季報で確認してください）。")
    selected = st.session_state.get("selected_company")
    top_n = 30

    plot_df = display_df[["企業名", metric_to_plot]].copy()
    plot_df[metric_to_plot] = pd.to_numeric(plot_df[metric_to_plot], errors="coerce")
    plot_df = plot_df.dropna(subset=[metric_to_plot]).sort_values(metric_to_plot, ascending=False)
    if plot_df.empty:
        st.caption("この指標のデータがありません。")
        return

    # 【修正】実データでは数百社になり棒グラフが読めないため、上位N社＋選択中の企業に絞る
    shown = plot_df.head(top_n)
    if selected and selected not in set(shown["企業名"]):
        shown = pd.concat([shown, plot_df[plot_df["企業名"] == selected]])
    shown = shown.assign(区分=["選択中の企業" if n == selected else "その他" for n in shown["企業名"]])
    st.caption(f"{len(plot_df)}社中、上位{min(top_n, len(plot_df))}社" + ("＋選択中の企業" if selected else "") + "を表示")

    bars = (
        alt.Chart(shown)
        .mark_bar()
        .encode(
            x=alt.X("企業名:N", sort=shown["企業名"].tolist(), title="企業名", axis=alt.Axis(labelAngle=-60)),
            y=alt.Y(f"{metric_to_plot}:Q", title=metric_to_plot),
            color=alt.Color(
                "区分:N",
                scale=alt.Scale(domain=["選択中の企業", "その他"], range=["#d62728", "#4C72B0"]),
                legend=alt.Legend(title=None),
            ),
            tooltip=["企業名", f"{metric_to_plot}:Q"],
        )
    )
    layers = [bars]
    baseline = thresholds.get(metric_to_plot)
    if baseline is not None:
        layers.append(
            alt.Chart(pd.DataFrame({"業界中央値": [baseline]}))
            .mark_rule(strokeDash=[6, 4], color="gray")
            .encode(y="業界中央値:Q", tooltip=["業界中央値:Q"])
        )
    st.altair_chart(alt.layer(*layers), width="stretch")


def page_company_data():
    industry = st.session_state["selected_industry"]
    st.title(f"【{industry}業界】企業データ")

    data = get_industry_data(industry)
    display_df = data["display"]
    render_data_source_notice(data)
    if display_df.empty:
        st.warning("この業界のデータはまだ準備中です。他の業界をお試しください。")
        if st.button("業界選択に戻る"):
            goto("industry_select")
        return

    thresholds = calculate_industry_threshold(industry)

    # 【修正】基準値が出せない指標（来期成長率予想など、EDINETから取れないもの）は表示しない
    headline = [(label, thresholds.get(metric), unit) for metric, label, unit in BASELINE_HEADLINE
                if thresholds.get(metric) is not None]
    if headline:
        st.caption("業界中央値：" + "　/　".join(f"{label} {value}{unit}" for label, value, unit in headline))
    with st.expander("業界基準値（中央値）の詳細を見る"):
        for metric, label, unit in BASELINE_DETAIL:
            if thresholds.get(metric) is not None:
                st.write(f"{label}：{thresholds[metric]}{unit}")
        missing = [label for metric, label, _ in BASELINE_HEADLINE + BASELINE_DETAIL if thresholds.get(metric) is None]
        if missing:
            st.caption(f"※ {'、'.join(missing)} は比較できる企業が少ないため表示していません（四季報で確認してください）。")
        n_secondary = int((display_df["区分"] != "主業種").sum()) if "区分" in display_df else 0
        if n_secondary:
            st.caption(f"※ 売上の3割以上をこの業界の事業が占める企業（{n_secondary}社）も含めて計算しています。")

    st.subheader(f"企業データ一覧（{len(display_df)}社）")
    table_df = display_df.copy()
    table_df["出典"] = table_df["出典"].map(lambda s: SOURCE_LABELS.get(s, s))
    table_df = table_df.drop(columns=HIDDEN_COLUMNS)
    table_df = table_df.dropna(axis=1, how="all")  # 全社「データなし」の列は表示しない
    st.dataframe(table_df, width="stretch", hide_index=True)

    with st.expander("🔍 企業を検索する", expanded=True):
        query = st.text_input(
            "企業名・略称・英語名・読み仮名・証券コード（4桁）", key="company_search_input",
            placeholder="例：トヨタ / 7203 / NRI / 野村総研 / のむら",
        )
        if st.button("検索") or st.session_state.pop("pending_search", False):
            hits = search_companies(display_df, query)
            st.session_state["search_candidates"] = hits
            st.session_state["search_not_found"] = not hits
            st.session_state["other_industry_hits"] = [] if hits else find_in_other_industries(query, industry)
            st.session_state.pop("candidate_select", None)

        candidates = [i for i in st.session_state["search_candidates"] if i in display_df.index]
        if candidates:
            def label(i):
                row = display_df.loc[i]
                code = f"［{row['証券コード']}］" if not is_missing(row["証券コード"]) else ""
                return f"{row['企業名']}{code}（{SOURCE_LABELS.get(row['出典'], row['出典'])}）"

            if len(candidates) > 1:
                st.caption(f"{len(candidates)}件見つかりました。比較する企業を選んでください。")
            chosen = st.selectbox("候補", candidates[:100], format_func=label, key="candidate_select")
            if st.button("この企業を業界と比較する", type="primary"):
                # NaN → None に変換してから評価する
                company_row = clean_row(display_df.loc[chosen])
                apply_comparison(company_row["企業名"], company_row, industry)
                st.session_state["skip_save"] = False
                st.success(f"「{company_row['企業名']}」を業界基準と比較しました")

        if st.session_state["search_not_found"]:
            others = st.session_state.get("other_industry_hits") or []
            movable = [o for o in others if o["industries"]]
            if movable:
                st.info("この業界には見つかりませんでしたが、別の業界のデータにありました。")
                for n, o in enumerate(movable):
                    for target in o["industries"]:
                        st.button(
                            f"「{o['name']}」を {target} で比較する",
                            key=f"move_{n}_{target}",
                            on_click=switch_industry_and_search, args=(target, o["name"]),
                        )
            no_data = [o["name"] for o in others if not o["has_data"]]
            if no_data and not movable:
                st.info(f"上場企業「{'」「'.join(no_data)}」が見つかりましたが、このツールの対象業種外か、"
                        "まだ有報のデータがないため比較できません。")
            render_manual_input_form(industry, thresholds, display_df)

    if st.session_state["comparison_result"]:
        st.subheader(f"「{st.session_state['selected_company']}」の比較結果")
        for metric, info in st.session_state["comparison_result"].items():
            st.write(f"・{metric}：{info['judgement']}")
        if st.session_state.get("segment_note"):
            st.caption(st.session_state["segment_note"])
        st.caption(f"企業データスコア：{st.session_state['company_score_pct']:.0f}%（-100〜100の範囲）")

    render_metric_chart(display_df, thresholds)

    if st.button("次へ", type="primary", disabled=not st.session_state["comparison_result"]):
        goto("reporter_comment")


def page_reporter_comment():
    st.title("記者コメント見出し／市場全体の見出しランキング")
    st.info(
        "会社四季報をお持ちでない場合は、何も入力せず「スキップ」を押して次に進んでください。"
        "その場合は企業データのみで評価します。"
    )
    st.write(
        "**対象企業の見出し**は四季報の記者コメント欄（右側）の見出し語をそのまま入力してください"
        "（例：「連続増益」「黒字化」など）。"
        "**市場ランキング**は、その時点で上場企業に多く見られる見出し語を1〜15位まで入力すると、"
        "市場全体の雰囲気（センチメント）として反映され、対象企業との相対評価が可能になります。"
    )

    render_location_popover(shikiho_guide.LOCATIONS_FOR_HEADLINE, "📍 見出しは四季報のどこ？")
    headline = st.text_input("記者コメントの見出し（対象企業のもの）", value=st.session_state["reporter_headline"])
    preview = calculate_company_headline_score(headline) if headline.strip() else None
    if headline.strip() and preview is None:
        st.caption("⚠️ 見出し辞書に一致するキーワードが見つかりませんでした（評価には反映されません）")
    elif preview:
        st.caption(f"→ 辞書マッチ：「{preview['keyword']}」（{preview['category']}／スコア{preview['score']:+d}）")

    st.write("市場全体の見出しランキング（1〜15位）")
    rankings = []
    for i in range(15):
        text = st.text_input(f"{i + 1}位", key=f"rank_{i}")
        rankings.append(text)
        # 【修正】辞書に無い語は評価に使われないことを入力時に分かるようにする
        if text.strip() and match_headline(text) is None:
            st.caption("　⚠️ 辞書に一致しないため、市場センチメントの計算から除外されます")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("スキップ"):
            st.session_state["reporter_headline"] = ""
            st.session_state["market_ranking"] = [""] * 15
            st.session_state["reporter_score_pct"] = 0.0
            st.session_state["reporter_weight"] = 0.0
            st.session_state["reporter_level"] = "スキップ（企業データのみで評価）"
            st.session_state["reporter_detail"] = None
            st.session_state["market_sentiment_skipped"] = True
            goto("result")
    with col2:
        if st.button("決定", type="primary"):
            st.session_state["reporter_headline"] = headline
            st.session_state["market_ranking"] = rankings
            st.session_state["market_sentiment_skipped"] = False
            reporter_score_pct, weight, level, detail = calculate_reporter_component(headline, rankings)
            st.session_state["reporter_score_pct"] = reporter_score_pct
            st.session_state["reporter_weight"] = weight
            st.session_state["reporter_level"] = level
            st.session_state["reporter_detail"] = detail
            goto("result")


# ---------------------------------------------------------------------------
# AI要約（有価証券報告書の文章 → 就活生向けの要約）
# ---------------------------------------------------------------------------
MAX_AI_CALLS_PER_SESSION = 5  # API料金の使いすぎ防止（キャッシュ済みの要約は回数に数えない）
AI_SECRET_KEYS = {
    "claude": ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", ai_summary.DEFAULT_CLAUDE_MODEL),
    "openai": ("OPENAI_API_KEY", "OPENAI_MODEL", ai_summary.DEFAULT_OPENAI_MODEL),
}


def get_ai_key(provider: str):
    """secrets のAPIキー。見本の「sk-ant-...」のような未記入のプレースホルダーは未設定として扱う。"""
    value = str(st.secrets.get(AI_SECRET_KEYS[provider][0]) or "").strip()
    if not value or value.endswith("...") or value.startswith("ここに"):
        return None
    return value


def get_ai_providers() -> list:
    """APIキーが設定されているプロバイダ。secrets の AI_PROVIDER に書いたものを先頭にする。"""
    available = [p for p in AI_SECRET_KEYS if get_ai_key(p)]
    preferred = st.secrets.get("AI_PROVIDER")
    if preferred in available:
        available.remove(preferred)
        available.insert(0, preferred)
    return available


def get_ai_model(provider: str) -> str:
    _, model_name, default = AI_SECRET_KEYS[provider]
    return st.secrets.get(model_name) or default


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_company_texts(edinet_code: str, _client: Client):
    rows = (
        _client.table("company_texts")
        .select("doc_id,period_end,business_description,management_policy,business_risks")
        .eq("edinet_code", edinet_code)
        .limit(1)
        .execute()
        .data
    )
    return rows[0] if rows else None


# 同じ書類・同じモデルの要約は全ユーザーで使い回す（APIを何度も呼ばないため）。
# 失敗（例外）はキャッシュされないので、次回は再試行される。
@st.cache_data(ttl=7 * 24 * 3600, max_entries=300, show_spinner=False)
def cached_ai_summary(provider: str, model: str, doc_id: str, prompt: str) -> str:
    return ai_summary.summarize(provider, prompt, get_ai_key(provider), model)


def render_ai_summary_section(company_name: str):
    st.subheader("🤖 有価証券報告書のAI要約")
    edinet_code = st.session_state.get("selected_edinet_code")
    if not edinet_code:
        st.caption("EDINETから取り込んだ企業を選んだときに使えます（手入力・サンプル企業は対象外）。")
        return
    providers = get_ai_providers()
    if not providers:
        st.caption("AI要約は、管理者が secrets に ANTHROPIC_API_KEY または OPENAI_API_KEY を設定すると使えます。")
        return

    try:
        texts = fetch_company_texts(edinet_code, get_supabase())
    except Exception as e:
        st.warning(f"有報の文章データを読み込めませんでした：{e}")
        st.info(SCHEMA_HINT)
        return
    if not texts or not any(texts.get(k) for k, _ in ai_summary.SECTIONS):
        st.caption("この企業は有報の文章データがまだ取り込まれていません。")
        return

    if len(providers) > 1:
        labels = {p: f"{ai_summary.PROVIDERS[p][0]}（{get_ai_model(p)}）" for p in providers}
        provider = st.radio("使うAI", providers, horizontal=True, key="ai_provider", format_func=labels.get)
    else:
        provider = providers[0]
    model = get_ai_model(provider)

    data = ai_summary.SummaryInput(company_name=company_name, period_end=texts.get("period_end"), texts=texts)
    try:
        prompt, truncated = ai_summary.build_user_prompt(data)
    except ai_summary.AISummaryError as e:
        st.caption(str(e))
        return

    found = [title for key, title in ai_summary.SECTIONS if texts.get(key)]
    st.caption(f"要約に使う有報のセクション：{'、'.join(found)}（書類ID {texts.get('doc_id')}）")

    session_key = f"{texts.get('doc_id')}|{provider}|{model}"
    summary = st.session_state["ai_summaries"].get(session_key)
    remaining = MAX_AI_CALLS_PER_SESSION - st.session_state["ai_calls"]

    if summary is None:
        if st.button(
            f"{ai_summary.PROVIDERS[provider][0]} で要約する（このセッションの残り{max(remaining, 0)}回）",
            disabled=remaining <= 0,
        ):
            with st.spinner("AIが有報を読んで要約しています…（数十秒かかることがあります）"):
                try:
                    summary = cached_ai_summary(provider, model, texts.get("doc_id"), prompt)
                except ai_summary.AISummaryError as e:
                    st.error(str(e))
                    return
                except Exception as e:  # SDK未インストールなど
                    st.error(f"AI要約に失敗しました：{e}")
                    return
            st.session_state["ai_calls"] += 1
            st.session_state["ai_summaries"][session_key] = summary
        elif remaining <= 0:
            st.caption("このセッションでのAI要約の上限に達しました。")

    if summary:
        with st.container(border=True):
            st.markdown(summary)
        if truncated:
            st.caption(f"※「{'、'.join(truncated)}」は長すぎたため、途中までを要約に使っています。")
        st.caption(
            f"⚠️ {ai_summary.PROVIDERS[provider][0]}（{model}）による自動要約です。"
            "誤りや抜け漏れがありうるので、気になる点は必ず有価証券報告書の原文で確認してください。"
        )


def page_result():
    st.title("評価結果")
    st.caption(f"評価日時：{datetime.now().strftime('%Y-%m-%d %H:%M')}")

    company = st.session_state["selected_company"] or "選択企業"
    industry = st.session_state["selected_industry"]

    company_score_pct = st.session_state["company_score_pct"]
    reporter_score_pct = st.session_state.get("reporter_score_pct", 0.0)
    reporter_weight = st.session_state.get("reporter_weight", 0.0)
    reporter_level = st.session_state.get("reporter_level", "")
    detail = st.session_state.get("reporter_detail")

    final_score = calculate_final_score(company_score_pct, reporter_score_pct, reporter_weight)

    st.metric("総合評価スコア（-100〜100）", f"{final_score:.0f}")

    col1, col2 = st.columns(2)
    with col1:
        st.write(f"企業データスコア：{company_score_pct:.0f}%（重み{COMPANY_WEIGHT:.0f}）")
    with col2:
        st.write(f"記者コメントスコア：{reporter_score_pct:.0f}%（重み{reporter_weight:.0f}）")
    st.caption(f"記者コメントの入力状況：{reporter_level}")

    comparison = st.session_state.get("comparison_result", {})
    if comparison:
        st.subheader("業界基準値（中央値）との比較")
        for metric, info in comparison.items():
            st.write(f"・{metric}：{info['judgement']}")
        if st.session_state.get("segment_note"):
            st.caption(st.session_state["segment_note"])
        scored = sum(1 for info in comparison.values() if info["score"] is not None)
        if scored <= 2:
            st.warning(f"スコアに使えた指標が{scored}個しかありません。評価の信頼性は低めです。")

    if detail:
        st.subheader("四季報見出しの分析")
        c = detail.get("company")
        market_sentiment = detail.get("market_sentiment")
        relative = detail.get("relative")
        if c:
            rare_note = "（📌 市場で非常に珍しい表現です）" if c["is_rare"] else ""
            st.write(f"対象企業の見出し：「{c['keyword']}」（{c['category']}／スコア{c['score']:+d}）{rare_note}")
        if market_sentiment is not None:
            st.write(f"市場センチメント（順位加重平均）：{market_sentiment:+.2f}（-5〜+5）")
        if relative is not None:
            mark = "🟢" if relative > 0 else ("🔴" if relative < 0 else "⚪")
            st.write(f"{mark} 市場平均との差：{relative:+.2f}（プラスなら市場より強い見出し）")
        breakdown = detail.get("market_category_breakdown") or {}
        if breakdown:
            total = sum(breakdown.values())
            st.write("市場ランキングのカテゴリ内訳：")
            for cat, count in sorted(breakdown.items(), key=lambda x: -x[1]):
                st.write(f"　- {cat}：{count}件（{count / total * 100:.0f}%）")

    if final_score >= 15:
        st.success(f"「{company}」は{industry}業界では「将来性に期待あり」でしょう。")
    elif final_score <= -15:
        st.warning(f"「{company}」は{industry}業界では「懸念材料あり」でしょう。")
    else:
        st.write(f"「{company}」は{industry}業界では「横ばい予想」でしょう。")

    render_ai_summary_section(company)

    if st.session_state.get("skip_save"):
        st.error("入力値が異常値と判定されたため、この結果はデータベースに保存されません。")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("❓ ヘルプ"):
            goto("help")
    with col2:
        if st.button("終了する（保存してリセット）", type="primary"):
            if not st.session_state.get("skip_save"):
                # 保存失敗でアプリが落ちないようにする
                try:
                    get_supabase().table("results").insert({
                        "user_email": st.session_state["auth_user"].email,
                        "industry": industry,
                        "company": company,
                        "score": round(final_score),
                        # 【修正】タイムゾーンなしのローカル時刻だとサーバー(UTC)とずれるので UTC で保存
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }).execute()
                except Exception as e:
                    st.error(f"結果の保存に失敗しました：{e}")
                    st.stop()
            reset_all_and_goto_title()


def draw_shikiho_guide_diagram():
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")
    regions = [
        (0, 8, 10, 2, "① 企業名・業種欄", "#4C72B0"),
        (0, 6, 6, 2, "② 業績欄（数値指標）", "#55A868"),
        (6, 6, 4, 2, "③ 平均年収・年齢・創業年欄", "#C44E52"),
        (0, 3, 10, 3, "④ 記者コメント見出し（右側）", "#8172B2"),
        (0, 0, 10, 3, "⑤ 株主・海外売上比率欄", "#CCB974"),
    ]
    for x, y, w, h, label, color in regions:
        ax.add_patch(patches.Rectangle((x, y), w, h, facecolor=color, alpha=0.3, edgecolor=color))
        ax.text(x + w / 2, y + h / 2, label, ha="center", va="center", fontsize=9)
    return fig


def render_location_table(items: list[str]):
    rows = shikiho_guide.locations(items)
    st.dataframe(
        pd.DataFrame([{"知りたいこと": r["item"], "四季報の場所": r["where"], "書かれ方": r["how"]} for r in rows]),
        hide_index=True, width="stretch",
    )


def render_location_popover(items: list[str], label: str = "📍 四季報のどこに書いてある？"):
    """入力欄の近くに置く小さなガイド（押すと開く）。"""
    with st.popover(label):
        for r in shikiho_guide.locations(items):
            st.markdown(f"**{r['item']}** → {r['where']}  \n{r['how']}")


def _render_guide_body(key: str):
    items = [x["item"] for x in shikiho_guide.SHIKIHO_LOCATIONS]
    chosen = st.selectbox("知りたいこと", items, key=key)
    r = shikiho_guide.locations([chosen])[0]
    st.info(f"**{r['where']}**\n\n{r['how']}")
    guide = next((g for g in shikiho_guide.METRIC_GUIDE if g["metric"].startswith(chosen[:4])), None)
    if guide:
        st.caption(f"見方：{guide['tips']}")


def is_mobile_device() -> bool:
    """ブラウザの User-Agent からスマホかどうかを判定する（分からなければパソコン扱い）。"""
    try:
        user_agent = st.context.headers.get("User-Agent", "") or ""
    except Exception:
        user_agent = ""
    return shikiho_guide.is_mobile_user_agent(user_agent)


def render_sidebar_guide():
    """【追加】どの画面からでも開ける四季報ミニガイド。

    パソコン：サイドバーに常に表示（画面が広いので邪魔にならない）。
    スマホ  ：サイドバーは圧迫感があるので使わず、画面右上のボタンから小窓で開く。
    """
    if is_mobile_device():
        _, right = st.columns([3, 1])
        with right:
            with st.popover("📖 四季報ミニガイド", width="stretch"):
                _render_guide_body("popover_guide_item")
        return
    with st.sidebar:
        st.subheader("📖 四季報ミニガイド")
        st.caption("知りたい情報が会社四季報のどこにあるかを確認できます。")
        _render_guide_body("sidebar_guide_item")


def page_help():
    st.title("就活目的での四季報の読み方・指標のコツ")
    tab_metrics, tab_where, tab_video, tab_image, tab_text, tab_dict = st.tabs(
        ["📊 指標の見方", "📍 四季報のどこを見る？", "🎥 動画で見る", "🖼️ 図解で見る", "📝 テキストで見る", "📖 見出し辞書"]
    )

    with tab_metrics:
        st.write("各指標が高い・低いと何が言えるか、就活でどう使うかをまとめました。"
                 "数字に良し悪しの正解はなく、**自分が働くうえで何を大事にしたいか**と照らし合わせて見てください。")
        for g in shikiho_guide.METRIC_GUIDE:
            with st.expander(g["metric"]):
                st.markdown(
                    f"**意味**：{g['meaning']}\n\n"
                    f"**高いと**：{g['high']}\n\n"
                    f"**低いと**：{g['low']}\n\n"
                    f"**就活での見方**：{g['tips']}\n\n"
                    f"**注意**：{g['caution']}"
                )
        st.subheader("ツールでは点数にしていないが、見ておきたいこと")
        for name, where, text in shikiho_guide.EXTRA_CHECKS:
            st.markdown(f"- **{name}**（{where}）：{text}")

    with tab_where:
        st.write("このツールで使う情報が、会社四季報のどの欄に書いてあるかの一覧です。"
                 "画面左のサイドバーの「四季報ミニガイド」からも、いつでも確認できます。")
        render_location_table([x["item"] for x in shikiho_guide.SHIKIHO_LOCATIONS])

    with tab_video:
        st.info(
            "実際の解説動画ファイルを用意した場合は st.video('assets/guide.mp4') のように"
            "パスまたはURLを指定してください。"
        )

    with tab_image:
        st.caption("※実際の四季報のレイアウトとは異なる、各欄の位置関係を示すイメージ図です。")
        fig = draw_shikiho_guide_diagram()
        st.pyplot(fig)
        plt.close(fig)  # 再実行のたびにFigureが溜まらないようにする

    with tab_text:
        st.write(
            "平均年齢と創業年をあわせて見ましょう。創業からかなり経っているのに"
            "平均年齢が低い企業は、早期退職者が多い可能性があります。"
            "平均勤続年数もあわせて見ると、定着度がより分かります。"
        )
        st.write(
            "営業利益率・売上高成長率・営業利益成長率は本業の稼ぐ力と成長性を見る基本指標です。"
            "平均勤続年数は人材の定着度、営業CFマージンは利益がどれだけ実際の現金として"
            "入ってきているかを示します。数字上の利益と現金の動きがズレている場合は要注意です。"
        )
        st.write(
            "本ツールの業界基準値は、EDINETから取得した有価証券報告書の数値の「中央値」です。"
            "平均ではなく中央値を使うのは、一部の企業の極端な値（急成長・赤字転落など）に"
            "業界の基準が引っ張られないようにするためです。"
        )
        st.write(
            "四季報の見出し語は、対象企業だけでなく市場全体のランキングと比べることが重要です。"
            "同じ「増益」でも、市場全体が「最高益」だらけの中での増益なら見劣りしますし、"
            "市場全体が「減益」だらけの中での増益ならかなり強い、と評価が変わります。"
        )

    with tab_dict:
        st.write(f"四季報の見出し語{len(HEADLINE_DICTIONARY)}語の完全一覧です。")
        if HEADLINE_DICTIONARY_ERRORS:
            for e in HEADLINE_DICTIONARY_ERRORS:
                st.error(f"辞書エラー：{e}")
        if HEADLINE_DICTIONARY_WARNINGS:
            with st.expander(f"⚠️ 包含関係の注意（{len(HEADLINE_DICTIONARY_WARNINGS)}件）"):
                for w in HEADLINE_DICTIONARY_WARNINGS:
                    st.write(f"・{w}")
        dict_df = pd.DataFrame([
            {
                "No.": i + 1, "見出し": k, "スコア": v["score"], "カテゴリ": v["category"],
                "対象": v["target"], "方向性": v["direction"], "出現数": v["frequency"],
            }
            for i, (k, v) in enumerate(HEADLINE_DICTIONARY.items())
        ])
        st.dataframe(dict_df, width="stretch", height=600, hide_index=True)
        st.caption(f"登録語数：{len(dict_df)}語")
        st.caption(
            f"出典：見出し語と出現数は「{HEADLINE_SOURCE_NAME}」の見出し語一覧（{HEADLINE_SOURCE_URL}）を参考にしました。"
            "スコア・カテゴリ・対象・方向性は、本ツールが生成AIの補助を受けて独自に付けたもので、同サイトの見解ではありません。"
        )

    st.write("---")
    if st.button("戻る"):
        # 【修正】help→help のように戻り先が自分自身になって抜けられなくなるのを防ぐ
        back = st.session_state["prev_page"]
        goto(back if back != "help" else "title")


def page_admin():
    st.title("🔒 管理者専用ページ")
    user = st.session_state["auth_user"]
    if get_user_role(user) != "admin":
        st.error("アクセス権がありません")
        if st.button("トップへ戻る"):
            goto("title")
        return

    if not st.session_state["is_admin_authed"]:
        if not ADMIN_PASSCODE:
            st.error("ADMIN_PASSCODE が secrets に設定されていないため、管理者ページは無効です。")
            return
        if st.session_state["admin_attempts"] >= MAX_ADMIN_ATTEMPTS:
            st.error("パスコードの試行回数が上限に達しました。ログアウトして再度ログインしてください。")
            return
        st.write("管理者ロールを確認しました。続けて管理者パスコードを入力してください")
        passcode = st.text_input("管理者パスコード", type="password")
        if st.button("認証する"):
            # 定数時間比較＋試行回数制限
            if hmac.compare_digest(passcode.encode("utf-8"), str(ADMIN_PASSCODE).encode("utf-8")):
                st.session_state["is_admin_authed"] = True
                st.session_state["admin_attempts"] = 0
                st.rerun()
            else:
                st.session_state["admin_attempts"] += 1
                remaining = MAX_ADMIN_ATTEMPTS - st.session_state["admin_attempts"]
                st.error(f"パスコードが正しくありません（残り{max(remaining, 0)}回）")
        return

    st.success(f"管理者として認証済み（{user.email}）")

    with st.expander(f"📖 見出し辞書の健全性チェック（登録{len(HEADLINE_DICTIONARY)}語）"):
        if not HEADLINE_DICTIONARY_ERRORS:
            st.success("エラーなし")
        for e in HEADLINE_DICTIONARY_ERRORS:
            st.error(e)
        for w in HEADLINE_DICTIONARY_WARNINGS:
            st.warning(w)

    st.write("登録データ一覧")
    # 【修正】取得失敗でページごと落ちないようにする
    try:
        data = get_supabase().table("results").select("*").order("id").execute().data
    except Exception as e:
        st.error(f"登録データの取得に失敗しました：{e}")
        data = []
    if not data:
        st.info("登録データがまだありません。")
        if st.button("管理者認証を解除してトップへ"):
            st.session_state["is_admin_authed"] = False
            goto("title")
        return

    df = pd.DataFrame(data)
    readonly = [c for c in ("id", "user_id", "user_email", "created_at") if c in df.columns]
    edited_df = st.data_editor(df, width="stretch", disabled=readonly, hide_index=True, key="results_editor")

    if st.button("データベースに反映"):
        # 【修正】旧版は全行を毎回 update しており、NaN や numpy 型で JSON 化に失敗することもあった。
        #   変更があったセルだけを送る。
        original = df.set_index("id")
        updated, failed = 0, []
        for row in edited_df.to_dict("records"):
            rid = _json_safe(row.get("id"))
            if rid is None or rid not in original.index:
                continue
            before = original.loc[rid]
            changes = {
                k: _json_safe(v) for k, v in row.items()
                if k not in readonly and _json_safe(v) != _json_safe(before.get(k))
            }
            if not changes:
                continue
            try:
                get_supabase().table("results").update(changes).eq("id", rid).execute()
                updated += 1
            except Exception as e:
                failed.append(f"id={rid}: {e}")
        if failed:
            st.error("一部の更新に失敗しました：\n" + "\n".join(failed))
        st.success(f"{updated}件を更新しました")

    buffer = BytesIO()
    edited_df.to_excel(buffer, index=False, engine="openpyxl")
    st.download_button(
        "Excelでダウンロード",
        data=buffer.getvalue(),
        file_name="results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    if st.button("管理者認証を解除してトップへ"):
        st.session_state["is_admin_authed"] = False
        goto("title")


PAGE_FUNCTIONS = {
    "title": page_title,
    "disclaimer": page_disclaimer,
    "industry_select": page_industry_select,
    "company_data": page_company_data,
    "reporter_comment": page_reporter_comment,
    "result": page_result,
    "help": page_help,
    "admin": page_admin,
}

if st.session_state["auth_user"] is None:
    page_login()
else:
    render_sidebar_guide()
    PAGE_FUNCTIONS.get(st.session_state["page"], page_title)()
