import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime,timedelta,timezone

st.set_page_config(page_title="就活アンケート",layout="centered")

try:
    url:str=st.secrets["SUPABASE_URL"]
    key:str=st.secrets["SUPABASE_KEY"]
    admin_password:str=st.secrets["ADMIN_PASSWORD"]
    admin_access_key:str=st.secrets["ADMIN_ACCESS_KEY"]
    supabase:Client=create_client(url,key)
except Exception as e:
    st.error("エラー： st.secrets の設定が見つかりません。ローカル環境の場合は .streamlit/secrets.toml を作成してください。")
    st.stop()

MAX_ATTEMPTS=5
LOCK_MINUTES=15

is_admin_mode=st.query_params.get("key")==admin_access_key

#ここに質問と選択肢を入力
q1_title="本アンケートの回答データを、今後のツール開発に利用させていただいてもよろしいですか？"
q1_options=[
    "同意する（学籍番号・メールアドレスを記入して回答）",
    "同意する（匿名で回答）"
    ]

q2_title="「就職四季報」や「会社四季報」を知っていますか？"
q2_options=[
    "両方とも知っている",
    "「就職四季報」のみ知っている",
    "「会社四季報」のみ知っている",
    "どちらも知らない"
    ]

q3_title="就職活動で「就職四季報」や「会社四季報」を利用しましたか？または利用する予定ですか？"
q3_options=[
    "両方とも利用した",
    "「就職四季報」のみ利用した",
    "「会社四季報」のみ利用した",
    "利用したことはない"
    ]

q4_title="「会社四季報」をどのような目的で利用しましたか？または利用する予定ですか？"
q4_options=[
    "企業の基本情報を調べるため",
    "業績や財務状況を確認するため",
    "企業の将来性や成長性を調べるため",
    "競合他社と比較するため","志望企業を探すため",
    "ESや面接などの選考対策に活用するため",
    "その他"
    ]

q5_title="面接やES作成のために企業分析・他社比較を行う際、どのような点に難しさを感じましたか？"
q5_options=[
    "競合他社との具体的な違いや、企業ごとの強み・弱みを把握すること",
    "有価証券報告書や決算資料などの情報を読み解くこと",
    "企業HPなどでは分からない、実際の職場の雰囲気や社風を知ること",
    "企業分析に十分な時間を確保すること",
    "特に難しさを感じなかった"
    ]

q6_title="企業分析において、生成AIを利用しましたか？または利用する予定ですか？"
q6_options=[
    "利用した（情報の整理・要約や時間短縮に役立った）",
    "利用したが、回答の正確性やプロンプトの作成に難しさを感じた",
    "利用しようとしたが、うまく活用できなかった",
    "利用していない"
    ]

q7_title="就職活動中に「もっと知りたかった」と感じた企業情報は何ですか？"
q7_options=[
    "実際の給与・待遇、残業時間、有給休暇の取得状況",
    "実際の職場の雰囲気、人間関係、社風、離職状況",
    "選考基準や、面接で評価されるポイント",
    "競合他社と比較した際の、その企業の強み・弱み",
    "特にない"
    ]

q8_title="企業分析や企業の実情を把握するための開発ツールがあれば利用してみたいと思いますか？"
q8_options=[
    "ぜひ利用したい（有料でも、価値があれば利用を検討する）",
    "無料であれば利用したい",
    "あまり必要性を感じない"
    ]

q9_title="就職活動において、精神的・身体的な疲労やストレスを特に感じるのはどのような場面ですか？"
q9_options=[
    "ES作成や企業研究などに追われているとき",
    "面接や選考結果を待っているとき",
    "移動時間や隙間時間にも就職活動をしなければならないとき",
    "周囲の就活生と自分を比較して、焦りや不安を感じるとき",
    "特に疲労やストレスを感じていない"
    ]

q10_title="就職活動の合間に気分転換できるサービスがあれば利用したいと感じますか？"
q10_options=[
    "ぜひ利用したい（短時間で頭を休めたり、リラックスできるコンテンツ）",
    "ぜひ利用したい（他の就活生と交流・雑談できるコミュニティ）",
    "ぜひ利用したい（モチベーション向上やマインドフルネスなどに役立つ音声・動画）",
    "内容や手軽さによっては利用してみたい",
    "就職活動の合間に休息サービスは必要ない"
    ]

def get_lockout_state():
    """Supabaseからロックアウト状態を取得する関数"""
    response=supabase.table("shukatsu_admin_lockout").select("*").eq("id",1).execute()
    if  len(response.data)==0:
        supabase.table("shukatsu_admin_lockout").insert({"id":1,"failed_attempts":0}).execute()
        return{"failed_attempts":0,"locked_until":None}
    return response.data[0]

def is_currently_locked(state):
    """今ロック中かどうかを判定する"""
    locked_until=state.get("locked_until")
    if not locked_until:
        return False,None
    locked_until_dt=datetime.fromisoformat(locked_until.replace("Z","+00:00"))
    now=datetime.now(timezone.utc)
    if now<locked_until_dt:
        remaining=locked_until_dt-now
        return True,remaining
    return False,None

def record_failed_attempt(state):
    """失敗を一回記録し、規定回数を超えたらロックする"""
    new_count=state.get("failed_attempts",0)+1
    update_data={
        "failed_attempts":new_count,
        "last_attempt_at":datetime.now(timezone.utc).isoformat(),
    }
    if new_count>=MAX_ATTEMPTS:
        lock_until=datetime.now(timezone.utc)+timedelta(minutes=LOCK_MINUTES)
        update_data["locked_until"]=lock_until.isoformat()
    supabase.table("shukatsu_admin_lockout").update(update_data).eq("id",1).execute()
    return new_count

def reset_lockout():
    """ログイン成功時に失敗回数をリセットする"""
    supabase.table("shukatsu_admin_lockout").update({
        "failed_attempts":0,
        "locked_until":None,
        "last_attempt_at":datetime.now(timezone.utc).isoformat(),
    }).eq("id",1).execute()

if not is_admin_mode:
    st.title("📋就活に関するアンケート")
    st.write("以下の質問にお答えいただき、最下部の「回答を送信する」ボタンを押してください。\n就職活動を経験していない方は推測で回答をお願いいたします。")
    st.markdown("---")

    user_responses={}

#ここに回答の保存のコマンドを入力

    input_q1=st.radio(q1_title,q1_options,index=None) #ラジオボタン形式
    user_responses["q1"]=input_q1

    if input_q1=="同意する（学籍番号・メールアドレスを記入して回答）":
        student_id=st.text_input(
            "学籍番号",
            placeholder="例：1234567"
        )
        email=st.text_input(
            "メールアドレス",
            placeholder="例：example@example.com"
        )
        user_responses["student_id"]=student_id
        user_responses["email"]=email
    else:
        user_responses["student_id"]=""
        user_responses["email"]=""
    st.markdown("---")

    input_q2=st.radio(q2_title,q2_options,index=None) #ラジオボタン形式
    user_responses["q2"]=input_q2
    st.markdown("---")

    input_q3=st.radio(q3_title,q3_options,index=None) #ラジオボタン形式
    user_responses["q3"]=input_q3
    st.markdown("---")  

    if input_q3 in [
        "両方とも利用した",
        "「就職四季報」のみ利用した"
    ]:
        st.write(f"**{q4_title}")
        selected_q4=[]
        for option in q4_options:
            if st.checkbox(
                option,
                key=f"q4_{option}"
            ):
                selected_q4.append(option)
        if selected_q4:
            user_responses["q4"]=",".join(selected_q4)
        else:
            user_responses["q4"]="選択なし"
    else:
        user_responses["q4"]="対象外"
    st.markdown("---")

    st.write(f"**{q5_title}**") # チェックボックス形式
    selected_q5=[]
    for option in q5_options:
        if st.checkbox(option,key=f"q5_{option}"):
            selected_q5.append(option)
    user_responses["q5"]=",".join(selected_q5) if selected_q5 else "選択なし"
    st.markdown("---")


    st.write(f"**{q6_title}**") # チェックボックス形式
    selected_q6=[]
    for option in q6_options:
        if st.checkbox(option,key=f"q6_{option}"):
            selected_q6.append(option)
    user_responses["q6"]=",".join(selected_q6) if selected_q6 else "選択なし"
    st.markdown("---")


    st.write(f"**{q7_title}**") # チェックボックス形式
    selected_q7=[]
    for option in q7_options:
        if st.checkbox(option,key=f"q7_{option}"):
            selected_q7.append(option)
    user_responses["q7"]=",".join(selected_q7) if selected_q7 else "選択なし"
    st.markdown("---")

    input_q8=st.radio(q8_title,q8_options,index=None) #ラジオボタン形式
    user_responses["q8"]=input_q8
    st.markdown("---") 

    st.write(f"**{q9_title}**") # チェックボックス形式
    selected_q9=[]
    for option in q9_options:
        if st.checkbox(option,key=f"q9_{option}"):
            selected_q9.append(option)
    user_responses["q9"]=",".join(selected_q9) if selected_q9 else "選択なし"
    st.markdown("---")

    input_q10=st.radio(q10_title,q10_options,index=None) #ラジオボタン形式
    user_responses["q10"]=input_q10
    st.markdown("---") 



    if st.button("回答を送信する",type="primary"):
        try:
            supabase.table("shukatsu_survey_responses").insert(user_responses).execute()
            st.success("🎉 アンケートの送信が完了しました！ご協力いただきありがとうございました。")
        except Exception as e:
            st.error(f"データベース送信エラーの理由: {e}")
else:
    st.title("🔒 管理者用データ確認ページ")
    st.write("このページは管理者専用です。閲覧するにはパスワードを入力してください。")

    if "authenticated" not in st.session_state:
        st.session_state["authenticated"]=False

    lockout_state=get_lockout_state()
    locked, remaining=is_currently_locked(lockout_state)

    if locked:
        minutes_left=int(remaining.total_seconds()//60)+1
        st.error(
                f"🚨 パスワードの入力に{MAX_ATTEMPTS}回連続で失敗したため、"
                f"アカウントがロックされています。"
        )
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
                reset_lockout()
                st.session_state["authenticated"]=True
                is_auth_success=True
                st.rerun()
            else:
                new_count=record_failed_attempt(lockout_state)
                remaining_tries=MAX_ATTEMPTS-new_count

                if remaining_tries<=0:
                    st.error("🚨パスワードの入力に５回連続で失敗したため、アカウントがロックされました。")
                    st.stop()
                else:
                    st.error(f"❌ パスワードが正しくありません。残り試行回数：{remaining_tries}回")
    if is_auth_success:
        st.success("🗝️ 認証に成功しました。データを読み込んでいます...")
        st.markdown("---")

        try:
            response=supabase.table("shukatsu_survey_responses").select("*").order("created_at",desc=True).execute()
            raw_data=response.data

            if len(raw_data)==0:
                st.info("現在、回答データは0件です。")
            else:
                df=pd.DataFrame(raw_data)
                df_view=df.rename(columns={
                    "id":"ID",
                    "created_at":"回答日時",
                    "q1":"Q1:",
                    "student_id":"学籍番号",
                    "email":"メールアドレス",
                    "q2":"Q2:四季報の認知",
                    "q3":"Q3:四季報の利用経験",
                    "q4":"Q4:会社四季報の利用目的",
                    "q5":"Q5:企業分析の課題",
                    "q6":"Q6:生成AIの利用",
                    "q7":"Q7:知りたかった企業情報",
                    "q8":"Q8:企業分析ツールの利用意向",
                    "q9":"Q9:就活中の疲労・ストレス",
                    "q10":"Q10:休息サービスの利用意向",
                    # ここにカラム名と表示名を対応ずけて入力
                })

                st.metric(label="現在の総回答数",value=f"{len(df_view)}件")
                st.subheader("📊 回答データ一覧（Pandas DataFrame）")
                st.dataframe(df_view,use_container_width=True)

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