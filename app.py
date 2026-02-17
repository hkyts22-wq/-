import streamlit as st
import pandas as pd
import google.generativeai as genai
import json
import tempfile
import os
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image
import hashlib # ★追加：重複チェック用

# --- 1. 設定エリア ---
# ★ここにあなたのスプレッドシートURLを入れてください
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/xxxxxxxxxxxx/edit"

# ★あなたの毎月の予算（円）
MONTHLY_BUDGET = 100000 

# APIキー設定
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
except:
    st.error("APIキー設定エラー: Secretsを確認してください")
    st.stop()

# モデル設定
TARGET_MODEL_NAME = 'gemini-1.5-flash'
try:
    model = genai.GenerativeModel(TARGET_MODEL_NAME)
except:
    st.error(f"モデルエラー: {TARGET_MODEL_NAME} が見つかりません")

# --- 2. スプレッドシート接続機能 ---
def get_sheet():
    """シートオブジェクトを取得する"""
    json_str = st.secrets["GCP_JSON_STR"]
    creds_dict = json.loads(json_str, strict=False)
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open_by_url(SPREADSHEET_URL).get_worksheet(0)

def add_to_sheet(data_list):
    """リスト形式のデータをまとめて保存する"""
    try:
        sheet = get_sheet()
        if len(sheet.get_all_values()) == 0:
            sheet.append_row(["日付", "品目", "カテゴリ", "金額", "AIコメント"])
            
        current_date = datetime.now().strftime("%Y-%m-%d")
        rows_to_add = []
        for item in data_list:
            row = [
                current_date,
                item.get('item', '不明'),
                item.get('category', 'その他'),
                item.get('amount', 0),
                item.get('comment', '')
            ]
            rows_to_add.append(row)
        sheet.append_rows(rows_to_add)
        return True
    except Exception as e:
        st.error(f"保存エラー: {e}")
        return False

def get_data_df():
    """スプレッドシートのデータをDataFrameとして取得"""
    try:
        sheet = get_sheet()
        records = sheet.get_all_records()
        df = pd.DataFrame(records)
        if not df.empty and '日付' not in df.columns:
            return pd.DataFrame()
        return df
    except:
        return pd.DataFrame()

# --- 3. アプリ画面 ---
st.title(f"💰 My AI 家計簿 (Dashboard)")

# データを取得
df = get_data_df()

# --- 上部：予算＆収支サマリー ---
if not df.empty and '日付' in df.columns and '金額' in df.columns:
    current_month = datetime.now().strftime("%Y-%m")
    df['日付'] = df['日付'].astype(str)
    df['金額'] = pd.to_numeric(df['金額'], errors='coerce').fillna(0)
    
    monthly_df = df[df['日付'].str.startswith(current_month)]
    total_spent = monthly_df['金額'].sum()
else:
    monthly_df = pd.DataFrame()
    total_spent = 0

remaining = MONTHLY_BUDGET - total_spent
ratio = min(total_spent / MONTHLY_BUDGET, 1.0)

col1, col2, col3 = st.columns(3)
col1.metric("📅 今月の出費", f"¥{total_spent:,.0f}")
col2.metric("💰 残り予算", f"¥{remaining:,.0f}")
col3.metric("📊 消化率", f"{ratio*100:.1f}%")

st.progress(ratio)
if ratio >= 1.0:
    st.error("💸 予算オーバーです！")

# --- メインエリア ---
tab1, tab2, tab3 = st.tabs(["🎙️ 入力・撮影", "📈 分析グラフ", "📝 履歴リスト"])

SYSTEM_PROMPT = """
あなたは家計簿アシスタントです。入力からJSONデータを作成してください。
フォーマットは必ずリスト形式 `[{"item":..., "category":..., "amount":...}, ...]` で返してください。
ユーザーが「固定費」と言及した場合は、以下のリストを返してください：
[
    {"item": "家賃", "category": "住居費", "amount": 80000, "comment": "毎月の家賃"},
    {"item": "電気代", "category": "光熱費", "amount": 5000, "comment": "概算"},
    {"item": "スマホ代", "category": "通信費", "amount": 3500, "comment": "基本料"}
]
"""

# ★重複防止用の記憶領域を作る
if "processed_hash" not in st.session_state:
    st.session_state.processed_hash = ""

with tab1:
    st.write("##### 🗣️ 音声で入力")
    audio_value = st.audio_input("話しかけて記録")

    if audio_value:
        # ★データの指紋（ハッシュ）を作って、前回と同じなら無視する
        audio_bytes = audio_value.getvalue()
        current_hash = hashlib.md5(audio_bytes).hexdigest()
        
        if st.session_state.processed_hash != current_hash:
            with st.spinner('音声解析中...'):
                with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_file:
                    tmp_file.write(audio_bytes)
                    tmp_path = tmp_file.name
                
                audio_file = genai.upload_file(path=tmp_path)
                response = model.generate_content([SYSTEM_PROMPT, audio_file])
                try:
                    json_str = response.text.replace("```json", "").replace("```", "").strip()
                    data_list = json.loads(json_str)
                    if isinstance(data_list, dict): data_list = [data_list]
                    
                    if add_to_sheet(data_list):
                        st.success(f"✅ {len(data_list)}件 保存しました！")
                        # ★処理が終わったら「今のデータ」を記憶する
                        st.session_state.processed_hash = current_hash
                        st.rerun()
                except Exception as e:
                    st.error(f"エラー: {e}")
                os.remove(tmp_path)

    st.write("---")
    st.write("##### 📸 レシートで入力")
    img_file = st.camera_input("レシート撮影")
    
    if img_file:
        # ★画像も同様に重複チェック
        img_bytes = img_file.getvalue()
        current_img_hash = hashlib.md5(img_bytes).hexdigest()

        if st.session_state.processed_hash != current_img_hash:
            with st.spinner('解析中...'):
                image = Image.open(img_file)
                response = model.generate_content([SYSTEM_PROMPT, image])
                try:
                    json_str = response.text.replace("```json", "").replace("```", "").strip()
                    data_list = json.loads(json_str)
                    if isinstance(data_list, dict): data_list = [data_list]
                    
                    if add_to_sheet(data_list):
                        st.success(f"✅ {len(data_list)}件 保存しました！")
                        st.session_state.processed_hash = current_img_hash
                        st.rerun()
                except Exception as e:
                    st.error(f"エラー: {e}")

with tab2:
    st.subheader("📊 今月の収支レポート")
    if not monthly_df.empty:
        st.write("**カテゴリ別の支出割合**")
        category_sum = monthly_df.groupby('カテゴリ')['金額'].sum()
        st.bar_chart(category_sum)

        st.write("**日別の支出推移**")
        daily_sum = monthly_df.groupby('日付')['金額'].sum()
        st.line_chart(daily_sum)
    else:
        st.info("データがありません")

with tab3:
    st.subheader("📝 最近の記録")
    if not df.empty and '日付' in df.columns:
        st.dataframe(df.tail(10).iloc[::-1])
    else:
        st.write("データなし")
