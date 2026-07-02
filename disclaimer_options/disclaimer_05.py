import streamlit as st

st.set_page_config(page_title="ステップ確認",page_icon="✅",layout="centered")
st.title("🔍ご利用前のステップ確認")
st.write("３つの確認タブをすべてチェックすると、ダッシュボードを開きます")
st.write("---")

tab1,tab2,tab3=st.tabs(["⓵数字の限界について","⓶業界差と断定の排除","⓷投資と自己責任"])

with tab1:
    st.info("### 📊財務数値だけで企業価値は決めつけられません")
    st.write("企業のブランド力、知名度、顧客からの信頼など、目に見えない価値（定性データ）は一切この分析には含まれていません。それを前提に数字をご確認ください。")
    check1=st.checkbox("数値以外の要素も重要であることを理解した",key="c1")

with tab2:
    st.info("### 🏢指標の基準は業界によって異なります")
    st.write("ある業界の「普通」が別の業界では「異常」になることもあります。また、分析結果は統計上の計算であり、「安全」「危険」を断定するものではありません。")
    check2=st.checkbox("単一の指標や計算で断定しないことに同意した",key="c2")

with tab3:
    st.info("### ⚠️最終的な判断はあなた自身の責任です")
    st.write("本プログラムはあくまで分析を補助する「参考情報」です。利用者が結果を過信して行った投資判断について、開発者は一切の責任を負いません。")
    check3=st.checkbox("最終判断は自己責任で行うことに同意した",key="c3")

st.write("---")

if check1 and check2 and check3:
    if st.button("すべての項目を確認しました。ダッシュボードを開く",type="primary"):
        st.success("➔全ステップクリア！ダッシュボードへ進みます。")

else:
    st.button("すべての項目を確認しました。ダッシュボードを開く。",disabled=True,help="各タブを開き、すべてのチェックボックスにチェックを入れてください。")
                   

