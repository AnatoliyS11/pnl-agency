"""Director view: projects, managers, staff breakdown, alerts, platform and trend analysis."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dashboard.components.charts import project_scatter, money, pct

# ── FOT scenario constants (must match parser.data_model) ─────────────────────
_EMPLOYEE_MULT = 1.302


def _trend_delta(curr: float, prev: float) -> str | None:
    """↑ +12,3% or ↓ −5,1% comparison string, or None if prev ≤ 0."""
    if prev is None or prev == 0:
        return None
    change = (curr - prev) / abs(prev) * 100
    arrow = "↑" if change > 0 else ("↓" if change < 0 else "→")
    return f"{arrow} {change:+.1f}%".replace(".", ",")


def _alert_panel(df: pd.DataFrame):
    """Show warnings for problematic projects."""
    loss = df[df["margin"] < 0]
    no_manager = df[df["manager"].isna() | (df["manager"] == "")]
    low_margin = df[(df["margin"] >= 0) & (df["margin_pct"] < 5)]

    issues = []
    if not loss.empty:
        issues.append(("error", f"{len(loss)} убыточных проект(а): маржа < 0",
                       loss[["project", "manager", "margin"]].head(5)))
    if not low_margin.empty:
        issues.append(("warning", f"{len(low_margin)} проект(а) с маржой ниже 5%",
                       low_margin[["project", "manager", "margin_pct"]].head(5)))
    if not no_manager.empty:
        issues.append(("warning", f"{len(no_manager)} проект(а) без менеджера",
                       no_manager[["project"]].head(5)))

    if not issues:
        st.success("Нет критических отклонений по проектам")
        return

    for level, msg, detail in issues:
        if level == "error":
            st.error(f"⚠️ {msg}")
        else:
            st.warning(f"⚡ {msg}")
        with st.expander("Подробнее"):
            st.dataframe(detail.style.format({
                "margin": money, "margin_pct": pct
            }), hide_index=True)


def _platform_chart(df: pd.DataFrame) -> go.Figure:
    """Horizontal bar chart: platforms ranked by gross margin."""
    plat = (
        df.groupby("platform")
        .agg(works=("works", "sum"), margin=("margin", "sum"), ebit=("ebit", "sum"))
        .reset_index()
    )
    plat = plat.sort_values("margin", ascending=True)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=plat["platform"], x=plat["works"],
        name="Выручка", orientation="h",
        marker_color="#90CAF9", opacity=0.7,
    ))
    fig.add_trace(go.Bar(
        y=plat["platform"], x=plat["margin"],
        name="Валовая маржа", orientation="h",
        marker_color="#A5D6A7",
    ))
    fig.add_trace(go.Bar(
        y=plat["platform"], x=plat["ebit"],
        name="EBIT", orientation="h",
        marker_color="#CE93D8",
    ))
    fig.update_layout(
        title="Рейтинг площадок",
        barmode="group",
        xaxis_title="Руб.",
        height=max(250, len(plat) * 60 + 80),
        margin=dict(t=50, b=20, l=120, r=20),
        legend=dict(orientation="h", y=-0.15),
    )
    return fig


def _manager_heatmap(df: pd.DataFrame) -> go.Figure | None:
    """Heatmap: manager × platform by margin %."""
    pivot = df.pivot_table(
        index="manager", columns="platform",
        values="margin_pct", aggfunc="mean"
    )
    if pivot.empty or pivot.shape[0] < 2:
        return None

    fig = px.imshow(
        pivot,
        color_continuous_scale=[[0, "#D32F2F"], [0.3, "#FFCC02"], [1, "#388E3C"]],
        aspect="auto",
        labels=dict(color="Маржа %"),
        title="Маржинальность: менеджер × площадка (%)",
        text_auto=".1f",
    )
    fig.update_layout(height=max(250, pivot.shape[0] * 50 + 100),
                      margin=dict(t=60, b=20, l=20, r=20))
    return fig


# ── Block D: employees ────────────────────────────────────────────────────────

def _employee_breakdown(
    margin_month_df: pd.DataFrame,
    salary_month_df: pd.DataFrame,
    fot_scenario: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns (attached_df, unassigned_df).

    attached_df: сотрудники, у которых есть проекты (как менеджер или специалист).
      columns: name, role, fot, margin_manager, margin_specialist,
               attribution, roi, projects_manager, projects_specialist
    unassigned_df: сотрудники, которых нет ни в менеджерах, ни в специалистах.
      columns: name, role, fot
    """
    if salary_month_df.empty:
        empty = pd.DataFrame(columns=["name", "role", "fot"])
        return empty, empty

    # Apply scenario multiplier once per row
    if fot_scenario == "employee":
        fot_per_name = (salary_month_df.groupby(["name", "role"])["total_accrued"]
                        .sum() * _EMPLOYEE_MULT)
    else:
        fot_per_name = (salary_month_df.assign(
            fot=salary_month_df["fiks"] + salary_month_df["activity"]
        ).groupby(["name", "role"])["fot"].sum())

    fot_df = fot_per_name.reset_index(name="fot")

    # Aggregate margin by manager/specialist (projects_* = unique projects count)
    if margin_month_df.empty:
        margin_as_mgr = pd.DataFrame(columns=["name", "margin_manager", "projects_manager"])
        margin_as_spec = pd.DataFrame(columns=["name", "margin_specialist", "projects_specialist"])
    else:
        m_mgr = (margin_month_df.dropna(subset=["manager"])
                 .query("manager != ''")
                 .groupby("manager")
                 .agg(margin_manager=("margin", "sum"),
                      projects_manager=("project", "nunique"))
                 .reset_index().rename(columns={"manager": "name"}))
        m_spec = (margin_month_df.dropna(subset=["specialist"])
                  .query("specialist != ''")
                  .groupby("specialist")
                  .agg(margin_specialist=("margin", "sum"),
                       projects_specialist=("project", "nunique"))
                  .reset_index().rename(columns={"specialist": "name"}))
        margin_as_mgr, margin_as_spec = m_mgr, m_spec

    df = (fot_df
          .merge(margin_as_mgr, on="name", how="left")
          .merge(margin_as_spec, on="name", how="left"))
    for col in ["margin_manager", "margin_specialist",
                "projects_manager", "projects_specialist"]:
        df[col] = df[col].fillna(0)

    df["attribution"] = df["margin_manager"] * 0.5 + df["margin_specialist"] * 0.5
    df["roi"] = df.apply(
        lambda r: (r["attribution"] / r["fot"]) if r["fot"] else 0.0, axis=1
    )

    has_projects = (df["margin_manager"] != 0) | (df["margin_specialist"] != 0)
    attached = df[has_projects].copy().sort_values("roi", ascending=False)
    unassigned = df[~has_projects][["name", "role", "fot"]].copy().sort_values("fot", ascending=False)
    return attached, unassigned


def _employee_bar_chart(attached: pd.DataFrame) -> go.Figure:
    """Horizontal paired bars: ФОТ vs атрибуция, сортировка по ROI."""
    if attached.empty:
        return go.Figure()
    df = attached.sort_values("roi", ascending=True).copy()  # ascending so best on top
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=df["name"], x=df["fot"],
        name="ФОТ", orientation="h",
        marker_color="#EF9A9A",
        text=[money(v) for v in df["fot"]], textposition="auto",
    ))
    fig.add_trace(go.Bar(
        y=df["name"], x=df["attribution"],
        name="Атрибуция маржи", orientation="h",
        marker_color="#81C784",
        text=[money(v) for v in df["attribution"]], textposition="auto",
    ))
    fig.update_layout(
        title="Сотрудники: ФОТ vs атрибутированная маржа (сортировка по ROI)",
        barmode="group",
        height=max(320, len(df) * 55 + 80),
        margin=dict(t=60, b=20, l=140, r=60),
        xaxis_title="Руб.",
        legend=dict(orientation="h", y=-0.15),
    )
    return fig


# ── Block G: top/anti-top and MoM decline ─────────────────────────────────────

def _top_antitop(df: pd.DataFrame, n: int = 5):
    """Return (top_n, bottom_n) by margin, aggregated per project."""
    agg = (df.groupby(["project", "manager"])
           .agg(works=("works", "sum"),
                margin=("margin", "sum"),
                ebit=("ebit", "sum"),
                margin_pct=("margin_pct", "mean"))
           .reset_index())
    top = agg.sort_values("margin", ascending=False).head(n)
    bottom = agg.sort_values("margin", ascending=True).head(n)
    return top, bottom


def _render_top_table(df: pd.DataFrame, title: str, color: str):
    st.markdown(f"#### {title}")
    if df.empty:
        st.caption("нет данных")
        return
    disp = df.rename(columns={
        "project": "Проект", "manager": "Менеджер МП",
        "works": "Выручка", "margin": "Маржа",
        "ebit": "EBIT", "margin_pct": "Маржа %",
    })
    money_cols = ["Выручка", "Маржа", "EBIT"]
    fmt_d = {c: money for c in money_cols if c in disp.columns}
    fmt_d["Маржа %"] = pct
    st.dataframe(disp.style.format(fmt_d), use_container_width=True, hide_index=True, height=220)


def _mom_decline_table(project_df: pd.DataFrame, months: list[str]):
    """Projects whose margin declined from previous month to current month."""
    if len(months) < 2:
        return None
    m1, m2 = months[-2], months[-1]
    a = (project_df[project_df["month"] == m1]
         .groupby("project")["margin"].sum().rename(f"margin_{m1}"))
    b = (project_df[project_df["month"] == m2]
         .groupby("project")["margin"].sum().rename(f"margin_{m2}"))
    both = pd.concat([a, b], axis=1).dropna()
    both["Δ руб"] = both[f"margin_{m2}"] - both[f"margin_{m1}"]
    both["Δ %"] = both.apply(
        lambda r: (r["Δ руб"] / abs(r[f"margin_{m1}"]) * 100) if r[f"margin_{m1}"] else 0, axis=1
    )
    decline = both[both["Δ руб"] < 0].sort_values("Δ руб").head(10).reset_index()
    return decline, m1, m2


# ── Main render ───────────────────────────────────────────────────────────────

def render(project_df: pd.DataFrame, pl_df: pd.DataFrame, months: list[str],
           salary_df: pd.DataFrame | None = None,
           fot_scenario: str = "employee"):
    st.header("Руководитель направления — Детализация по проектам и штату")

    if project_df.empty:
        st.warning("Нет данных для отображения")
        return

    # Month selector
    available_months = [m for m in months if m in project_df["month"].unique()]
    if not available_months:
        st.warning("Нет доступных месяцев")
        return
    sel_month = st.selectbox("Месяц", available_months,
                             index=len(available_months) - 1, key="dir_month")
    df = project_df[project_df["month"] == sel_month].copy()
    df["margin_pct"] = df.apply(
        lambda r: r["margin"] / r["works"] * 100 if r.get("works") else 0, axis=1
    )

    # Previous month for trends
    prev_idx = available_months.index(sel_month) - 1
    prev_month = available_months[prev_idx] if prev_idx >= 0 else None
    prev_df = project_df[project_df["month"] == prev_month] if prev_month else pd.DataFrame()

    # ── Top KPIs with trend arrows ───────────────────────────────────────────
    total_rev = df["works"].sum()
    total_margin = df["margin"].sum()
    total_ebit = df["ebit"].sum()
    n_projects = df["project"].nunique()
    n_staff = salary_df["name"].nunique() if salary_df is not None and not salary_df.empty else 0

    prev_rev = prev_df["works"].sum() if not prev_df.empty else None
    prev_margin = prev_df["margin"].sum() if not prev_df.empty else None
    prev_ebit = prev_df["ebit"].sum() if not prev_df.empty else None

    kpi_cols = st.columns(5)
    kpi_cols[0].metric("Выручка", money(total_rev),
                       delta=_trend_delta(total_rev, prev_rev))
    kpi_cols[1].metric("Валовая маржа", money(total_margin),
                       delta=_trend_delta(total_margin, prev_margin))
    kpi_cols[2].metric("EBIT", money(total_ebit),
                       delta=_trend_delta(total_ebit, prev_ebit))
    kpi_cols[3].metric("Проектов", n_projects)
    kpi_cols[4].metric("Сотрудников в штате", n_staff,
                       help="Всего уникальных ФИО в ведомости ЗП (включая не привязанных к проектам)")

    st.divider()

    # ── Alerts ────────────────────────────────────────────────────────────────
    st.subheader("Сигналы")
    _alert_panel(df)

    st.divider()

    # ── Block D: Employees breakdown ─────────────────────────────────────────
    if salary_df is not None and not salary_df.empty:
        salary_month = salary_df[salary_df["month"] == sel_month]
        margin_month = df
        attached, unassigned = _employee_breakdown(margin_month, salary_month, fot_scenario)

        st.subheader(f"Сотрудники юнита — {sel_month}")
        st.caption("ФОТ — начисления из ведомости (для «Сотрудника» умножены на 1.302 на страховые). "
                   "**Атрибуция маржи** = половина как менеджер + половина как специалист по всем его проектам. "
                   "**ROI** = Атрибуция / ФОТ.")

        if attached.empty:
            st.info("За этот месяц сотрудники с проектной занятостью не найдены")
        else:
            disp_attached = attached.rename(columns={
                "name": "ФИО", "role": "Роль",
                "fot": "ФОТ",
                "margin_manager": "Маржа (как менеджер)",
                "margin_specialist": "Маржа (как специалист)",
                "attribution": "Атрибуция маржи",
                "roi": "ROI (Маржа/ФОТ)",
                "projects_manager": "Проектов вёл",
                "projects_specialist": "Проектов исп.",
            })

            money_cols = ["ФОТ", "Маржа (как менеджер)",
                          "Маржа (как специалист)", "Атрибуция маржи"]

            def roi_highlight(v):
                if isinstance(v, float):
                    if v < 1.0:
                        return "color:#D32F2F;font-weight:bold"
                    if v < 2.0:
                        return "color:#F57C00;font-weight:bold"
                    return "color:#388E3C;font-weight:bold"
                return ""

            _roi_fmt = lambda v: (f"{v:.2f}".replace(".", ",") + "×") if v else "—"
            fmt_emp = {c: money for c in money_cols}
            fmt_emp["ROI (Маржа/ФОТ)"] = _roi_fmt
            styled = (
                disp_attached.style
                .format(fmt_emp)
                .map(roi_highlight, subset=["ROI (Маржа/ФОТ)"])
            )
            st.dataframe(styled, use_container_width=True, hide_index=True,
                         height=min(45 * len(disp_attached) + 40, 420))

            st.plotly_chart(_employee_bar_chart(attached), use_container_width=True)

        # Unassigned block
        if not unassigned.empty:
            with st.expander(
                f"🏢 Не закреплены за проектами — {len(unassigned)} чел. "
                f"(управленческий ФОТ юнита: {money(unassigned['fot'].sum())})",
                expanded=True,
            ):
                st.caption("Эти сотрудники не ведут проекты напрямую — их ФОТ относится к "
                           "общеуправленческим накладным расходам юнита.")
                unass_disp = unassigned.rename(columns={
                    "name": "ФИО", "role": "Роль", "fot": "ФОТ",
                })
                st.dataframe(
                    unass_disp.style.format({"ФОТ": money}),
                    use_container_width=True, hide_index=True,
                )
        else:
            st.caption("✅ Все сотрудники закреплены за проектами.")

        st.divider()

    # ── Scatter chart ─────────────────────────────────────────────────────────
    st.plotly_chart(project_scatter(project_df, sel_month), use_container_width=True)

    st.divider()

    # ── Top-5 / Anti-top-5 ───────────────────────────────────────────────────
    st.subheader("Топ и анти-топ проектов")
    top, bottom = _top_antitop(df, n=5)
    t_cols = st.columns(2)
    with t_cols[0]:
        _render_top_table(top, "🏆 Флагманы (макс. маржа)", "#388E3C")
    with t_cols[1]:
        _render_top_table(bottom, "⚠️ Проблемные (мин. маржа)", "#D32F2F")

    # ── MoM project decline ──────────────────────────────────────────────────
    mom = _mom_decline_table(project_df, available_months)
    if mom is not None:
        decline, m1, m2 = mom
        if not decline.empty:
            st.subheader(f"Снижение маржи по проектам: {m1} → {m2}")
            st.caption(f"Проекты, у которых маржа в {m2} ниже, чем в {m1}.")
            disp = decline.rename(columns={
                "project": "Проект",
                f"margin_{m1}": f"Маржа {m1}",
                f"margin_{m2}": f"Маржа {m2}",
                "Δ руб": "Δ руб",
                "Δ %": "Δ %",
            })
            fmt_d = {
                f"Маржа {m1}": money,
                f"Маржа {m2}": money,
                "Δ руб": money,
                "Δ %": pct,
            }
            st.dataframe(disp.style.format(fmt_d), use_container_width=True,
                         hide_index=True, height=min(40 * len(disp) + 38, 420))

    st.divider()

    # ── Platform ranking ──────────────────────────────────────────────────────
    st.subheader("Рейтинг площадок")
    st.plotly_chart(_platform_chart(df), use_container_width=True)

    # Manager × platform heatmap
    hm = _manager_heatmap(df)
    if hm is not None:
        st.subheader("Тепловая карта: менеджер × площадка")
        st.plotly_chart(hm, use_container_width=True)

    st.divider()

    # ── Project table with filters ────────────────────────────────────────────
    st.subheader("Таблица проектов")
    filter_cols = st.columns(3)
    managers = ["Все"] + sorted(df["manager"].dropna().unique().tolist())
    platforms = ["Все"] + sorted(df["platform"].dropna().unique().tolist())
    entities = ["Все"] + sorted(df["entity"].dropna().unique().tolist())

    sel_manager  = filter_cols[0].selectbox("Менеджер МП", managers, key="dir_mgr")
    sel_platform = filter_cols[1].selectbox("Площадка", platforms, key="dir_plat")
    sel_entity   = filter_cols[2].selectbox("Компания", entities, key="dir_ent")

    fdf = df.copy()
    if sel_manager  != "Все": fdf = fdf[fdf["manager"]  == sel_manager]
    if sel_platform != "Все": fdf = fdf[fdf["platform"] == sel_platform]
    if sel_entity   != "Все": fdf = fdf[fdf["entity"]   == sel_entity]

    agg = (
        fdf.groupby(["project", "platform", "manager", "specialist"])
        .agg(
            turnover_vat=("turnover_vat", "sum"),
            works=("works", "sum"),
            expenses=("expenses", "sum"),
            margin=("margin", "sum"),
            allocated_fot=("allocated_fot", "sum"),
            allocated_overhead=("allocated_overhead", "sum"),
            ebit=("ebit", "sum"),
        )
        .reset_index()
    )
    agg["margin_pct"] = agg.apply(
        lambda r: r["margin"] / r["works"] * 100 if r["works"] else 0, axis=1
    )
    agg["ebit_pct"] = agg.apply(
        lambda r: r["ebit"] / r["works"] * 100 if r["works"] else 0, axis=1
    )
    agg = agg.sort_values("margin", ascending=False)

    display = agg.rename(columns={
        "project": "Проект", "platform": "Площадка",
        "manager": "Менеджер МП", "specialist": "Специалист",
        "turnover_vat": "Оборот с НДС", "works": "Выручка",
        "expenses": "Расходы", "margin": "Валовая маржа",
        "margin_pct": "Маржа %", "allocated_fot": "ФОТ (аллок)",
        "allocated_overhead": "Накладные (аллок)", "ebit": "EBIT", "ebit_pct": "EBIT %",
    })

    money_cols = ["Оборот с НДС", "Выручка", "Расходы", "Валовая маржа",
                  "ФОТ (аллок)", "Накладные (аллок)", "EBIT"]
    pct_cols_d = ["Маржа %", "EBIT %"]

    def highlight_margin(val):
        if isinstance(val, float) and val < 0:
            return "color: #D32F2F; font-weight: bold"
        if isinstance(val, float) and val < 5:
            return "color: #F57C00"
        return ""

    fmt_proj = {c: money for c in money_cols if c in display.columns}
    fmt_proj.update({c: pct for c in pct_cols_d if c in display.columns})
    styled = (
        display.style
        .format(fmt_proj)
        .map(highlight_margin, subset=[c for c in ["EBIT", "Маржа %"] if c in display.columns])
    )
    st.dataframe(styled, use_container_width=True, height=400, hide_index=True)

    st.divider()

    # ── Manager summary ───────────────────────────────────────────────────────
    st.subheader("Сводка по менеджерам")
    mgr_agg = (
        fdf.groupby("manager")
        .agg(projects=("project", "nunique"), works=("works", "sum"),
             margin=("margin", "sum"), ebit=("ebit", "sum"))
        .reset_index()
    )
    mgr_agg["margin_pct"] = mgr_agg.apply(
        lambda r: r["margin"] / r["works"] * 100 if r["works"] else 0, axis=1
    )
    mgr_agg["выручка_на_проект"] = mgr_agg.apply(
        lambda r: r["works"] / r["projects"] if r["projects"] else 0, axis=1
    )
    mgr_agg["маржа_на_проект"] = mgr_agg.apply(
        lambda r: r["margin"] / r["projects"] if r["projects"] else 0, axis=1
    )
    mgr_agg = mgr_agg.sort_values("margin", ascending=False)

    mgr_display = mgr_agg.rename(columns={
        "manager": "Менеджер", "projects": "Проектов",
        "works": "Выручка", "margin": "Маржа", "ebit": "EBIT",
        "margin_pct": "Маржа %",
        "выручка_на_проект": "Выручка/проект",
        "маржа_на_проект": "Маржа/проект",
    })
    mgr_money = ["Выручка", "Маржа", "EBIT", "Выручка/проект", "Маржа/проект"]
    fmt_mgr = {c: money for c in mgr_money if c in mgr_display.columns}
    if "Маржа %" in mgr_display.columns:
        fmt_mgr["Маржа %"] = pct
    st.dataframe(
        mgr_display.style.format(fmt_mgr),
        use_container_width=True, hide_index=True,
    )
