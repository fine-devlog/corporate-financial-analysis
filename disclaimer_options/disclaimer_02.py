import streamlit as st

st.set_page_config(page_title="ご利用上の注意",page_icon="💡",layout="centered")

st.title("💡ダッシュボードをご利用いただく前に")
st.write("数字の背景にあるドラマを見落とさないために、３つの約束をお願いしています。")
st.write("---")

col1,col2,col3=st.columns(3)
with col1:
    with st.container(border=True):
        st.subheader("📈1.数字の限界")
        st.write("ブランド力や知名度、技術力など、**数字にできない価値**はここには映りません。数字は企業の一面に過ぎないことを忘れないでください。")
with col2:
    with st.container(border=True):
        st.subheader("🏢2.業界の壁")
        st.write("指標の良し悪しは、業界やビジネスモデルでガラリと変わります。一つの物差しで企業を決めつけないでください。")
with col3:
    with st.container(border=True):
        st.subheader("⚠️3.自己責任の原則")
        st.write("このツールは「参考書」であり「預言書」ではありません。結果を過信せず、最終的な判断はご自身で行ってください。その判断の結果ご自身が被った損失、または利益について、開発者は一切の責任を負いません。")
st.write("---")

if st.button("３つの約束を理解して、分析を始める　➔", use_container_width=True,type="primary"):
    st.balloons()
    st.success("準備完了！　ダッシュボードページへ移動します。")