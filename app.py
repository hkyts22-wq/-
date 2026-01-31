import streamlit as st
import pandas as pd
import google.generativeai as genai
import json
import tempfile
import os
from datetime import datetime

# --- 1. APIキーの設定 ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
except:
    st.error("APIキーが設定されていません。StreamlitのSecretsを設定してください。")
    st.stop()

# --- 2. モデル設定 (Gemini 3.0 Pro) ---
# あなたの指定通り 3.0 Pro を呼び出します
TARGET_MODEL_NAME = 'gemini-3.0-pro' 

try:
    model = genai.GenerativeModel(TARGET_MODEL_NAME)
except Exception as e:
    st.error(f"モデル設定エラー: {e}")

st.title("💰 My AI 家計簿 (Gemini 3.0 Pro)")

# --- デバッグ機能: モデルが見つからない場合の救済策 ---
# 万が一 3.0 Pro という名前でエラーが出る場合、使える名前一覧を表示します
with st.expander("🛠️ 使用可能なモデル一覧を確認する（エラー時用）"):
    if st.button("モデルリストを取得"):
        try:
            available_models = []
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    available_models.append(m.name)
            st.write(available_models)
            st.info(f"現在の指定: {TARGET_MODEL_NAME}")
        except Exception as e:
            st.error(f"リスト取得失敗: {e}")

# --- 3. アプリ本体 ---
if 'expenses' not in st.session_state:
    st.session_state.expenses = pd.DataFrame(columns=["日付", "品目", "カテゴリ", "金額", "AIコメント"])

tab1, tab2 = st.tabs(["🎙️ 入力", "📊 分析"])

with tab1:
    st.write(f"起動中のモデル: **{TARGET_MODEL_NAME}**")
    audio_value = st.audio_input("録音ボタンを押して話しかけてください")

    if audio_value:
        with st.spinner(f'{TARGET_MODEL_NAME} が思考中...'):
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_file:
                    tmp_file.write(audio_value.read())
                    tmp_path = tmp_file.name

                audio_file = genai.upload_file(path=tmp_path)

                prompt = """
                この音声から家計簿データを抽出して。
                JSON形式: {"item": "品目", "category": "カテゴリ", "amount": 数値, "comment": "短いアドバイス"}
                金額不明なら0。
                """
                response = model.generate_content([prompt, audio_file])
                
                # JSONクリーニング処理
                json_str = response.text.replace("```json", "").replace("```", "").strip()
                data = json.loads(json_str)

                new_row = {
                    "日付": datetime.now().strftime("%Y-%m-%d"),
                    "品目": data['item'],
                    "カテゴリ": data['category'],
                    "金額": data['amount'],
                    "AIコメント": data['comment']
                }
                st.session_state.expenses = pd.concat([st.session_state.expenses, pd.DataFrame([new_row])], ignore_index=True)
                
                st.success(f"✅ 記録完了")
                st.write(f"**{data['item']}**: ¥{data['amount']}")
                st.info(f"🤖 {data['comment']}")
                
                os.remove(tmp_path)

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
                # エラーの詳細を表示（モデル名のミスか、API制限かを見分けるため）
                st.code(str(e))

with tab2:
    if not st.session_state.expenses.empty:
        df = st.session_state.expenses
        st.metric("合計", f"¥{df['金額'].sum():,}")
        st.bar_chart(df.groupby("カテゴリ")["金額"].sum())
        st.dataframe(df)
    else:
        st.write("データなし")
