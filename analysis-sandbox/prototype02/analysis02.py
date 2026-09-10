import random
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from datetime import datetime
from supabase import create_client, Client
import altair as alt

st.set_page_config(
    page_title="就活生のための企業データ分析ツール",
    layout="wide",
    initial_sidebar_state="expanded",
)

CURRENT_YEAR = datetime.now().year


@st.cache_resource
def init_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


supabase = init_supabase()
ADMIN_PASSCODE = st.secrets["ADMIN_PASSCODE"]


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
        "search_not_found": False,
        "skip_save": False,
        "manual_confirmed": False,
        "is_admin_authed": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_session_state()


def goto(page_name: str):
    st.session_state["prev_page"] = st.session_state["page"]
    st.session_state["page"] = page_name
    st.rerun()


def reset_all_and_goto_title():
    keys_to_clear = [
        "selected_industry", "selected_company", "reporter_headline",
        "market_ranking", "market_sentiment_skipped", "comparison_result",
        "company_score_pct", "reporter_score_pct", "reporter_weight",
        "reporter_level", "reporter_detail", "segment_note",
        "search_not_found", "skip_save", "manual_confirmed",
    ]
    for k in keys_to_clear:
        if k in st.session_state:
            del st.session_state[k]
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


@st.cache_data(ttl=60)
def fetch_companies_from_db(industry: str) -> pd.DataFrame:
    try:
        rows = supabase.table("companies").select("*").eq("industry", industry).execute().data
    except Exception:
        rows = []
    if not rows:
        return pd.DataFrame(columns=["企業名", *ALL_DATA_COLUMNS])
    return pd.DataFrame(rows).rename(columns={
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
    })[["企業名", *ALL_DATA_COLUMNS]]


def get_industry_dataframe(industry: str):
    base_data = COMPANY_DATA_BY_INDUSTRY.get(industry)
    base_df = pd.DataFrame(base_data) if base_data else pd.DataFrame(columns=["企業名", *ALL_DATA_COLUMNS])
    db_df = fetch_companies_from_db(industry)
    combined_df = pd.concat([base_df, db_df], ignore_index=True)
    if combined_df.empty:
        return None
    return combined_df


def calculate_industry_threshold(industry: str) -> dict:
    df = get_industry_dataframe(industry)
    if df is None:
        return {}
    return {metric: round(df[metric].mean(), 1) for metric in METRIC_COLUMNS}


def calculate_industry_avg_segment_concentration(industry: str):
    df = get_industry_dataframe(industry)
    if df is None or "主力セグメント利益集中度（％）" not in df.columns:
        return None
    return round(df["主力セグメント利益集中度（％）"].mean(), 1)


def evaluate_metric_diff(value: float, base_value: float) -> float:
    if base_value == 0:
        return 0.0
    diff_ratio = (value - base_value) / base_value
    return max(-30.0, min(30.0, diff_ratio * 100))


def evaluate_age_with_tenure(avg_age, industry_avg_age, founding_year):
    base_score = evaluate_metric_diff(avg_age, industry_avg_age)
    tenure_adjustment = 0
    tenure_note = ""
    if founding_year:
        company_age_years = CURRENT_YEAR - founding_year
        if company_age_years >= 15 and avg_age < 35:
            tenure_adjustment = -15
            tenure_note = f"（懸念：創業{company_age_years}年に対し平均年齢が若く、早期離職の可能性）"
        elif company_age_years >= 15 and avg_age >= 40:
            tenure_adjustment = 5
            tenure_note = f"（好材料：創業{company_age_years}年で平均年齢も高く、定着率の良さがうかがえます）"
    total_score = base_score + tenure_adjustment
    if total_score >= 10:
        judgement = "業界平均より高い" + tenure_note
    elif total_score <= -10:
        judgement = "業界平均より低い" + tenure_note
    else:
        judgement = "業界平均並み" + tenure_note
    return total_score, judgement


def evaluate_against_industry(company_row: dict, industry: str) -> dict:
    thresholds = calculate_industry_threshold(industry)
    result = {}
    for metric, base_value in thresholds.items():
        company_value = company_row.get(metric)
        if company_value is None:
            result[metric] = {"score": None, "judgement": "データなし"}
            continue
        if metric == "平均年齢（歳）":
            score, judgement = evaluate_age_with_tenure(company_value, base_value, company_row.get("創業年"))
        else:
            score = evaluate_metric_diff(company_value, base_value)
            if score >= 10:
                judgement = "業界平均より高い"
            elif score <= -10:
                judgement = "業界平均より低い"
            else:
                judgement = "業界平均並み"
        result[metric] = {"score": score, "judgement": judgement}
    return result


def calculate_company_score_pct(comparison: dict) -> float:
    total = 0.0
    max_possible = 0.0
    for metric, info in comparison.items():
        if info["score"] is None:
            # データなし（スキップ）の指標は評価から除外する
            continue
        weight = 45 if metric == "平均年齢（歳）" else 30
        total += info["score"]
        max_possible += weight
    if max_possible == 0:
        return 0.0
    return max(-100.0, min(100.0, total / max_possible * 100))


def describe_segment_concentration(company_value, industry_avg):
    if company_value is None or industry_avg is None:
        return None
    diff = company_value - industry_avg
    if diff >= 15:
        note = "特定事業への依存度が業界平均より高めです（1事業に利益が偏っています）"
    elif diff <= -15:
        note = "事業が業界平均より分散されており、特定事業への依存は低めです"
    else:
        note = "業界平均並みの事業構成です"
    return f"主力セグメント利益集中度：{company_value:.0f}%（業界平均{industry_avg:.0f}%）→ {note}"


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
_SORTED_HEADLINE_KEYS = sorted(HEADLINE_DICTIONARY.keys(), key=len, reverse=True)

EXPECTED_HEADLINE_COUNT = 133


def validate_headline_dictionary():
    errors = []
    warnings = []
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
                        "符号が逆です（順位ウェイト適用前に必ず長い語からマッチさせる設計で対応済み）"
                    )
    return errors, warnings


HEADLINE_DICTIONARY_ERRORS, HEADLINE_DICTIONARY_WARNINGS = validate_headline_dictionary()


def match_headline(text: str):
    if not text:
        return None
    for key in _SORTED_HEADLINE_KEYS:
        if key in text:
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

    filled_rankings_count = sum(1 for r in rankings if r.strip())
    headline_filled = bool(headline_text.strip())

    if not headline_filled and filled_rankings_count == 0:
        return 0.0, 0.0, "スキップ（企業データのみで評価）", None

    company_abs = company_result["score"] if company_result else None
    relative = None
    if company_abs is not None and market_sentiment is not None:
        relative = company_abs - market_sentiment

    if company_abs is not None:
        if relative is not None:
            blended = company_abs * 0.6 + relative * 0.4
            reporter_score_pct = max(-100.0, min(100.0, blended / 8 * 100))
        else:
            reporter_score_pct = max(-100.0, min(100.0, company_abs / 5 * 100))
    elif market_sentiment is not None:
        reporter_score_pct = max(-100.0, min(100.0, market_sentiment / 5 * 100))
    else:
        reporter_score_pct = 0.0

    if filled_rankings_count >= 12:
        weight = 60.0
        level = "市場全体ランキング（ほぼ全件入力・最重視）"
    elif headline_filled and filled_rankings_count < 3:
        weight = 25.0
        level = "対象企業の記者コメントのみ"
    else:
        weight = min(60.0, 25.0 + filled_rankings_count * 2.5)
        level = f"ランキング一部入力（{filled_rankings_count}件）"

    detail = {
        "company": company_result,
        "market_sentiment": market_sentiment,
        "relative": relative,
        "market_category_breakdown": market_result["category_breakdown"],
    }
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
            # 未入力／スキップされた指標は検証対象外（「データなし」として扱う）
            continue

        if metric in POSITIVE_ONLY_METRICS and value < 0:
            has_negative_error = True
            messages.append(f"❌「{metric}」はマイナスの値を取りえません。修正してください。（入力値：{value}）")
            continue

        if metric == "海外売上比率（％）":
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


def validate_founding_year(founding_year: int):
    if founding_year > CURRENT_YEAR:
        return False, f"❌「創業年」が未来の年になっています（入力値：{founding_year}）。修正してください。"
    if founding_year < 1850:
        return False, f"⚠️「創業年」が古すぎます（入力値：{founding_year}）。入力に誤りがないかご確認ください。"
    return True, ""


# 「データが四季報に載っていない／わからない」ことを表すための入力。
# 空欄のほか、カンマなどの記号を入力してもスキップ扱いになる。
SKIP_INPUT_SYMBOLS = {"", ",", "、", "，", "-", "ー", "－", "‐", "―", "なし", "N/A", "n/a"}


def parse_optional_metric(raw_value: str):
    """テキスト入力を数値に変換する。

    未入力や「,」などの記号が入力された場合は「データなし」とみなし (None, None) を返す。
    数値として解釈できない場合は (None, エラーメッセージ) を返す。
    """
    text = (raw_value or "").strip()
    if text in SKIP_INPUT_SYMBOLS:
        return None, None
    normalized = text.replace(",", "").replace("，", "").replace("%", "").replace("％", "")
    try:
        return float(normalized), None
    except ValueError:
        return None, (
            f"「{raw_value}」を数値として認識できません。"
            "数値を入力するか、データが無い場合は空欄または「,」にしてスキップしてください。"
        )


def calculate_operating_margin(operating_profit, revenue):
    """四季報に記載の営業利益と売上高から営業利益率（％）を自動計算する。

    どちらかが未入力、または売上高が0の場合は計算できないため None を返す。
    """
    if operating_profit is None or revenue is None or revenue == 0:
        return None
    return round(operating_profit / revenue * 100, 1)


def get_user_role(user) -> str:
    try:
        return (user.user_metadata or {}).get("role", "user")
    except Exception:
        return "user"


def page_login():
    st.title("🔐 ログイン")
    st.write("本ツールの利用にはログインが必要です")
    tab_login, tab_signup = st.tabs(["ログイン", "新規登録"])
    with tab_login:
        email = st.text_input("メールアドレス", key="login_email")
        password = st.text_input("パスワード", type="password", key="login_password")
        if st.button("ログイン", type="primary"):
            try:
                res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state["auth_user"] = res.user
                st.rerun()
            except Exception:
                st.error("メールアドレスまたはパスワードが正しくありません。")
    with tab_signup:
        new_email = st.text_input("メールアドレス", key="signup_email")
        new_password = st.text_input("パスワード（8文字以上）", type="password", key="signup_password")
        if st.button("登録する"):
            if len(new_password) < 8:
                st.error("パスワードは8文字以上にしてください。")
            else:
                try:
                    supabase.auth.sign_up({"email": new_email, "password": new_password})
                    st.success("確認メールを送信しました。メール内のリンクから認証を完了してください。")
                except Exception as e:
                    st.error(f"登録に失敗しました：{e}")


def page_title():
    st.title("📊 就活生のための企業データ分析ツール")
    st.write("財務指標・人材指標・四季報の見出し語から企業の傾向を多角的に分析します。")
    user = st.session_state["auth_user"]
    st.caption(f"ログイン中：{user.email}")
    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("始める", type="primary"):
            goto("disclaimer")
    with col2:
        if st.button("ログアウト"):
            supabase.auth.sign_out()
            st.session_state["auth_user"] = None
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
本プログラムは、公開情報等をもとにした財務指標・人材指標・四季報の見出し語等の
指標により、業界内での企業の傾向を把握するための参考情報提供ツールです。

第二条（断定的表現の排除）
本ツールが示す評価スコアは機械的な計算結果であり、
対象企業への入社の可否や優劣を断定するものではありません。

第三条（業界差の考慮）
指標の基準は業界によって大きく異なります。単一の指標のみで
企業の良し悪しを判断しないようご注意ください。

第四条（免責事項）
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
    industry = st.selectbox("業界", INDUSTRIES, index=None, placeholder="選択してください")
    if st.button("次へ", disabled=(industry is None)):
        st.session_state["selected_industry"] = industry
        goto("company_data")


def page_company_data():
    industry = st.session_state["selected_industry"]
    st.title(f"【{industry}業界】代表企業のデータ")

    df = get_industry_dataframe(industry)
    if df is None:
        st.warning("この業界のデータはまだ準備中です。他の業界をお試しください。")
        if st.button("業界選択に戻る"):
            goto("industry_select")
        return

    thresholds = calculate_industry_threshold(industry)
    seg_avg = calculate_industry_avg_segment_concentration(industry)

    st.caption(
        f"平均年収 {thresholds['平均年収（万）']}万円　/　"
        f"平均年齢 {thresholds['平均年齢（歳）']}歳　/　"
        f"海外売上比率 {thresholds['海外売上比率（％）']}％"
    )
    with st.expander("業界基準値の詳細（Sランク指標）を見る"):
        st.write(f"営業利益率：{thresholds['営業利益率（％）']}％")
        st.write(f"売上高成長率：{thresholds['売上高成長率（％）']}％")
        st.write(f"営業利益成長率：{thresholds['営業利益成長率（％）']}％")
        st.write(f"平均勤続年数：{thresholds['平均勤続年数（年）']}年")
        st.write(f"来期成長率予想：{thresholds['来期成長率予想（％）']}％")
        st.write(f"営業CFマージン：{thresholds['営業CFマージン（％）']}％")
        if seg_avg is not None:
            st.write(f"主力セグメント利益集中度（参考情報・スコア対象外）：{seg_avg}％")

    st.subheader("企業データ一覧")
    st.dataframe(df, use_container_width=True)

    with st.expander("🔍 企業を検索する", expanded=True):
        company_name = st.text_input("企業名（上記のいずれか）", key="company_search_input")
        if st.button("検索"):
            matched = df[df["企業名"] == company_name]
            if matched.empty:
                st.session_state["search_not_found"] = True
            else:
                st.session_state["search_not_found"] = False
                st.session_state["selected_company"] = company_name
                company_row = matched.iloc[0].to_dict()
                comparison = evaluate_against_industry(company_row, industry)
                st.session_state["comparison_result"] = comparison
                st.session_state["company_score_pct"] = calculate_company_score_pct(comparison)
                st.session_state["segment_note"] = describe_segment_concentration(
                    company_row.get("主力セグメント利益集中度（％）"), seg_avg
                )
                st.success(f"「{company_name}」を業界基準と比較しました")

        if st.session_state["search_not_found"]:
            st.warning("該当企業が見つかりません。データを直接入力してください。")
            st.caption(
                "四季報に載っていない・わからない項目は、空欄のままか「,」などの記号を入力すると"
                "「データなし」としてスキップされます（業界平均で穴埋めせず、評価からも除外されます）。"
            )
            my_company = st.text_input("企業名", value=company_name or "マイカンパニー", key="manual_company")
            my_income = st.number_input("平均年収（万）", value=400, key="manual_income")
            my_age = st.number_input("平均年齢（歳）", value=40, key="manual_age")
            my_overseas_raw = st.text_input(
                "海外売上比率（％）　※不明なら空欄または「,」でスキップ可",
                value="30",
                key="manual_overseas",
            )
            my_founding_year = st.number_input(
                "創業年（西暦）", value=2010, min_value=1850, max_value=CURRENT_YEAR, key="manual_founding_year"
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
                        "→ 営業利益・売上高のどちらか一方しか入力されていないため、"
                        "営業利益率は「データなし」として扱われます。"
                    )

                my_rev_growth_raw = st.text_input(
                    "売上高成長率（％）　※不明なら空欄または「,」でスキップ可",
                    value=str(thresholds["売上高成長率（％）"]),
                    key="manual_rev_growth",
                )
                my_op_growth_raw = st.text_input(
                    "営業利益成長率（％）　※不明なら空欄または「,」でスキップ可",
                    value=str(thresholds["営業利益成長率（％）"]),
                    key="manual_op_growth",
                )
                my_tenure_raw = st.text_input(
                    "平均勤続年数（年）　※不明なら空欄または「,」でスキップ可",
                    value=str(thresholds["平均勤続年数（年）"]),
                    key="manual_tenure",
                )
                my_forecast_raw = st.text_input(
                    "来期成長率予想（％）　※不明なら空欄または「,」でスキップ可",
                    value=str(thresholds["来期成長率予想（％）"]),
                    key="manual_forecast",
                )
                my_cf_margin_raw = st.text_input(
                    "営業CFマージン（％）　※不明なら空欄または「,」でスキップ可",
                    value=str(thresholds["営業CFマージン（％）"]),
                    key="manual_cf_margin",
                )
                my_seg_concentration_raw = st.text_input(
                    "主力セグメント利益集中度（％・参考情報）　※不明なら空欄または「,」でスキップ可",
                    value=str(seg_avg) if seg_avg is not None else "",
                    key="manual_seg_concentration",
                )

            my_overseas, overseas_error = parse_optional_metric(my_overseas_raw)
            my_rev_growth, rev_growth_error = parse_optional_metric(my_rev_growth_raw)
            my_op_growth, op_growth_error = parse_optional_metric(my_op_growth_raw)
            my_tenure, tenure_error = parse_optional_metric(my_tenure_raw)
            my_forecast, forecast_error = parse_optional_metric(my_forecast_raw)
            my_cf_margin, cf_margin_error = parse_optional_metric(my_cf_margin_raw)
            my_seg_concentration, seg_error = parse_optional_metric(my_seg_concentration_raw)

            parse_errors = [
                msg for msg in [
                    op_profit_error, revenue_error, overseas_error, rev_growth_error,
                    op_growth_error, tenure_error, forecast_error, cf_margin_error, seg_error,
                ]
                if msg
            ]
            for msg in parse_errors:
                st.write(f"❌ {msg}")

            values = {
                "平均年収（万）": my_income,
                "平均年齢（歳）": my_age,
                "海外売上比率（％）": my_overseas,
                "営業利益率（％）": my_op_margin,
                "売上高成長率（％）": my_rev_growth,
                "営業利益成長率（％）": my_op_growth,
                "平均勤続年数（年）": my_tenure,
                "来期成長率予想（％）": my_forecast,
                "営業CFマージン（％）": my_cf_margin,
                "主力セグメント利益集中度（％）": my_seg_concentration,
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
                has_negative_error or (not year_ok) or (needs_confirmation and not confirmed) or bool(parse_errors)
            )

            if st.button("この内容で比較する", disabled=submit_disabled):
                company_row = {"企業名": my_company, "創業年": my_founding_year, **values}
                comparison = evaluate_against_industry(company_row, industry)
                st.session_state["selected_company"] = my_company
                st.session_state["comparison_result"] = comparison
                st.session_state["company_score_pct"] = calculate_company_score_pct(comparison)
                st.session_state["segment_note"] = describe_segment_concentration(my_seg_concentration, seg_avg)
                st.session_state["skip_save"] = is_extreme_outlier
                st.session_state["search_not_found"] = False

                if not is_extreme_outlier:
                    insert_payload = {
                        "industry": industry,
                        "company_name": my_company,
                        "income": my_income,
                        "age": my_age,
                        "founding_year": my_founding_year,
                        # スキップされた項目は None（NULL）として保存される。
                        # ※companiesテーブル側に対応する列が無いと登録は失敗するので、
                        #   その場合は下に表示されるSQLで列を追加してください。
                        "overseas_ratio": my_overseas,
                        "operating_margin": my_op_margin,
                        "revenue_growth": my_rev_growth,
                        "operating_profit_growth": my_op_growth,
                        "avg_tenure": my_tenure,
                        "next_year_growth_forecast": my_forecast,
                        "operating_cf_margin": my_cf_margin,
                        "segment_concentration": my_seg_concentration,
                    }
                    try:
                        supabase.table("companies").insert(insert_payload).execute()
                        fetch_companies_from_db.clear()
                        st.success(f"「{my_company}」のデータを比較し、企業データベースにも登録しました")
                    except Exception as e:
                        error_text = str(e)
                        st.warning(f"比較はできましたが、企業データベースへの登録に失敗しました：{error_text}")
                        if "Could not find the" in error_text and "column" in error_text:
                            st.info(
                                "Supabaseの`companies`テーブルに、このアプリが保存しようとしている列が"
                                "存在していないようです。下記SQLをSupabaseのSQL Editorで実行し、"
                                "不足している列を追加してから再度お試しください。"
                            )
                            st.code(
                                "alter table companies\n"
                                "  add column if not exists founding_year integer,\n"
                                "  add column if not exists overseas_ratio numeric,\n"
                                "  add column if not exists operating_margin numeric,\n"
                                "  add column if not exists revenue_growth numeric,\n"
                                "  add column if not exists operating_profit_growth numeric,\n"
                                "  add column if not exists avg_tenure numeric,\n"
                                "  add column if not exists next_year_growth_forecast numeric,\n"
                                "  add column if not exists operating_cf_margin numeric,\n"
                                "  add column if not exists segment_concentration numeric;",
                                language="sql",
                            )
                else:
                    st.success(f"「{my_company}」のデータを比較しました（異常値のため企業データベースには登録しません）")

    if st.session_state["comparison_result"]:
        st.subheader(f"「{st.session_state['selected_company']}」の比較結果")
        for metric, info in st.session_state["comparison_result"].items():
            st.write(f"・{metric}：{info['judgement']}")
        if st.session_state.get("segment_note"):
            st.caption(st.session_state["segment_note"])
        st.caption(f"企業データスコア：{st.session_state['company_score_pct']:.0f}%（-100〜100の範囲）")

    st.subheader("指標比較グラフ")
    metric_to_plot = st.selectbox("表示する指標", METRIC_COLUMNS)
    sorted_df = df.sort_values(metric_to_plot, ascending=False)
    chart = (
        alt.Chart(sorted_df)
        .mark_bar()
        .encode(
            x=alt.X("企業名", sort=sorted_df["企業名"].tolist(), title="企業名"),
            y=alt.Y(metric_to_plot, title=metric_to_plot),
        )
    )
    st.altair_chart(chart, use_container_width=True)

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
        "（例：「連続増益」「黒字転換」など）。"
        "**市場ランキング**は、その時点で上場企業に多く見られる見出し語を1〜15位まで入力すると、"
        "市場全体の雰囲気（センチメント）として反映され、対象企業との相対評価が可能になります。"
    )

    headline = st.text_input("記者コメントの見出し（対象企業のもの）")
    preview = calculate_company_headline_score(headline) if headline.strip() else None
    if headline.strip() and preview is None:
        st.caption("⚠️ 見出し辞書に一致するキーワードが見つかりませんでした（評価には反映されません）")
    elif preview:
        st.caption(f"→ 辞書マッチ：「{preview['keyword']}」（{preview['category']}／スコア{preview['score']:+d}）")

    st.write("市場全体の見出しランキング（1〜15位）")
    rankings = [st.text_input(f"{i + 1}位", key=f"rank_{i}") for i in range(15)]

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
            reporter_score_pct, weight, level, detail = calculate_reporter_component(headline, rankings)
            st.session_state["reporter_score_pct"] = reporter_score_pct
            st.session_state["reporter_weight"] = weight
            st.session_state["reporter_level"] = level
            st.session_state["reporter_detail"] = detail
            goto("result")


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

    st.metric("総合評価スコア", f"{final_score:.0f}")

    col1, col2 = st.columns(2)
    with col1:
        st.write(f"企業データスコア：{company_score_pct:.0f}%（重み{COMPANY_WEIGHT:.0f}）")
    with col2:
        st.write(f"記者コメントスコア：{reporter_score_pct:.0f}%（重み{reporter_weight:.0f}）")
    st.caption(f"記者コメントの入力状況：{reporter_level}")

    comparison = st.session_state.get("comparison_result", {})
    if comparison:
        st.subheader("業界基準値との比較")
        for metric, info in comparison.items():
            st.write(f"・{metric}：{info['judgement']}")
        if st.session_state.get("segment_note"):
            st.caption(st.session_state["segment_note"])

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

    if st.session_state.get("skip_save"):
        st.error("入力値が異常値と判定されたため、この結果はデータベースに保存されません。")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("❓ ヘルプ"):
            goto("help")
    with col2:
        if st.button("終了する（保存してリセット）", type="primary"):
            if not st.session_state.get("skip_save"):
                supabase.table("results").insert({
                    "user_email": st.session_state["auth_user"].email,
                    "industry": industry,
                    "company": company,
                    "score": round(final_score),
                    "created_at": datetime.now().isoformat(),
                }).execute()
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


def page_help():
    st.title("就活目的での四季報の読み方・指標のコツ")
    tab_video, tab_image, tab_text, tab_dict = st.tabs(
        ["🎥 動画で見る", "🖼️ 図解で見る", "📝 テキストで見る", "📖 見出し辞書"]
    )

    with tab_video:
        st.info(
            "実際の解説動画ファイルを用意した場合は st.video('assets/guide.mp4') のように"
            "パスまたはURLを指定してください。"
        )

    with tab_image:
        fig = draw_shikiho_guide_diagram()
        st.pyplot(fig)

    with tab_text:
        st.write(
            "平均年齢と創業年をあわせて見ましょう。創業からかなり経っているのに"
            "平均年齢が低い企業は、早期退職者が多い可能性があります。"
        )
        st.write(
            "営業利益率・売上高成長率・営業利益成長率は本業の稼ぐ力と成長性を見る基本指標です。"
            "平均勤続年数は人材の定着度、営業CFマージンは利益がどれだけ実際の現金として"
            "入ってきているかを示します。数字上の利益と現金の動きがズレている場合は要注意です。"
        )
        st.write(
            "四季報の見出し語は、対象企業だけでなく市場全体のランキングと比べることが重要です。"
            "同じ「増益」でも、市場全体が「最高益」だらけの中での増益なら見劣りしますし、"
            "市場全体が「減益」だらけの中での増益ならかなり強い、と評価が変わります。"
        )

    with tab_dict:
        st.write(f"四季報の見出し語{EXPECTED_HEADLINE_COUNT}語の完全一覧です。")
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
        st.dataframe(dict_df, use_container_width=True, height=600, hide_index=True)
        st.caption(f"登録語数：{len(dict_df)}語")

    st.write("---")
    if st.button("戻る"):
        goto(st.session_state["prev_page"])


def page_admin():
    st.title("🔒 管理者専用ページ")
    user = st.session_state["auth_user"]
    if get_user_role(user) != "admin":
        st.error("アクセス権がありません")
        if st.button("トップへ戻る"):
            goto("title")
        return

    if not st.session_state["is_admin_authed"]:
        st.write("管理者ロールを確認しました。続けて管理者パスコードを入力してください")
        passcode = st.text_input("管理者パスコード", type="password")
        if st.button("認証する"):
            if passcode == ADMIN_PASSCODE:
                st.session_state["is_admin_authed"] = True
                st.rerun()
            else:
                st.error("パスコードが正しくありません")
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
    data = supabase.table("results").select("*").execute().data
    if data:
        df = pd.DataFrame(data)
    else:
        st.info("登録データがまだありません。")
        df = pd.DataFrame({"企業名": ["サンプル株式会社"], "評価ポイント": [3]})

    edited_df = st.data_editor(df, use_container_width=True)

    if st.button("データベースに反映"):
        for row in edited_df.to_dict("records"):
            if "id" in row:
                update_data = {k: v for k, v in row.items() if k != "id"}
                supabase.table("results").update(update_data).eq("id", row["id"]).execute()
        st.success("更新しました")

    from io import BytesIO
    buffer = BytesIO()
    edited_df.to_excel(buffer, index=False, engine="openpyxl")
    st.download_button(
        "Excelでダウンロード",
        data=buffer.getvalue(),
        file_name="data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    if st.button("ログアウトしてトップへ"):
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
    PAGE_FUNCTIONS[st.session_state["page"]]()
