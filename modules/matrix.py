import streamlit as st
import pandas as pd


def render_matrix_tab():
    """渲染 Tab 2：10万本金收益矩阵"""
    st.subheader("📊 多标的试算对比 (10万本金基准)")
    if not st.session_state.favorites:
        st.info("请先收藏基金。")
    else:
        cp, cd = st.columns(2)
        p_val = cp.number_input("试算本金 (元)", value=100000)
        d_val = cd.number_input("持有周期 (天)", value=30)

        results = []
        for f in st.session_state.favorites:
            mock_annual = 3.2
            gross = p_val * (mock_annual / 100) * (d_val / 365)
            one_time_cost = p_val * (f['buy_fee'] + f['sell_fee']) / 100
            holding_cost = p_val * (f['annual_fee'] / 100) * (d_val / 365)
            net_profit = gross - one_time_cost - holding_cost

            results.append({
                "标的": f['name'],
                "投资期净利润": round(net_profit, 2),
                "月均预期": round(net_profit / (d_val / 30), 2),
                "实际折算年化": f"{(net_profit / p_val) * (365 / d_val) * 100:.2f}%"
            })

        st.table(pd.DataFrame(results))
