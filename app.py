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
TARGET_MODEL_NAME = 'gemini-2.0-flash-exp' # 画像処理も得意な高速モデルに変更
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
        
        # ヘッダー確認
        if len(sheet.get_all_values()) == 0:
            sheet.append_row(["日付", "品目", "カテゴリ", "金額", "AIコメント"])
            
        # データ追加ループ
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
            
        sheet.append_rows(rows_to_add) # 一括追加
        return True
    except Exception as e:
        st.error(f"保存エラー: {e}")
        return False

def get_current_total():
    """今月の使用合計額を計算する"""
    try:
        sheet = get_sheet()
        records = sheet.get_all_records()
        df = pd.DataFrame(records)
        
        if df.empty:
            return 0
            
        # 日付でフィルタ（今月分のみ）
        current_month = datetime.now().strftime("%Y-%m") # 例: "2024-05"
        # 日付カラムを文字列として扱う
        df['日付'] = df['日付'].astype(str)
        # 今月のデータだけ抽出
        monthly_df = df[df['日付'].str.startswith(current_month)]
        
        total = monthly_df['金額'].sum()
        return total
    except:
        return 0

# --- 3. アプリ画面 ---
st.title(f"💰 My AI 家計簿 (Ultimate)")

# --- 機能1: 予算バー ---
try:
    total_spent = get_current_total()
    remaining = MONTHLY_BUDGET - total_spent
    ratio = min(total_spent / MONTHLY_BUDGET, 1.0)
    
    st.metric("今月の出費", f"¥{total_spent:,}", delta=f"残り ¥{remaining:,}")
    
    bar_color = "red" if ratio >= 1.0 else "green"
    st.progress(ratio)
    if ratio >= 1.0:
        st.error("💸 予算オーバーです！節約しましょう！")
    elif ratio >= 0.8:
        st.warning("⚠️ 予算の8割を使いました。注意！")

except Exception as e:
    st.warning("データがまだ少ないため分析できません")

# --- 入力エリア ---
tab1, tab2, tab3 = st.tabs(["🎙️ 音声入力", "📸 レシート", "📊 データ確認"])

# 共通のプロンプト（固定費リスト入り）
SYSTEM_PROMPT = """
あなたは家計簿アシスタントです。入力（音声または画像）からJSONデータを作成してください。
フォーマットは必ずリスト形式のJSON `[{"item":..., "amount":...}, ...]` で返してください。

★特別ルール：
ユーザーが「固定費」や「いつもの」と言及した場合は、入力内容に関わらず以下のリストを返してください：
[
    {"item": "家賃", "category": "住居費", "amount": 80000, "comment": "毎月の家賃"},
    {"item": "電気代", "category": "光熱費", "amount": 5000, "comment": "概算"},
    {"item": "スマホ代", "category": "通信費", "amount": 3500, "comment": "基本料"}
]

通常の入力の場合は、品目(item)、カテゴリ(category)、金額(amount:数値)、短いコメント(comment)を抽出してください。
金額が不明な場合は0にしてください。
"""

with tab1: # 音声入力
    st.write("話しかけてください。（例：「コンビニでパンを200円で買った」「固定費入れて」）")
    audio_value = st.audio_input("録音開始")

    if audio_value:
        with st.spinner('音声解析中...'):
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_file:
                tmp_file.write(audio_value.read())
                tmp_path = tmp_file.name
            
            audio_file = genai.upload_file(path=tmp_path)
            response = model.generate_content([SYSTEM_PROMPT, audio_file])
            
            # 共通処理へ
            try:
                json_str = response.text.replace("```json", "").replace("```", "").strip()
                data_list = json.loads(json_str)
                # 辞書型ならリストに変換
                if isinstance(data_list, dict): data_list = [data_list]
                
                if add_to_sheet(data_list):
                    st.success(f"✅ {len(data_list)}件 保存しました！")
                    st.rerun() # 画面更新してバーを反映
            except Exception as e:
                st.error(f"エラー: {e}")
            os.remove(tmp_path)

with tab2: # カメラ入力
    st.write("レシートを撮影してください。")
    img_file = st.camera_input("カメラ起動")

    if img_file:
        with st.spinner('レシート読み取り中...'):
            image = Image.open(img_file)
            response = model.generate_content([SYSTEM_PROMPT, image])
            
            try:
                json_str = response.text.replace("```json", "").replace("```", "").strip()
                data_list = json.loads(json_str)
                if isinstance(data_list, dict): data_list = [data_list]

                if add_to_sheet(data_list):
                    st.success(f"✅ レシートから {len(data_list)}件 保存しました！")
                    # 詳細表示
                    for item in data_list:
                        st.write(f"- {item['item']}: ¥{item['amount']}")
                    if st.button("更新"):
                        st.rerun()
            except Exception as e:
                st.error(f"読み取りエラー: {e}")

with tab3:
    st.write("スプレッドシートへのリンク:")
    st.link_button("シートを開く", SPREADSHEET_URL)
    # 最新5件を表示
    try:
        sheet = get_sheet()
        df = pd.DataFrame(sheet.get_all_records())
        st.dataframe(df.tail(5))
    except:
        st.write("まだデータがありません")
