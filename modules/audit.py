import streamlit as st
import akshare as ak
import pandas as pd
import plotly.express as px


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

                st.session_state.audit_cache = {
                    "code": fund_code,
                    "df_1y": df_1y,
                    "ret_1y": ret_1y,
                    "mdd": mdd,
                }
            except Exception as e:
                st.error(f"审计失败: {e}")

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
                prompt = f"分析基金{audited_code}，收益率{ret_1y:.2f}%，回撤{mdd:.2f}%。针对台胞证持有者，给出稳健投资建议。"
                res = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
                st.info(res.text)
            except Exception:
                pass
