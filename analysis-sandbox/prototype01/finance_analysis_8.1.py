import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client, Client

st.set_page_config(page_title="就活生のための企業データ分析ツール", layout="wide")


@st.cache_resource
def init_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


supabase = init_supabase()
ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]


def init_session_state():
    defaults = {
        "page": "title",
        "prev_page": "title",
        "selected_industry": None,
        "selected_company": None,
        "reporter_headline": "",
        "market_ranking": [""] * 10,
        "market_sentiment_skipped": False,
        "evaluation_score": 0,
        "comparison_result": {},
        "search_not_found": False,
        "is_admin": False,
        "disclaimer_attempts":0,
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
        "comparison_result", "search_not_found","disclaimer_attempts",
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

METRIC_COLUMNS = ["平均年収(万)", "平均年齢(歳)", "海外売上比率(％)"]

# キーは INDUSTRIES のリストと完全一致させる（誤字を修正）
COMPANY_DATA_BY_INDUSTRY = {
    "1.電機・電子機器": {
        "企業名": ["テックフロンティア", "エレクトロブライド", "サンライズデバイセズ", "フューチャーサーキット", "ネオメカトロニクス"],
        "平均年収(万)": [480, 410, 395, 520, 450],
        "平均年齢(歳)": [39, 42, 44, 37, 41],
        "海外売上比率(％)": [65, 40, 30, 72, 55],
    },
    "2.IT・ソフト・SI": {
        "企業名": ["クラウドネクサス", "コードウェーブ", "データブリッジ", "スマートロジック", "バイトフォース"],
        "平均年収(万)": [520, 460, 430, 610, 400],
        "平均年齢(歳)": [34, 37, 40, 33, 42],
        "海外売上比率(％)": [59, 68, 83, 60, 95],
    },
}


def get_industry_dataframe(industry: str):
    data = COMPANY_DATA_BY_INDUSTRY.get(industry)
    if data is None:
        return None
    return pd.DataFrame(data)


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


def page_title():
    st.title("📊就活生のための企業データ分析ツール")
    st.write("平均年収・平均年齢・海外売上比率など、就活生が見るべき指標に注目して企業分析を行うツールです。")
    st.write("")
    if st.button("始める", type="primary"):
        goto("disclaimer")


def page_disclaimer():
    st.title("⚖️ご利用前の確認と同意")
    st.write("本システムを安全にご利用いただくため、以下の規約への同意が必要です。")
    with st.container(border=True):
        st.subheader("企業分析ダッシュボード　利用規約")
        st.markdown("""
                第一条（目的）
                本プログラムは、財務データおよび統計的手法（IQR法）を用いた企業分析・他社比較の補助を目的とした参考情報の提供ツールです。

                第二条（断定的表現の排除）
                本ツールが提供する「外れ値」等のデータは自動的な計算結果であり、対象企業の優劣、危険度、または安全性を断定するものではありません。

                第三条（定性データの非考慮）
                本分析は財務諸表等の数値データのみをもとにしており、企業のブランド力、知名度、技術力、経営陣の質など、数値化できない重要な要素は一切評価に含まれません。

                第四条（業界差の考慮）
                財務指標の基準は業界やビジネスモデルによって大きく異なります。単一の指標のみで企業価値を決めつけないようご注意ください。

                第五条（免責事項・投資判断の責任）
                利用者は本ツールの情報を過信せず、投資等の最終判断を自己の責任において行うものとします。本ツールの利用により生じた利益または損害について、開発者および提供者は一切の責任を負いません。
                """)
    st.write("---")

    MAX_ATTEMPTS=5

    if st.session_state["disclaimer_attempts"]<MAX_ATTEMPTS:
        user_input = st.text_input("内容を確認したら「理解した」と入力してください")
        if st.button("送信"):
            if user_input == "理解した":
                goto("industry_select")
            elif user_input == ADMIN_PASSWORD:
                st.session_state["is_admin"] = True
                goto("admin")
            else:
                st.session_state["disclaimer_attempts"]+=1
                remaining=MAX_ATTEMPTS-st.session_state["disclaimer_attempts"]
                if remaining>0:
                    st.error(f"入力内容が正しくありません。あと{remaining}回入力できます。")
                else:
                    st.rerun()
    else:
        st.warning(
            "「理解した」の入力に５回失敗しました"
            "下記のチェックボックスのご同意いただければそのまま次へ進めます"
        )
        agree=st.checkbox("上記の利用規約の内容を理解し、同意します")
        if st.button("同意して次へ進む",type="primary",disabled=not agree):
            st.session_state["disclaimer_attempts"]=0
            goto("industry_select")


def page_industry_select():
    st.title("業界を選択してください")

    industry = st.selectbox(
        "業界",
        INDUSTRIES,
        index=None,
        placeholder="選択してください",
    )

    if st.button("次へ", disabled=(industry is None)):
        st.session_state["selected_industry"] = industry
        goto("company_data")


def page_company_data():
    industry = st.session_state["selected_industry"]
    st.title(f"【{industry}業界】代表５社（架空）のデータ")

    df = get_industry_dataframe(industry)

    if df is None:
        st.warning("この業界のデータはまだ準備中です。他の業界をお試しください。")
        if st.button("業界選択に戻る"):
            goto("industry_select")
        return

    thresholds = calculate_industry_threshold(industry)
    st.caption(
        "この業界の基準値（登録されているデータの平均から自動算出）：　"
        f"平均年収{thresholds['平均年収(万)']}万円　/　"
        f"平均年齢{thresholds['平均年齢(歳)']}歳　/　"
        f"海外売上比率{thresholds['海外売上比率(％)']}％"
    )
    st.subheader("企業データ一覧")
    st.dataframe(df, use_container_width=True)

    st.sidebar.header("企業を検索")
    st.sidebar.caption("上記５社のいずれかの企業名を入力してください。")
    company_name = st.sidebar.text_input("企業名")

    if st.sidebar.button("検索"):
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
            st.sidebar.success(f"「{company_name}」を業界基準と比較しました")

    if st.session_state["search_not_found"]:
        st.sidebar.warning("該当企業が見つかりません。データを直接入力してください。")
        with st.sidebar.form("manual_input_form"):
            my_company = st.text_input("企業名", value=company_name or "マイカンパニー")
            my_income = st.number_input("平均年収(万)", min_value=0, value=400)
            my_age = st.number_input("平均年齢(歳)", min_value=18, max_value=75, value=40)
            my_overseas = st.number_input("海外売上比率(％)", min_value=0, max_value=100, value=50)
            submitted = st.form_submit_button("この内容で比較する")

        if submitted:
            company_row = {
                "企業名": my_company,
                "平均年収(万)": my_income,
                "平均年齢(歳)": my_age,
                "海外売上比率(％)": my_overseas,
            }
            comparison = evaluate_against_industry(company_row, industry)
            st.session_state["selected_company"] = my_company
            st.session_state["comparison_result"] = comparison
            apply_comparison_to_score(comparison)
            st.session_state["search_not_found"] = False
            st.success(f"「{my_company}」のデータを比較しました")

    if st.session_state["comparison_result"]:
        st.subheader(f"「{st.session_state['selected_company']}」の比較結果")
        for metric, judgement in st.session_state["comparison_result"].items():
            st.write(f"・{metric}：{judgement}")

    st.subheader("指標比較グラフ")
    metric_to_plot = st.selectbox("表示する指標", METRIC_COLUMNS)
    st.bar_chart(data=df, x="企業名", y=metric_to_plot)

    if st.button("次へ（記者コメント・見出しランキング入力画面）", type="primary"):
        goto("reporter_comment")


def page_reporter_comment():
    st.title("記者コメント見出し/市場全体の見出しランキング")
    st.info("会社四季報をお持ちでない場合は何も入力せず「スキップ」を押して次に進んで下さい。")

    headline = st.text_input("記者コメントの見出し（四季報右側の見出し）")
    st.write("市場全体の見出しランキング（1~10位）")
    rankings = [st.text_input(f"{i+1}位", key=f"rank_{i}") for i in range(10)]

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
    company = st.session_state["selected_company"] or "業界選択"
    industry = st.session_state["selected_industry"]
    st.metric("総合評価ポイント", score)

    comparison = st.session_state.get("comparison_result", {})
    if comparison:
        st.subheader("業界基準値との比較")
        for metric, judgement in comparison.items():
            st.write(f"・{metric}：{judgement}")

    if score > 0:
        st.success(f"「{company}」は{industry}業界では「将来性への期待」の可能性があります。")
    elif score < 0:
        st.warning(f"「{company}」は{industry}業界では「懸念材料あり」の可能性があります。")
    else:
        st.write(f"「{company}」は{industry}業界では「横ばい」の可能性があります。")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("❓ヘルプ（指標の見方）"):
            goto("help")
    with col2:
        if st.button("終了する（保存してリセット）", type="primary"):
            supabase.table("results").insert({
                "industry": industry,
                "company": company,
                "score": score,
                "created_at": datetime.now().isoformat(),
            }).execute()
            reset_all_and_goto_title()


def page_help():
    st.title("就活目的での会社四季報の読み方・指標のコツ")
    st.write("平均年齢と企業の創業年に注目しましょう。創業からかなり経っているのに\n平均年齢が低い企業は早期退職者が多い可能性があります。")
    st.write("海外売上比率は60％以上だと比較的安心とされます。\n日本は今後も少子高齢化が進む見込みのため、国内市場中心の企業より\n海外売上比率が高い企業の方が将来性を期待しやすいという見方があります。")
    st.write("---")

    if st.button("戻る"):
        goto(st.session_state["prev_page"])


def page_admin():
    st.title("🔒管理者専用ページ")

    if not st.session_state.get("is_admin"):
        st.error("アクセス権がありません。")
        if st.button("トップへ戻る"):
            goto("title")
        return

    st.write("登録データ一覧")
    data = supabase.table("results").select("*").execute().data
    if data:
        df = pd.DataFrame(data)
    else:
        st.info("登録データがまだありません（サンプルを表示しています）")
        df = pd.DataFrame({"企業名": ["サンプル株式会社"], "評価ポイント": [3]})

    edited_df = st.data_editor(df, use_container_width=True)

    if st.button("Supabaseに反映"):
        for row in edited_df.to_dict("records"):
            if "id" in row:
                supabase.table("results").update(row).eq("id", row["id"]).execute()
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
        st.session_state["is_admin"] = False
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

PAGE_FUNCTIONS[st.session_state["page"]]()