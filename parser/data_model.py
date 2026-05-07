"""
Unified P&L data model.

Builds the consolidated P&L from:
  - margin_df  (from parser.margin_report)
  - salary_df  (from parser.margin_report — Отчет по ЗП sheet)
  - overhead_df (from parser.overhead)

Two FOT scenarios:
  Employee: total_accrued × 1.302  (employer pays +30.2% insurance on top)
  IP:       fiks + activity  (no НДФЛ, no insurance from company side)
"""

import pandas as pd

# Список месяцев всегда приходит из данных (margin_df["month"].unique()).
# Константа оставлена пустой для обратной совместимости импорта.
MONTHS: list[str] = []

NDFL_RATE = 0.13          # deducted from employee
INSURANCE_RATE = 0.302    # paid by employer on top of gross (simplified rate)
EMPLOYER_MULTIPLIER = 1 + INSURANCE_RATE  # = 1.302


def build_fot(salary_df: pd.DataFrame, scenario: str = "employee") -> pd.DataFrame:
    """
    Returns DataFrame with columns: month, fot_total, fot_fiks, fot_bonuses, fot_other.
    scenario: 'employee' | 'ip'
    """
    if salary_df.empty:
        return pd.DataFrame(columns=["month", "fot_total", "fot_fiks", "fot_bonuses", "fot_other"])

    rows = []
    for month in salary_df["month"].unique():
        df = salary_df[salary_df["month"] == month]
        fiks = df["fiks"].sum()
        bonuses = df["activity"].sum()
        other = df["other_pay"].sum()
        vacation = df["vacation_sick"].sum()
        total_accrued = df["total_accrued"].sum()

        if scenario == "employee":
            fot_total = total_accrued * EMPLOYER_MULTIPLIER
        else:  # ip
            fot_total = fiks + bonuses  # company pays only fixed + performance, no social taxes

        rows.append({
            "month": month,
            "fot_total": fot_total,
            "fot_fiks": fiks,
            "fot_bonuses": bonuses,
            "fot_other": other + vacation,
            "total_accrued": total_accrued,
        })
    return pd.DataFrame(rows)


def build_pl(
    margin_df: pd.DataFrame,
    salary_df: pd.DataFrame,
    overhead_df: pd.DataFrame,
    fot_scenario: str = "employee",
    overhead_calc: str = "actual",
    months: list[str] | None = None,
) -> pd.DataFrame:
    """
    Build consolidated P&L per month.

    Returns DataFrame with columns:
      month, revenue, direct_expenses, gross_margin, gross_margin_pct,
      fot, contribution_margin, contribution_margin_pct,
      overhead, ebit, ebit_pct,
      fot_scenario, overhead_calc
    """
    if months is None:
        if not margin_df.empty and "month" in margin_df.columns:
            months = list(margin_df["month"].unique())
        else:
            months = []

    fot_df = build_fot(salary_df, fot_scenario)
    fot_by_month = fot_df.set_index("month")["fot_total"].to_dict()

    overhead_col = overhead_calc  # 'plan'|'forecast'|'actual'
    oh_by_month = {}
    if not overhead_df.empty:
        # Exclude FOT lines from overhead (they're covered by salary_df)
        non_fot = overhead_df[~overhead_df["category"].str.startswith("ФОТ")]
        grouped = non_fot.groupby("month")[overhead_col].sum()
        oh_by_month = grouped.to_dict()

    rows = []
    for month in months:
        mdf = margin_df[margin_df["month"] == month] if not margin_df.empty else pd.DataFrame()

        revenue = mdf["works"].sum() if not mdf.empty else 0.0
        turnover_vat = mdf["turnover_vat"].sum() if not mdf.empty else 0.0
        turnover = mdf["turnover"].sum() if not mdf.empty else 0.0
        direct_exp = mdf["expenses"].sum() if not mdf.empty else 0.0
        gross_margin = mdf["margin"].sum() if not mdf.empty else 0.0

        fot = fot_by_month.get(month, 0.0)
        contribution_margin = gross_margin - fot
        overhead = oh_by_month.get(month, 0.0)
        ebit = contribution_margin - overhead

        gm_pct = (gross_margin / revenue * 100) if revenue else 0.0
        cm_pct = (contribution_margin / revenue * 100) if revenue else 0.0
        ebit_pct = (ebit / revenue * 100) if revenue else 0.0

        rows.append({
            "month": month,
            "turnover_vat": turnover_vat,
            "turnover": turnover,
            "revenue": revenue,
            "direct_expenses": direct_exp,
            "gross_margin": gross_margin,
            "gross_margin_pct": gm_pct,
            "fot": fot,
            "contribution_margin": contribution_margin,
            "contribution_margin_pct": cm_pct,
            "overhead": overhead,
            "ebit": ebit,
            "ebit_pct": ebit_pct,
            "fot_scenario": fot_scenario,
            "overhead_calc": overhead_calc,
        })

    return pd.DataFrame(rows)


def build_project_pl(
    margin_df: pd.DataFrame,
    salary_df: pd.DataFrame,
    overhead_df: pd.DataFrame,
    fot_scenario: str = "employee",
    overhead_calc: str = "actual",
) -> pd.DataFrame:
    """
    Project-level P&L: allocates FOT and overhead proportionally to project margin.
    """
    if margin_df.empty:
        return pd.DataFrame()

    fot_df = build_fot(salary_df, fot_scenario)
    fot_by_month = fot_df.set_index("month")["fot_total"].to_dict()

    overhead_col = overhead_calc
    oh_by_month = {}
    if not overhead_df.empty:
        non_fot = overhead_df[~overhead_df["category"].str.startswith("ФОТ")]
        grouped = non_fot.groupby("month")[overhead_col].sum()
        oh_by_month = grouped.to_dict()

    result = margin_df.copy()
    result["allocated_fot"] = 0.0
    result["allocated_overhead"] = 0.0

    for month in result["month"].unique():
        mask = result["month"] == month
        month_margin = result.loc[mask, "margin"].sum()
        fot = fot_by_month.get(month, 0.0)
        oh = oh_by_month.get(month, 0.0)

        if month_margin > 0:
            ratio = result.loc[mask, "margin"] / month_margin
            result.loc[mask, "allocated_fot"] = ratio * fot
            result.loc[mask, "allocated_overhead"] = ratio * oh

    result["ebit"] = result["margin"] - result["allocated_fot"] - result["allocated_overhead"]
    result["ebit_pct"] = result.apply(
        lambda r: (r["ebit"] / r["works"] * 100) if r["works"] else 0.0, axis=1
    )
    result["margin_pct"] = result.apply(
        lambda r: (r["margin"] / r["works"] * 100) if r["works"] else 0.0, axis=1
    )
    return result


_MONTH_NAMES = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]


def _next_month_label(month_label: str) -> str:
    """«Февраль 2026» → «Март 2026»; year rolls over on December."""
    try:
        name, year = month_label.rsplit(" ", 1)
        year = int(year)
        idx = _MONTH_NAMES.index(name.capitalize())
    except (ValueError, IndexError):
        return "Следующий месяц"
    if idx == 11:
        return f"{_MONTH_NAMES[0]} {year + 1}"
    return f"{_MONTH_NAMES[idx + 1]} {year}"


def build_forecast(pl_df: pd.DataFrame) -> pd.DataFrame:
    """
    Trend forecast based on last two available months.

    Revenue grows at prev→last rate.
    FOT is projected using last month's value × 1.05.
    EBIT is derived, not projected directly.
    """
    if len(pl_df) < 2:
        return pd.DataFrame()

    # Use the last two rows (pl_df is chronologically ordered upstream)
    j = pl_df.iloc[-2]
    f = pl_df.iloc[-1]
    forecast_label = f"{_next_month_label(f['month'])} (прогноз)"

    def safe_rate(jv: float, fv: float, cap: float = 3.0) -> float:
        """Growth rate capped to avoid blow-up from sign changes or tiny bases."""
        if abs(jv) < 1 or jv * fv < 0:  # near-zero base or sign change
            return 1.05  # assume modest 5% growth
        rate = fv / jv
        return min(max(rate, 0.5), cap)  # cap between -50% and +200%

    rev_rate = safe_rate(j["revenue"], f["revenue"])
    oh_rate = safe_rate(j["overhead"], f["overhead"])
    exp_rate = safe_rate(j.get("direct_expenses", 1), f.get("direct_expenses", 1))

    # Revenue projection
    proj_revenue = f["revenue"] * rev_rate
    proj_turnover_vat = f["turnover_vat"] * rev_rate
    proj_turnover = f["turnover"] * rev_rate
    proj_expenses = f.get("direct_expenses", 0) * exp_rate
    proj_gross = proj_revenue - proj_expenses

    # FOT: use Feb as base + mild growth
    proj_fot = f["fot"] * 1.05

    # Overhead: project from Feb trend
    proj_overhead = f["overhead"] * oh_rate

    # Derived P&L lines
    proj_cm = proj_gross - proj_fot
    proj_ebit = proj_cm - proj_overhead
    rev = proj_revenue or 1

    row = {
        "month": forecast_label,
        "fot_scenario": j["fot_scenario"],
        "overhead_calc": j["overhead_calc"],
        "turnover_vat": proj_turnover_vat,
        "turnover": proj_turnover,
        "revenue": proj_revenue,
        "direct_expenses": proj_expenses,
        "gross_margin": proj_gross,
        "gross_margin_pct": proj_gross / rev * 100,
        "fot": proj_fot,
        "contribution_margin": proj_cm,
        "contribution_margin_pct": proj_cm / rev * 100,
        "overhead": proj_overhead,
        "ebit": proj_ebit,
        "ebit_pct": proj_ebit / rev * 100,
    }
    return pd.DataFrame([row])
