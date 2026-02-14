import streamlit as st
import google.generativeai as genai
import akshare as ak
import pandas as pd
import plotly.express as px

# --- 0. 狀態回調函數 (關鍵修復) ---
# 這個函數會在按鈕點擊時立即執行，更新 session_state
def update_fund_code(code):
    st.session_state.fund_code_input = code

# --- 1. 頁面配置 ---
st.set_page_config(
    page_title="我的私人理財顧問",
    page_icon="💰",
    layout="wide"
)

# 初始化 session_state (如果你是第一次打開)
if "fund_code_input" not in st.session_state:
    st.session_state.fund_code_input = "003002"

# --- 2. 側邊欄：配置與掃描雷達 ---
with st.sidebar:
    st.header("⚙️ 系統設置")
    
    # 獲取 API Key
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
    else:
        api_key = st.text_input("請輸入 Google API Key", type="password")
        if not api_key:
            st.warning("請先配置 Google API Key 才能開始分析。")
            st.stop()
    
    st.divider()
    
    # --- 新增功能：市場雷達 ---
    st.header("📡 市場雷達 (Beta)")
    st.caption("掃描全市場穩健短債")
    
    if st.button("🔍 開始掃描"):
        with st.spinner("正在全市場海選..."):
            try:
                # 獲取債券型基金排名
                df_rank = ak.fund_open_fund_rank_em(symbol="債券型")
                
                # 數據清洗：轉為數字
                df_rank['近1年'] = pd.to_numeric(df_rank['近1年'], errors='coerce')
                df_rank['近6月'] = pd.to_numeric(df_rank['近6月'], errors='coerce')
                
                # 篩選邏輯 (R2穩健型)
                # 1. 近1年收益 2.5% ~ 6.0% (太高通常是假象或踩雷)
                # 2. 近6月必須正收益 (排除近期暴雷)
                candidates = df_rank[
                    (df_rank['近1年'] > 2.5) & 
                    (df_rank['近1年'] < 6.0) &
                    (df_rank['近6月'] > 1.0)
                ].head(10) # 展示前10名
                
                st.success(f"發現 {len(candidates)} 隻潛力標的：")
                
                # 展示結果
                for index, row in candidates.iterrows():
                    code = row['基金代碼']
                    name = row['基金簡稱']
                    year_ret = row['近1年']
                    
                    with st.expander(f"{year_ret}% | {name} ({code})"):
                        st.write(f"近6月: {row['近6月']}%")
                        st.write(f"手續費: {row['手續費']}")
                        
                        # --- 關鍵：使用 on_click 回調更新主輸入框 ---
                        st.button(
                            "審計此基金", 
                            key=f"btn_{code}", 
                            on_click=update_fund_code, # 點擊時觸發回調
                            args=(code,) # 傳參
                        )
                        
            except Exception as e:
                st.error(f"掃描失敗，請稍後重試: {e}")

    st.divider()
    st.markdown("### 🎯 策略說明 (R2穩健)")
    st.markdown("- **回撤閾值:** < -0.3% (拒絕)")
    st.markdown("- **收益閾值:** > 2.0% (否則存餘額寶)")

# --- 3. 核心邏輯區 ---
st.title("🤖 個人理財中台 (Cloud Native)")
st.caption("Powered by Gemini 2.0 Flash & AkShare | 最終版 V3.0")

# 配置 Gemini
genai.configure(api_key=api_key)

# 輸入區域 (注意：這裡綁定了 key="fund_code_input")
# 當側邊欄按鈕點擊後，session_state.fund_code_input 會變，這裡就會自動更新
col1, col2 = st.columns([3, 1])
with col1:
    fund_code = st.text_input("輸入基金代碼 (例如: 003002)", key="fund_code_input")
with col2:
    analyze_btn = st.button("🚀 開始雲端審計", type="primary")

if analyze_btn:
    status_text = st.empty()
    progress_bar = st.progress(0)

    try:
        # --- 步驟 1: 獲取數據 (使用累計淨值修復數據源) ---
        status_text.info("🔄 正在連接交易所數據 (AkShare)...")
        progress_bar.progress(20)

        try:
            # 強制使用 '累計淨值走勢' 避免分紅導致的回撤幻覺
            df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="累計淨值走勢")
        except:
            st.error(f"❌ 無法獲取代碼 {fund_code} 的累計淨值，請檢查代碼是否正確。")
            st.stop()

        if df is None or df.empty:
            st.error(f"❌ 找不到代碼 {fund_code} 的數據。")
            st.stop()

        # 數據清洗
        df = df[['淨值日期', '累計淨值']].rename(columns={'淨值日期': 'date', '累計淨值': 'nav'})
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # 截取最近一年
        progress_bar.progress(40)
        one_year_ago = pd.Timestamp.now() - pd.Timedelta(days=365)
        df_1y = df[df['date'] >= one_year_ago].copy()
        
        if df_1y.empty:
             st.warning("⚠️ 該基金數據不足一年，將使用所有歷史數據分析。")
             df_1y = df.copy()

        # --- 步驟 2: Python 硬邏輯計算 (杜絕 AI 幻覺) ---
        status_text.info("🧮 正在進行脫水計算...")
        progress_bar.progress(60)

        # 計算累計收益率
        start_nav = df_1y['nav'].iloc[0]
        end_nav = df_1y['nav'].iloc[-1]
        total_return = (end_nav / start_nav - 1) * 100
        
        # 計算最大回撤 (Max Drawdown)
        roll_max = df_1y['nav'].cummax()
        drawdown = (df_1y['nav'] - roll_max) / roll_max
        mdd = drawdown.min() * 100 # 結果通常是負數，例如 -0.5
        
        # Python 決策守衛 (Hard Guardrails)
        decision = "待定"
        reason_core = ""
        color = "grey"

        if mdd < -0.3: # 回撤超過 -0.3% (例如 -1.0%)
            decision = "🛑 SELL / AVOID (拒絕)"
            reason_core = f"最大回撤 {mdd:.2f}% 嚴重超過安全閾值 (-0.3%)，風險過大。"
            color = "red"
        elif total_return < 2.0:
            decision = "⚪ PASS (觀望)"
            reason_core = f"年化收益 {total_return:.2f}% 過低，不如直接存餘額寶 (約1.8%)。"
            color = "orange"
        else:
            decision = "✅ BUY (推薦)"
            reason_core = "收益達標且回撤控制在安全範圍內，符合穩健策略。"
            color = "green"

        # --- 步驟 3: 展示圖表與數據 ---
        progress_bar.progress(80)
        
        # 關鍵指標卡片
        m1, m2, m3 = st.columns(3)
        m1.metric("近一年真實收益", f"{total_return:.2f}%", delta=None)
        m2.metric("最大回撤 (風險)", f"{mdd:.2f}%", delta_color="inverse") 
        m3.metric("最新累計淨值", f"{end_nav:.4f}")

        # 繪製交互式圖表
        fig = px.line(df_1y, x='date', y='nav', title=f"基金 {fund_code} 累計淨值走勢 (真實收益)")
        st.plotly_chart(fig, use_container_width=True)

        # --- 步驟 4: Gemini 生成報告 (基於 Python 結論) ---
        status_text.info("🧠 Gemini 正在生成分析報告...")
        progress_bar.progress(90)
        
        st.divider()
        st.subheader(f"🤖 AI 決策報告: :{color}[{decision}]")
        
        with st.chat_message("assistant"):
            model = genai.GenerativeModel('gemini-2.0-flash')
            
            # 這裡的 Prompt 強制 AI 解釋 Python 的結論
            prompt = f"""
            你是一個專業的理財顧問。
            分析對象: 基金 {fund_code}
            數據: 近一年收益 {total_return:.2f}%, 最大回撤 {mdd:.2f}%。
            
            【系統強制結論】: {decision}
            【核心理由】: {reason_core}
            
            請根據上述結論和理由，寫一段簡短、專業的分析報告（100字以內）。
            用戶是台胞證持有者，追求穩健。
            **必須嚴格支持系統的結論，禁止反駁或自行發揮。**
            """
            
            response_container = st.empty()
            full_response = ""
            for chunk in model.generate_content(prompt, stream=True):
                full_response += chunk.text
                response_container.markdown(full_response)
        
        status_text.success("✅ 分析完成！")
        progress_bar.progress(100)

    except Exception as e:
        st.error(f"發生系統錯誤: {e}")
        st.code(str(e))
