import streamlit as st
import pandas as pd
import google.generativeai as genai
import json
import tempfile
import os
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import hashlib

# --- 1. 設定エリア ---
# ★あなたのスプレッドシートURL
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1EqrzveseDusUHWXlXfwewDcxJ412UIA7BtLjiEydDh4/edit?gid=0#gid=0"

# ★あなたの毎月の予算（円）
MONTHLY_BUDGET = 30000

# APIキー設定
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
except:
    st.error("APIキー設定エラー: Secretsを確認してください")
    st.stop()

# モデル設定 (gemini-3-pro-preview)
TARGET_MODEL_NAME = 'gemini-3-pro-preview'

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
    """スプレッドシートのデータをDataFrameとして取得（強力なクリーニング付き）"""
    try:
        sheet = get_sheet()
        records = sheet.get_all_records()
        df = pd.DataFrame(records)
        
        # データが空の場合
        if df.empty:
            return pd.DataFrame()

        # カラム名の余計な空白を削除
        df.columns = df.columns.str.strip()
        
        # 必須カラムチェック
        if '日付' not in df.columns or '金額' not in df.columns:
            st.error("⚠️ スプレッドシートに「日付」または「金額」の列が見つかりません。1行目を確認してください。")
            return pd.DataFrame()
            
        return df
    except Exception as e:
        st.error(f"データ読み込みエラー: {e}")
        return pd.DataFrame()

# --- 3. アプリ画面 ---
st.title(f"💰 My AI 家計簿")

# データを取得
df = get_data_df()

# --- データの前処理（ここを強化しました） ---
monthly_df = pd.DataFrame()
total_spent = 0

if not df.empty:
    try:
        # 日付を強制的に統一フォーマットに変換
        df['日付'] = pd.to_datetime(df['日付'], errors='coerce')
        # 金額を数値に変換
        df['金額'] = pd.to_numeric(df['金額'], errors='coerce').fillna(0)
        
        # 今月のデータを抽出
        current_month = datetime.now().strftime("%Y-%m")
        # 日付が無効な行（Nat）を除外してフィルタリング
        monthly_df = df[df['日付'].dt.strftime('%Y-%m') == current_month].copy()
        
        total_spent = monthly_df['金額'].sum()
    except Exception as e:
        st.error(f"集計エラー: {e}")

remaining = MONTHLY_BUDGET - total_spent
ratio = min(total_spent / MONTHLY_BUDGET, 1.0) if MONTHLY_BUDGET > 0 else 0

# --- 上部サマリー ---
col1, col2, col3 = st.columns(3)
col1.metric("📅 今月の出費", f"¥{total_spent:,.0f}")
col2.metric("💰 残り予算", f"¥{remaining:,.0f}")
col3.metric("📊 消化率", f"{ratio*100:.1f}%")

st.progress(ratio)
if ratio >= 1.0:
    st.error("💸 予算オーバーです！")

# --- メインエリア ---
tab1, tab2 = st.tabs(["🎙️ 音声入力", "📊 分析グラフ"])

SYSTEM_PROMPT = """
あなたは家計簿アシスタントです。音声入力からJSONデータを作成してください。
フォーマットは必ずリスト形式 `[{"item":..., "category":..., "amount":...}, ...]` で返してください。
ユーザーが「固定費」と言及した場合は、以下のリストを返してください：
[
    {"item": "家賃", "category": "住居費", "amount": 80000, "comment": "毎月の家賃"},
    {"item": "電気代", "category": "光熱費", "amount": 5000, "comment": "概算"},
    {"item": "スマホ代", "category": "通信費", "amount": 3500, "comment": "基本料"}
]
"""

if "processed_hash" not in st.session_state:
    st.session_state.processed_hash = ""

with tab1:
    st.write("##### 🗣️ 話しかけて記録")
    audio_value = st.audio_input("録音開始")

    if audio_value:
        audio_bytes = audio_value.getvalue()
        current_hash = hashlib.md5(audio_bytes).hexdigest()
        
        if st.session_state.processed_hash != current_hash:
            with st.spinner('解析中...'):
                with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_file:
                    tmp_file.write(audio_bytes)
                    tmp_path = tmp_file.name
                
                try:
                    audio_file = genai.upload_file(path=tmp_path)
                    response = model.generate_content([SYSTEM_PROMPT, audio_file])
                    json_str = response.text.replace("```json", "").replace("```", "").strip()
                    data_list = json.loads(json_str)
                    if isinstance(data_list, dict): data_list = [data_list]
                    
                    if add_to_sheet(data_list):
                        st.success(f"✅ {len(data_list)}件 保存しました！")
                        st.session_state.processed_hash = current_hash
                        st.rerun()
                except Exception as e:
                    st.error(f"エラー: {e}")
                finally:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)

with tab2:
    st.subheader("📊 今月の収支レポート")
    
    if not monthly_df.empty:
        # カテゴリ別 円グラフ（のような棒グラフ）
        st.write("**カテゴリ別の支出**")
        category_sum = monthly_df.groupby('カテゴリ')['金額'].sum()
        st.bar_chart(category_sum)

        # 日別推移
        st.write("**日別の支出推移**")
        daily_sum = monthly_df.groupby('日付')['金額'].sum()
        st.line_chart(daily_sum)
        
        # 生データ確認用（デバッグ）
        with st.expander("データ詳細を見る"):
            st.dataframe(monthly_df)
    else:
        st.info("今月のデータがまだありません。")
        if not df.empty:
            st.warning(f"※スプレッドシート全体には {len(df)} 件のデータがありますが、日付が今月（{datetime.now().strftime('%Y-%m')}）のものがありません。")
            with st.expander("全データを確認"):
                st.dataframe(df)
