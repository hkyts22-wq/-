import streamlit as st
import google.generativeai as genai
import os

st.title("🔍 APIキー & モデル診断ツール")

# 1. APIキーのチェック
st.header("1. APIキーの確認")
try:
    # Secretsからキーを取得
    api_key = st.secrets["GEMINI_API_KEY"]
    
    # キーの隠蔽表示（セキュリティのため）
    masked_key = api_key[:5] + "..." + api_key[-4:]
    st.success(f"✅ StreamlitのSecretsからキーを読み込めました: {masked_key}")
    
    # GenAIにセット
    genai.configure(api_key=api_key)

except Exception as e:
    st.error("❌ APIキーが読み込めません！")
    st.error("Streamlitの 'Secrets' 設定を確認してください。")
    st.code('GEMINI_API_KEY = "ここにキー"')
    st.stop() # ここで止める

# 2. 接続テスト & モデル一覧取得
st.header("2. Googleサーバーとの通信テスト")

if st.button("モデル一覧を取得する（ここを押す）"):
    try:
        models_list = []
        # Googleに「使えるモデル教えて」と聞く
        for m in genai.list_models():
            # "generateContent"（会話機能）が使えるモデルだけ抽出
            if 'generateContent' in m.supported_generation_methods:
                models_list.append(m.name)
        
        if models_list:
            st.success("🎉 通信成功！あなたのキーで使えるモデルは以下です：")
            st.write("この中のどれか一つをコードに書けば動きます。")
            st.json(models_list) # 一覧を表示
        else:
            st.warning("⚠️ 通信はできましたが、使えるモデルが見つかりませんでした。")
            
    except Exception as e:
        st.error("❌ Googleサーバーと通信できませんでした。")
        st.error("APIキー自体が間違っているか、有効期限切れの可能性があります。")
        st.code(str(e))
