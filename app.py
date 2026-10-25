import pandas as pd
import streamlit as st
from collections import Counter

import store


def profit_counts(run):
    return Counter(t["sell_id"] for t in run["trades"] if t["net_profit"] > 0)

st.set_page_config(page_title="Z-day-trading", page_icon="↗", layout="centered")
st.markdown("""<style>
.block-container {max-width: 920px; padding-top: 2.5rem;}
h1 {font-size: 1.8rem !important; letter-spacing: -.04em;}
h3 {font-size: 1.15rem !important;}
[data-testid="stHeader"] {background: transparent;}
#MainMenu, footer {visibility: hidden;}
[data-testid="stAppDeployButton"] {display: none;}
[data-testid="stDataFrame"] {border-radius: 10px;}
</style>""", unsafe_allow_html=True)
store.initialize()
st.title("Z-day-trading")
page = st.radio("导航", ["结果", "想法", "想法库", "排名", "个股排名"], horizontal=True, label_visibility="collapsed")
items = store.ideas()
buys = [x for x in items if x["kind"] == "buy"]
sells = [x for x in items if x["kind"] == "sell"]

if page == "想法":
    kind_label = st.radio("想法类型", ["买入想法", "卖出方法"], horizontal=True, label_visibility="collapsed")
    kind = "buy" if kind_label == "买入想法" else "sell"
    choices = [x for x in items if x["kind"] == kind]
    lookup = {x["id"]: x for x in choices}
    selected = st.selectbox("选择想法", ["new", *lookup],
                            format_func=lambda key: "＋ 新建" if key == "new" else lookup[key]["name"])
    item = lookup.get(selected)
    with st.form(f"edit_{selected}_{item['updated_at'] if item else 'new'}", clear_on_submit=False):
        name = st.text_input("名称", value=item["name"] if item else "", max_chars=120)
        description = st.text_area("Description", value=item["description"] if item else "", height=300)
        reset = st.checkbox("重新实现（realize = false）") if item else False
        if st.form_submit_button("保存", type="primary"):
            try:
                store.save(kind, name, description, selected if item else None, reset,
                           expected_updated_at=item["updated_at"] if item else None)
                st.session_state["notice"] = "已保存。修改描述后会等待重新实现。"
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    if st.session_state.get("notice"):
        st.success(st.session_state.pop("notice"))
    if item:
        st.caption(f"版本 {item['version']} · {'已实现' if item['realize'] else '待实现'}")

elif page == "想法库":
    st.dataframe(
        pd.DataFrame([
            {"名称": x["name"],
             "类型": "买入" if x["kind"] == "buy" else "卖出",
             "状态": "已实现" if x["realize"] else "待实现"}
            for x in items
        ], columns=["名称", "类型", "状态"]),
        hide_index=True, width="stretch",
    )

elif page == "个股排名":
    import equities
    st.caption("2025/10/23—2026/10/22 · 251个交易日 · IBKR正常交易时段1分钟数据")
    symbol = st.selectbox("股票", ["全部", *equities.SYMBOLS])
    minimum = st.number_input("最少交易笔数", min_value=0, value=0, step=1)
    rows = equities.ranking_rows(items)
    if rows:
        table = pd.DataFrame(rows)
        if symbol != "全部":
            table = table[table["股票"] == symbol]
        table = table[table["笔数"] >= minimum]
        table = table.sort_values("平均净收益率", ascending=False, kind="stable", na_position="last").reset_index(drop=True)
        table.insert(0, "排名", range(1, len(table)+1))
        st.dataframe(table, hide_index=True, width="stretch", height=600,
                     column_config={"平均净收益率": st.column_config.NumberColumn(format="%.2f%%"),
                                    "胜率": st.column_config.NumberColumn(format="%.1f%%")})
        st.caption(r"平均单笔净收益排序 · 固定Delta 0.5、\$200/张、损耗\$1/分钟、往返费\$2；并非真实期权报价。不同股票沿用原规则的美元阈值。")
        st.caption("指标从数据起点预热；半日市在实际收盘退出。0笔不代表收益为0。")
    else:
        st.info("暂无有效个股结果，需完成回测；修改规则或数据后需重新运行。")

elif page == "排名":
    st.subheader("SPY")
    rows = []
    ranking_source = None
    names = {x["id"]: x["name"] for x in sells}
    for buy in buys:
        run = store.latest(buy["id"])
        if not (run and buy["realize"] and all(x["realize"] for x in sells)
                and run["signature"] == store.signature(buy, sells)):
            continue
        ranking_source = run["source"]
        wins = profit_counts(run)
        for result in run["summary"]:
            rows.append({"买入想法": buy["name"],
                             "卖出方法": names.get(result["sell_id"], result["name"]),
                             "平均净收益率": result["mean_return"] * 100 if result["mean_return"] is not None else None,
                             "胜率": wins[result["sell_id"]] / result["trades"] * 100 if result["trades"] else None,
                             "盈利笔数": wins[result["sell_id"]],
                             "笔数": result["trades"]})
    if rows:
        if ranking_source and ranking_source.get("start"):
            venue = "IBKR正常交易时段" if ranking_source.get("whatToShow") == "TRADES" else "Nasdaq 单一场所行情"
            st.caption(f"SPY · {ranking_source['start'][:10]} — {ranking_source['end'][:10]} · {venue}")
        table = pd.DataFrame(rows).sort_values("平均净收益率", ascending=False, kind="stable", na_position="last").reset_index(drop=True)
        table.insert(0, "排名", range(1, len(table) + 1))
        st.dataframe(table, hide_index=True, width="stretch", height=600,
                     column_config={"平均净收益率": st.column_config.NumberColumn(format="%.2f%%"),
                                    "胜率": st.column_config.NumberColumn(format="%.1f%%")})
        st.caption("按平均单笔净收益排序。胜率 = 扣除损耗及手续费后盈利的笔数 ÷ 总笔数；持平不算盈利。")
    else:
        st.info("暂无有效回测结果，完成回测后显示排名。")

    st.subheader("QQQ")
    import equities
    qqq_rows = equities.ranking_rows(items, symbols=("QQQ",))
    if qqq_rows:
        st.caption("2025-10-23 — 2026-10-22 · IBKR正常交易时段1分钟数据")
        qqq_table = pd.DataFrame(qqq_rows).drop(columns=["股票", "状态"])
        qqq_table = qqq_table.sort_values("平均净收益率", ascending=False, kind="stable", na_position="last").reset_index(drop=True)
        qqq_table.insert(0, "排名", range(1, len(qqq_table) + 1))
        st.dataframe(qqq_table, hide_index=True, width="stretch", height=600,
                     column_config={"平均净收益率": st.column_config.NumberColumn(format="%.2f%%"),
                                    "胜率": st.column_config.NumberColumn(format="%.1f%%")})
        st.caption("同一组买入与卖出规则、同一费用模型；显示平均单笔净收益，不是真实期权报价。")
    else:
        st.info("QQQ 暂无有效回测结果。")

else:
    if not buys:
        st.info("先在「想法」中保存一个买入想法。")
        st.stop()
    lookup = {x["id"]: x for x in buys}
    selected = st.selectbox("买入想法", list(lookup), format_func=lambda key: lookup[key]["name"])
    buy = lookup[selected]
    with st.expander("买入规则"):
        st.text(buy["description"])
    run = store.latest(selected)
    fresh = run and buy["realize"] and all(x["realize"] for x in sells) and run["signature"] == store.signature(buy, sells)
    if not run:
        st.info("这个想法尚无回测结果。请到「想法库」查看状态。")
    elif not fresh:
        st.info("想法或卖出方法已更新，等待重新实现和回测。")
        with st.expander("上一版本结果"):
            st.caption(run["snapshot"]["buy"]["description"])
            wins = profit_counts(run)
            historical = pd.DataFrame([{"卖出方法": x["name"],
                "平均净收益率": None if x["mean_return"] is None else x["mean_return"] * 100,
                "胜率": wins[x["sell_id"]] / x["trades"] * 100 if x["trades"] else None,
                "盈利笔数": wins[x["sell_id"]], "交易次数": x["trades"]} for x in run["summary"]])
            st.dataframe(historical, hide_index=True, column_config={
                "平均净收益率": st.column_config.NumberColumn(format="%.2f%%"),
                "胜率": st.column_config.NumberColumn(format="%.1f%%")})
    else:
        source = run["source"]
        venue = "IBKR正常交易时段" if source.get("whatToShow") == "TRADES" else "Nasdaq 单一场所行情"
        st.caption(f"SPY · 1 分钟 · {source['start'][:10]} — {source['end'][:10]} · {venue}")
        names = {x["id"]: x["name"] for x in sells}
        wins = profit_counts(run)
        table = pd.DataFrame([{"卖出方法": names.get(x["sell_id"], x["name"]),
                               "平均净收益率": None if x["mean_return"] is None else x["mean_return"] * 100,
                               "胜率": wins[x["sell_id"]] / x["trades"] * 100 if x["trades"] else None,
                               "盈利笔数": wins[x["sell_id"]],
                               "交易次数": x["trades"]} for x in run["summary"]])
        st.dataframe(table, hide_index=True, width="stretch", column_config={
            "平均净收益率": st.column_config.NumberColumn(format="%.2f%%"),
            "胜率": st.column_config.NumberColumn(format="%.1f%%")})
        st.caption("固定 Delta 0.5 · 200 美元/张 · 每分钟损耗 1 美元 · 往返手续费 2 美元")
