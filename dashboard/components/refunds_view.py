"""Refunds tab — shows MP commission/funds refunds."""

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from dashboard.components.charts import money, MONTH_COLORS


def _pivot_to_money(df, group_col, months):
    if df.empty:
        return pd.DataFrame()
    pivot = (
        df.groupby([group_col, "month"])["amount"]
        .sum()
        .unstack("month")
        .reindex(columns=months, fill_value=0)
    )
    pivot["Итого"] = pivot.sum(axis=1)
    return pivot.sort_values("Итого", ascending=False)


def render_refunds(refunds_df: pd.DataFrame, months: list[str]) -> None:
    st.subheader("↩️ Возвраты средств / комиссий от МП")

    if refunds_df is None or refunds_df.empty:
        st.info(
            "Нет данных по возвратам.\n\n"
            "Чтобы появилась статистика, добавьте лист **«Возвраты МП»** в месячный файл "
            "«Для ИИ МП NN. <Месяц> <Год> Отчет по марже.xlsx» с колонками:\n"
            "- `month` (или «Месяц») — месяц возврата\n"
            "- `platform` (или «Площадка») — Ozon / WB / Я.Маркет / …\n"
            "- `client` (или «Клиент») — клиент / проект\n"
            "- `refund_type` (или «Тип возврата») — комиссия / реклама / прочее\n"
            "- `amount` (или «Сумма») — сумма возврата в рублях"
        )
        return

    df = refunds_df[refunds_df["month"].isin(months)].copy() if months else refunds_df

    # ── KPI ──────────────────────────────────────────────────────────────
    total = float(df["amount"].sum())
    by_month = df.groupby("month")["amount"].sum()
    avg = by_month.mean() if len(by_month) else 0.0
    cols = st.columns(3)
    cols[0].metric("Всего возвратов", money(total))
    cols[1].metric("Среднее за месяц", money(avg))
    cols[2].metric("Записей", len(df))

    st.divider()

    # ── Bar chart по месяцам и типам ────────────────────────────────────
    st.markdown("**Динамика по типу возврата**")
    bar_df = (
        df.groupby(["month", "refund_type"])["amount"]
        .sum().reset_index()
    )
    types = sorted(bar_df["refund_type"].unique())
    fig = go.Figure()
    for t in types:
        sub = bar_df[bar_df["refund_type"] == t]
        fig.add_trace(go.Bar(
            name=t, x=sub["month"], y=sub["amount"],
            text=sub["amount"].apply(money), textposition="outside",
        ))
    fig.update_layout(
        barmode="stack", height=380,
        margin=dict(t=30, b=20, l=20, r=20),
        plot_bgcolor="white", paper_bgcolor="white",
        yaxis=dict(tickformat=",", showgrid=True, gridcolor="#f0f0f0"),
        legend=dict(orientation="h", y=-0.2),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Pivot tables ────────────────────────────────────────────────────
    st.markdown("**По типу возврата × месяц**")
    p1 = _pivot_to_money(df, "refund_type", months)
    if not p1.empty:
        st.dataframe(p1.style.format({c: money for c in p1.columns}), use_container_width=True)

    st.markdown("**По площадке × месяц**")
    p2 = _pivot_to_money(df, "platform", months)
    if not p2.empty:
        st.dataframe(p2.style.format({c: money for c in p2.columns}), use_container_width=True)

    st.markdown("**Топ клиентов по возвратам**")
    p3 = _pivot_to_money(df, "client", months)
    if not p3.empty:
        st.dataframe(p3.head(20).style.format({c: money for c in p3.columns}),
                     use_container_width=True)
