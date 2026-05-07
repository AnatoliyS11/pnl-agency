"""Data validation and reconciliation checks across all data sources."""

import pandas as pd


def validate_data(
    margin_df: pd.DataFrame,
    salary_df: pd.DataFrame,
    overhead_df: pd.DataFrame,
    pl_df: pd.DataFrame,
) -> list[dict]:
    """
    Returns list of dicts: {"level": "error"|"warning"|"ok", "msg": str}
    """
    results = []

    def _ok(msg: str):
        results.append({"level": "ok", "msg": msg})

    def _warn(msg: str):
        results.append({"level": "warning", "msg": msg})

    def _err(msg: str):
        results.append({"level": "error", "msg": msg})

    # ── 1. Margin reconciliation: sum of project margins ≈ gross_margin in pl_df ──
    if not margin_df.empty and not pl_df.empty:
        for month in pl_df["month"].unique():
            m_sum = margin_df[margin_df["month"] == month]["margin"].sum()
            pl_row = pl_df[pl_df["month"] == month]
            if pl_row.empty:
                continue
            gm = float(pl_row.iloc[0].get("gross_margin", 0) or 0)
            diff = abs(m_sum - gm)
            tol = max(abs(gm) * 0.01, 1000)
            if diff > tol:
                _warn(f"{month}: сумма маржи по проектам ({m_sum:,.0f}) расходится с Валовой маржой P&L ({gm:,.0f}) на {diff:,.0f} руб.")
            else:
                _ok(f"{month}: маржа по проектам сходится с P&L ({gm:,.0f} руб.)")

    # ── 2. Salary reconciliation: total_accrued from salary_df ≈ fot in pl_df ──
    if not salary_df.empty and not pl_df.empty:
        for month in pl_df["month"].unique():
            sal = salary_df[salary_df["month"] == month]
            if sal.empty:
                _warn(f"{month}: нет данных ФОТ из ведомости")
                continue
            sal_total = sal["total_accrued"].sum()
            pl_row = pl_df[pl_df["month"] == month]
            if pl_row.empty:
                continue
            fot_pl = float(pl_row.iloc[0].get("fot", 0) or 0)
            diff = abs(sal_total - fot_pl)
            tol = max(abs(fot_pl) * 0.05, 5000)
            if diff > tol:
                _warn(f"{month}: ФОТ из ведомости ({sal_total:,.0f}) расходится с ФОТ P&L ({fot_pl:,.0f}) на {diff:,.0f} руб. (сценарий ФОТ влияет на расчёт)")
            else:
                _ok(f"{month}: ФОТ из ведомости сходится с P&L")

    # ── 3. Missing managers ───────────────────────────────────────────────────
    if not margin_df.empty:
        no_mgr = margin_df[margin_df["manager"].isna() | (margin_df["manager"].astype(str).str.strip() == "")]
        if not no_mgr.empty:
            _warn(f"{len(no_mgr)} строк в отчёте по марже без менеджера МП")
        else:
            _ok("Все проекты имеют менеджера")

    # ── 4. Negative margin projects ──────────────────────────────────────────
    if not margin_df.empty:
        loss = margin_df[margin_df["margin"] < 0]
        if not loss.empty:
            _warn(f"{len(loss)} проект(а) с отрицательной маржой (прямые расходы > выручки)")
        else:
            _ok("Нет убыточных проектов на уровне прямых расходов")

    # ── 5. Duplicate projects within a month ─────────────────────────────────
    if not margin_df.empty:
        dups = margin_df[margin_df.duplicated(subset=["month", "project"], keep=False)]
        if not dups.empty:
            _warn(f"{len(dups)} строк с дублирующимися проектами в одном месяце")
        else:
            _ok("Дубликатов проектов не обнаружено")

    # ── 6. Overhead data presence ─────────────────────────────────────────────
    if overhead_df.empty:
        _err("Файл накладных расходов не загружен — P&L неполный")
    else:
        n_cats = overhead_df["category"].nunique() if "category" in overhead_df.columns else 0
        _ok(f"Накладные расходы загружены: {n_cats} категорий")

    # ── 7. EBIT sign check ────────────────────────────────────────────────────
    if not pl_df.empty:
        for _, row in pl_df.iterrows():
            ebit = float(row.get("ebit", 0) or 0)
            if ebit < 0:
                _err(f"{row['month']}: EBIT отрицательный ({ebit:,.0f} руб.) — операционный убыток")

    return results
