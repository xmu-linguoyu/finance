import streamlit as st

# 2026 标准：必须是第一行
st.set_page_config(page_title="私人理财中台 Pro", layout="wide", page_icon="💰")

from google import genai 
import akshare as ak
import pandas as pd
import plotly.express as px
from google.cloud import firestore
from google.oauth2 import service_account
import json

# --- 0. 初始化 Session State ---
if "fund_code_input" not in st.session_state:
    st.session_state.fund_code_input = "003002"
if "auto_run" not in st.session_state:
    st.session_state.auto_run = False
if "favorites" not in st.session_state:
    st.session_state.favorites = []
if "current_fund_name" not in st.session_state:
    st.session_state.current_fund_name = ""

# --- 1. 数据库初始化 (AttrDict 兼容版) ---
@st.cache_resource
def init_db():
    if "firebase_config" not in st.secrets:
        st.error("❌ Secrets 中缺少 firebase_config")
        return None
    try:
        key_dict = dict(st.secrets["firebase_config"])
        if "private_key" in key_dict:
            key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
        creds = service_account.Credentials.from_service_account_info(key_dict)
        return firestore.Client(credentials=creds, project=key_dict["project_id"])
    except Exception as e:
        st.error(f"❌ 数据库连接失败: {e}")
        return None

db = init_db()
DOC_PATH = "finance_app/user_portfolio"

# --- 2. 持久化同步逻辑 ---
def sync_to_cloud():
    if db:
        try:
            # 1. 數據清洗：確保 favorites 列表裡只有純粹的 Python 數據類型
            # Firestore 不接受 Streamlit 的內部對象 (如 AttrDict)
            import json
            current_favs = list(st.session_state.favorites)
            clean_data = json.loads(json.dumps(current_favs, ensure_ascii=False))
            
            # 2. 獲取文件引用
            doc_ref = db.collection("finance_app").document("user_portfolio")
            
            # 3. 執行寫入並等待結果
            doc_ref.set({"funds": clean_data})
            
            st.toast("✅ 雲端同步成功！請刷新 Firebase 頁面查看。", icon="☁️")
            return True
        except Exception as e:
            # 這裡會顯示具體的報錯，例如：Permission Denied, Project Not Found 等
            st.error(f"❌ 寫入失敗！具體原因：{str(e)}")
            return False
    else:
        st.error("❌ 數據庫未連接 (db 為 None)，請檢查 Secrets 中的 firebase_config。")
        return False

def set_target_fund(code, name):
    st.session_state.fund_code_input = code
    st.session_state.current_fund_name = name
    st.session_state.auto_run = True

# 初始加载
if db and not st.session_state.favorites:
    try:
        res = db.document(DOC_PATH).get()
        if res.exists:
            st.session_state.favorites = res.to_dict().get("funds", [])
    except:
        pass

# --- 3. 界面布局 ---
st.title("🤖 个人理财中台 (2026 生产版)")

with st.sidebar:
    st.header("⚙️ 资产配置面板")
    api_key = st.secrets.get("GOOGLE_API_KEY") or st.text_input("Gemini API Key", type="password")
    
    st.divider()
    st.subheader("❤️ 云端追踪清单")
    if not st.session_state.favorites:
        st.caption("暂无收藏，请在审计页添加")
    else:
        for idx, fav in enumerate(st.session_state.favorites):
            with st.expander(f"{fav['name']} ({fav['code']})"):
                st.write(f"费率: 申购{fav['buy_fee']}% | 赎回{fav['sell_fee']}%")
                st.write(f"年化杂费: {fav['annual_fee']}%")
                c1, c2 = st.columns(2)
                if c1.button("一键审计", key=f"aud_{idx}"):
                    set_target_fund(fav['code'], fav['name'])
                if c2.button("移除", key=f"rm_{idx}"):
                    st.session_state.favorites.pop(idx)
                    sync_to_cloud()
                    st.rerun()

# --- 4. 功能标签页 ---
tab1, tab2 = st.tabs(["🔍 深度审计与收藏", "🧮 多基金试算矩阵"])

if not api_key:
    st.warning("⚠️ 请配置 API Key 以启用 AI 分析")
    client = None
else:
    client = genai.Client(api_key=api_key)

# ------------------------------------------
# TAB 1: 智能审计
# ------------------------------------------
with tab1:
    ci, cb = st.columns([3, 1])
    fund_code = ci.text_input("输入基金代码", key="f_code_in")
    run_audit = cb.button("🚀 开始审计", type="primary")

    if run_audit or st.session_state.auto_run:
        st.session_state.auto_run = False
        with st.spinner("正在透视底层资产..."):
            try:
                df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="累计净值走势")
                df = df[['净值日期', '累计净值']].rename(columns={'净值日期': 'date', '累计净值': 'nav'})
                df['date'] = pd.to_datetime(df['date'])
                df_slice = df.tail(252) # 最近一年

                # 计算核心指标
                ret_1y = (df_slice['nav'].iloc[-1] / df_slice['nav'].iloc[0] - 1) * 100
                mdd = ((df_slice['nav'] - df_slice['nav'].cummax()) / df_slice['nav'].cummax()).min() * 100

                st.subheader(f"📊 资产透视: {fund_code}")
                col_m1, col_m2 = st.columns(2)
                col_m1.metric("近一年收益率", f"{ret_1y:.2f}%")
                col_m2.metric("最大历史回撤", f"{mdd:.2f}%")

                # 2026 API 修复：使用 width='stretch'
                fig = px.line(df_slice, x='date', y='nav', title="累计净值增长曲线")
                st.plotly_chart(fig, width='stretch')

                # 持久化表单
                with st.expander("📌 录入个性化费率并保存"):
                    with st.form("save_form"):
                        f_name = st.text_input("备注名称", value=fund_code)
                        c1, c2, c3 = st.columns(3)
                        b_fee = c1.number_input("申购费 %", 0.0, 5.0, 0.0, step=0.01)
                        s_fee = c2.number_input("赎回费 %", 0.0, 5.0, 0.0, step=0.01)
                        a_fee = c3.number_input("年化杂费/汇损 %", 0.0, 5.0, 0.1, step=0.01)
                        if st.form_submit_button("💾 存入云端"):
                            new_fav = {"code": fund_code, "name": f_name, "buy_fee": b_fee, "sell_fee": s_fee, "annual_fee": a_fee}
                            st.session_state.favorites = [f for f in st.session_state.favorites if f['code'] != fund_code]
                            st.session_state.favorites.append(new_fav)
                            sync_to_cloud()
                
                if client:
                    st.divider()
                    st.write("🤖 AI 深度解析：")
                    try:
                        prompt = f"分析基金{fund_code}，年化{ret_1y:.2f}%，回撤{mdd:.2f}%。用户追求稳健，10万本金，给一句建议。"
                        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
                        st.info(response.text)
                    except Exception as e:
                        if "429" in str(e):
                            st.warning("⚠️ AI 顾问由于配额限制暂时下班了（429 错误）。")
                            st.caption("底层的 Python 审计数据是准确的，你可以先手动进行保存或试算。请 1 分钟后再试。")
                        else:
                            st.error(f"AI 调用出错: {e}")

            except Exception as e:
                st.error(f"审计中断: {e}")

    st.divider()
    st.subheader("🛠️ Firebase 強制診斷工具")
    col_diag1, col_diag2 = st.columns(2)

    if col_diag1.button("🔥 測試：強制寫入簡單數據"):
        if db:
            try:
                # 排除所有複雜結構，只寫入一個字串
                doc_ref = db.collection("finance_app").document("user_portfolio")
                doc_ref.set({"test_mode": "active", "timestamp": str(pd.Timestamp.now())}, merge=True)
                st.success("✅ 簡單數據寫入成功！請立刻查看 Firebase 後台。")
            except Exception as e:
                st.error(f"❌ 強制寫入失敗：{str(e)}")
        else:
            st.error("❌ 數據庫對象 (db) 為空，請檢查 Secrets。")
    
    if col_diag2.button("📋 檢查本地數據內容"):
        st.write("目前收藏夾內容：", st.session_state.favorites)
        st.write("數據類型：", type(st.session_state.favorites))

# ------------------------------------------
# TAB 2: 多基金试算矩阵 (核心算法升级)
# ------------------------------------------
with tab2:
    st.subheader("📊 10万本金：全家桶收益矩阵")
    if not st.session_state.favorites:
        st.info("尚未在云端收藏任何基金标的。")
    else:
        # 输入区
        c_p, c_d = st.columns(2)
        principal = c_p.number_input("统一本金 (元)", value=100000)
        days = c_d.number_input("预期持有周期 (天)", value=30, min_value=1)

        st.divider()
        
        comparison_list = []
        for fund in st.session_state.favorites:
            # 实时收益抓取（模拟逻辑，建议生产中加入缓存）
            try:
                # 假设实时年化为 3.0%，实际可从 df_slice 计算得出
                real_annual_yield = 3.0 
                
                # --- 收益与费率模型 ---
                # 理论收益 = 本金 * 年化 * (天数/365)
                gross_profit = principal * (real_annual_yield / 100) * (days / 365)
                
                # 一次性成本 (申购费 + 赎回费)
                fixed_cost = principal * (fund['buy_fee'] + fund['sell_fee']) / 100
                
                # 时间成本 (年化杂费 * 天数)
                time_cost = principal * (fund['annual_fee'] / 100) * (days / 365)
                
                # 实际总收益
                net_profit = gross_profit - fixed_cost - time_cost
                
                # 每月预期收益 (按30天折算)
                monthly_expected = net_profit / (days / 30)
                
                comparison_list.append({
                    "基金标的": fund['name'],
                    "代码": fund['code'],
                    "投资期净收益": round(net_profit, 2),
                    "每个月份预期": round(monthly_expected, 2),
                    "实际折算年化": f"{((net_profit/principal)*(365/days)*100):.2f}%"
                })
            except:
                continue

        if comparison_list:
            df_compare = pd.DataFrame(comparison_list)
            # 2026 API 修复：使用 width='stretch'
            st.dataframe(df_compare, width='stretch')
            
            # 可视化对比
            fig_bar = px.bar(
                df_compare, 
                x="基金标的", 
                y="投资期净收益", 
                color="投资期净收益",
                text="每个月份预期",
                title=f"投入 {principal} 元，持有 {days} 天后的到手利润对比"
            )
            st.plotly_chart(fig_bar, width='stretch')
