import streamlit as st

# 2026 规范：必须是第一行命令
st.set_page_config(
    page_title="私人理财决策中台", 
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

# --- 0. 数据库初始化 (强化版) ---
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

# --- 1. 持久化核心逻辑 ---
def sync_to_cloud():
    """清洗数据并强制同步到 Firebase"""
    if db:
        try:
            # 关键步骤：将 session_state 数据转化为纯 JSON 格式，排除 AttrDict
            raw_favs = list(st.session_state.favorites)
            clean_list = json.loads(json.dumps(raw_favs, ensure_ascii=False))
            
            # 写入指定的文档路径
            db.document(DOC_PATH).set({
                "funds": clean_list, 
                "last_sync": str(pd.Timestamp.now())
            }, merge=True)
            st.toast("✅ 云端同步完成", icon="☁️")
        except Exception as e:
            st.error(f"❌ 云端同步失败: {e}")

def load_from_cloud():
    """启动时自动拉取云端数据"""
    if db and "initialized" not in st.session_state:
        try:
            res = db.document(DOC_PATH).get()
            if res.exists:
                st.session_state.favorites = res.to_dict().get("funds", [])
            st.session_state.initialized = True
        except:
            st.session_state.favorites = []

# --- 2. 状态管理 ---
if "favorites" not in st.session_state:
    st.session_state.favorites = []
if "fund_code_input" not in st.session_state:
    st.session_state.fund_code_input = "003002"
if "auto_run" not in st.session_state:
    st.session_state.auto_run = False
if "audit_cache" not in st.session_state:
    st.session_state.audit_cache = None

load_from_cloud()

# --- 3. 界面布局 ---
st.title("🤖 稳健投资决策系统")

with st.sidebar:
    st.header("⚙️ 系统配置")
    api_key = st.secrets.get("GOOGLE_API_KEY") or st.text_input("Gemini API Key", type="password")
    
    st.divider()
    st.subheader("❤️ 云端收藏清单")
    if not st.session_state.favorites:
        st.caption("目前无收藏")
    else:
        for idx, fav in enumerate(st.session_state.favorites):
            with st.expander(f"{fav['name']} ({fav['code']})"):
                st.write(f"费率合计: {fav['buy_fee'] + fav['sell_fee'] + fav['annual_fee']}%")
                c1, c2 = st.columns(2)
                if c1.button("审计", key=f"aud_{idx}"):
                    st.session_state.fund_code_input = fav['code']
                    st.session_state.auto_run = True
                    st.rerun()
                if c2.button("移除", key=f"rm_{idx}"):
                    st.session_state.favorites.pop(idx)
                    sync_to_cloud()
                    st.rerun()

# 功能分页
tab1, tab2 = st.tabs(["🔍 智能审计与收藏", "🧮 10万本金收益矩阵"])

if not api_key:
    st.warning("⚠️ 请配置 API Key 以启用 AI 解析")
    client = None
else:
    client = genai.Client(api_key=api_key)

# ------------------------------------------
# TAB 1: 智能审计 (核心写入位置)
# ------------------------------------------
with tab1:
    ci, cb = st.columns([3, 1])
    fund_code = ci.text_input("输入基金代码", key="f_input", value=st.session_state.fund_code_input)
    run_audit = cb.button("🚀 开始审计", type="primary")

    # 清除缓存：若用户切换了基金代码
    if st.session_state.audit_cache and st.session_state.audit_cache.get("code") != fund_code:
        st.session_state.audit_cache = None

    if run_audit or st.session_state.auto_run:
        st.session_state.auto_run = False
        with st.spinner("抓取实时数据中..."):
            try:
                # 获取历史净值 (AkShare)
                df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="累计净值走势")
                df = df[['净值日期', '累计净值']].rename(columns={'净值日期': 'date', '累计净值': 'nav'})
                df['date'] = pd.to_datetime(df['date'])
                df_1y = df.tail(252)

                # 计算关键指标
                ret_1y = (df_1y['nav'].iloc[-1] / df_1y['nav'].iloc[0] - 1) * 100
                mdd = ((df_1y['nav'] - df_1y['nav'].cummax()) / df_1y['nav'].cummax()).min() * 100

                # 缓存审计结果，确保表单提交后页面重跑仍能渲染
                st.session_state.audit_cache = {
                    "code": fund_code,
                    "df_1y": df_1y,
                    "ret_1y": ret_1y,
                    "mdd": mdd,
                }
            except Exception as e:
                st.error(f"审计失败: {e}")

    # 从缓存渲染审计结果与写入表单（解决表单提交后重跑时条件块不执行的问题）
    if st.session_state.audit_cache:
        cache = st.session_state.audit_cache
        audited_code = cache["code"]
        df_1y = cache["df_1y"]
        ret_1y = cache["ret_1y"]
        mdd = cache["mdd"]

        st.subheader(f"📊 标的审计: {audited_code}")
        col1, col2 = st.columns(2)
        col1.metric("近一年回报率", f"{ret_1y:.2f}%")
        col2.metric("最大回撤", f"{mdd:.2f}%")

        st.plotly_chart(px.line(df_1y, x='date', y='nav'), width='stretch')

        # --- 核心写入表单 ---
        st.divider()
        st.subheader("💾 设置费率并存入 Firebase")
        # 必须使用 st.form 配合 form_submit_button
        with st.form("save_fund_form"):
            f_name = st.text_input("备注名称", value=audited_code)
            c1, c2, c3 = st.columns(3)
            # 针对 10 万本金和台胞证背景，精确录入费率
            b_fee = c1.number_input("申购费率 %", 0.0, 5.0, 0.0, step=0.01)
            s_fee = c2.number_input("赎回费率 %", 0.0, 5.0, 0.0, step=0.01)
            a_fee = c3.number_input("年化杂费 % (含汇损预留)", 0.0, 5.0, 0.1, step=0.01)

            submit_save = st.form_submit_button("确认同步至云端", type="primary")

            if submit_save:
                # 构建数据条目
                new_data = {
                    "code": audited_code, "name": f_name,
                    "buy_fee": float(b_fee), "sell_fee": float(s_fee),
                    "annual_fee": float(a_fee)
                }
                # 更新本地列表 (去重)
                st.session_state.favorites = [f for f in st.session_state.favorites if f['code'] != audited_code]
                st.session_state.favorites.append(new_data)

                # 触发写入
                sync_to_cloud()

        # AI 分析
        if client:
            try:
                st.divider()
                st.write("🤖 AI 投资建议：")
                prompt = f"分析基金{audited_code}，收益率{ret_1y:.2f}%，回撤{mdd:.2f}%。针对台胞证持有者，给出稳健投资建议。"
                res = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
                st.info(res.text)
            except Exception: pass

# ------------------------------------------
# TAB 2: 收益对比矩阵
# ------------------------------------------
with tab2:
    st.subheader("📊 多标的试算对比 (10万本金基准)")
    if not st.session_state.favorites:
        st.info("请先收藏基金。")
    else:
        cp, cd = st.columns(2)
        p_val = cp.number_input("试算本金 (元)", value=100000)
        d_val = cd.number_input("持有周期 (天)", value=30)

        results = []
        for f in st.session_state.favorites:
            # 简化收益计算逻辑
            mock_annual = 3.2 
            gross = p_val * (mock_annual / 100) * (d_val / 365)
            # 费用损耗计算
            one_time_cost = p_val * (f['buy_fee'] + f['sell_fee']) / 100
            holding_cost = p_val * (f['annual_fee'] / 100) * (d_val / 365)
            net_profit = gross - one_time_cost - holding_cost
            
            results.append({
                "标的": f['name'],
                "投资期净利润": round(net_profit, 2),
                "月均预期": round(net_profit / (d_val/30), 2),
                "实际折算年化": f"{(net_profit/p_val)*(365/d_val)*100:.2f}%"
            })
        
        st.table(pd.DataFrame(results))
