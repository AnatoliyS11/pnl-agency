"""
Detail panel tab — drill-down view in the same P&L-style format.

Pick a section + dimension, see a full month-by-month breakdown
with the same visual styling as the main P&L tree.
"""

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from dashboard.components.charts import money, money_compact
from dashboard.components.owner_pl_tree import (
    _COMMERCIAL_GROUPS, _OPERATIONAL_GROUPS, _FINANCIAL_GROUPS,
    EMPLOYER_TAX_RATE,
)

_DIMS = {
    "Выручка": [
        ("По платформе / сервису", "platform", "works"),
        ("По клиенту (проект)",    "project",  "works"),
        ("По менеджеру",           "manager",  "works"),
        ("По специалисту",         "specialist", "works"),
    ],
    "ФОТ производства": [
        ("По сотруднику (ФИО)",        "name", "total_accrued"),
        ("По роли / должности",         "role", "total_accrued"),
        ("По структуре (ФИКС/KPI/Налоги)", "__structure__", None),
        ("По роли + структура",         "__role_structure__", None),
    ],
    "Коммерческие расходы": [
        ("По категории", "category", None),  # value_col = overhead_calc
        ("По группе",    "group",    None),
    ],
    "Операционные расходы": [
        ("По категории", "category", None),
        ("По группе",    "group",    None),
    ],
    "Финансовые расходы": [
        ("По категории", "category", None),
    ],
}


_PANEL_STYLE = """
<style>
.dp-table{width:100%;border-collapse:collapse;font-size:13px;
  font-family:Inter,Arial,sans-serif;}
.dp-table th{padding:8px 12px;text-align:right;
  background:#1a237e;color:#fff;font-weight:600;border:1px solid #283593;}
.dp-table th:first-child{text-align:left;min-width:240px;}
.dp-table td{padding:6px 12px;border-bottom:1px solid #eeeeee;}
.dp-table td:first-child{text-align:left;font-weight:500;}
.dp-table td:not(:first-child){text-align:right;font-variant-numeric:tabular-nums;}
.dp-table tr.total td{background:#E3F2FD;font-weight:700;
  border-top:2px solid #1976D2;}
.dp-table tr:hover td{background:#FAFAFA;}
.dp-table tr.total:hover td{background:#E3F2FD;}
</style>
"""


def _pivot_to_html(pivot: pd.DataFrame, months: list[str], total_label: str = "Итого") -> str:
    """Render a pivot DataFrame as a styled HTML table with month columns + total row."""
    cols = months + [total_label]
    head = "".join(f"<th>{c}</th>" for c in cols)
    thead = f"<thead><tr><th>Статья</th>{head}</tr></thead>"

    body = []
    for label, row in pivot.iterrows():
        cells = [f"<td>{label}</td>"]
        for c in cols:
            v = row.get(c, 0)
            cells.append(f"<td>{money_compact(v)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")

    # Total row
    totals = pivot.sum(axis=0)
    tcells = [f"<td>ВСЕГО</td>"]
    for c in cols:
        tcells.append(f"<td>{money_compact(totals.get(c, 0))}</td>")
    body.append("<tr class='total'>" + "".join(tcells) + "</tr>")

    return f"{_PANEL_STYLE}<table class='dp-table'>{thead}<tbody>{''.join(body)}</tbody></table>"


def _build_pivot(df: pd.DataFrame, group_col: str, value_col: str,
                 months: list[str]) -> pd.DataFrame:
    """Group by group_col × month, return pivot with months as columns."""
    df_m = df[df["month"].isin(months)] if "month" in df.columns else df
    if df_m.empty:
        return pd.DataFrame()
    pivot = (
        df_m.groupby([group_col, "month"])[value_col]
        .sum()
        .unstack("month")
        .reindex(columns=months, fill_value=0)
    )
    pivot["Итого"] = pivot.sum(axis=1)
    pivot = pivot.sort_values("Итого", ascending=False)
    return pivot


def _salary_structure_pivot(salary_df: pd.DataFrame, months: list[str]) -> pd.DataFrame:
    rows = []
    for m in months:
        sdf = salary_df[salary_df["month"] == m]
        if sdf.empty:
            continue
        accrued = float(sdf["total_accrued"].sum())
        rows += [
            {"k": "ФИКС",            "month": m, "v": float(sdf["fiks"].sum())},
            {"k": "KPI / Активити",  "month": m, "v": float(sdf["activity"].sum())},
            {"k": "Налоги (30,2%)",  "month": m, "v": accrued * EMPLOYER_TAX_RATE},
        ]
    if not rows:
        return pd.DataFrame()
    pivot = (
        pd.DataFrame(rows).groupby(["k", "month"])["v"].sum()
        .unstack("month").reindex(columns=months, fill_value=0)
    )
    pivot["Итого"] = pivot.sum(axis=1)
    return pivot


def _salary_role_structure_pivot(salary_df: pd.DataFrame, months: list[str]) -> pd.DataFrame:
    rows = []
    for m in months:
        sdf = salary_df[salary_df["month"] == m]
        for role, grp in sdf.groupby("role"):
            accrued = float(grp["total_accrued"].sum())
            rows += [
                {"k": f"{role} / ФИКС",   "month": m, "v": float(grp["fiks"].sum())},
                {"k": f"{role} / KPI",    "month": m, "v": float(grp["activity"].sum())},
                {"k": f"{role} / Налоги", "month": m, "v": accrued * EMPLOYER_TAX_RATE},
            ]
    if not rows:
        return pd.DataFrame()
    pivot = (
        pd.DataFrame(rows).groupby(["k", "month"])["v"].sum()
        .unstack("month").reindex(columns=months, fill_value=0)
    )
    pivot["Итого"] = pivot.sum(axis=1)
    return pivot.sort_values("Итого", ascending=False)


def _top_n_bar(pivot: pd.DataFrame, months: list[str], top_n: int = 10) -> go.Figure:
    """Top-N rows bar chart by month."""
    if pivot.empty:
        return go.Figure()
    top = pivot.head(top_n)
    fig = go.Figure()
    for m in months:
        if m in top.columns:
            fig.add_trace(go.Bar(
                name=m, x=top.index, y=top[m],
                text=top[m].apply(money_compact), textposition="outside",
            ))
    fig.update_layout(
        barmode="group", height=400,
        title=f"Топ-{top_n} по сумме",
        margin=dict(t=50, b=80, l=20, r=20),
        plot_bgcolor="white", paper_bgcolor="white",
        yaxis=dict(tickformat=",", showgrid=True, gridcolor="#f0f0f0"),
        xaxis=dict(tickangle=-25),
        legend=dict(orientation="h", y=-0.3),
    )
    return fig


def render_detail_panel(
    pl_df: pd.DataFrame,
    overhead_df: pd.DataFrame,
    margin_df: pd.DataFrame | None,
    salary_df: pd.DataFrame | None,
    months: list[str],
    overhead_calc: str = "actual",
) -> None:
    st.subheader("🔍 Детализация — полный разрез по разделам")
    st.caption(
        "Выберите раздел P&L и измерение для глубокой аналитики. "
        "Данные показаны в том же оформлении, что и сводная панель."
    )

    cols = st.columns([2, 3])
    section = cols[0].selectbox("Раздел", list(_DIMS.keys()), key="dp_section")
    dim_options = [d[0] for d in _DIMS[section]]
    dim_label = cols[1].selectbox("Измерение", dim_options, key="dp_dim")

    dim_meta = next(d for d in _DIMS[section] if d[0] == dim_label)
    _, group_col, value_col_default = dim_meta

    # Resolve source df + value column
    pivot = pd.DataFrame()
    if section == "Выручка":
        if margin_df is None or margin_df.empty:
            st.info("Нет данных по проектам")
            return
        pivot = _build_pivot(margin_df, group_col, value_col_default, months)

    elif section == "ФОТ производства":
        if salary_df is None or salary_df.empty:
            st.info("Нет данных по сотрудникам")
            return
        if group_col == "__structure__":
            pivot = _salary_structure_pivot(salary_df, months)
        elif group_col == "__role_structure__":
            pivot = _salary_role_structure_pivot(salary_df, months)
        else:
            pivot = _build_pivot(salary_df, group_col, value_col_default, months)

    else:  # Overhead-based sections
        groups_map = {
            "Коммерческие расходы": _COMMERCIAL_GROUPS,
            "Операционные расходы": _OPERATIONAL_GROUPS,
            "Финансовые расходы":   _FINANCIAL_GROUPS,
        }
        if overhead_df is None or overhead_df.empty:
            st.info("Нет данных по накладным расходам")
            return
        sub = overhead_df[overhead_df["group"].isin(groups_map[section])]
        pivot = _build_pivot(sub, group_col, overhead_calc, months)

    if pivot.empty:
        st.info("Нет данных для выбранного разреза")
        return

    # ── Render ──────────────────────────────────────────────────────────
    st.markdown(_pivot_to_html(pivot, months), unsafe_allow_html=True)

    st.divider()

    # ── Top-N chart ─────────────────────────────────────────────────────
    st.plotly_chart(_top_n_bar(pivot, months, top_n=10), use_container_width=True)

    # ── Sortable table (full) ───────────────────────────────────────────
    with st.expander("Полная таблица (сортируемая)"):
        st.dataframe(pivot.style.format({c: money for c in pivot.columns}),
                     use_container_width=True)
