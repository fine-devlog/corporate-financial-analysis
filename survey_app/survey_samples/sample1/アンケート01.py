import streamlit as st
import pandas as pd
from supabase import create_client, Client

st.set_page_config(page_title="アンケート＆管理システム　サンプル",layout="centered")

try:
    url:str=st.secrets["SUPABASE_URL"]
    key:str=st.secrets["SUPABASE_KEY"]
    admin_password:str=st.secrets["ADMIN_PASSWORD"]
    supabase:Client=create_client(url,key)
except Exception as e:
    st.error("エラー： st.secrets の設定が見つかりません。ローカル環境の場合は .streamlit/secrets.toml を作成してください。")
    st.stop()

q_text_title="１．あなたのお名前を教えてください"
q_textarea_title="２．今日一日はどんな日でしたか。出来事や感想を自由にご記入ください。"
q_radio_title="３．選択肢の中であなたの一番好きなお菓子の種類を教えてください。"
q_radio_options=["チョコレート","クッキー","ポテトチップス","せんべい","アイス"]
q_checkbox_title="４．普段よく利用するSNSを教えてください。（複数選択可）"
q_checkbox_options=["X(旧Twitter)","Instagram","Youtube","Facebook","TikTok","LINE"]
q_selectbox_title="5.お住まいの地域を選択してください。"
q_selectbox_options=["北海道東北","関東","中部・近畿","中国・四国","九州・沖縄"]
q_matrix_title="６．以下の各項目の満足度を教えてください。"
q_matrix_rows=["サービスの内容","サポートの対応速度","価格の妥当性"]
q_matrix_cols=["不満","やや不満","普通","満足","大変満足"]
q_star_title="７．本サービスの満足度を星で評価してください。（0~5）"

tab1,tab2=st.tabs(["📋 アンケートに回答する","🔒 管理者専用ページ"])

with tab1:
    st.title("📋 特設アンケートフォーム")
    st.write("以下の質問にお答えいただき、最下部の「回答を送信する」ボタンを押してください。")
    st.markdown("---")

    user_responses={}


    input_name=st.text_input(q_text_title,placeholder="例：山田　太郎") #テキストボックス形式
    user_responses["name"]=input_name
    st.markdown("---")


    input_feedback=st.text_area(q_textarea_title,placeholder="具体的なエピソードなどがあればご記入ください。") # テキストエリア形式
    user_responses["comment"]=input_feedback
    st.markdown("---")


    input_transport=st.radio(q_radio_title,q_radio_options,index=None) #ラジオボタン形式
    user_responses["transportation"]=input_transport
    st.markdown("---")


    st.write(f"**{q_checkbox_title}**") # チェックボックス形式
    selected_sns=[]
    for option in q_checkbox_options:
        if st.checkbox(option,key=f"cd_{option}"):
            selected_sns.append(option)

    user_responses["sns"]=",".join(selected_sns) if selected_sns else "選択なし"
    st.markdown("---")


    input_area=st.selectbox(q_selectbox_title,q_selectbox_options,index=None,placeholder="選択してください。") #セレクトボックス形式
    user_responses["location"]=input_area
    st.markdown("---")

    st.write(f"**{q_matrix_title}**") # マトリクス形式
    for row in q_matrix_rows:
        choice=st.radio(f"【{row}】",q_matrix_cols,index=None,horizontal=True,key=f"mat_{row}")

        if row=="サービスの内容":
            user_responses["satisfaction_service"]=choice if choice else "未回答"
        elif row=="サポートの対応速度":
            user_responses["satisfaction_support"]=choice if choice else "未回答"
        elif row=="価格の妥当性":
            user_responses["satisfaction_price"]=choice if choice else "未回答"
    st.markdown("---")


    st.write(f"**{q_star_title}**") # 星評価
    star_index=st.feedback("stars",key="star_rating")

    user_responses["rating"]=star_index+1 if star_index is not None else 0
    st.write(f"現在：{user_responses['rating']}つ星")
    st.markdown("---")


    if st.button("回答を送信する",type="primary"):
        try:
            supabase.table("survey_responses").insert(user_responses).execute()
            st.success("🎉 アンケートの送信が完了しました！ご協力いただきありがとうございました。")
        except Exception as e:
            st.error(f"データベース送信エラーの理由: {e}")
with tab2:
    st.title("🔒 管理者用データ確認ページ")
    st.write("このページは管理者専用です。閲覧するにはパスワードを入力してください。")

    if "login_sttempts" not in st.session_state:
        st.session_state["login_attempts"]=0
    if "is_locked" not in st.session_state:
        st.session_state["is_locked"]=False
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"]=False

    if st.session_state["is_locked"]:
        st.error("🚨 パスワードの入力に５回連続で失敗したため、アカウントがロックされました。アプリを再起動するか、管理者に連絡してください。")
        st.stop()

    if st.session_state["authenticated"]:
        is_auth_success=True
    else:
        input_pwd=st.text_input("パスワードを入力してください。",type="password",key="admin_pwd_input")
        submit_auth=st.button("ログイン")

        is_auth_success=False

        if submit_auth or (input_pwd and st.session_state.get("admin_pwd_input")):
            import time
            time.sleep(1.0)

            if input_pwd==admin_password:
                st.session_state["authenticated"]=True
                st.session_state["login_attempts"]=0
                is_auth_success=True
                st.rerun()
            else:
                st.session_state["login_attempts"]+=1
                remaining=5-st.session_state["login_attempts"]

                if remaining<=0:
                    st.session_state["is_locked"]=True
                    st.error("🚨パスワードの入力に５回連続で失敗したため、アカウントがロックされました。")
                    st.stop()
                else:
                    st.error(f"❌ パスワードが正しくありません。残り試行回数：{remaining}回")
    if is_auth_success:
        st.success("🗝️ 認証に成功しました。データを読み込んでいます...")
        st.markdown("---")

        try:
            response=supabase.table("survey_responses").select("*").order("created_at",desc=True).execute()
            raw_data=response.data

            if len(raw_data)==0:
                st.info("現在、回答データは0件です。")
            else:
                df=pd.DataFrame(raw_data)
                df_view=df.rename(columns={
                    "id":"ID","created_at":"回答日時","name":"名前","comment":"自由感想","transportation":"移動手段","sns":"利用SNS","location":"住まい","satisfaction_service":"満足度：サービス","satisfaction_support":"満足度：サポート","satisfaction_price":"満足度：価格","rating":"星評価"
                })

                st.metric(label="現在の総回答数",value=f"{len(df_view)}件")
                st.subheader("📊 回答データ一覧（Pandas DataFrame）")
                st.dataframe(df_view)

                st.subheader("📥 データのダウンロード")
                import io
                buffer=io.BytesIO()
                with pd.ExcelWriter(buffer,engine='openpyxl')as writer:
                    df_view.to_excel(writer,index=False,sheet_name='アンケート結果')
                
                st.download_button(
                    label="Excelファイル（.xlsx）としてダウンロード",
                    data=buffer.getvalue(),
                    file_name="アンケート回答データ一覧.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        except Exception as e:
            st.error(f"データの読み込み中にエラーが発生しました：{e}")