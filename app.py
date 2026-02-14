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
    st.session_state.favorites = [] 
if "current_fund_name" not in st.session_state:
    st.session_state.current_fund_name = ""
# [新增] 专门用来存储扫描结果，防止点击后消失
if "scan_results" not in st.session_state:
    st.session_state.scan_results = None 

# 回调：设置目标基金并触发自动运行
def set_target_fund(code, name):
    st.session_state.fund_code_input = code
    st.session_state.current_fund_name = name
    st.session_state.auto_run = True 

# 回调：添加/移除收藏
def toggle_favorite(code, name):
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

# 辅助函数：尝试获取基金名称
def get_fund_name_by_code(code):
    try:
        return f"基金-{code}" 
    except:
        return code

# --- 1. 页面配置 ---
st.set_page_config(
    page_title="我的私人理财顾问 Pro",
    page_icon="💰",
    layout="wide"
)

# --- 2. 侧边栏 ---
with st.sidebar:
    st.title("⚙️ 控制台")
    
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
    else:
        api_key = st.text_input("Google API Key", type="password")
        if not api_key:
            st.warning("请输入 API Key")
            st.stop()
    
    st.divider()
    
    # --- A. 动态策略阈值 ---
    st.header("🎚️ 策略阈值设定")
    min_yield_threshold = st.slider("最低年化收益率 (%)", 1.0, 5.0, 2.0, 0.1)
    max_mdd_threshold = st.slider("最大回撤容忍度 (%)", -5.0, -0.1, -0.3, 0.1)
    st.info(f"策略：收益 > {min_yield_threshold}% 且 回撤 > {max_mdd_threshold}%")

    st.divider()

    # --- B. 收藏夹 ---
    st.header("❤️ 我的收藏")
    if not st.session_state.favorites:
        st.caption("暂无收藏")
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
                if st.button("✕", key=f"del_{fav['code']}"):
                    toggle_favorite(fav['code'], fav['name'])
                    st.rerun()

    st.divider()
    
    # --- C. 市场雷达 (修复版) ---
    st.header("📡 市场雷达")
    
    # 1. 扫描按钮只负责“抓数据”并存入 session_state
    if st.button("🔍 扫描稳健短债 (Top 10)"):
        with st.spinner("正在扫描全市场..."):
            try:
                df_rank = ak.fund_open_fund_rank_em(symbol="债券型")
                df_rank['近1年'] = pd.to_numeric(df_rank['近1年'], errors='coerce')
                df_rank['近6月'] = pd.to_numeric(df_rank['近6月'], errors='coerce')
                
                candidates = df_rank[
                    (df_rank['近1年'] > min_yield_threshold) & 
                    (df_rank['近1年'] < 8.0) & 
                    (df_rank['近6月'] > 0.5)
                ].head(10)
                
                # 【关键修复】将结果存入 session_state
                st.session_state.scan_results = candidates
                st.success(f"发现 {len(candidates)} 只潜力标的")
            except Exception as e:
                st.error(f"扫描失败: {e}")

    # 2. 渲染列表逻辑移到按钮外面，只要 session_state 里有数据就显示
    if st.session_state.scan_results is not None:
        if st.button("🗑️ 清空扫描结果"):
            st.session_state.scan_results = None
            st.rerun()
            
        for index, row in st.session_state.scan_results.iterrows():
            code = row['基金代码']
            name = row['基金简称']
            
            with st.expander(f"{row['近1年']}% | {name}"):
                st.write(f"近6月: {row['近6月']}%")
                # 这里的按钮点击后，虽然脚本重跑，但 session_state.scan_results 还在
                # 所以列表不会消失
                st.button(
                    "审计此基金", 
                    key=f"scan_{code}", 
                    on_click=set_target_fund, 
                    args=(code, name)
                )

# --- 3. 主界面逻辑 ---
st.title("🤖 个人理财中台 Pro")
st.caption(f"Powered by Gemini 2.0 | 动态阈值版")

genai.configure(api_key=api_key)

col1, col2 = st.columns([3, 1])
with col1:
    fund_code_input = st.text_input("输入基金代码", key="fund_code_input")
with col2:
    manual_start = st.button("🚀 开始审计", type="primary")

if manual_start or st.session_state.auto_run:
    st.session_state.auto_run = False
    
    if not st.session_state.current_fund_name:
        st.session_state.current_fund_name = get_fund_name_by_code(fund_code_input)

    status_text = st.empty()
    progress_bar = st.progress(0)
    
    try:
        # 步骤 1: 获取数据
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

        df = df[['净值日期', '累计净值']].rename(columns={'净值日期': 'date', '累计净值': 'nav'})
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        one_year_ago = pd.Timestamp.now() - pd.Timedelta(days=365)
        df_1y = df[df['date'] >= one_year_ago].copy()
        if df_1y.empty: df_1y = df.copy()

        # 步骤 2: 计算
        status_text.info("正在进行动态阈值判定...")
        progress_bar.progress(50)

        start_nav = df_1y['nav'].iloc[0]
        end_nav = df_1y['nav'].iloc[-1]
        total_return = (end_nav / start_nav - 1) * 100
        
        roll_max = df_1y['nav'].cummax()
        drawdown = (df_1y['nav'] - roll_max) / roll_max
        mdd = drawdown.min() * 100 
        
        # 动态逻辑守卫
        decision = "待定"
        reason_core = ""
        color = "grey"

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

        # 步骤 3: 界面展示
        progress_bar.progress(80)
        
        col_title, col_fav = st.columns([5, 1])
        with col_title:
            # 标题栏现在显示名称了
            st.subheader(f"📊 {st.session_state.current_fund_name} ({fund_code_input})")
        with col_fav:
            is_fav = any(f['code'] == fund_code_input for f in st.session_state.favorites)
            fav_label = "💔 取消收藏" if is_fav else "❤️ 加入收藏"
            st.button(fav_label, on_click=toggle_favorite, args=(fund_code_input, st.session_state.current_fund_name))

        m1, m2, m3 = st.columns(3)
        m1.metric("真实收益率", f"{total_return:.2f}%", delta=None)
        m2.metric("最大回撤", f"{mdd:.2f}%", delta_color="inverse", help=f"阈值: {max_mdd_threshold}%")
        m3.metric("决策结论", decision)

        fig = px.line(df_1y, x='date', y='nav', title="累计净值走势 (真实收益)")
        st.plotly_chart(fig, use_container_width=True)

        # 步骤 4: Gemini 报告
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
