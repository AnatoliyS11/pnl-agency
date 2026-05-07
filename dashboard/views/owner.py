"""Owner view: tabs for summary P&L, drill-down detail, salary editor, refunds, agency earnings."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from dashboard.components.charts import (
    multi_metric_bar, overhead_breakdown_chart,
    expense_pie_chart, money, pct
)
from dashboard.components.owner_pl_tree import render_owner_pl_tree
from dashboard.components.detail_panel import render_detail_panel
from dashboard.components.salary_editor import render_salary_editor
from dashboard.components.refunds_view import render_refunds
from dashboard.components.agency_view import render_agency_earnings

DEFAULT_TARGETS = {
    "gross_margin_pct":        {"label": "Валовая маржа %",       "good": "above", "default": 50.0},
    "contribution_margin_pct": {"label": "Маржа вклада %",        "good": "above", "default": 30.0},
    "ebit_pct":                {"label": "EBIT %",                "good": "above", "default": 15.0},
    "fot_pct":                 {"label": "ФОТ / Выручка %",       "good": "below", "default": 35.0},
    "overhead_pct":            {"label": "Накладные / Выручка %", "good": "below", "default": 25.0},
}


def _gauge(value: float, target: float, title: str, good: str = "above") -> go.Figure:
    if good == "above":
        bar_color = "#388E3C" if value >= target else "#D32F2F"
        steps = [
            {"range": [0, target], "color": "#FFEBEE"},
            {"range": [target, max(value * 1.3, target * 1.5)], "color": "#E8F5E9"},
        ]
    else:
        bar_color = "#388E3C" if value <= target else "#D32F2F"
        steps = [
            {"range": [0, target], "color": "#E8F5E9"},
            {"range": [target, max(value * 1.3, target * 1.5)], "color": "#FFEBEE"},
        ]
    max_val = max(value * 1.3, target * 1.5, 1.0)
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=value,
        delta={"reference": target, "valueformat": ".1f",
               "increasing": {"color": "#388E3C" if good == "above" else "#D32F2F"},
               "decreasing": {"color": "#D32F2F" if good == "above" else "#388E3C"}},
        number={"suffix": "%", "valueformat": ".1f"},
        title={"text": title, "font": {"size": 13}},
        gauge={
            "axis": {"range": [0, max_val], "ticksuffix": "%"},
            "bar": {"color": bar_color, "thickness": 0.25},
            "steps": steps,
            "threshold": {"line": {"color": "#1a237e", "width": 3},
                          "thickness": 0.75, "value": target},
        },
    ))
    fig.update_layout(height=220, margin=dict(t=50, b=10, l=20, r=20))
    return fig


def _compute_ratios(row: pd.Series) -> dict:
    rev = float(row.get("revenue", 0) or 0) or 1.0
    fot = float(row.get("fot", 0) or 0)
    oh  = float(row.get("overhead", 0) or 0)
    return {
        "gross_margin_pct":        float(row.get("gross_margin_pct", 0) or 0),
        "contribution_margin_pct": float(row.get("contribution_margin_pct", 0) or 0),
        "ebit_pct":                float(row.get("ebit_pct", 0) or 0),
        "fot_pct":                 fot / rev * 100,
        "overhead_pct":            oh  / rev * 100,
    }


def _render_summary_tab(
    pl_df: pd.DataFrame, overhead_df: pd.DataFrame,
    margin_df: pd.DataFrame | None, salary_df: pd.DataFrame | None,
    months: list[str], overhead_calc: str,
) -> None:
    """The classic owner summary view: KPIs, benchmarks, P&L tree, pie chart, dynamics."""
    months_available = pl_df["month"].tolist()
    sel_cols = st.columns([2, 3])
    focus_month = sel_cols[0].selectbox(
        "📅 Фокусный месяц", months_available,
        index=len(months_available) - 1, key="owner_focus",
        help="Gauge-индикаторы и диаграмма расходов строятся по этому месяцу.",
    )
    compare_months = sel_cols[1].multiselect(
        "Сравнивать с", [m for m in months_available if m != focus_month],
        default=[m for m in months_available if m != focus_month],
        key="owner_compare",
    )
    active_months = [focus_month] + compare_months
    pl_active = pl_df[pl_df["month"].isin(active_months)].copy()
    focus_row = pl_df[pl_df["month"] == focus_month].iloc[0]

    prev_row = None
    if compare_months:
        try:
            prev_idx = months_available.index(focus_month) - 1
            if prev_idx >= 0 and months_available[prev_idx] in compare_months:
                prev_row = pl_df[pl_df["month"] == months_available[prev_idx]].iloc[0]
        except (ValueError, IndexError):
            pass

    st.divider()

    # KPI row
    st.subheader("Ключевые показатели")

    def _delta(curr, prev):
        if prev is None or prev == 0:
            return None
        return f"{(curr - prev) / abs(prev) * 100:+.1f}%".replace(".", ",")

    kcols = st.columns(4)
    kcols[0].metric("Выручка", money(focus_row["revenue"]),
                    delta=_delta(focus_row["revenue"],
                                 prev_row["revenue"] if prev_row is not None else None))
    kcols[1].metric("Валовая маржа", money(focus_row["gross_margin"]),
                    delta=pct(focus_row["gross_margin_pct"]))
    kcols[2].metric("Маржа вклада", money(focus_row["contribution_margin"]),
                    delta=pct(focus_row["contribution_margin_pct"]))
    kcols[3].metric("EBIT", money(focus_row["ebit"]),
                    delta=pct(focus_row["ebit_pct"]))

    ebit_val     = float(focus_row["ebit"])
    ebit_pct_val = float(focus_row["ebit_pct"])
    if ebit_val < 0:
        st.error(f"{focus_month}: EBIT отрицательный ({money(ebit_val)}) — операционный убыток")
    elif ebit_pct_val < 10:
        st.warning(f"{focus_month}: рентабельность ниже 10%")
    else:
        st.success(f"{focus_month}: рентабельность в норме")

    st.divider()

    # Benchmarks
    st.subheader("Бенчмарки")
    st.caption(
        "Сравниваем с **вашими целями** и **лучшим фактическим месяцем**. "
        "Цели редактируются ниже."
    )

    if "owner_targets" not in st.session_state:
        st.session_state["owner_targets"] = {k: v["default"] for k, v in DEFAULT_TARGETS.items()}

    with st.expander("⚙️ Настроить целевые значения"):
        tcols = st.columns(len(DEFAULT_TARGETS))
        for i, (key, cfg) in enumerate(DEFAULT_TARGETS.items()):
            with tcols[i]:
                st.session_state["owner_targets"][key] = st.number_input(
                    cfg["label"], min_value=0.0, max_value=100.0, step=1.0,
                    value=float(st.session_state["owner_targets"][key]),
                    key=f"owner_target_input_{key}",
                )
        if st.button("Сбросить к дефолтам", key="owner_targets_reset"):
            st.session_state["owner_targets"] = {k: v["default"] for k, v in DEFAULT_TARGETS.items()}
            st.rerun()

    user_targets = st.session_state["owner_targets"]

    pl_df_ext = pl_df.copy()
    pl_df_ext["fot_pct"] = pl_df_ext.apply(
        lambda r: float(r["fot"] or 0) / float(r["revenue"] or 1) * 100, axis=1)
    pl_df_ext["overhead_pct"] = pl_df_ext.apply(
        lambda r: float(r["overhead"] or 0) / float(r["revenue"] or 1) * 100, axis=1)

    focus_ratios = _compute_ratios(focus_row)

    st.markdown("**Сравнение с вашей целью:**")
    g_cols = st.columns(len(DEFAULT_TARGETS))
    for col, (key, cfg) in zip(g_cols, DEFAULT_TARGETS.items()):
        val    = focus_ratios[key]
        target = user_targets[key]
        good   = cfg["good"]
        ok     = (val >= target) if good == "above" else (val <= target)
        col.plotly_chart(_gauge(val, target, cfg["label"], good), use_container_width=True)
        col.caption(f"{'✅' if ok else '❌'} цель {pct(target)}")

    st.markdown("**Сравнение с лучшим вашим фактическим месяцем:**")
    best_cols = st.columns(len(DEFAULT_TARGETS))
    for col, (key, cfg) in zip(best_cols, DEFAULT_TARGETS.items()):
        good = cfg["good"]
        try:
            best_val = (max(pl_df_ext[key]) if good == "above" else min(pl_df_ext[key]))
        except (KeyError, ValueError):
            best_val = 0.0
        best_month = (pl_df_ext.sort_values(key, ascending=(good != "above")).iloc[0]["month"])
        val = focus_ratios[key]
        ok  = (val >= best_val) if good == "above" else (val <= best_val)
        col.plotly_chart(_gauge(val, best_val, cfg["label"], good), use_container_width=True)
        col.caption(f"{'🏆' if ok else '📉'} лучший: {best_month} — {pct(best_val)}")

    st.divider()

    # Per-employee efficiency
    if salary_df is not None and not salary_df.empty:
        st.subheader("Эффективность на сотрудника")
        headcount = salary_df["name"].nunique() if "name" in salary_df.columns else None
        if headcount and headcount > 0:
            eff_cols = st.columns(len(pl_active) + 1)
            eff_cols[0].metric("Штат (уник. ФИО)", headcount)
            for i, (_, row) in enumerate(pl_active.iterrows()):
                r = float(row.get("revenue", 0) or 0)
                m = float(row.get("gross_margin", 0) or 0)
                e = float(row.get("ebit", 0) or 0)
                with eff_cols[i + 1]:
                    st.markdown(f"**{row['month']}**")
                    st.metric("Выручка/чел", money(r / headcount))
                    st.metric("Маржа/чел",   money(m / headcount))
                    st.metric("EBIT/чел",    money(e / headcount))
        else:
            st.info("Нет данных по сотрудникам для расчёта эффективности")
        st.divider()

    # Pioneer P&L tree (with collapse + level switcher)
    st.subheader("Структура P&L")
    render_owner_pl_tree(
        pl_df, overhead_df, margin_df, salary_df,
        months=active_months, overhead_calc=overhead_calc,
    )

    st.divider()

    # Expense structure pie chart
    st.subheader(f"Структура расходов и прибыли — {focus_month}")
    st.plotly_chart(
        expense_pie_chart(focus_row, overhead_df, overhead_calc, focus_month),
        use_container_width=True,
    )

    st.divider()

    # Dynamic comparison
    st.subheader("Динамика")
    st.plotly_chart(multi_metric_bar(pl_active), use_container_width=True)

    st.divider()

    # Overhead breakdown
    st.subheader("Накладные расходы")
    if not overhead_df.empty:
        st.plotly_chart(
            overhead_breakdown_chart(overhead_df, calc_type=overhead_calc),
            use_container_width=True,
        )
    else:
        st.info("Файл накладных расходов не найден")

    # Summary table
    st.subheader("Сводная таблица P&L")
    display_cols = {
        "month":                    "Месяц",
        "turnover_vat":             "Оборот с НДС",
        "revenue":                  "Выручка (работы)",
        "gross_margin":             "Валовая маржа",
        "gross_margin_pct":         "Валовая маржа %",
        "fot":                      "ФОТ",
        "contribution_margin":      "Маржа вклада",
        "contribution_margin_pct":  "Маржа вклада %",
        "overhead":                 "Накладные",
        "ebit":                     "EBIT",
        "ebit_pct":                 "EBIT %",
    }
    tbl = pl_active[list(display_cols.keys())].rename(columns=display_cols)
    pct_cols   = ["Валовая маржа %", "Маржа вклада %", "EBIT %"]
    money_cols = ["Оборот с НДС", "Выручка (работы)", "Валовая маржа", "ФОТ",
                  "Маржа вклада", "Накладные", "EBIT"]
    fmt_dict = {c: money for c in money_cols}
    fmt_dict.update({c: pct for c in pct_cols})
    st.dataframe(tbl.style.format(fmt_dict), use_container_width=True, hide_index=True)


def render(
    pl_df: pd.DataFrame,
    overhead_df: pd.DataFrame,
    margin_df: pd.DataFrame | None = None,
    salary_df: pd.DataFrame | None = None,
    months: list[str] | None = None,
    overhead_calc: str = "actual",
    refunds_df: pd.DataFrame | None = None,
) -> None:
    st.header("Собственник — Сводный P&L")

    if pl_df.empty:
        st.warning("Нет данных для отображения")
        return

    months = months or pl_df["month"].tolist()

    tabs = st.tabs([
        "📊 Сводный P&L",
        "🔍 Детализация",
        "👥 Зарплаты",
        "↩️ Возвраты МП",
        "💼 Заработок агентства",
    ])

    with tabs[0]:
        _render_summary_tab(pl_df, overhead_df, margin_df, salary_df, months, overhead_calc)

    with tabs[1]:
        render_detail_panel(pl_df, overhead_df, margin_df, salary_df, months, overhead_calc)

    with tabs[2]:
        render_salary_editor(salary_df, months)

    with tabs[3]:
        render_refunds(refunds_df, months)

    with tabs[4]:
        render_agency_earnings(margin_df, months)
