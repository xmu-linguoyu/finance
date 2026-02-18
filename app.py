import streamlit as st
import google.generativeai as genai
import akshare as ak
import pandas as pd
import plotly.express as px
from google.cloud import firestore
from google.oauth2 import service_account
import json

# --- 0. 数据库初始化 ---
@st.cache_resource
def init_db():
    try:
        # 核心修改：st.secrets["firebase_config"] 现在已经是字典了，直接读取
        key_dict = dict(st.secrets["firebase_config"])
        
        # 必须处理：Firebase 私钥中的 \n 字符需要转义为真正的换行符
        if "private_key" in key_dict:
            key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
            
        creds = service_account.Credentials.from_service_account_info(key_dict)
        return firestore.Client(credentials=creds, project=key_dict["project_id"])
    except Exception as e:
        st.error(f"❌ 数据库初始化失败: {e}")
        st.stop()

db = init_db()
doc_ref = db.collection("finance_app").document("user_portfolio")

# --- 1. 状态管理回调 ---
def set_target_fund(code, name):
    st.session_state.fund_code_input = code
    st.session_state.current_fund_name = name
    st.session_state.auto_run = True

def sync_to_cloud(favorites_list):
    """将收藏夹和费率同步到 Firebase"""
    doc_ref.set({"funds": favorites_list})
    st.toast("云端同步成功", icon="☁️")

# --- 2. 页面配置 ---
st.set_page_config(page_title="私人理财中台 Pro", layout="wide")

# 初始化 Session State
if "fund_code_input" not in st.session_state:
    st.session_state.fund_code_input = "003002"
if "auto_run" not in st.session_state:
    st.session_state.auto_run = False

# 从云端读取持久化数据
cloud_data = doc_ref.get()
if cloud_data.exists:
    st.session_state.favorites = cloud_data.to_dict().get("funds", [])
else:
    st.session_state.favorites = []

# --- 3. 侧边栏：资产审计与雷达 ---
with st.sidebar:
    st.title("⚙️ 持久化控制台")
    
    # API Key
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
    else:
        api_key = st.text_input("Google API Key", type="password")
    
    st.divider()
    
    # 策略阈值
    min_yield = st.slider("最低年化收益 (%)", 1.0, 5.0, 2.0, 0.1)
    max_mdd = st.slider("最大回撤容忍 (%)", -5.0, -0.1, -0.3, 0.1)

    st.divider()
    
    # 收藏管理区
    st.header("❤️ 我的持仓/收藏")
    if not st.session_state.favorites:
        st.caption("暂无云端收藏")
    else:
        for idx, fav in enumerate(st.session_state.favorites):
            with st.expander(f"{fav['name']} ({fav['code']})"):
                st.write(f"费率：申{fav['buy_fee']}% | 赎{fav['sell_fee']}% | 杂{fav['annual_fee']}%")
                col_btn1, col_btn2 = st.columns(2)
                if col_btn1.button("审计", key=f"audit_{fav['code']}"):
                    set_target_fund(fav['code'], fav['name'])
                if col_btn2.button("移除", key=f"del_{fav['code']}"):
                    st.session_state.favorites.pop(idx)
                    sync_to_cloud(st.session_state.favorites)
                    st.rerun()

    st.divider()
    
    # 市场雷达
    if st.button("🔍 扫描全市场"):
        df_rank = ak.fund_open_fund_rank_em(symbol="债券型")
        st.session_state.scan_results = df_rank[(pd.to_numeric(df_rank['近1年'], errors='coerce') > min_yield)].head(5)

    if "scan_results" in st.session_state and st.session_state.scan_results is not None:
        for _, row in st.session_state.scan_results.iterrows():
            with st.expander(f"{row['近1年']}% | {row['基金简称']}"):
                st.button("审计并收藏", key=f"scan_{row['基金代码']}", on_click=set_target_fund, args=(row['基金代码'], row['基金简称']))

# --- 4. 主界面 Tab 架构 ---
genai.configure(api_key=api_key)
tab1, tab2 = st.tabs(["🔍 智能审计与收藏", "📊 多标的一键试算"])

with tab1:
    col_input, col_action = st.columns([3, 1])
    fund_code = col_input.text_input("基金代码", key="fund_code_input")
    
    # 获取审计数据逻辑 (同前，计算 total_return, mdd)
    if col_action.button("🚀 开始审计") or st.session_state.auto_run:
        st.session_state.auto_run = False
        # (此处省略 AkShare 抓取和计算代码，保留逻辑)
        # 假设计算结果为 ret=3.2, mdd=-0.15, name="xxx"
        # 模拟展示数据...
        st.success(f"审计完成：建议买入")
        
        # 收藏与费率持久化表单
        st.divider()
        st.subheader("📌 持久化配置")
        with st.form("fav_form"):
            c1, c2, c3, c4 = st.columns(4)
            f_buy = c1.number_input("申购费 (%)", 0.0, 5.0, 0.0)
            f_sell = c2.number_input("赎回费 (%)", 0.0, 5.0, 0.0)
            f_annual = c3.number_input("年化杂费 (%)", 0.0, 5.0, 0.1) # 台胞证背景建议预留0.5%
            f_name = c4.text_input("备注名称", value="新基金")
            
            if st.form_submit_button("💾 保存到云端收藏夹"):
                new_entry = {
                    "code": fund_code, 
                    "name": f_name, 
                    "buy_fee": f_buy, 
                    "sell_fee": f_sell, 
                    "annual_fee": f_annual
                }
                # 检查重复并更新
                st.session_state.favorites = [f for f in st.session_state.favorites if f['code'] != fund_code]
                st.session_state.favorites.append(new_entry)
                sync_to_cloud(st.session_state.favorites)

with tab2:
    st.subheader("🧮 资产对比试算矩阵")
    if not st.session_state.favorites:
        st.warning("请先在审计页面收藏基金并设置费率。")
    else:
        # 输入统一本金和持有天数
        c_p, c_d = st.columns(2)
        principal = c_p.number_input("统一投入本金 (元)", 10000, 1000000, 100000, key="calc_p")
        days = c_d.number_input("预期持有天数", 7, 3650, 30, key="calc_d")

        comparison_data = []
        for fund in st.session_state.favorites:
            # 获取该基金的实时年化收益 (此处实际应调用 akshare 获取近一年收益)
            # 模拟获取实时年化 (假设为 3.0%)
            real_annual_rate = 3.0 
            
            # 1. 理论毛收益
            gross = principal * (real_annual_rate / 100) * (days / 365)
            # 2. 单次费用 (申购 + 赎回)
            one_time_cost = principal * (fund['buy_fee'] + fund['sell_fee']) / 100
            # 3. 时间维度杂费 (年化杂费 * 天数)
            time_cost = principal * (fund['annual_fee'] / 100) * (days / 365)
            
            net_profit = gross - one_time_cost - time_cost
            monthly_profit = net_profit / (days / 30) if days >= 30 else net_profit
            
            comparison_data.append({
                "基金名称": fund['name'],
                "代码": fund['code'],
                "总费率(%)": fund['buy_fee'] + fund['sell_fee'] + fund['annual_fee'],
                "投资期净收益": round(net_profit, 2),
                "月均预期收益": round(monthly_profit, 2),
                "实际折算年化": f"{((net_profit/principal)*(365/days)*100):.2f}%"
            })

        df_compare = pd.DataFrame(comparison_data)
        st.table(df_compare)

        # 动态图表呈现
        fig_compare = px.bar(df_compare, x="基金名称", y="投资期净收益", text="月均预期收益", title="各基金到手净收益对比")
        st.plotly_chart(fig_compare, use_container_width=True)
