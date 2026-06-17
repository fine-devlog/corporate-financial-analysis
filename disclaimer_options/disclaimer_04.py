import streamlit as st

st.set_page_config(page_title="ツールの使い方ガイド",page_icon="🤝",layout="centered")

st.title("🤝 ツールを正しく使いこなすためのQ＆A")
st.write("このダッシュボードのポテンシャルを最大限に引き出すための大切な心得です。")
st.write("---")

with st.chat_message("user"):
    st.markdown("""Q.このツールで「安全な企業」や「危険な企業」がすべてわかりますか？""" )

with st.chat_message("assistant"):
    st.markdown("""A.いいえ、わかりません。\nこのツールは数字を整理して見やすくするだけで、企業の未来を明確に言い当てるものではなく、安全性を保障するものでもありません。""")

with st.chat_message("user"):
    st.markdown("""Q.財務データがよければいい企業と判断してもいいですか？""" )

with st.chat_message("assistant"):
    st.markdown("""A.それだけでは不十分です。\n企業の本当の価値には、ブランド力、知名度、技術の特許、働く人の質など、**「数値化の難しい資産」**が半分以上を占めています。数字だけで決めつけないようにご注意ください。""")

with st.chat_message("user"):
    st.markdown("""Q. 投資の参考にしても大丈夫ですか？""" )

with st.chat_message("assistant"):
    st.markdown("""A.最終的な判断はご自身で行ってください。\n本ツールの予測や分析を過信せず、業界の特性なども考慮した上で、最終的な判断はご自身の責任で行うようお願いいたします。""")

st.write("---")

if st.button("理解しました！ダッシュボードへ　➔"):
    st.success("ありがとうございます！　それでは分析を始めましょう！")