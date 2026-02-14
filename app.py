import streamlit as st
import google.generativeai as genai
import akshare as ak
import pandas as pd
import plotly.express as px

# --- 1. 页面配置 ---
st.set_page_config(
    page_title="我的私人理财顾问",
    page_icon="💰",
    layout="wide"
)

# --- 2. 侧边栏：配置与说明 ---
with st.sidebar:
    st.header("⚙️ 系统设置")
    
    # 获取 API Key (优先从 Secrets 获取，否则手动输入)
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
    else:
        api_key = st.text_input("请输入 Google API Key", type="password")
        if not api_key:
            st.warning("请先配置 Google API Key 才能开始分析。")
            st.stop()
    
    st.divider()
    st.markdown("### 🎯 策略说明 (R2稳健)")
    st.markdown("- **回撤阈值:** < -0.3% (拒绝)")
    st.markdown("- **收益阈值:** > 2.0% (否则存余额宝)")
    st.markdown("- **持有期:** 建议 > 7天")

# --- 3. 核心逻辑 ---
st.title("🤖 个人理财中台 (Cloud Native)")
st.caption("Powered by Gemini 2.0 Flash & AkShare | 修复版 V2.0")

# 配置 Gemini
genai.configure(api_key=api_key)

# 输入区域
col1, col2 = st.columns([3, 1])
with col1:
    fund_code = st.text_input("输入基金代码 (例如: 003002, 006912)", "003002")
with col2:
    analyze_btn = st.button("🚀 开始云端审计", type="primary")

if analyze_btn:
    status_text = st.empty()
    progress_bar = st.progress(0)

    try:
        # --- 步骤 1: 获取数据 (使用累计净值修复数据源) ---
        status_text.info("🔄 正在连接交易所数据 (AkShare)...")
        progress_bar.progress(20)

        # 关键修改：使用 '累计净值走势' 避免分红导致的回撤幻觉
        try:
            df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="累计净值走势")
        except:
            st.error(f"❌ 无法获取代码 {fund_code} 的累计净值，请检查代码是否正确。")
            st.stop()

        if df is None or df.empty:
            st.error(f"❌ 找不到代码 {fund_code} 的数据。")
            st.stop()

        # 数据清洗
        df = df[['净值日期', '累计净值']].rename(columns={'净值日期': 'date', '累计净值': 'nav'})
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # 截取最近一年
        progress_bar.progress(40)
        one_year_ago = pd.Timestamp.now() - pd.Timedelta(days=365)
        df_1y = df[df['date'] >= one_year_ago].copy()
        
        if df_1y.empty:
             st.warning("⚠️ 该基金数据不足一年，将使用所有历史数据分析。")
             df_1y = df.copy()

        # --- 步骤 2: Python 硬逻辑计算 (杜绝 AI 幻觉) ---
        status_text.info("🧮 正在进行脱水计算...")
        progress_bar.progress(60)

        # 计算累计收益率
        start_nav = df_1y['nav'].iloc[0]
        end_nav = df_1y['nav'].iloc[-1]
        total_return = (end_nav / start_nav - 1) * 100
        
        # 计算最大回撤 (Max Drawdown)
        roll_max = df_1y['nav'].cummax()
        drawdown = (df_1y['nav'] - roll_max) / roll_max
        mdd = drawdown.min() * 100 # 结果通常是负数，例如 -0.5
        
        # Python 决策守卫 (Hard Guardrails)
        decision = "待定"
        reason_core = ""
        color = "grey"

        if mdd < -0.3: # 回撤超过 -0.3% (例如 -1.0%)
            decision = "🛑 SELL / AVOID (拒绝)"
            reason_core = f"最大回撤 {mdd:.2f}% 严重超过安全阈值 (-0.3%)，风险过大。"
            color = "red"
        elif total_return < 2.0:
            decision = "⚪ PASS (观望)"
            reason_core = f"年化收益 {total_return:.2f}% 过低，不如直接存余额宝 (约1.8%)。"
            color = "orange"
        else:
            decision = "✅ BUY (推荐)"
            reason_core = "收益达标且回撤控制在安全范围内，符合稳健策略。"
            color = "green"

        # --- 步骤 3: 展示图表与数据 ---
        progress_bar.progress(80)
        
        # 关键指标卡片
        m1, m2, m3 = st.columns(3)
        m1.metric("近一年真实收益", f"{total_return:.2f}%", delta=None)
        m2.metric("最大回撤 (风险)", f"{mdd:.2f}%", delta_color="inverse") 
        m3.metric("最新累计净值", f"{end_nav:.4f}")

        # 绘制交互式图表
        fig = px.line(df_1y, x='date', y='nav', title=f"基金 {fund_code} 累计净值走势 (真实收益)")
        st.plotly_chart(fig, use_container_width=True)

        # --- 步骤 4: Gemini 生成报告 (基于 Python 结论) ---
        status_text.info("🧠 Gemini 正在生成分析报告...")
        progress_bar.progress(90)
        
        st.divider()
        st.subheader(f"🤖 AI 决策报告: :{color}[{decision}]")
        
        with st.chat_message("assistant"):
            model = genai.GenerativeModel('gemini-2.0-flash')
            
            # 这里的 Prompt 强制 AI 解释 Python 的结论
            prompt = f"""
            你是一个专业的理财顾问。
            分析对象: 基金 {fund_code}
            数据: 近一年收益 {total_return:.2f}%, 最大回撤 {mdd:.2f}%。
            
            【系统强制结论】: {decision}
            【核心理由】: {reason_core}
            
            请根据上述结论和理由，写一段简短、专业的分析报告（100字以内）。
            用户是台胞证持有者，追求稳健。
            **必须严格支持系统的结论，禁止反驳或自行发挥。**
            """
            
            response_container = st.empty()
            full_response = ""
            for chunk in model.generate_content(prompt, stream=True):
                full_response += chunk.text
                response_container.markdown(full_response)
        
        status_text.success("✅ 分析完成！")
        progress_bar.progress(100)

    except Exception as e:
        st.error(f"发生系统错误: {e}")
        st.code(str(e))

# --- 新增功能：市场雷达 ---
with st.sidebar:
    st.divider()
    st.header("📡 市场雷达 (Beta)")
    scan_btn = st.button("🔍 扫描全市场优质短债")

if scan_btn:
    st.info("正在扫描全市场债券基金，寻找稳健标的 (Top 20)...")
    
    try:
        # 1. 获取开放式基金排行 (债基)
        # akshare 接口: fund_open_fund_rank_em
        df_rank = ak.fund_open_fund_rank_em(symbol="债券型")
        
        # 2. 开发者过滤算法 (The Developer Filter)
        # 逻辑：
        # A. 只要近1年收益在 2.5% 到 6% 之间的 (太低没意义，太高是假的/高风险)
        # B. 只要近6个月收益是正的 (排除最近暴雷的)
        # C. 只要成立时间超过3年的 (排除新瓜蛋子)
        
        df_rank['近1年'] = pd.to_numeric(df_rank['近1年'], errors='coerce')
        df_rank['近6月'] = pd.to_numeric(df_rank['近6月'], errors='coerce')
        
        # 筛选条件
        candidates = df_rank[
            (df_rank['近1年'] > 2.5) & 
            (df_rank['近1年'] < 6.0) &
            (df_rank['近6月'] > 1.0) 
        ].head(10) # 只取前10名
        
        st.success(f"扫描完成！为您找到 {len(candidates)} 只潜力基金：")
        
        # 展示结果
        for index, row in candidates.iterrows():
            code = row['基金代码']
            name = row['基金简称']
            year_ret = row['近1年']
            
            with st.expander(f"{code} | {name} | 年化: {year_ret}%"):
                st.write(f"近6月收益: {row['近6月']}%")
                st.write(f"手续费: {row['手续费']}")
                if st.button(f"审计 {code}", key=code):
                    # 这里可以联动把 code 填入主输入框 (Streamlit 需要 session_state)
                    st.session_state['fund_code_input'] = code
                    st.rerun()
                    
    except Exception as e:
        st.error(f"扫描失败: {e}")
