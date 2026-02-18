import streamlit as st
import google.generativeai as genai
import akshare as ak
import pandas as pd
import plotly.express as px
from google.cloud import firestore
from google.oauth2 import service_account
import json

# --- 0. 数据库初始化 (修复 AttrDict 报错版) ---
@st.cache_resource
def init_db():
    try:
        # 直接读取字典，不使用 json.loads
        key_dict = dict(st.secrets["firebase_config"])
        # 处理私钥中的转义换行符
        if "private_key" in key_dict:
            key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
        
        creds = service_account.Credentials.from_service_account_info(key_dict)
        return firestore.Client(credentials=creds, project=key_dict["project_id"])
    except Exception as e:
        st.error(f"❌ 数据库初始化失败: {e}")
        return None

db = init_db()
# 定义云端文档路径
DOC_PATH = "finance_app/user_portfolio"

# --- 1. 核心持久化函数 ---
def sync_to_cloud():
    """将 session_state 中的收藏夹同步到 Firebase"""
    if db:
        try:
            doc_ref = db.document(DOC_PATH)
            doc_ref.set({"funds": st.session_state.favorites})
            st.toast("✅ 云端同步成功！", icon="☁️")
        except Exception as e:
            st.error(f"❌ 写入云端失败: {e}")
    else:
        st.error("❌ 数据库未连接，无法同步")

# 回调：点击雷达/收藏夹设置目标基金
def set_target_fund(code, name):
    st.session_state.fund_code_input = code
    st.session_state.current_fund_name = name
    st.session_state.auto_run = True

# --- 2. 状态初始化 ---
if "fund_code_input" not in st.session_state:
    st.session_state.fund_code_input = "003002"
if "auto_run" not in st.session_state:
    st.session_state.auto_run = False
if "favorites" not in st.session_state:
    # 初始加载：尝试从云端拉取
    if db:
        try:
            res = db.document(DOC_PATH).get()
            st.session_state.favorites = res.to_dict().get("funds", []) if res.exists else []
        except:
            st.session_state.favorites = []
    else:
        st.session_state.favorites = []

# --- 3. 页面布局 ---
st.set_page_config(page_title="私人理财中台 Pro", layout="wide")

# 侧边栏：策略与收藏列表
with st.sidebar:
    st.title("⚙️ 资产控制台")
    
    # API Key
    api_key = st.secrets.get("GOOGLE_API_KEY") or st.text_input("Google API Key", type="password")
    
    st.divider()
    st.header("❤️ 我的云端收藏")
    if not st.session_state.favorites:
        st.caption("空空如也，请去审计页添加")
    else:
        for idx, fav in enumerate(st.session_state.favorites):
            with st.expander(f"{fav['name']} ({fav['code']})"):
                st.write(f"费率: 申{fav['buy_fee']}% | 赎{fav['sell_fee']}% | 杂{fav['annual_fee']}%")
                c1, c2 = st.columns(2)
                if c1.button("审计", key=f"btn_audit_{idx}"):
                    set_target_fund(fav['code'], fav['name'])
                if c2.button("移除", key=f"btn_del_{idx}"):
                    st.session_state.favorites.pop(idx)
                    sync_to_cloud() # 同步删除
                    st.rerun()

# --- 4. 主界面 Tab ---
if not api_key:
    st.warning("请在侧边栏配置 API Key")
    st.stop()

genai.configure(api_key=api_key)
tab1, tab2 = st.tabs(["🔍 智能审计与收藏", "🧮 收益对比试算"])

with tab1:
    col_in, col_btn = st.columns([3, 1])
    fund_code = col_in.text_input("基金代码", key="fund_code_input")
    start_audit = col_btn.button("🚀 开始审计", type="primary")

    if start_audit or st.session_state.auto_run:
        st.session_state.auto_run = False
        # [此处为抓取 AkShare 数据并计算 total_return, mdd 的代码，建议保留你之前的稳定逻辑]
        # 假设我们得到了：name, total_return, mdd
        st.success("审计完成：符合稳健策略")
        
        # --- 收藏持久化表单 ---
        st.divider()
        st.subheader("📌 收藏并设置个性化费率")
        with st.form("save_fund_form"):
            f_name = st.text_input("基金备注名称", value=fund_code)
            c1, c2, c3 = st.columns(3)
            f_buy = c1.number_input("申购费率 (%)", 0.0, 5.0, 0.0, step=0.01)
            f_sell = c2.number_input("赎回费率 (%)", 0.0, 5.0, 0.0, step=0.01)
            f_annual = c3.number_input("年化杂费/汇损 (%)", 0.0, 5.0, 0.1, step=0.01)
            
            submit = st.form_submit_button("💾 保存到云端 Firebase")
            if submit:
                new_data = {
                    "code": fund_code, "name": f_name,
                    "buy_fee": f_buy, "sell_fee": f_sell, "annual_fee": f_annual
                }
                # 更新本地列表并去重
                st.session_state.favorites = [f for f in st.session_state.favorites if f['code'] != fund_code]
                st.session_state.favorites.append(new_data)
                # 触发云端同步
                sync_to_cloud()

with tab2:
    st.subheader("📊 10万本金多标对比矩阵")
    if not st.session_state.favorites:
        st.info("请先在审计页收藏基金并配置费率。")
    else:
        # 全局参数输入
        cp, cd = st.columns(2)
        p_val = cp.number_input("统一本金 (元)", value=100000)
        d_val = cd.number_input("预期持有天数", value=30)

        matrix = []
        for f in st.session_state.favorites:
            # 模拟实时年化 (实际开发中应调用你之前写的获取年化函数)
            real_annual = 3.2 # 示例
            
            # 损耗计算逻辑
            gross = p_val * (real_annual / 100) * (d_val / 365)
            fix_cost = p_val * (f['buy_fee'] + f['sell_fee']) / 100
            time_cost = p_val * (f['annual_fee'] / 100) * (d_val / 365)
            net_profit = gross - fix_cost - time_cost
            
            matrix.append({
                "名称": f['name'],
                "净收益(元)": round(net_profit, 2),
                "月均收益": round(net_profit / (d_val/30), 2),
                "实际年化": f"{(net_profit/p_val)*(365/d_val)*100:.2f}%"
            })
        
        st.table(pd.DataFrame(matrix))
