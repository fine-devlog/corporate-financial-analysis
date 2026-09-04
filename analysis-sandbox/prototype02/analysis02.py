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
        "evaluation_score": 0,
        "comparison_result": {},
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
        "market_ranking", "market_sentiment_skipped", "evaluation_score",
        "comparison_result", "search_not_found", "skip_save", "manual_confirmed",
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

METRIC_COLUMNS = ["平均年収（万）", "平均年齢（歳）", "海外売上比率（％）"]

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


@st.cache_data(ttl=60)
def fetch_companies_from_db(industry: str) -> pd.DataFrame:
    try:
        rows = supabase.table("companies").select("*").eq("industry", industry).execute().data
    except Exception:
        rows = []
    if not rows:
        return pd.DataFrame(columns=["企業名", *METRIC_COLUMNS])
    return pd.DataFrame(rows).rename(columns={
        "company_name": "企業名",
        "income": "平均年収（万）",
        "age": "平均年齢（歳）",
        "overseas_ratio": "海外売上比率（％）",
    })[["企業名", *METRIC_COLUMNS]]


def get_industry_dataframe(industry: str):
    base_data = COMPANY_DATA_BY_INDUSTRY.get(industry)
    base_df = pd.DataFrame(base_data) if base_data else pd.DataFrame(columns=["企業名", *METRIC_COLUMNS])
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


def evaluate_against_industry(company_row: dict, industry: str) -> dict:
    thresholds = calculate_industry_threshold(industry)
    result = {}
    for metric, base_value in thresholds.items():
        company_value = company_row.get(metric)
        if company_value is None:
            result[metric] = "データなし"
            continue
        diff_ratio = (company_value - base_value) / base_value
        if diff_ratio >= 0.10:
            result[metric] = "業界平均より高い"
        elif diff_ratio <= -0.10:
            result[metric] = "業界平均より低い"
        else:
            result[metric] = "業界平均並み"
    return result


def apply_comparison_to_score(comparison: dict):
    score_delta = sum(
        1 if v == "業界平均より高い" else (-1 if v == "業界平均より低い" else 0)
        for v in comparison.values()
    )
    st.session_state["evaluation_score"] += score_delta


# ★指標名はMETRIC_COLUMNSと完全一致させる（全角カッコで統一）
EXPECTED_TYPICAL_MAX = {
    "平均年収（万）": 1500,
    "平均年齢（歳）": 65,
    "海外売上比率（％）": 100,
}
POSITIVE_ONLY_METRICS = {"平均年収（万）", "平均年齢（歳）", "海外売上比率（％）"}


def validate_metrics(values: dict):
    has_negative_error = False
    needs_confirmation = False
    is_extreme_outlier = False
    messages = []

    for metric, value in values.items():
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
        if value >= typical_max * 10:
            is_extreme_outlier = True
            messages.append(
                f"🚨「{metric}」が想定の10倍程度（{typical_max * 10}以上）です。"
                "異常値と判断し、この結果はデータベースには保存されません。"
            )
        elif value >= typical_max * 3:
            needs_confirmation = True
            messages.append(
                f"⚠️「{metric}」が想定範囲の3倍近く（{typical_max * 3}以上）です。"
                "入力に間違いがないかご確認の上、チェックしてください。"
            )

    return has_negative_error, needs_confirmation, is_extreme_outlier, messages


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
    st.write("平均年収・平均年齢・海外売上比率など、就活生が見るべき指標に注目して企業分析を行うツールです。")
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
本プログラムは、公開情報等をもとにした平均年収・平均年齢・海外売上比率等の
指標により、業界内での企業の傾向を把握するための参考情報提供ツールです。

第二条（断定的表現の排除）
本ツールが示す「業界平均より高い／低い」等の表示は機械的な計算結果であり、
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
    st.caption(
        "この業界の基準値（代表企業の平均から自動算出）：　"
        f"平均年収 {thresholds['平均年収（万）']}万円　/　"
        f"平均年齢 {thresholds['平均年齢（歳）']}歳　/　"
        f"海外売上比率 {thresholds['海外売上比率（％）']}％"
    )

    st.subheader("企業データ一覧")
    st.dataframe(df, use_container_width=True)

    # =====================================================
    # ★企業検索〜手入力までを、すべてこの expander の中に収める
    #   （前回の版はここが関数の外に飛び出して壊れていました）
    # =====================================================
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
                apply_comparison_to_score(comparison)
                st.success(f"「{company_name}」を業界基準と比較しました")

        if st.session_state["search_not_found"]:
            st.warning("該当企業が見つかりません。データを直接入力してください。")
            my_company = st.text_input("企業名", value=company_name or "マイカンパニー", key="manual_company")
            my_income = st.number_input("平均年収（万）", value=400, key="manual_income")
            my_age = st.number_input("平均年齢（歳）", value=40, key="manual_age")
            my_overseas = st.number_input("海外売上比率（％）", value=30, key="manual_overseas")

            values = {
                "平均年収（万）": my_income,
                "平均年齢（歳）": my_age,
                "海外売上比率（％）": my_overseas,
            }
            has_negative_error, needs_confirmation, is_extreme_outlier, messages = validate_metrics(values)

            for msg in messages:
                st.write(msg)

            confirmed = True
            if needs_confirmation:
                confirmed = st.checkbox("入力内容に間違いがないことを確認しました", key="manual_confirm_checkbox")

            submit_disabled = has_negative_error or (needs_confirmation and not confirmed)

            if st.button("この内容で比較する", disabled=submit_disabled):
                company_row = {"企業名": my_company, **values}
                comparison = evaluate_against_industry(company_row, industry)
                st.session_state["selected_company"] = my_company
                st.session_state["comparison_result"] = comparison
                st.session_state["skip_save"] = is_extreme_outlier
                apply_comparison_to_score(comparison)
                st.session_state["search_not_found"] = False

                if not is_extreme_outlier:
                    try:
                        supabase.table("companies").insert({
                            "industry": industry,
                            "company_name": my_company,
                            "income": my_income,
                            "age": my_age,
                            "overseas_ratio": my_overseas,
                        }).execute()
                        fetch_companies_from_db.clear()
                        st.success(f"「{my_company}」のデータを比較し、企業データベースにも登録しました")
                    except Exception as e:
                        st.warning(f"比較はできましたが、企業データベースへの登録に失敗しました：{e}")
                else:
                    st.success(f"「{my_company}」のデータを比較しました（異常値のため企業データベースには登録しません）")

    # ここから先はexpanderの外（page_company_data関数の中）
    if st.session_state["comparison_result"]:
        st.subheader(f"「{st.session_state['selected_company']}」の比較結果")
        for metric, judgement in st.session_state["comparison_result"].items():
            st.write(f"・{metric}：{judgement}")

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
    st.info("会社四季報をお持ちでない場合は、何も入力せず「スキップ」を押して次に進んでください。")
    headline = st.text_input("記者コメントの見出し")
    st.write("市場全体の見出しランキング（1〜15位）")
    rankings = [st.text_input(f"{i + 1}位", key=f"rank_{i}") for i in range(15)]

    col1, col2 = st.columns(2)
    with col1:
        if st.button("スキップ"):
            st.session_state["market_sentiment_skipped"] = True
            goto("result")
    with col2:
        if st.button("決定", type="primary"):
            st.session_state["reporter_headline"] = headline
            st.session_state["market_ranking"] = rankings

            positive_words = ["最高益", "増配", "上方修正"]
            negative_words = ["減益", "赤字", "下方修正"]
            score = 0
            for r in rankings:
                if not r:
                    continue
                if any(w in r for w in positive_words):
                    score += 1
                if any(w in r for w in negative_words):
                    score -= 1
            st.session_state["evaluation_score"] += score
            goto("result")


def page_result():
    st.title("評価結果")
    st.caption(f"評価日時：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    score = st.session_state["evaluation_score"]
    company = st.session_state["selected_company"] or "選択企業"
    industry = st.session_state["selected_industry"]
    st.metric("総合評価ポイント", score)

    comparison = st.session_state.get("comparison_result", {})
    if comparison:
        st.subheader("業界基準値との比較")
        for metric, judgement in comparison.items():
            st.write(f"・{metric}：{judgement}")

    if score > 0:
        st.success(f"「{company}」は{industry}業界では「将来性に期待あり」でしょう。")
    elif score < 0:
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
                    "score": score,
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
        (6, 6, 4, 2, "③ 平均年収・年齢欄", "#C44E52"),
        (0, 3, 10, 3, "④ 記者コメント見出し（右側）", "#8172B2"),
        (0, 0, 10, 3, "⑤ 株主・海外売上比率欄", "#CCB974"),
    ]
    for x, y, w, h, label, color in regions:
        ax.add_patch(patches.Rectangle((x, y), w, h, facecolor=color, alpha=0.3, edgecolor=color))
        ax.text(x + w / 2, y + h / 2, label, ha="center", va="center", fontsize=9)

    return fig


def page_help():
    st.title("就活目的での四季報の読み方・指標のコツ")
    tab_video, tab_image, tab_text = st.tabs(["🎥 動画で見る", "🖼️ 図解で見る", "📝 テキストで見る"])

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
            "平均年齢と企業の創業年に注目しましょう。"
            "創業からかなり経っているのに平均年齢が低い企業は早期退職者が多い可能性があります。"
        )
        st.write(
            "海外売上比率は60％以上だと比較的安心とされます。日本は今後も少子高齢化が"
            "進む見込みのため、国内市場中心の企業より海外売上比率が高い企業の方が"
            "将来性を期待しやすいという見方があります。"
        )
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