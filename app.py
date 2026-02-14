import streamlit as st
import google.generativeai as genai
import akshare as ak
import pandas as pd
import plotly.express as px

# --- 0. 状态管理与回调函数 ---

# 初始化 Session State
if "fund_code_input" not in st.session_state:
    st.session_state.fund_code_input = "003002"
if "auto_run" not in st.session_state:
    st.session_state.auto_run = False
if "favorites" not in st.session_state:
    st.session_state.favorites = [] # 存储格式: [{"code": "00xxxx", "name": "基金名称"}]
if "current_fund_name" not in st.session_state:
    st.session_state.current_fund_name = ""

# 回调：设置目标基金并触发自动运行
def set_target_fund(code, name):
    st.session_state.fund_code_input = code
    st.session_state.current_fund_name = name
    st.session_state.auto_run = True # 开启自动运行开关

# 回调：添加/移除收藏
def toggle_favorite(code, name):
    # 检查是否已存在
    exists = False
    for item in st.session_state.favorites:
        if item["code"] == code:
            st.session_state.favorites.remove(item)
            exists = True
            st.toast(f"已取消收藏 {name}", icon="🗑️")
            break
    if not exists:
        st.session_state.favorites.append({"code": code, "name": name})
        st.toast(f"已加入收藏 {name}", icon="❤️")

# 辅助函数：尝试获取基金名称（针对手动输入的情况）
def get_fund_name_by_code(code):
    try:
        # 这里使用一个轻量级的接口尝试获取名称，如果失败则返回代码本身
        # 也可以通过 fund_em_open_fund_info 获取，但为了速度，这里做个简单处理
        # 实际生产中建议建立本地基金代码-名称字典
        return f"基金-{code}" 
    except:
        return code

# --- 1. 页面配置 ---
st.set_page_config(
    page_title="我的私人理财顾问 Pro",
    page_icon="💰",
    layout="wide"
)

# --- 2. 侧边栏：设置、收藏与雷达 ---
with st.sidebar:
    st.title("⚙️ 控制台")
    
    # API Key 配置
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
    else:
        api_key = st.text_input("Google API Key", type="password")
        if not api_key:
            st.warning("请输入 API Key")
            st.stop()
    
    st.divider()
    
    # --- A. 动态策略阈值 (UI 可操作) ---
    st.header("🎚️ 策略阈值设定")
    
    # 1. 收益阈值滑块
    min_yield_threshold = st.slider(
        "最低年化收益率 (%)", 
        min_value=1.0, 
        max_value=5.0, 
        value=2.0, 
        step=0.1,
        help="低于此数值建议直接存余额宝"
    )
    
    # 2. 回撤阈值滑块
    max_mdd_threshold = st.slider(
        "最大回撤容忍度 (%)", 
        min_value=-5.0, 
        max_value=-0.1, 
        value=-0.3, 
        step=0.1,
        help="回撤超过此数值（更负）将触发拒绝信号"
    )
    
    st.info(f"当前策略：收益 > {min_yield_threshold}% 且 回撤 > {max_mdd_threshold}%")

    st.divider()

    # --- B. 收藏夹功能 ---
    st.header("❤️ 我的收藏")
    if not st.session_state.favorites:
        st.caption("暂无收藏，快去添加吧")
    else:
        for fav in st.session_state.favorites:
            col_f1, col_f2 = st.columns([4, 1])
            with col_f1:
                st.button(
                    f"{fav['name']}", 
                    key=f"fav_{fav['code']}", 
                    on_click=set_target_fund,
                    args=(fav['code'], fav['name'])
                )
            with col_f2:
                # 这是一个小小的删除按钮
                if st.button("✕", key=f"del_{fav['code']}"):
                    toggle_favorite(fav['code'], fav['name'])
                    st.rerun()

    st.divider()
    
    # --- C. 市场雷达 ---
    st.header("📡 市场雷达")
    if st.button("🔍 扫描稳健短债 (Top 10)"):
        with st.spinner("正在扫描全市场..."):
            try:
                df_rank = ak.fund_open_fund_rank_em(symbol="债券型")
                df_rank['近1年'] = pd.to_numeric(df_rank['近1年'], errors='coerce')
                df_rank['近6月'] = pd.to_numeric(df_rank['近6月'], errors='coerce')
                
                # 使用用户设定的动态阈值进行筛选
                candidates = df_rank[
                    (df_rank['近1年'] > min_yield_threshold) & 
                    (df_rank['近1年'] < 8.0) & # 排除异常高收益
                    (df_rank['近6月'] > 0.5)
                ].head(10)
                
                st.success(f"发现 {len(candidates)} 只潜力标的")
                
                for index, row in candidates.iterrows():
                    code = row['基金代码']
                    name = row['基金简称']
                    
                    with st.expander(f"{row['近1年']}% | {name}"):
                        st.write(f"近6月: {row['近6月']}%")
                        st.button(
                            "审计此基金", 
                            key=f"scan_{code}", 
                            on_click=set_target_fund, 
                            args=(code, name)
                        )
            except Exception as e:
                st.error(f"扫描失败: {e}")

# --- 3. 主界面逻辑 ---
st.title("🤖 个人理财中台 Pro")
st.caption(f"Powered by Gemini 2.0 | 动态阈值版")

genai.configure(api_key=api_key)

# 输入区
col1, col2 = st.columns([3, 1])
with col1:
    # 主输入框，绑定 session_state
    fund_code_input = st.text_input(
        "输入基金代码", 
        key="fund_code_input",
        help="输入代码后点击开始，或从左侧选择"
    )
with col2:
    # 两个触发条件：1. 点击按钮 2. 自动运行开关为 True
    manual_start = st.button("🚀 开始审计", type="primary")

# 核心判断逻辑：是否开始运行
if manual_start or st.session_state.auto_run:
    # 立即重置自动运行开关，防止无限刷新
    st.session_state.auto_run = False
    
    # 如果没有名称（手动输入的情况），尝试给一个默认名
    if not st.session_state.current_fund_name:
        st.session_state.current_fund_name = get_fund_name_by_code(fund_code_input)

    status_text = st.empty()
    progress_bar = st.progress(0)
    
    try:
        # --- 步骤 1: 获取数据 ---
        status_text.info(f"正在获取 {st.session_state.current_fund_name} ({fund_code_input}) 数据...")
        progress_bar.progress(20)

        try:
            df = ak.fund_open_fund_info_em(symbol=fund_code_input, indicator="累计净值走势")
        except:
            st.error("数据获取失败，请检查代码。")
            st.stop()

        if df is None or df.empty:
            st.error("未找到数据。")
            st.stop()

        # 数据清洗
        df = df[['净值日期', '累计净值']].rename(columns={'净值日期': 'date', '累计净值': 'nav'})
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # 截取最近一年
        one_year_ago = pd.Timestamp.now() - pd.Timedelta(days=365)
        df_1y = df[df['date'] >= one_year_ago].copy()
        if df_1y.empty: df_1y = df.copy()

        # --- 步骤 2: 计算与动态判定 ---
        status_text.info("正在进行动态阈值判定...")
        progress_bar.progress(50)

        # 指标计算
        start_nav = df_1y['nav'].iloc[0]
        end_nav = df_1y['nav'].iloc[-1]
        total_return = (end_nav / start_nav - 1) * 100
        
        roll_max = df_1y['nav'].cummax()
        drawdown = (df_1y['nav'] - roll_max) / roll_max
        mdd = drawdown.min() * 100 
        
        # === 动态逻辑守卫 (使用侧边栏的变量) ===
        decision = "待定"
        reason_core = ""
        color = "grey"

        # 注意：回撤通常是负数，比如 -0.5。阈值是 -0.3。
        # 如果 mdd (-0.5) < threshold (-0.3)，说明跌得更深，触发风险
        if mdd < max_mdd_threshold: 
            decision = "🛑 拒绝 (风险超标)"
            reason_core = f"最大回撤 {mdd:.2f}% 超过了您设定的阈值 ({max_mdd_threshold}%)。"
            color = "red"
        elif total_return < min_yield_threshold:
            decision = "⚪ 观望 (收益不足)"
            reason_core = f"年化收益 {total_return:.2f}% 低于您设定的目标 ({min_yield_threshold}%)。"
            color = "orange"
        else:
            decision = "✅ 推荐 (买入)"
            reason_core = f"收益 ({total_return:.2f}%) 与回撤 ({mdd:.2f}%) 均符合您当前的稳健策略。"
            color = "green"

        # --- 步骤 3: 界面展示 ---
        progress_bar.progress(80)
        
        # 标题栏：显示名称 + 收藏按钮
        col_title, col_fav = st.columns([5, 1])
        with col_title:
            st.subheader(f"📊 {st.session_state.current_fund_name} ({fund_code_input})")
        with col_fav:
            # 判断当前是否已收藏，改变按钮样式
            is_fav = any(f['code'] == fund_code_input for f in st.session_state.favorites)
            fav_label = "💔 取消收藏" if is_fav else "❤️ 加入收藏"
            st.button(fav_label, on_click=toggle_favorite, args=(fund_code_input, st.session_state.current_fund_name))

        # 核心指标
        m1, m2, m3 = st.columns(3)
        m1.metric("真实收益率", f"{total_return:.2f}%", delta=None)
        m2.metric("最大回撤", f"{mdd:.2f}%", delta_color="inverse", help=f"阈值: {max_mdd_threshold}%")
        m3.metric("决策结论", decision)

        # 图表
        fig = px.line(df_1y, x='date', y='nav', title="累计净值走势 (真实收益)")
        # 增加一条回撤辅助线（可选，视觉上不太好看先不加）
        st.plotly_chart(fig, use_container_width=True)

        # --- 步骤 4: Gemini 报告 ---
        status_text.info("AI 正在生成报告...")
        progress_bar.progress(90)
        
        st.divider()
        st.markdown(f"### 🤖 AI 投资建议: :{color}[{decision}]")
        
        with st.chat_message("assistant"):
            model = genai.GenerativeModel('gemini-2.0-flash')
            
            prompt = f"""
            你是一个理财顾问。分析对象: {st.session_state.current_fund_name} ({fund_code_input})。
            数据: 年化 {total_return:.2f}%, 回撤 {mdd:.2f}%。
            用户设定标准: 收益 > {min_yield_threshold}%, 回撤 > {max_mdd_threshold}%。
            
            系统判定结论: 【{decision}】
            核心理由: {reason_core}
            
            请基于此生成简短分析（100字内），语气专业客观。
            """
            
            response_container = st.empty()
            full_response = ""
            for chunk in model.generate_content(prompt, stream=True):
                full_response += chunk.text
                response_container.markdown(full_response)
        
        status_text.success("审计完成")
        progress_bar.progress(100)

    except Exception as e:
        st.error(f"运行出错: {e}")
