import streamlit as st

# 必须是第一行 Streamlit 命令，防止白屏
st.set_page_config(page_title="私人理财中台 Pro", layout="wide", page_icon="💰")

from google import genai  # 升级到新版 SDK
import akshare as ak
import pandas as pd
import plotly.express as px
from google.cloud import firestore
from google.oauth2 import service_account
import json

# --- 0. 初始化 Session State (必须在逻辑开始前) ---
if "fund_code_input" not in st.session_state:
    st.session_state.fund_code_input = "003002"
if "auto_run" not in st.session_state:
    st.session_state.auto_run = False
if "favorites" not in st.session_state:
    st.session_state.favorites = []
if "current_fund_name" not in st.session_state:
    st.session_state.current_fund_name = ""

# --- 1. 数据库初始化 (鲁棒模式) ---
@st.cache_resource
def init_db():
    if "firebase_config" not in st.secrets:
        st.error("❌ Secrets 中缺少 firebase_config 配置")
        return None
    try:
        # Streamlit 自动解析 TOML 为字典
        key_dict = dict(st.secrets["firebase_config"])
        if "private_key" in key_dict:
            key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
        
        creds = service_account.Credentials.from_service_account_info(key_dict)
        return firestore.Client(credentials=creds, project=key_dict["project_id"])
    except Exception as e:
        st.error(f"❌ 数据库初始化失败: {e}")
        return None

db = init_db()
DOC_PATH = "finance_app/user_portfolio"

# --- 2. 核心函数 ---
def sync_to_cloud():
    """强制同步到 Firebase"""
    if db:
        try:
            # 过滤掉无法序列化的对象，确保数据干净
            clean_favs = json.loads(json.dumps(st.session_state.favorites))
            db.document(DOC_PATH).set({"funds": clean_favs})
            st.toast("✅ 数据已同步至云端", icon="☁️")
        except Exception as e:
            st.error(f"❌ 写入云端失败: {e}")
    else:
        st.error("⚠️ 数据库未连接，数据仅保存在本地内存")

def set_target_fund(code, name):
    st.session_state.fund_code_input = code
    st.session_state.current_fund_name = name
    st.session_state.auto_run = True

# 初始加载云端数据
if db and not st.session_state.favorites:
    try:
        res = db.document(DOC_PATH).get()
        if res.exists:
            st.session_state.favorites = res.to_dict().get("funds", [])
    except:
        pass

# --- 3. 界面逻辑 ---
st.title("🤖 个人理财中台 (2026 稳定版)")

# 侧边栏
with st.sidebar:
    st.header("⚙️ 控制台")
    api_key = st.secrets.get("GOOGLE_API_KEY") or st.text_input("API Key", type="password")
    
    st.divider()
    st.subheader("❤️ 我的收藏")
    if not st.session_state.favorites:
        st.caption("暂无收藏")
    else:
        for idx, fav in enumerate(st.session_state.favorites):
            with st.expander(f"{fav['name']} ({fav['code']})"):
                st.write(f"费率: 申{fav['buy_fee']}% | 赎{fav['sell_fee']}%")
                c1, c2 = st.columns(2)
                if c1.button("审计", key=f"audit_idx_{idx}"):
                    set_target_fund(fav['code'], fav['name'])
                if c2.button("移除", key=f"del_idx_{idx}"):
                    st.session_state.favorites.pop(idx)
                    sync_to_cloud()
                    st.rerun()

# 主界面 Tab
if not api_key:
    st.info("💡 请先在侧边栏配置 Google API Key 以开启 AI 分析功能")
    # 哪怕没有 API Key，我们也让程序跑下去，只禁用 AI 部分，防止白屏
    ai_client = None
else:
    ai_client = genai.Client(api_key=api_key)

tab1, tab2 = st.tabs(["🔍 智能审计", "🧮 收益试算矩阵"])

with tab1:
    ci, cb = st.columns([3, 1])
    fund_code = ci.text_input("基金代码", key="f_input")
    start_btn = cb.button("🚀 开始审计", type="primary")

    if start_btn or st.session_state.auto_run:
        st.session_state.auto_run = False
        with st.spinner("正在穿透数据..."):
            try:
                # 获取数据
                df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="累计净值走势")
                df = df[['净值日期', '累计净值']].rename(columns={'净值日期': 'date', '累计净值': 'nav'})
                df['date'] = pd.to_datetime(df['date'])
                df_1y = df.tail(252) # 约一年交易日

                # 计算指标
                total_ret = (df_1y['nav'].iloc[-1] / df_1y['nav'].iloc[0] - 1) * 100
                mdd = ((df_1y['nav'] - df_1y['nav'].cummax()) / df_1y['nav'].cummax()).min() * 100

                # 界面展示
                st.subheader(f"📊 审计报告: {fund_code}")
                m1, m2 = st.columns(2)
                m1.metric("近一年收益", f"{total_ret:.2f}%")
                m2.metric("最大回撤", f"{mdd:.2f}%")
                
                st.plotly_chart(px.line(df_1y, x='date', y='nav'), use_container_width=True)

                # 收藏表单
                with st.expander("📌 保存至云端收藏夹"):
                    with st.form("save_form"):
                        f_name = st.text_input("基金备注", value=fund_code)
                        f_buy = st.number_input("申购费 %", 0.0, 5.0, 0.0)
                        f_sell = st.number_input("赎回费 %", 0.0, 5.0, 0.0)
                        f_ann = st.number_input("年化杂费 %", 0.0, 5.0, 0.1)
                        if st.form_submit_button("💾 确认收藏"):
                            new_data = {"code": fund_code, "name": f_name, "buy_fee": f_buy, "sell_fee": f_sell, "annual_fee": f_ann}
                            st.session_state.favorites = [f for f in st.session_state.favorites if f['code'] != fund_code]
                            st.session_state.favorites.append(new_data)
                            sync_to_cloud()
                
                # AI 分析
                if ai_client:
                    st.divider()
                    st.write("🤖 AI 深度解析：")
                    res = ai_client.models.generate_content(
                        model="gemini-2.0-flash",
                        contents=f"分析基金{fund_code}，收益率{total_ret:.2f}%，回撤{mdd:.2f}%。针对台胞证持有者，追求稳健，给出50字建议。"
                    )
                    st.info(res.text)

            except Exception as e:
                st.error(f"分析失败: {e}")

with tab2:
    st.subheader("📊 10万本金同场对比")
    if not st.session_state.favorites:
        st.write("收藏夹为空")
    else:
        df_comp = pd.DataFrame(st.session_state.favorites)
        # 这里可以加入你的计算逻辑矩阵...
        st.table(df_comp)
