"""Agency earnings tab — by-client agency-commission revenue and margin."""

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from dashboard.components.charts import money, pct, project_scatter
from dashboard.components.owner_pl_tree import _month_key


def _pivot(df: pd.DataFrame, group_col: str, value_col: str,
           months: list[str]) -> pd.DataFrame:
    pivot = (
        df.groupby([group_col, "month"])[value_col]
        .sum()
        .unstack("month")
        .reindex(columns=months, fill_value=0)
    )
    pivot["Итого"] = pivot.sum(axis=1)
    return pivot.sort_values("Итого", ascending=False)


def render_agency_earnings(margin_df: pd.DataFrame, months: list[str]) -> None:
    st.subheader("💼 Заработок агентства — агентская комиссия и маржа клиентов")

    if margin_df is None or margin_df.empty:
        st.info("Нет данных по проектам")
        return

    df = margin_df[margin_df["month"].isin(months)].copy() if months else margin_df

    # ── KPI ──────────────────────────────────────────────────────────────
    works     = float(df["works"].sum())
    expenses  = float(df["expenses"].sum())
    margin    = float(df["margin"].sum())
    n_clients = df["project"].nunique() if "project" in df.columns else 0
    avg_check = works / n_clients if n_clients else 0.0

    last_month = sorted(months, key=_month_key)[-1] if months else None
    n_clients_last = (
        df[df["month"] == last_month]["project"].nunique()
        if last_month and "project" in df.columns else 0
    )

    cols = st.columns(3)
    cols[0].metric("Маржа клиентов", money(margin))
    cols[1].metric("Средний чек",    money(avg_check))
    cols[2].metric(f"Активных клиентов ({last_month})", n_clients_last)

    st.divider()

    # ── Динамика: works/margin по месяцам ────────────────────────────────
    monthly = (
        df.groupby("month").agg(
            works=("works", "sum"),
            margin=("margin", "sum"),
            expenses=("expenses", "sum"),
        ).reindex(months).fillna(0).reset_index()
    )
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Агентская комиссия", x=monthly["month"], y=monthly["works"],
        marker_color="#2196F3",
        text=monthly["works"].apply(money), textposition="outside",
    ))
    fig.add_trace(go.Bar(
        name="Маржа клиентов", x=monthly["month"], y=monthly["margin"],
        marker_color="#4CAF50",
        text=monthly["margin"].apply(money), textposition="outside",
    ))
    fig.update_layout(
        barmode="group", height=380,
        title="Динамика по месяцам",
        margin=dict(t=50, b=20, l=20, r=20),
        plot_bgcolor="white", paper_bgcolor="white",
        yaxis=dict(tickformat=",", showgrid=True, gridcolor="#f0f0f0"),
        legend=dict(orientation="h", y=-0.2),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Топ клиентов ─────────────────────────────────────────────────────
    st.markdown("**Топ-15 клиентов по выручке**")
    top_works = _pivot(df, "project", "works", months).head(15)
    if not top_works.empty:
        st.dataframe(top_works.style.format({c: money for c in top_works.columns}),
                     use_container_width=True)

    st.markdown("**Топ-15 клиентов по марже**")
    top_margin = _pivot(df, "project", "margin", months).head(15)
    if not top_margin.empty:
        st.dataframe(top_margin.style.format({c: money for c in top_margin.columns}),
                     use_container_width=True)

    st.divider()

    # ── Scatter: works vs margin% per project ────────────────────────────
    if months:
        focus = st.selectbox("Месяц для скаттер-плота", months,
                             index=len(months) - 1, key="agency_scatter_month")
        # build a project_df-shape df expected by project_scatter
        scatter_df = df.copy()
        scatter_df["ebit"] = scatter_df["margin"]  # no allocations here, use margin
        st.plotly_chart(project_scatter(scatter_df, focus), use_container_width=True)

    st.divider()

    # ── Разбивка по платформам ───────────────────────────────────────────
    st.markdown("**По площадке × месяц (агентская комиссия)**")
    by_platform = _pivot(df, "platform", "works", months)
    if not by_platform.empty:
        st.dataframe(by_platform.style.format({c: money for c in by_platform.columns}),
                     use_container_width=True)

    st.markdown("**По менеджеру × месяц (маржа)**")
    by_mgr = _pivot(df, "manager", "margin", months)
    if not by_mgr.empty:
        st.dataframe(by_mgr.style.format({c: money for c in by_mgr.columns}),
                     use_container_width=True)
