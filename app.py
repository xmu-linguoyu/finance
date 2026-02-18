import streamlit as st

# 2026 規範：必須是第一行命令
st.set_page_config(
    page_title="私人理財決策中台", 
    layout="wide", 
    page_icon="💰"
)

from google import genai
import akshare as ak
import pandas as pd
import plotly.express as px
from google.cloud import firestore
from google.oauth2 import service_account
import json

# --- 0. 數據庫初始化 (強化版) ---
@st.cache_resource
def init_db():
    if "firebase_config" not in st.secrets:
        st.error("❌ 請在 Secrets 中配置 firebase_config")
        return None
    try:
        # 自動處理 AttrDict 轉換與私鑰換行符
        key_dict = dict(st.secrets["firebase_config"])
        if "private_key" in key_dict:
            key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
        creds = service_account.Credentials.from_service_account_info(key_dict)
        return firestore.Client(credentials=creds, project=key_dict["project_id"])
    except Exception as e:
        st.error(f"❌ 數據庫初始化失敗: {e}")
        return None

db = init_db()
DOC_PATH = "finance_app/user_portfolio"

# --- 1. 持久化核心邏輯 ---
def sync_to_cloud():
    """清洗數據並強制同步到 Firebase"""
    if db:
        try:
            # 關鍵步驟：將 session_state 數據轉化為純 JSON 格式，排除 AttrDict
            raw_favs = list(st.session_state.favorites)
            clean_list = json.loads(json.dumps(raw_favs, ensure_ascii=False))
            
            # 寫入指定的文檔路徑
            db.document(DOC_PATH).set({
                "funds": clean_list, 
                "last_sync": str(pd.Timestamp.now())
            }, merge=True)
            st.toast("✅ 雲端同步完成", icon="☁️")
        except Exception as e:
            st.error(f"❌ 雲端同步失敗: {e}")

def load_from_cloud():
    """啟動時自動拉取雲端數據"""
    if db and "initialized" not in st.session_state:
        try:
            res = db.document(DOC_PATH).get()
            if res.exists:
                st.session_state.favorites = res.to_dict().get("funds", [])
            st.session_state.initialized = True
        except:
            st.session_state.favorites = []

# --- 2. 狀態管理 ---
if "favorites" not in st.session_state:
    st.session_state.favorites = []
if "fund_code_input" not in st.session_state:
    st.session_state.fund_code_input = "003002"
if "auto_run" not in st.session_state:
    st.session_state.auto_run = False

load_from_cloud()

# --- 3. 界面布局 ---
st.title("🤖 穩健投資決策系統")

with st.sidebar:
    st.header("⚙️ 系統配置")
    api_key = st.secrets.get("GOOGLE_API_KEY") or st.text_input("Gemini API Key", type="password")
    
    st.divider()
    st.subheader("❤️ 雲端收藏清單")
    if not st.session_state.favorites:
        st.caption("目前無收藏")
    else:
        for idx, fav in enumerate(st.session_state.favorites):
            with st.expander(f"{fav['name']} ({fav['code']})"):
                st.write(f"費率合計: {fav['buy_fee'] + fav['sell_fee'] + fav['annual_fee']}%")
                c1, c2 = st.columns(2)
                if c1.button("審計", key=f"aud_{idx}"):
                    st.session_state.fund_code_input = fav['code']
                    st.session_state.auto_run = True
                    st.rerun()
                if c2.button("移除", key=f"rm_{idx}"):
                    st.session_state.favorites.pop(idx)
                    sync_to_cloud()
                    st.rerun()

# 功能分頁
tab1, tab2 = st.tabs(["🔍 智能審計與收藏", "🧮 10萬本金收益矩陣"])

if not api_key:
    st.warning("⚠️ 請配置 API Key 以啟用 AI 解析")
    client = None
else:
    client = genai.Client(api_key=api_key)

# ------------------------------------------
# TAB 1: 智能審計 (核心寫入位置)
# ------------------------------------------
with tab1:
    ci, cb = st.columns([3, 1])
    fund_code = ci.text_input("輸入基金代碼", key="f_input", value=st.session_state.fund_code_input)
    run_audit = cb.button("🚀 開始審計", type="primary")

    if run_audit or st.session_state.auto_run:
        st.session_state.auto_run = False
        with st.spinner("抓取實時數據中..."):
            try:
                # 獲取歷史淨值 (AkShare)
                df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="累積淨值走勢")
                df = df[['淨值日期', '累積淨值']].rename(columns={'淨值日期': 'date', '累積淨值': 'nav'})
                df['date'] = pd.to_datetime(df['date'])
                df_1y = df.tail(252)

                # 計算關鍵指標
                ret_1y = (df_1y['nav'].iloc[-1] / df_1y['nav'].iloc[0] - 1) * 100
                mdd = ((df_1y['nav'] - df_1y['nav'].cummax()) / df_1y['nav'].cummax()).min() * 100

                st.subheader(f"📊 標的審計: {fund_code}")
                col1, col2 = st.columns(2)
                col1.metric("近一年回報率", f"{ret_1y:.2f}%")
                col2.metric("最大回撤", f"{mdd:.2f}%")
                
                st.plotly_chart(px.line(df_1y, x='date', y='nav'), width='stretch')

                # --- 核心寫入表單 ---
                st.divider()
                st.subheader("💾 設置費率並存入 Firebase")
                # 必須使用 st.form 配合 form_submit_button
                with st.form("save_fund_form"):
                    f_name = st.text_input("備註名稱", value=fund_code)
                    c1, c2, c3 = st.columns(3)
                    # 針對 10 萬本金和台胞證背景，精確錄入費率
                    b_fee = c1.number_input("申購費率 %", 0.0, 5.0, 0.0, step=0.01)
                    s_fee = c2.number_input("贖回費率 %", 0.0, 5.0, 0.0, step=0.01)
                    a_fee = c3.number_input("年化雜費 % (含匯損預留)", 0.0, 5.0, 0.1, step=0.01)
                    
                    submit_save = st.form_submit_button("確認同步至雲端", type="primary")
                    
                    if submit_save:
                        # 構建數據條目
                        new_data = {
                            "code": fund_code, "name": f_name,
                            "buy_fee": float(b_fee), "sell_fee": float(s_fee), 
                            "annual_fee": float(a_fee)
                        }
                        # 更新本地列表 (去重)
                        st.session_state.favorites = [f for f in st.session_state.favorites if f['code'] != fund_code]
                        st.session_state.favorites.append(new_data)
                        
                        # 觸發寫入
                        sync_to_cloud()
                
                # AI 分析
                if client:
                    try:
                        st.divider()
                        st.write("🤖 AI 投資建議：")
                        prompt = f"分析基金{fund_code}，收益率{ret_1y:.2f}%，回撤{mdd:.2f}%。針對台胞證持有者，給出穩健投資建議。"
                        res = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
                        st.info(res.text)
                    except: pass

            except Exception as e:
                st.error(f"審計失敗: {e}")

# ------------------------------------------
# TAB 2: 收益對比矩陣
# ------------------------------------------
with tab2:
    st.subheader("📊 多標的試算對比 (10萬本金基準)")
    if not st.session_state.favorites:
        st.info("請先收藏基金。")
    else:
        cp, cd = st.columns(2)
        p_val = cp.number_input("試算本金 (元)", value=100000)
        d_val = cd.number_input("持有周期 (天)", value=30)

        results = []
        for f in st.session_state.favorites:
            # 簡化收益計算邏輯
            mock_annual = 3.2 
            gross = p_val * (mock_annual / 100) * (d_val / 365)
            # 費用損耗計算
            one_time_cost = p_val * (f['buy_fee'] + f['sell_fee']) / 100
            holding_cost = p_val * (f['annual_fee'] / 100) * (d_val / 365)
            net_profit = gross - one_time_cost - holding_cost
            
            results.append({
                "標的": f['name'],
                "投資期淨利潤": round(net_profit, 2),
                "月均預期": round(net_profit / (d_val/30), 2),
                "實際折算年化": f"{(net_profit/p_val)*(365/d_val)*100:.2f}%"
            })
        
        st.table(pd.DataFrame(results))
