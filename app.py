import streamlit as st
import pandas as pd
import google.generativeai as genai
import json
import tempfile
import os
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 1. 設定エリア ---
# https://docs.google.com/spreadsheets/d/1EqrzveseDusUHWXlXfwewDcxJ412UIA7BtLjiEydDh4/edit?gid=0#gid=0
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1EqrzveseDusUHWXlXfwewDcxJ412UIA7BtLjiEydDh4/edit"

# APIキー設定
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
except:
    st.error("APIキー設定エラー: Secretsを確認してください")
    st.stop()

# モデル設定 (Gemini 3.0 Pro Preview)
TARGET_MODEL_NAME = 'gemini-3-pro-preview'
try:
    model = genai.GenerativeModel(TARGET_MODEL_NAME)
except:
    st.error(f"モデルエラー: {TARGET_MODEL_NAME} が見つかりません")

# --- 2. スプレッドシート接続機能 ---
def add_to_sheet(data_dict):
    """スプレッドシートに行を追加する"""
    try:
        # SecretsからJSON文字列を読み込む
        json_str = st.secrets["GCP_JSON_STR"]
        creds_dict = json.loads(json_str, strict=False)
        
        scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # シートを開く
        sheet = client.open_by_url(SPREADSHEET_URL).get_worksheet(0)
        
        # ヘッダーが無い場合は追加（初回のみ）
        if len(sheet.get_all_values()) == 0:
            sheet.append_row(["日付", "品目", "カテゴリ", "金額", "AIコメント"])
            
        # データ追加
        row = [
            datetime.now().strftime("%Y-%m-%d"),
            data_dict['item'],
            data_dict['category'],
            data_dict['amount'],
            data_dict['comment']
        ]
        sheet.append_row(row)
        return True
    except Exception as e:
        st.error(f"スプレッドシート保存エラー: {e}")
        return False

# --- 3. アプリ画面 ---
st.title(f"💰 My AI 家計簿 (Complete)")

tab1, tab2 = st.tabs(["🎙️ 入力", "📊 分析"])

with tab1:
    st.info(f"Using: {TARGET_MODEL_NAME}")
    st.write("話しかけると、Googleスプレッドシートに記録されます。")
    
    audio_value = st.audio_input("録音開始")

    if audio_value:
        with st.spinner('Geminiが解析＆保存中...'):
            try:
                # 音声保存
                with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_file:
                    tmp_file.write(audio_value.read())
                    tmp_path = tmp_file.name

                # Geminiへ送信
                audio_file = genai.upload_file(path=tmp_path)
                
                prompt = """
                この音声は支出の記録です。家計簿データを作成してください。
                JSON形式: {"item": "品目", "category": "カテゴリ", "amount": 数値, "comment": "アドバイス"}
                金額不明は0。
                """
                
                response = model.generate_content([prompt, audio_file])
                
                # JSON抽出
                json_str = response.text
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0]
                elif "```" in json_str:
                    json_str = json_str.replace("```", "")
                
                data = json.loads(json_str.strip())
                
                # ★シートへ保存実行！
                if add_to_sheet(data):
                    st.success("✅ スプレッドシートに保存しました！")
                    st.write(f"**{data['item']}**: ¥{data['amount']}")
                    st.info(f"🤖 {data['comment']}")
                
                os.remove(tmp_path)

            except Exception as e:
                st.error(f"エラー: {e}")

with tab2:
    st.write("データはGoogleスプレッドシートに保存されています。")
    st.link_button("スプレッドシートを開く", SPREADSHEET_URL)
