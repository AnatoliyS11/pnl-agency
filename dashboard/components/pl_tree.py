"""
Hierarchical P&L tree table — mirrors the collapsible structure from the overhead Excel file.

Columns: Показатель | Январь план | Январь факт | Февраль план | Февраль факт | Март (прогноз)
Sections: Доходы → Валовая маржа → ФОТ → Маржа вклада → Накладные (дерево) → EBIT
"""

import pandas as pd
import streamlit as st
from typing import Any

from dashboard.components.charts import money as _money_fmt

# Actual labels are derived from pl_df/forecast_df at render-time.
# These are fallback defaults (used only if data is missing).
MONTHS = ["Январь 2026", "Февраль 2026"]
FORECAST_MONTH = "Март 2026 (прогноз)"

# ── Formatting helpers ────────────────────────────────────────────────────────

def _rub(v: Any) -> str:
    """RU money for table cells: '1 234 567,89' (2 decimals, no ₽)."""
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    try:
        iv = float(v)
    except (TypeError, ValueError):
        return str(v)
    if iv == 0:
        return "0,00"
    return _money_fmt(iv, unit="")


def _pct(v: Any) -> str:
    """Signed RU percent for variance columns: '+10,5%'."""
    if v is None:
        return "—"
    try:
        return f"{float(v):+.1f}%".replace(".", ",")
    except (TypeError, ValueError):
        return str(v)


# ── Row builders ─────────────────────────────────────────────────────────────

_HEADER_STYLE = "background-color:#1a237e;color:white;font-weight:bold"
_TOTAL_STYLE  = "background-color:#E3F2FD;font-weight:bold"
_SUBTOTAL_STYLE = "background-color:#E8F5E9;font-weight:bold"
_NEG_STYLE    = "color:#D32F2F"
_POS_STYLE    = "color:#388E3C"
_GRAY_STYLE   = "color:#607D8B"


def build_pl_tree(
    pl_df: pd.DataFrame,
    overhead_df: pd.DataFrame,
    salary_df: pd.DataFrame,
    fot_scenario: str,
    forecast_df: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict]]:
    """
    Returns (display_df, style_map) where style_map is a list of
    {row_idx: style_string} for apply_map-style coloring.
    """
    rows = []   # list of dicts with display values
    styles = [] # parallel list: each entry is dict {col: css_str}

    # Derive month labels from actual data
    actual_months: list[str] = list(pl_df["month"]) if not pl_df.empty else []
    forecast_month = forecast_df.iloc[0]["month"] if not forecast_df.empty else None

    # Support up to two actual months in the plan/fact layout (most common case).
    month_a = actual_months[0] if len(actual_months) >= 1 else None
    month_b = actual_months[1] if len(actual_months) >= 2 else None

    # Build lookup dicts
    pl_by = {r["month"]: r for _, r in pl_df.iterrows()}
    if forecast_month is not None:
        pl_by[forecast_month] = forecast_df.iloc[0]

    oh_by_cat_month: dict[tuple, dict] = {}
    if not overhead_df.empty:
        for _, r in overhead_df.iterrows():
            key = (r["category"], r["month"])
            oh_by_cat_month[key] = {"plan": r["plan"], "actual": r["actual"]}

    sal_by: dict[str, pd.Series] = {}
    if not salary_df.empty:
        for m in actual_months:
            sub = salary_df[salary_df["month"] == m]
            if not sub.empty:
                sal_by[m] = sub.sum(numeric_only=True)

    def _get(month: str, key: str, default: float = 0.0) -> float:
        r = pl_by.get(month)
        if r is None:
            return default
        try:
            return float(r.get(key, default) or default)
        except (TypeError, ValueError):
            return default

    def add(label: str,
            jan_plan: Any = None, jan_fact: Any = None,
            feb_plan: Any = None, feb_fact: Any = None,
            mar_fore: Any = None,
            delta: Any = None,
            row_type: str = "data",   # header | total | subtotal | data | detail
            indent: int = 0,
            sign: int = 1):
        prefix = "  " * indent
        # Compute feb variance (fact vs plan) as number for traffic light
        _feb_delta_num: float | None = None
        if feb_fact is not None and feb_plan is not None and feb_plan != 0:
            _feb_delta_num = (feb_fact * sign - feb_plan * sign) / abs(feb_plan * sign) * 100

        a_label = month_a or "Период 1"
        b_label = month_b or "Период 2"
        f_label = forecast_month or "Прогноз"
        rows.append({
            "Показатель": prefix + label,
            f"{a_label} план": _rub(jan_plan * sign) if jan_plan is not None else "—",
            f"{a_label} факт": _rub(jan_fact * sign) if jan_fact is not None else "—",
            f"{b_label} план": _rub(feb_plan * sign) if feb_plan is not None else "—",
            f"{b_label} факт": _rub(feb_fact * sign) if feb_fact is not None else "—",
            f"{f_label}": _rub(mar_fore * sign) if mar_fore is not None else "—",
            "Δ факт/план %": _pct(_feb_delta_num) if _feb_delta_num is not None else "—",
            "Δ м/м %": _pct((feb_fact / jan_fact - 1) * 100)
                    if (jan_fact and feb_fact and jan_fact != 0) else "—",
            "_delta_num": _feb_delta_num,  # hidden: used for traffic light
        })
        styles.append(row_type)

    def add_pl(label: str, key: str, indent: int = 0, sign: int = 1, row_type: str = "data"):
        jf = _get(month_a, key) if month_a else None
        ff = _get(month_b, key) if month_b else None
        mf = _get(forecast_month, key) if forecast_month else None
        add(label, jan_fact=jf, feb_fact=ff, mar_fore=mf, row_type=row_type,
            indent=indent, sign=sign)

    def add_oh_cat(cat: str, group: str = "", indent: int = 1):
        j = oh_by_cat_month.get((cat, month_a), {}) if month_a else {}
        f = oh_by_cat_month.get((cat, month_b), {}) if month_b else {}
        fc_val = f.get("actual", 0)
        add(cat,
            jan_plan=j.get("plan"), jan_fact=j.get("actual"),
            feb_plan=f.get("plan"), feb_fact=f.get("actual"),
            mar_fore=fc_val * 1.05,
            row_type="detail", indent=indent)

    # ─── ДОХОДЫ ──────────────────────────────────────────────────────────────
    add("ДОХОДЫ", row_type="header")

    def _a(key): return _get(month_a, key) if month_a else None
    def _b(key): return _get(month_b, key) if month_b else None
    def _fc(key): return _get(forecast_month, key) if forecast_month else None

    add("Оборот с НДС",             jan_fact=_a("turnover_vat"),  feb_fact=_b("turnover_vat"),
        mar_fore=_fc("turnover_vat"),  indent=1)
    add("Оборот без НДС",           jan_fact=_a("turnover"),      feb_fact=_b("turnover"),
        mar_fore=_fc("turnover"),       indent=1)
    add("Выручка (работы агентства)",jan_fact=_a("revenue"),       feb_fact=_b("revenue"),
        mar_fore=_fc("revenue"),        indent=1)
    add("(−) Прямые расходы по проектам", jan_fact=_a("direct_expenses"), feb_fact=_b("direct_expenses"),
        mar_fore=_fc("direct_expenses"), indent=1, sign=-1)
    add_pl("= ВАЛОВАЯ МАРЖА", "gross_margin", row_type="total")

    # ─── ФОТ ─────────────────────────────────────────────────────────────────
    fot_title = ("ФОТ ЮНИТА — Сотрудник (× 1.302 на страховые)"
                 if fot_scenario == "employee"
                 else "ФОТ ЮНИТА — ИП (ФИКС + KPI)")
    add(fot_title, row_type="header")

    # FOT from salary sheet — one detail row per month
    for month in [m for m in [month_a, month_b] if m]:
        sal = sal_by.get(month)
        if sal is None:
            continue
        fiks    = float(sal.get("fiks", 0))
        act     = float(sal.get("activity", 0))
        accrued = float(sal.get("total_accrued", 0))
        is_a = (month == month_a)
        if fot_scenario == "employee":
            add(f"  ФОТ начислено ({month})",
                jan_fact=accrued if is_a else None,
                feb_fact=accrued if not is_a else None,
                indent=1)
            ins = accrued * 0.302
            add(f"  + Страховые взносы 30.2% ({month})",
                jan_fact=ins if is_a else None,
                feb_fact=ins if not is_a else None,
                indent=2, row_type="detail")
        else:
            add(f"  ФИКС ({month})",
                jan_fact=fiks if is_a else None,
                feb_fact=fiks if not is_a else None, indent=1)
            add(f"  KPI / активити ({month})",
                jan_fact=act if is_a else None,
                feb_fact=act if not is_a else None,
                indent=1, row_type="detail")

    add_pl("(−) ФОТ итого", "fot", sign=-1, indent=0, row_type="subtotal")
    add_pl("= МАРЖА ВКЛАДА", "contribution_margin", row_type="total")

    # ─── НАКЛАДНЫЕ РАСХОДЫ ───────────────────────────────────────────────────
    add("НАКЛАДНЫЕ РАСХОДЫ", row_type="header")

    # Group categories
    if not overhead_df.empty:
        groups_order = ["ФОТ (производство)", "ФОТ (руководство)", "Сервисы",
                        "Персонал", "Административные", "Офис",
                        "IT и бизнес-процессы", "Маркетинг", "Продажи",
                        "Финансовые расходы", "Прочие"]
        seen_groups: set = set()
        all_cats = overhead_df[["category","group"]].drop_duplicates()

        for g in groups_order + [x for x in overhead_df["group"].unique() if x not in groups_order]:
            cats_in_group = all_cats[all_cats["group"] == g]["category"].tolist()
            if not cats_in_group:
                continue
            if g not in seen_groups:
                # group subtotal
                j_sub  = sum(oh_by_cat_month.get((c, month_a), {}).get("actual", 0) for c in cats_in_group) if month_a else 0
                f_sub  = sum(oh_by_cat_month.get((c, month_b), {}).get("actual", 0) for c in cats_in_group) if month_b else 0
                jp_sub = sum(oh_by_cat_month.get((c, month_a), {}).get("plan",   0) for c in cats_in_group) if month_a else 0
                fp_sub = sum(oh_by_cat_month.get((c, month_b), {}).get("plan",   0) for c in cats_in_group) if month_b else 0
                add(g, jan_plan=jp_sub, jan_fact=j_sub, feb_plan=fp_sub, feb_fact=f_sub,
                    mar_fore=f_sub * 1.02, row_type="subtotal", indent=1)
                seen_groups.add(g)
            for cat in cats_in_group:
                add_oh_cat(cat, g, indent=2)

    add_pl("(−) НАКЛАДНЫЕ итого", "overhead", sign=-1, row_type="subtotal")

    # ─── EBIT ────────────────────────────────────────────────────────────────
    add_pl("═══ EBIT (Операционная прибыль)", "ebit", row_type="total")

    df = pd.DataFrame(rows)
    return df, styles


# ── Rendering ─────────────────────────────────────────────────────────────────

def _style_rows(df: pd.DataFrame, styles: list[str]):
    """Apply row-level background colors based on row type."""

    def row_style(idx):
        if idx >= len(styles):
            return [""] * len(df.columns)
        t = styles[idx]
        if t == "header":
            return [_HEADER_STYLE] * len(df.columns)
        if t == "total":
            return [_TOTAL_STYLE] * len(df.columns)
        if t == "subtotal":
            return [_SUBTOTAL_STYLE] * len(df.columns)
        if t == "detail":
            return [_GRAY_STYLE] * len(df.columns)
        return [""] * len(df.columns)

    styler = df.style
    for i in range(len(df)):
        t = styles[i] if i < len(styles) else "data"
        if t == "header":
            styler = styler.apply(
                lambda row, i=i: [_HEADER_STYLE if idx == i else "" for idx in range(len(df))],
                axis=None, subset=pd.IndexSlice[i, :]
            )
    return df.style.apply(
        lambda _: [row_style(i) for i in range(len(df))],
        axis=None
    )


def render_pl_tree(
    pl_df: pd.DataFrame,
    overhead_df: pd.DataFrame,
    salary_df: pd.DataFrame,
    fot_scenario: str,
    forecast_df: pd.DataFrame,
):
    """Render the hierarchical P&L table with collapsible sections via st.expander."""

    df, styles = build_pl_tree(pl_df, overhead_df, salary_df, fot_scenario, forecast_df)

    # Remove internal helper column before display
    delta_nums = df.pop("_delta_num") if "_delta_num" in df.columns else None

    # Money columns: all columns except "Показатель" and delta-percent columns
    variance_col = "Δ факт/план %"
    mom_col = "Δ м/м %"
    money_cols = [c for c in df.columns if c not in ("Показатель", variance_col, mom_col)]

    # Sections for collapsible rendering
    sections = {
        "💰 ДОХОДЫ": [],
        "👥 ФОТ ЮНИТА": [],
        "📊 НАКЛАДНЫЕ РАСХОДЫ": [],
        "📈 ИТОГОВЫЕ ПОКАЗАТЕЛИ": [],
    }

    current_section = "💰 ДОХОДЫ"
    for i, row in df.iterrows():
        label = str(row["Показатель"]).strip()
        t = styles[i] if i < len(styles) else "data"

        if t == "header":
            if "ДОХОД" in label:
                current_section = "💰 ДОХОДЫ"
            elif "ФОТ" in label:
                current_section = "👥 ФОТ ЮНИТА"
            elif "НАКЛАДН" in label:
                current_section = "📊 НАКЛАДНЫЕ РАСХОДЫ"
        elif t == "total" and "EBIT" in label:
            current_section = "📈 ИТОГОВЫЕ ПОКАЗАТЕЛИ"

        sections[current_section].append(i)

    def render_section(section_name: str, indices: list[int], expanded: bool = True):
        with st.expander(section_name, expanded=expanded):
            sub = df.iloc[indices].copy()
            sub_styles = [styles[i] for i in indices]
            sub_deltas = delta_nums.iloc[indices].tolist() if delta_nums is not None else [None] * len(indices)

            def cell_bg(col):
                def fn(s):
                    colors = []
                    for pos, (idx, v) in enumerate(s.items()):
                        t = sub_styles[pos]
                        if t == "header":
                            colors.append("background-color:#1a237e;color:white;font-weight:bold")
                        elif t == "total":
                            colors.append("background-color:#E3F2FD;font-weight:bold")
                        elif t == "subtotal":
                            colors.append("background-color:#E8F5E9;font-weight:bold")
                        elif t == "detail":
                            colors.append("color:#607D8B;font-size:12px")
                        else:
                            if col == variance_col:
                                d = sub_deltas[pos]
                                if d is None:
                                    colors.append("")
                                elif abs(d) <= 5:
                                    colors.append("color:#388E3C;font-weight:bold")
                                elif abs(d) <= 15:
                                    colors.append("color:#F57C00;font-weight:bold")
                                else:
                                    colors.append("color:#D32F2F;font-weight:bold")
                            elif col in money_cols and isinstance(v, str) and v.startswith("-"):
                                colors.append("color:#D32F2F")
                            else:
                                colors.append("")
                    return colors
                return fn

            styled = sub.style
            for col in sub.columns:
                styled = styled.apply(cell_bg(col), subset=[col])

            st.dataframe(styled, use_container_width=True, hide_index=True,
                         height=min(35 * len(sub) + 38, 600))

    for section_name, indices in sections.items():
        if indices:
            expanded = section_name in ("📈 ИТОГОВЫЕ ПОКАЗАТЕЛИ", "💰 ДОХОДЫ")
            render_section(section_name, indices, expanded=expanded)

    st.caption("Строки: синий — заголовок | голубой — итог | зелёный — подытог | серый — детализация | "
               "Δ факт/план: зелёный ≤5% | оранжевый 5–15% | красный >15%")
