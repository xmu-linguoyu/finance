import streamlit as st
import google.generativeai as genai
import akshare as ak
import pandas as pd
import plotly.express as px

# --- 页面配置 ---
st.set_page_config(
    page_title="我的私人理财顾问",
    page_icon="💰",
    layout="wide"
)

# --- 侧边栏：配置 ---
with st.sidebar:
    st.header("⚙️ 系统设置")
    # 从 Streamlit Secrets 获取 Key，或者让用户临时输入
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
    else:
        api_key = st.text_input("请输入 Google API Key", type="password")

    st.info("此应用运行在云端，不消耗本地算力。")
    st.divider()
    st.markdown("### 🎯 策略说明")
    st.markdown("- **稳健型 (R2)**")
    st.markdown("- **厌恶回撤 > 0.3%**")
    st.markdown("- **持有期 > 7天**")

# --- 核心逻辑 ---
st.title("🤖 个人理财中台 (Cloud Native)")
st.caption("Powered by Gemini 2.0 Flash & AkShare")

if not api_key:
    st.warning("请先配置 Google API Key 才能开始分析。")
    st.stop()

genai.configure(api_key=api_key)

# 输入区域
col1, col2 = st.columns([3, 1])
with col1:
    fund_code = st.text_input("输入基金代码 (例如: 003002)", "003002")
with col2:
    analyze_btn = st.button("🚀 开始云端审计", type="primary")

if analyze_btn:
    status_text = st.empty()
    status_text.info("🔄 正在连接中国基金市场数据 (AkShare)...")

    try:
        # 1. 获取数据 (AkShare)
        # 使用更稳定的接口 '单位净值走势'
        df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")

        if df is None or df.empty:
            st.error(f"❌ 找不到代码 {fund_code} 的数据，请检查是否正确。")
            st.stop()

        # 数据清洗
        df = df[['净值日期', '单位净值']].rename(columns={'净值日期': 'date', '单位净值': 'nav'})
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')

        # 截取最近一年
        one_year_ago = pd.Timestamp.now() - pd.Timedelta(days=365)
        df_1y = df[df['date'] >= one_year_ago].copy()

        if df_1y.empty:
             st.warning("⚠️ 该基金数据不足一年，分析可能不准确。")
             df_1y = df.copy() # 如果不足一年，就用所有数据

        # 2. 计算核心指标
        latest_nav = df_1y['nav'].iloc[-1]
        total_return = (df_1y['nav'].iloc[-1] / df_1y['nav'].iloc[0] - 1) * 100

        # 计算最大回撤
        roll_max = df_1y['nav'].cummax()
        drawdown = (df_1y['nav'] - roll_max) / roll_max
        mdd = drawdown.min() * 100

        # 3. 展示图表
        status_text.info("📈 正在绘制净值曲线...")

        # 关键指标卡片
        m1, m2, m3 = st.columns(3)
        m1.metric("近一年收益率", f"{total_return:.2f}%", delta_color="normal")
        m2.metric("最大回撤 (风险)", f"{mdd:.2f}%", delta_color="inverse") # 回撤越小越好
        m3.metric("最新净值", f"{latest_nav:.4f}")

        # 交互式图表 (Plotly)
        fig = px.line(df_1y, x='date', y='nav', title=f"基金 {fund_code} 净值走势")
        st.plotly_chart(fig, use_container_width=True)

        # 4. Gemini 智能分析
        status_text.info("🧠 Gemini 正在进行脱水分析...")
        st.divider()
        st.subheader("🤖 AI 决策报告")

        with st.chat_message("assistant"):
            model = genai.GenerativeModel('gemini-2.0-flash')

            prompt = f"""
            你是一个严格的理财风控官。
            分析对象: 基金代码 {fund_code}
            数据指标:
            - 近一年收益: {total_return:.2f}%
            - 最大回撤: {mdd:.2f}%

            用户画像: 台胞证持有者，追求稳健，厌恶亏损。
            决策规则: 
            1. 如果最大回撤 < -0.3%，必须提示风险，建议观望。
            2. 如果收益率 < 2.0%，建议直接存余额宝。
            3. 如果回撤小且收益尚可，建议买入。

            请输出:
            1. **决策建议** (BUY / SELL / PASS)
            2. **简短理由** (不超过3句话)
            """

            response_container = st.empty()
            full_response = ""
            # 流式输出，体验更好
            for chunk in model.generate_content(prompt, stream=True):
                full_response += chunk.text
                response_container.markdown(full_response)

        status_text.success("✅ 分析完成！")

    except Exception as e:
        st.error(f"发生系统错误: {e}")
        st.code(str(e)) # 显示报错详情方便调试
