import streamlit as st
import pandas as pd
import google.generativeai as genai
import json
import tempfile
import os
from datetime import datetime

# --- 1. APIキー設定 ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
except:
    st.error("APIキー設定エラー: StreamlitのSecretsを確認してください。")
    st.stop()

# --- 2. モデル設定 (あなたの環境にある最新版を指定) ---
# 診断結果の No.23 に基づき、最新の3.0 Proプレビュー版を指定します
TARGET_MODEL_NAME = 'gemini-3-pro-preview'

try:
    model = genai.GenerativeModel(TARGET_MODEL_NAME)
except Exception as e:
    st.error(f"モデル設定エラー: {e}")

st.title(f"💰 My AI 家計簿 ({TARGET_MODEL_NAME})")

# --- 3. アプリ本体 ---
if 'expenses' not in st.session_state:
    st.session_state.expenses = pd.DataFrame(columns=["日付", "品目", "カテゴリ", "金額", "AIコメント"])

tab1, tab2 = st.tabs(["🎙️ 入力", "📊 分析"])

with tab1:
    st.info(f"起動中のモデル: **{TARGET_MODEL_NAME}**")
    st.write("録音ボタンを押して、買い物の内容を話してください。")
    
    audio_value = st.audio_input("録音開始")

    if audio_value:
        with st.spinner(f'{TARGET_MODEL_NAME} が思考中...'):
            try:
                # 一時ファイル保存
                with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_file:
                    tmp_file.write(audio_value.read())
                    tmp_path = tmp_file.name

                # ファイルアップロード
                audio_file = genai.upload_file(path=tmp_path)

                # プロンプト（3.0 Pro向けに少し高度に）
                prompt = """
                この音声はユーザーの支出記録です。内容を分析して家計簿データを作成してください。
                
                【ルール】
                1. 出力は以下のJSON形式のみ。Markdownの ```json 等は不要。
                2. 金額が明言されていない場合、文脈から推測するか、0にしてコメントで質問する。
                3. "comment"には、Gemini 3.0 Proとしての洞察（無駄遣いの指摘や、褒める言葉など）を入れる。

                JSON形式: {"item": "品目", "category": "カテゴリ", "amount": 数値, "comment": "アドバイス"}
                """
                
                # 推論実行
                response = model.generate_content([prompt, audio_file])
                
                # JSON抽出（3.0は余計な装飾をつけることがあるため念のためクリーニング）
                json_str = response.text
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0]
                elif "```" in json_str:
                    json_str = json_str.replace("```", "")
                
                data = json.loads(json_str.strip())

                # データ追加
                new_row = {
                    "日付": datetime.now().strftime("%Y-%m-%d"),
                    "品目": data['item'],
                    "カテゴリ": data['category'],
                    "金額": data['amount'],
                    "AIコメント": data['comment']
                }
                st.session_state.expenses = pd.concat([st.session_state.expenses, pd.DataFrame([new_row])], ignore_index=True)
                
                st.success("✅ 記録しました！")
                st.write(f"**{data['item']}**: ¥{data['amount']}")
                st.info(f"🤖 AI: {data['comment']}")
                
                # 掃除
                os.remove(tmp_path)

            except Exception as e:
                st.error("エラーが発生しました。")
                st.code(str(e))

with tab2:
    if not st.session_state.expenses.empty:
        df = st.session_state.expenses
        st.metric("合計", f"¥{df['金額'].sum():,}")
        st.bar_chart(df.groupby("カテゴリ")["金額"].sum())
        st.dataframe(df)
    else:
        st.write("まだデータがありません。")
