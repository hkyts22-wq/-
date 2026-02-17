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
MONTHLY_BUDGET = 300000

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
                item.get('comment', '特になし')
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
        if df.empty: return pd.DataFrame()
        df.columns = df.columns.str.strip()
        if '日付' not in df.columns or '金額' not in df.columns: return pd.DataFrame()
        
        # 前処理
        df['日付'] = pd.to_datetime(df['日付'], errors='coerce')
        df['金額'] = df['金額'].astype(str).str.replace(',', '').str.replace('¥', '').str.replace('円', '')
        df['金額'] = pd.to_numeric(df['金額'], errors='coerce').fillna(0)
        return df
    except Exception as e:
        return pd.DataFrame()

def get_spending_context(df):
    """AIに渡すための「今の家計状況」の要約文を作る"""
    if df.empty:
        return "現在はまだデータがありません。これが初めての記録です。"
    
    try:
        current_month = datetime.now().strftime("%Y-%m")
        monthly_df = df[df['日付'].dt.strftime('%Y-%m') == current_month]
        
        if monthly_df.empty:
            return "今月のデータはまだありません。"

        total_spent = monthly_df['金額'].sum()
        remaining = MONTHLY_BUDGET - total_spent
        
        # カテゴリごとの集計（トップ3）
        category_counts = monthly_df.groupby('カテゴリ')['金額'].sum().sort_values(ascending=False).head(3)
        cat_text = ""
        for cat, amount in category_counts.items():
            cat_text += f"- {cat}: {int(amount):,}円\n"
        
        context = f"""
        【現在の家計状況 ({current_month})】
        - 今月の出費合計: {int(total_spent):,}円
        - 予算残り: {int(remaining):,}円
        - 出費が多いカテゴリTop3:
        {cat_text}
        """
        return context
    except:
        return "データ集計中にエラーが発生しました。"

# --- 3. アプリ画面 ---
st.title(f"💰 My AI 家計簿 (秘書モード)")

# データを取得
df = get_data_df()

# --- 上部サマリー ---
monthly_df = pd.DataFrame()
total_spent = 0
if not df.empty:
    current_month = datetime.now().strftime("%Y-%m")
    monthly_df = df[df['日付'].dt.strftime('%Y-%m') == current_month]
    total_spent = monthly_df['金額'].sum()

remaining = MONTHLY_BUDGET - total_spent
ratio = min(total_spent / MONTHLY_BUDGET, 1.0) if MONTHLY_BUDGET > 0 else 0

col1, col2, col3 = st.columns(3)
col1.metric("📅 今月の出費", f"¥{total_spent:,.0f}")
col2.metric("💰 残り予算", f"¥{remaining:,.0f}")
col3.metric("📊 消化率", f"{ratio*100:.1f}%")
st.progress(ratio)

# --- メインエリア ---
tab1, tab2, tab3 = st.tabs(["🎙️ 音声入力", "📊 分析グラフ", "📝 履歴リスト"])

# ★AIへの「今の状況」レポートを作成
current_context = get_spending_context(df)

# ★プロンプトに状況を埋め込む
SYSTEM_PROMPT = f"""
あなたは優秀な家計簿アシスタントです。
以下の「現在の家計状況」を踏まえて、ユーザーの音声入力からJSONデータを作成してください。

【重要：コメントのルール】
「comment」フィールドには、単なる感想ではなく、**以下の家計状況データを根拠にしたアドバイス**を書いてください。
例：「食費が今月ピンチです！」「予算にはまだ余裕がありますね」「最近カフェ代がかさんでいます」

{current_context}

【出力フォーマット（JSONリスト）】
[
    {{"item": "品目", "category": "カテゴリ", "amount": 1000, "comment": "状況を踏まえたアドバイス"}}
]

ユーザーが「固定費」と言及した場合は、いつもの固定費リストを返してください。
"""

if "processed_hash" not in st.session_state:
    st.session_state.processed_hash = ""

with tab1:
    st.write("##### 🗣️ 話しかけて記録")
    st.info("💡 AIはあなたの今月の出費状況を把握しています。")
    audio_value = st.audio_input("録音開始")

    if audio_value:
        audio_bytes = audio_value.getvalue()
        current_hash = hashlib.md5(audio_bytes).hexdigest()
        
        if st.session_state.processed_hash != current_hash:
            with st.spinner('家計状況と照らし合わせて解析中...'):
                with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_file:
                    tmp_file.write(audio_bytes)
                    tmp_path = tmp_file.name
                
                try:
                    audio_file = genai.upload_file(path=tmp_path)
                    # コンテキスト入りのプロンプトを送信
                    response = model.generate_content([SYSTEM_PROMPT, audio_file])
                    json_str = response.text.replace("```json", "").replace("```", "").strip()
                    data_list = json.loads(json_str)
                    if isinstance(data_list, dict): data_list = [data_list]
                    
                    if add_to_sheet(data_list):
                        st.success(f"✅ 保存しました！")
                        # AIのコメントを強調表示
                        for item in data_list:
                            st.write(f"**{item['item']}** ({item['amount']}円)")
                            st.info(f"🤖 AI秘書: {item['comment']}")
                        
                        st.session_state.processed_hash = current_hash
                        # 少し待ってからリロード（コメントを読ませるためボタンにする手もあり）
                        if st.button("OK（画面更新）"):
                            st.rerun()
                except Exception as e:
                    st.error(f"エラー: {e}")
                finally:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)

with tab2:
    st.subheader("📊 今月の収支レポート")
    if not monthly_df.empty:
        st.write("**カテゴリ別の支出**")
        category_sum = monthly_df.groupby('カテゴリ')['金額'].sum()
        st.bar_chart(category_sum)
        st.write("**日別の支出推移**")
        daily_sum = monthly_df.groupby('日付')['金額'].sum()
        st.line_chart(daily_sum)
    else:
        st.info("データがありません")

with tab3:
    st.subheader("📝 全データの履歴")
    if not df.empty:
        st.dataframe(df.sort_values('日付', ascending=False))
