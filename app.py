import streamlit as st
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

st.title("🏥 スプレッドシート接続診断")

# 1. URLの確認
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1EqrzveseDusUHWXlXfwewDcxJ412UIA7BtLjiEydDh4/edit"
st.write(f"📝 ターゲットURL: `{SPREADSHEET_URL}`")

# 2. 認証情報のテスト
st.subheader("ステップ1: ロボットの認証")
try:
    json_str = st.secrets["GCP_JSON_STR"]
    creds_dict = json.loads(json_str, strict=False)
    
    # ロボットのメールアドレスを表示
    bot_email = creds_dict.get("client_email", "不明")
    st.success(f"✅ 認証情報の読み込み成功！\n\nロボット名: `{bot_email}`")
    
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    st.info("Googleサーバーへのログインに成功しました。")

except Exception as e:
    st.error("❌ 認証エラー：Secretsの設定が間違っています。")
    st.code(str(e))
    st.stop()

# 3. スプレッドシート発見テスト
st.subheader("ステップ2: シートの探索")
try:
    # URLからシートを探す
    spreadsheet = client.open_by_url(SPREADSHEET_URL)
    st.success(f"✅ スプレッドシート「{spreadsheet.title}」を見つけました！")
    
    # 1枚目のシートを開く
    sheet = spreadsheet.get_worksheet(0)
    st.success("✅ 1枚目のシートを開けました！")

    # 4. 書き込みテスト
    st.subheader("ステップ3: 書き込みテスト")
    try:
        sheet.append_row(["診断テスト", "接続OK", "成功", 100, "テスト成功です"])
        st.balloons()
        st.success("🎉 書き込み成功！スプレッドシートを確認してください。")
    except Exception as e:
        st.error("❌ 書き込みエラー：権限が「閲覧者」になっていませんか？")
        st.error(str(e))

except Exception as e:
    st.error("❌ シートが見つかりません (404エラー)")
    st.warning("考えられる原因：")
    st.markdown(f"""
    1. **共有設定のミス**: 
       上の「ロボット名 (`{bot_email}`)」が、スプレッドシートの「共有」に入っていますか？
       もう一度スプレッドシートの「共有」ボタンを押して確認してください。
    2. **APIが無効**: 
       Google Cloud Consoleで「Google Drive API」が有効になっていない可能性があります。
    """)
    st.code(str(e))
