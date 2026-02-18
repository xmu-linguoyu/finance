import streamlit as st
import akshare as ak
import pandas as pd
import plotly.express as px
import datetime


def render_audit_tab(client, db, sync_to_cloud):
    """渲染 Tab 1：智能审计与收藏"""
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
                df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="累计净值走势")
                df = df[['净值日期', '累计净值']].rename(columns={'净值日期': 'date', '累计净值': 'nav'})
                df['date'] = pd.to_datetime(df['date'])
                df_1y = df.tail(252)

                ret_1y = (df_1y['nav'].iloc[-1] / df_1y['nav'].iloc[0] - 1) * 100
                mdd = ((df_1y['nav'] - df_1y['nav'].cummax()) / df_1y['nav'].cummax()).min() * 100

                # 基金基本信息（类型、规模、管理费率等）
                try:
                    info_df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="基金基本信息")
                except Exception:
                    info_df = None

                # 同类排名走势
                try:
                    rank_df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="同类排名走势")
                    # 取最新一条排名数据
                    latest_rank = rank_df.iloc[-1].to_dict() if rank_df is not None and not rank_df.empty else None
                except Exception:
                    rank_df = None
                    latest_rank = None

                # 重仓股持仓（用当前年份，失败则尝试上一年）
                now = datetime.datetime.now()
                current_year = str(now.year)
                prev_year = str(now.year - 1)
                try:
                    hold_df = ak.fund_portfolio_hold_em(symbol=fund_code, date=current_year)
                except Exception:
                    try:
                        hold_df = ak.fund_portfolio_hold_em(symbol=fund_code, date=prev_year)
                    except Exception:
                        hold_df = None

                # 基金经理
                try:
                    manager_df = ak.fund_open_fund_manager_em(symbol=fund_code)
                except Exception:
                    manager_df = None

                st.session_state.audit_cache = {
                    "code": fund_code,
                    "df_1y": df_1y,
                    "ret_1y": ret_1y,
                    "mdd": mdd,
                    "info_df": info_df,
                    "latest_rank": latest_rank,
                    "hold_df": hold_df,
                    "manager_df": manager_df,
                }
            except Exception as e:
                st.error(f"审计失败: {e}")

    if st.session_state.audit_cache:
        cache = st.session_state.audit_cache
        audited_code = cache["code"]
        df_1y = cache["df_1y"]
        ret_1y = cache["ret_1y"]
        mdd = cache["mdd"]
        info_df = cache.get("info_df")
        latest_rank = cache.get("latest_rank")
        hold_df = cache.get("hold_df")
        manager_df = cache.get("manager_df")

        st.subheader(f"📊 标的审计: {audited_code}")
        col1, col2 = st.columns(2)
        col1.metric("近一年回报率", f"{ret_1y:.2f}%")
        col2.metric("最大回撤", f"{mdd:.2f}%")

        st.plotly_chart(px.line(df_1y, x='date', y='nav'), use_container_width=True)

        # 显示基金基本信息
        if info_df is not None and not info_df.empty:
            st.subheader("📋 基金基本信息")
            st.dataframe(info_df, use_container_width=True)

        # 显示基金经理
        if manager_df is not None and not manager_df.empty:
            st.subheader("👤 基金经理")
            st.dataframe(manager_df, use_container_width=True)

        # 显示同类最新排名
        if latest_rank:
            st.subheader("🏆 同类最新排名")
            # Limit to max 5 columns for better readability
            rank_items = list(latest_rank.items())
            num_cols = min(len(rank_items), 5)
            rank_cols = st.columns(num_cols)
            for idx, (key, value) in enumerate(rank_items[:num_cols]):
                rank_cols[idx].metric(key, str(value))
            # Display remaining items in structured format if more than 5
            if len(rank_items) > 5:
                with st.expander("查看更多排名信息"):
                    remaining = {k: v for k, v in rank_items[5:]}
                    st.json(remaining)

        # 显示重仓股持仓
        if hold_df is not None and not hold_df.empty:
            st.subheader("💼 前十重仓股")
            st.dataframe(hold_df.head(10), use_container_width=True)

        st.divider()
        st.subheader("💾 设置费率并存入 Firebase")
        with st.form("save_fund_form"):
            f_name = st.text_input("备注名称", value=audited_code)
            c1, c2, c3 = st.columns(3)
            b_fee = c1.number_input("申购费率 %", 0.0, 5.0, 0.0, step=0.01)
            s_fee = c2.number_input("赎回费率 %", 0.0, 5.0, 0.0, step=0.01)
            a_fee = c3.number_input("年化杂费 % (含汇损预留)", 0.0, 5.0, 0.1, step=0.01)

            submit_save = st.form_submit_button("确认同步至云端", type="primary")

            if submit_save:
                new_data = {
                    "code": audited_code, "name": f_name,
                    "buy_fee": float(b_fee), "sell_fee": float(s_fee),
                    "annual_fee": float(a_fee)
                }
                st.session_state.favorites = [f for f in st.session_state.favorites if f['code'] != audited_code]
                st.session_state.favorites.append(new_data)
                sync_to_cloud(db)

        if client:
            try:
                st.divider()
                st.write("🤖 AI 投资建议：")
                
                # 构建丰富的基金概况文字
                fund_summary_parts = [f"基金代码：{audited_code}", f"近一年收益率：{ret_1y:.2f}%", f"最大回撤：{mdd:.2f}%"]

                if info_df is not None and not info_df.empty:
                    # Limit to first 20 rows to avoid excessively long prompts
                    info_sample = info_df.head(20)
                    fund_summary_parts.append(f"基本信息：{info_sample.to_string(index=False)}")

                if latest_rank:
                    fund_summary_parts.append(f"最新同类排名：{latest_rank}")

                if manager_df is not None and not manager_df.empty:
                    # Limit to first 10 rows to avoid excessively long prompts
                    manager_sample = manager_df.head(10)
                    fund_summary_parts.append(f"基金经理：{manager_sample.to_string(index=False)}")

                if hold_df is not None and not hold_df.empty:
                    # Already limited to top 10 holdings
                    fund_summary_parts.append(f"前十重仓股：{hold_df.head(10).to_string(index=False)}")

                fund_summary = "\n".join(fund_summary_parts)
                prompt = f"请根据以下基金信息，给出全面的投资分析与稳健建议（针对台胞证持有者）：\n{fund_summary}"
                
                res = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
                st.info(res.text)
            except Exception:
                pass
