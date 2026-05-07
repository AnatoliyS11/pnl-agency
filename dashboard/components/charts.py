"""Reusable Plotly chart builders for the P&L dashboard."""

import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

COLORS = {
    "revenue": "#4CAF50",
    "gross_margin": "#2196F3",
    "contribution_margin": "#FF9800",
    "ebit": "#9C27B0",
    "fot": "#F44336",
    "overhead": "#FF5722",
    "expenses": "#795548",
    "positive": "#4CAF50",
    "negative": "#F44336",
    "neutral": "#607D8B",
    "jan": "#1976D2",
    "feb": "#42A5F5",
    "forecast": "#90CAF9",
}

MONTH_COLORS = {
    "Январь 2026": COLORS["jan"],
    "Февраль 2026": COLORS["feb"],
    "Март 2026 (прогноз)": COLORS["forecast"],
}


def money(v, unit: str = " ₽") -> str:
    """Russian money format: '1 234 567,89 ₽' (space thousands, comma decimals, 2 decimals)."""
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return str(v)
    sign = "-" if fv < 0 else ""
    s = f"{abs(fv):,.2f}"                          # '1,234,567.89'
    s = s.replace(",", "\u00a0").replace(".", ",").replace("\u00a0", " ")
    return f"{sign}{s}{unit}"


def money_compact(v, unit: str = " ₽") -> str:
    """Compact money for charts: '1,56 млн ₽' if ≥1M, else full 'money()' form."""
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return str(v)
    sign = "-" if fv < 0 else ""
    av = abs(fv)
    if av >= 1_000_000:
        s = f"{av/1_000_000:.2f}".replace(".", ",")
        return f"{sign}{s} млн{unit}"
    return money(fv, unit)


def pct(v, decimals: int = 1) -> str:
    """Russian percent format: '10,5%'."""
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    try:
        return f"{float(v):.{decimals}f}".replace(".", ",") + "%"
    except (TypeError, ValueError):
        return str(v)


# Backward-compat aliases
def fmt(v, unit: str = " ₽") -> str:
    return money_compact(v, unit)


def fmt_tbl(v) -> str:
    return money(v, unit="")


def waterfall_chart(pl_row: pd.Series, title: str = "P&L waterfall") -> go.Figure:
    """Horizontal waterfall: revenue → direct exp → gross margin → FOT → contribution → overhead → EBIT.

    Шкала в процентах от выручки, на каждом баре абсолютная сумма + % от выручки.
    Прямые расходы скрываются, если они <0.5% выручки (невидимый бар путает).
    """
    rev  = float(pl_row.get("revenue", 0) or 0) or 1.0  # guard against zero
    d_exp = float(pl_row.get("direct_expenses", 0) or 0)
    fot  = float(pl_row.get("fot", 0) or 0)
    ovh  = float(pl_row.get("overhead", 0) or 0)
    ebit = float(pl_row.get("ebit", 0) or 0)
    gm   = float(pl_row.get("gross_margin", 0) or 0)
    cm   = float(pl_row.get("contribution_margin", 0) or 0)
    ebit_pct_val = float(pl_row.get("ebit_pct", 0) or 0)

    items = [
        ("Выручка (работы)", rev, "absolute"),
    ]
    if abs(d_exp) / abs(rev) >= 0.005:
        items.append(("(−) Прямые расходы", -d_exp, "relative"))
    items += [
        ("= Валовая маржа", None, "total"),
        ("(−) ФОТ юнита", -fot, "relative"),
        ("= Маржа вклада", None, "total"),
        ("(−) Накладные расходы", -ovh, "relative"),
        ("= EBIT", None, "total"),
    ]

    labels, values, measures, texts = [], [], [], []
    for label, val, measure in items:
        labels.append(label)
        if measure == "total":
            # totals auto-computed by Plotly — label shows absolute + % for clarity
            total_val = {"= Валовая маржа": gm, "= Маржа вклада": cm, "= EBIT": ebit}[label]
            values.append(0)
            texts.append(f"{money(total_val)} ({pct(total_val / rev * 100)})")
        else:
            values.append(val)
            texts.append(f"{money(val)} ({pct(val / rev * 100)})")
        measures.append(measure)

    # Reverse so the flow reads top→bottom as Revenue → … → EBIT
    labels   = list(reversed(labels))
    values   = list(reversed(values))
    measures = list(reversed(measures))
    texts    = list(reversed(texts))

    fig = go.Figure(go.Waterfall(
        name="P&L",
        orientation="h",
        measure=measures,
        y=labels,
        x=values,
        text=texts,
        textposition="outside",
        connector={"line": {"color": "#9E9E9E", "dash": "dot"}},
        decreasing={"marker": {"color": "#E57373"}},
        increasing={"marker": {"color": "#81C784"}},
        totals={"marker": {"color": "#5C6BC0"}},
    ))
    fig.update_layout(
        title=f"{title} — EBIT {pct(ebit_pct_val)}",
        showlegend=False,
        height=max(420, 70 * len(labels) + 80),
        margin=dict(t=70, b=30, l=180, r=120),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Inter, Arial", size=13),
        xaxis=dict(showgrid=True, gridcolor="#f0f0f0", tickformat=",", zeroline=True, zerolinecolor="#BDBDBD"),
        yaxis=dict(automargin=True),
    )
    return fig


def dynamic_bar_chart(pl_df: pd.DataFrame, metric: str, title: str) -> go.Figure:
    """Bar chart comparing metric across months."""
    fig = go.Figure()
    for _, row in pl_df.iterrows():
        month = row["month"]
        color = MONTH_COLORS.get(month, "#90A4AE")
        fig.add_trace(go.Bar(
            name=month,
            x=[month],
            y=[row[metric]],
            marker_color=color,
            text=fmt(row[metric]),
            textposition="outside",
        ))
    fig.update_layout(
        title=title,
        height=350,
        barmode="group",
        showlegend=True,
        margin=dict(t=60, b=20, l=20, r=20),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Inter, Arial", size=13),
        yaxis=dict(tickformat=",", showgrid=True, gridcolor="#f0f0f0"),
    )
    return fig


def multi_metric_bar(pl_df: pd.DataFrame) -> go.Figure:
    """Grouped bar chart: revenue, gross margin, ebit per month."""
    metrics = [
        ("revenue", "Выручка", COLORS["revenue"]),
        ("gross_margin", "Валовая маржа", COLORS["gross_margin"]),
        ("contribution_margin", "Маржа вклада", COLORS["contribution_margin"]),
        ("ebit", "EBIT", COLORS["ebit"]),
    ]
    fig = go.Figure()
    for key, label, color in metrics:
        fig.add_trace(go.Bar(
            name=label,
            x=pl_df["month"],
            y=pl_df[key],
            marker_color=color,
            text=pl_df[key].apply(fmt),
            textposition="outside",
        ))
    fig.update_layout(
        title="Динамика ключевых показателей",
        barmode="group",
        height=420,
        margin=dict(t=60, b=20, l=20, r=20),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Inter, Arial", size=13),
        yaxis=dict(tickformat=",", showgrid=True, gridcolor="#f0f0f0"),
        legend=dict(orientation="h", y=-0.15),
    )
    return fig


def margin_pct_line(pl_df: pd.DataFrame) -> go.Figure:
    """Line chart: margin %, EBIT % dynamics."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=pl_df["month"], y=pl_df["gross_margin_pct"],
        name="Валовая маржа %", mode="lines+markers+text",
        marker=dict(size=10, color=COLORS["gross_margin"]),
        line=dict(width=2, color=COLORS["gross_margin"]),
        text=[pct(v) for v in pl_df["gross_margin_pct"]],
        textposition="top center",
    ))
    fig.add_trace(go.Scatter(
        x=pl_df["month"], y=pl_df["contribution_margin_pct"],
        name="Маржа вклада %", mode="lines+markers+text",
        marker=dict(size=10, color=COLORS["contribution_margin"]),
        line=dict(width=2, color=COLORS["contribution_margin"]),
        text=[pct(v) for v in pl_df["contribution_margin_pct"]],
        textposition="top center",
    ))
    fig.add_trace(go.Scatter(
        x=pl_df["month"], y=pl_df["ebit_pct"],
        name="EBIT %", mode="lines+markers+text",
        marker=dict(size=10, color=COLORS["ebit"]),
        line=dict(width=2, color=COLORS["ebit"]),
        text=[pct(v) for v in pl_df["ebit_pct"]],
        textposition="top center",
    ))
    fig.update_layout(
        title="Рентабельность по месяцам",
        height=350,
        margin=dict(t=60, b=20, l=20, r=20),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Inter, Arial", size=13),
        yaxis=dict(ticksuffix="%", showgrid=True, gridcolor="#f0f0f0"),
        legend=dict(orientation="h", y=-0.2),
    )
    return fig


def overhead_breakdown_chart(overhead_df: pd.DataFrame, calc_type: str = "actual") -> go.Figure:
    """Stacked bar: overhead by category per month."""
    if overhead_df.empty:
        return go.Figure()

    non_fot = overhead_df[~overhead_df["category"].str.startswith("ФОТ")]
    grouped = non_fot.groupby(["group", "month"])[calc_type].sum().reset_index()
    pivot = grouped.pivot(index="group", columns="month", values=calc_type).fillna(0)

    fig = go.Figure()
    months = sorted(grouped["month"].unique())
    palette = px.colors.qualitative.Set2
    for i, month in enumerate(months):
        col_data = pivot.get(month, pd.Series(0, index=pivot.index))
        fig.add_trace(go.Bar(
            name=month,
            x=pivot.index,
            y=col_data,
            marker_color=MONTH_COLORS.get(month, palette[i % len(palette)]),
            text=col_data.apply(lambda v: fmt(v) if v else ""),
            textposition="outside",
        ))

    fig.update_layout(
        title="Накладные расходы по категориям",
        barmode="group",
        height=400,
        margin=dict(t=60, b=80, l=20, r=20),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Inter, Arial", size=12),
        xaxis=dict(tickangle=-20),
        yaxis=dict(tickformat=",", showgrid=True, gridcolor="#f0f0f0"),
        legend=dict(orientation="h", y=-0.3),
    )
    return fig


def expense_pie_chart(
    pl_row: pd.Series,
    overhead_df: pd.DataFrame,
    overhead_calc: str = "actual",
    month: str | None = None,
) -> go.Figure:
    """Donut chart of expense + profit structure for a single month."""
    rev = float(pl_row.get("revenue", 1) or 1)
    fot = float(pl_row.get("fot", 0) or 0)
    de  = float(pl_row.get("direct_expenses", 0) or 0)

    _COMMERCIAL = {"Продажи", "Маркетинг"}
    _OPERATIONAL = {"Административные", "Офис", "IT и бизнес-процессы", "Персонал"}
    _FINANCIAL = {"Финансовые расходы"}
    _SERVICES = {"Сервисы"}

    services = commercial = operational = financial = 0.0
    if not overhead_df.empty and month:
        moh = overhead_df[overhead_df["month"] == month]
        services    = float(moh[moh["group"].isin(_SERVICES)   ][overhead_calc].sum())
        commercial  = float(moh[moh["group"].isin(_COMMERCIAL) ][overhead_calc].sum())
        operational = float(moh[moh["group"].isin(_OPERATIONAL)][overhead_calc].sum())
        financial   = float(moh[moh["group"].isin(_FINANCIAL)  ][overhead_calc].sum())

    total_costs = de + fot + services + commercial + operational + financial
    profit = max(rev - total_costs, 0)

    segments = [
        ("Прямые расходы",       de,          "#EF9A9A"),
        ("ФОТ производства",     fot,         "#FFCC80"),
        ("Сервисы производства", services,    "#CE93D8"),
        ("Коммерческие расходы", commercial,  "#F48FB1"),
        ("Операционные расходы", operational, "#80CBC4"),
        ("Финансовые расходы",   financial,   "#90CAF9"),
        ("Прибыль",              profit,      "#A5D6A7"),
    ]
    labels_f = [s[0] for s in segments if s[1] > 0]
    values_f = [s[1] for s in segments if s[1] > 0]
    colors_f = [s[2] for s in segments if s[1] > 0]

    if not labels_f:
        return go.Figure()

    fig = go.Figure(go.Pie(
        labels=labels_f,
        values=values_f,
        hole=0.4,
        marker_colors=colors_f,
        textinfo="label+percent",
        hovertemplate="%{label}: %{value:,.0f} ₽ (%{percent})<extra></extra>",
    ))
    fig.update_layout(
        title=f"Структура расходов и прибыли — {month or ''}",
        height=420,
        margin=dict(t=60, b=20, l=20, r=20),
        font=dict(family="Inter, Arial", size=12),
        legend=dict(orientation="v", x=1.0),
    )
    return fig


def project_scatter(project_df: pd.DataFrame, month: str) -> go.Figure:
    """Scatter: project margin vs revenue, sized by EBIT."""
    df = project_df[project_df["month"] == month].copy()
    if df.empty:
        return go.Figure()

    # Aggregate by project
    agg = df.groupby("project").agg(
        works=("works", "sum"),
        margin=("margin", "sum"),
        ebit=("ebit", "sum"),
        manager=("manager", "first"),
    ).reset_index()
    agg["margin_pct"] = agg.apply(lambda r: r["margin"] / r["works"] * 100 if r["works"] else 0, axis=1)
    agg["size"] = agg["works"].apply(lambda v: max(v / 1000, 5))

    fig = px.scatter(
        agg, x="works", y="margin_pct",
        size="size", color="manager",
        hover_name="project",
        hover_data={"works": ":,.0f", "margin": ":,.0f", "ebit": ":,.0f", "size": False},
        title=f"Проекты: выручка vs маржа % — {month}",
        labels={"works": "Выручка (руб)", "margin_pct": "Маржа %"},
    )
    fig.update_layout(
        height=420,
        margin=dict(t=60, b=20, l=20, r=20),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Inter, Arial", size=12),
    )
    return fig
