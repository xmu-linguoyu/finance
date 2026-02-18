import streamlit as st

# 2026 规范：必须作为第一行 Streamlit 命令
st.set_page_config(
    page_title="私人理财中台 Pro", 
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

# --- 0. 数据库初始化 (AttrDict 兼容版) ---
@st.cache_resource
def init_db():
    if "firebase_config" not in st.secrets:
        st.error("❌ 请在 Secrets 中配置 firebase_config")
        return None
    try:
        # 自动处理 AttrDict 转换与私钥换行符
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

# --- 1. 核心持久化逻辑 ---
def sync_to_cloud():
    """将收藏夹同步至 Firebase，处理数据清洗"""
    if db:
        try:
            # 确保序列化为纯 JSON，解决 Firestore 无法识别 AttrDict 的问题
            clean_list = json.loads(json.dumps(st.session_state.favorites, ensure_ascii=False))
            db.document(DOC_PATH).set({"funds": clean_list, "last_sync": str(pd.Timestamp.now())}, merge=True)
            st.toast("✅ 云端同步成功", icon="☁️")
        except Exception as e:
            st.error(f"❌ 同步失败: {e}")

def load_from_cloud():
    """启动时自动恢复收藏数据"""
    if db and not st.session_state.get("initialized", False):
        try:
            res = db.document(DOC_PATH).get()
            if res.exists:
                st.session_state.favorites = res.to_dict().get("funds", [])
            st.session_state.initialized = True
        except:
            st.session_state.favorites = []

# --- 2. 状态初始化 ---
if "favorites" not in st.session_state:
    st.session_state.favorites = []
if "fund_code_input" not in st.session_state:
    st.session_state.fund_code_input = "003002"
if "auto_run" not in st.session_state:
    st.session_state.auto_run = False

load_from_cloud()

# --- 3. 界面布局 ---
st.title("🤖 个人理财决策系统 (2026 版)")

# 侧边栏：配置与收藏列表
with st.sidebar:
    st.header("⚙️ 配置面板")
    api_key = st.secrets.get("GOOGLE_API_KEY") or st.text_input("Gemini API Key", type="password")
    
    st.divider()
    st.subheader("❤️ 我的云端追踪")
    if not st.session_state.favorites:
        st.caption("暂无收藏，请在审计页添加")
    else:
        for idx, fav in enumerate(st.session_state.favorites):
            with st.expander(f"{fav['name']} ({fav['code']})"):
                st.write(f"费率损耗: {fav['buy_fee'] + fav['sell_fee'] + fav['annual_fee']}%")
                c1, c2 = st.columns(2)
                if c1.button("审计", key=f"aud_{idx}"):
                    st.session_state.fund_code_input = fav['code']
                    st.session_state.auto_run = True
                    st.rerun()
                if c2.button("移除", key=f"rm_{idx}"):
                    st.session_state.favorites.pop(idx)
                    sync_to_cloud()
                    st.rerun()

# 主界面 Tab
tab1, tab2 = st.tabs(["🔍 智能审计与收藏", "🧮 10万本金对比矩阵"])

if not api_key:
    st.warning("⚠️ 请在侧边栏配置 API Key 以开启 AI 顾问功能")
    client = None
else:
    client = genai.Client(api_key=api_key)

# ------------------------------------------
# TAB 1: 智能审计
# ------------------------------------------
with tab1:
    ci, cb = st.columns([3, 1])
    fund_code = ci.text_input("输入基金代码", key="f_input", value=st.session_state.fund_code_input)
    start_audit = cb.button("🚀 开始审计", type="primary")

    if start_audit or st.session_state.auto_run:
        st.session_state.auto_run = False
        with st.spinner("正在透视资产数据..."):
            try:
                # 数据抓取
                df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="累计净值走势")
                df = df[['净值日期', '累计净值']].rename(columns={'净值日期': 'date', '累计净值': 'nav'})
                df['date'] = pd.to_datetime(df['date'])
                df_slice = df.tail(252)

                # 指标计算
                ret_1y = (df_slice['nav'].iloc[-1] / df_slice['nav'].iloc[0] - 1) * 100
                mdd = ((df_slice['nav'] - df_slice['nav'].cummax()) / df_slice['nav'].cummax()).min() * 100

                st.subheader(f"📊 资产报告: {fund_code}")
                m1, m2 = st.columns(2)
                m1.metric("近一年收益率 (年化参考)", f"{ret_1y:.2f}%")
                m2.metric("最大回撤 (风险边界)", f"{mdd:.2f}%")
                
                fig = px.line(df_slice, x='date', y='nav', title="累计净值增长趋势")
                st.plotly_chart(fig, width='stretch')

                # 持久化表单
                with st.expander("💾 设置费率并保存至云端", expanded=True):
                    with st.form("save_form"):
                        f_name = st.text_input("自定义备注", value=fund_code)
                        c1, c2, c3 = st.columns(3)
                        b_fee = c1.number_input("申购费 %", 0.0, 5.0, 0.0, step=0.01)
                        s_fee = c2.number_input("赎回费 %", 0.0, 5.0, 0.0, step=0.01)
                        # 台胞证背景建议考虑跨境管理成本
                        a_fee = c3.number_input("年化杂费 %", 0.0, 5.0, 0.1, step=0.01)
                        
                        if st.form_submit_button("确认存入 Firebase"):
                            new_fav = {
                                "code": fund_code, "name": f_name, 
                                "buy_fee": b_fee, "sell_fee": s_fee, "annual_fee": a_fee
                            }
                            st.session_state.favorites = [f for f in st.session_state.favorites if f['code'] != fund_code]
                            st.session_state.favorites.append(new_fav)
                            sync_to_cloud()
                
                # AI 分析 (处理 429 错误)
                if client:
                    try:
                        st.divider()
                        st.write("🤖 AI 专家分析建议：")
                        prompt = f"分析基金{fund_code}，收益{ret_1y:.2f}%，回撤{mdd:.2f}%。用户10万本金，稳健型，一句建议。"
                        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
                        st.info(response.text)
                    except Exception as ai_e:
                        if "429" in str(ai_e):
                            st.warning("⚠️ AI 顾问配额已达上限，请稍后再试。")

            except Exception as e:
                st.error(f"审计中断: {e}")

# ------------------------------------------
# TAB 2: 多基金试算矩阵 (核心算法)
# ------------------------------------------
with tab2:
    st.subheader("🧮 资产对比试算矩阵")
    if not st.session_state.favorites:
        st.info("尚未在云端收藏任何标的。")
    else:
        # 输入区
        c_p, c_d = st.columns(2)
        p_val = c_p.number_input("统一投入本金 (元)", value=100000)
        d_val = c_d.number_input("预期持有周期 (天)", value=30, min_value=1)

        st.divider()
        results = []
        for fund in st.session_state.favorites:
            try:
                # 收益估算逻辑 (基于10万本金和持久化费率)
                mock_annual = 3.0 # 实际可动态获取
                gross = p_val * (mock_annual / 100) * (d_val / 365)
                # 固定成本与时间成本
                fix_cost = p_val * (fund['buy_fee'] + fund['sell_fee']) / 100
                time_cost = p_val * (fund['annual_fee'] / 100) * (d_val / 365)
                net_profit = gross - fix_cost - time_cost
                
                results.append({
                    "标的": fund['name'],
                    "投资期净收益": round(net_profit, 2),
                    "月均预期回报": round(net_profit / (d_val/30), 2),
                    "实际折算年化": f"{(net_profit/p_val)*(365/d_val)*100:.2f}%"
                })
            except: continue

        if results:
            df_res = pd.DataFrame(results)
            st.dataframe(df_res, width='stretch')
            
            fig_bar = px.bar(df_res, x="标的", y="投资期净收益", text="月均预期回报", 
                             title=f"{p_val}元投入 {d_val}天 后净收益对比")
            st.plotly_chart(fig_bar, width='stretch')
