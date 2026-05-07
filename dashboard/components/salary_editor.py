"""Editable salary view — writes changes back to the source Excel file."""

import openpyxl
import pandas as pd
import streamlit as st
from pathlib import Path
from dashboard.components.charts import money

# Column mapping for the "Отчет по ЗП" sheet (1-based, see parser/margin_report.py:138)
_COL_MAP = {
    "group":            1,
    "role":             2,
    "name":             3,
    "fiks":             4,
    "manager_bonus":    7,
    "specialist_bonus": 8,
    "activity":         9,
    "other_pay":       11,
    "vacation_sick":   12,
    "total_accrued":   13,
    "paid_1c":         14,
}
_DATA_START_ROW = 5
# Parser only keeps rows whose "name" cell starts with "ФИО"
_NAME_PREFIX = "ФИО"


def _save_salary_to_excel(month: str, df_edited: pd.DataFrame) -> tuple[bool, str]:
    from parser.margin_report import FILES
    if month not in FILES:
        return False, f"Файл за {month} не найден"
    path: Path = FILES[month]

    try:
        wb = openpyxl.load_workbook(path)  # keep formulas
    except Exception as e:
        return False, f"Не удалось открыть {path.name}: {e}"

    if "Отчет по ЗП" not in wb.sheetnames:
        return False, f"В файле {path.name} нет листа «Отчет по ЗП»"

    ws = wb["Отчет по ЗП"]

    # Filter out rows with empty name
    clean = df_edited.copy()
    clean["name"] = clean["name"].fillna("").astype(str).str.strip()
    clean = clean[clean["name"] != ""]

    # Recompute total_accrued (avoid stale values)
    component_cols = ["fiks", "manager_bonus", "specialist_bonus", "activity",
                      "other_pay", "vacation_sick"]
    for c in component_cols:
        if c not in clean.columns:
            clean[c] = 0.0
        clean[c] = pd.to_numeric(clean[c], errors="coerce").fillna(0.0)
    clean["total_accrued"] = clean[component_cols].sum(axis=1)

    # Clear old data rows (only columns we own)
    last_row = max(ws.max_row, _DATA_START_ROW)
    for r in range(_DATA_START_ROW, last_row + 1):
        for col in _COL_MAP.values():
            ws.cell(row=r, column=col).value = None

    # Write new rows
    for offset, (_, rec) in enumerate(clean.iterrows()):
        row = _DATA_START_ROW + offset
        # Ensure name has the "ФИО" prefix that the parser expects
        nm = str(rec["name"]).strip()
        if not nm.startswith(_NAME_PREFIX):
            nm = f"{_NAME_PREFIX} {nm}"
        ws.cell(row=row, column=_COL_MAP["group"]).value = rec.get("group", "") or ""
        ws.cell(row=row, column=_COL_MAP["role"]).value  = rec.get("role", "")  or ""
        ws.cell(row=row, column=_COL_MAP["name"]).value  = nm
        ws.cell(row=row, column=_COL_MAP["fiks"]).value             = float(rec.get("fiks", 0) or 0)
        ws.cell(row=row, column=_COL_MAP["manager_bonus"]).value    = float(rec.get("manager_bonus", 0) or 0)
        ws.cell(row=row, column=_COL_MAP["specialist_bonus"]).value = float(rec.get("specialist_bonus", 0) or 0)
        ws.cell(row=row, column=_COL_MAP["activity"]).value         = float(rec.get("activity", 0) or 0)
        ws.cell(row=row, column=_COL_MAP["other_pay"]).value        = float(rec.get("other_pay", 0) or 0)
        ws.cell(row=row, column=_COL_MAP["vacation_sick"]).value    = float(rec.get("vacation_sick", 0) or 0)
        ws.cell(row=row, column=_COL_MAP["total_accrued"]).value    = float(rec.get("total_accrued", 0) or 0)
        ws.cell(row=row, column=_COL_MAP["paid_1c"]).value          = float(rec.get("paid_1c", 0) or 0)

    try:
        wb.save(path)
    except PermissionError:
        return False, f"Файл {path.name} открыт в Excel — закройте и попробуйте снова."
    except Exception as e:
        return False, f"Ошибка сохранения: {e}"
    return True, f"Сохранено: {path.name} ({len(clean)} сотрудников)"


def render_salary_editor(salary_df: pd.DataFrame, months: list[str]) -> None:
    st.subheader("👥 Зарплаты сотрудников — редактирование")
    st.caption(
        "Изменения сохраняются прямо в исходный Excel-файл за выбранный месяц. "
        "Поле «Итого начислено» рассчитывается автоматически как сумма ФИКС + бонусы + KPI + прочие выплаты."
    )

    if salary_df is None or salary_df.empty:
        st.info("Нет данных по зарплатам")
        return

    available = [m for m in months if (salary_df["month"] == m).any()]
    if not available:
        st.info("Нет данных по зарплате за выбранные месяцы")
        return

    month = st.selectbox("Месяц для редактирования", available,
                         index=len(available) - 1, key="salary_edit_month")
    df_m = salary_df[salary_df["month"] == month].copy()
    df_m = df_m.drop(columns=["month"], errors="ignore")

    # Strip the "ФИО " prefix for display (will be re-added on save)
    if "name" in df_m.columns:
        df_m["name"] = df_m["name"].astype(str).str.replace(
            r"^ФИО\s+", "", regex=True
        )

    edit_cols_order = ["name", "role", "group", "fiks", "manager_bonus",
                       "specialist_bonus", "activity", "other_pay",
                       "vacation_sick", "total_accrued", "paid_1c"]
    df_m = df_m.reindex(columns=[c for c in edit_cols_order if c in df_m.columns])

    edited = st.data_editor(
        df_m,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "name":             st.column_config.TextColumn("ФИО"),
            "role":             st.column_config.TextColumn("Роль / должность"),
            "group":            st.column_config.TextColumn("Группа"),
            "fiks":             st.column_config.NumberColumn("ФИКС",       format="%.2f", step=1000.0),
            "manager_bonus":    st.column_config.NumberColumn("Бонус M",    format="%.2f", step=1000.0),
            "specialist_bonus": st.column_config.NumberColumn("Бонус S",    format="%.2f", step=1000.0),
            "activity":         st.column_config.NumberColumn("KPI",        format="%.2f", step=1000.0),
            "other_pay":        st.column_config.NumberColumn("Прочее",     format="%.2f", step=1000.0),
            "vacation_sick":    st.column_config.NumberColumn("Отпуск/б/л", format="%.2f", step=1000.0),
            "total_accrued":    st.column_config.NumberColumn("Итого начислено", format="%.2f",
                                                              disabled=True,
                                                              help="Пересчитывается автоматически при сохранении."),
            "paid_1c":          st.column_config.NumberColumn("Выдано 1С",  format="%.2f", step=1000.0),
        },
        key=f"salary_editor_{month}",
    )

    btn_cols = st.columns([1, 1, 4])
    save_clicked = btn_cols[0].button("💾 Сохранить в Excel", type="primary",
                                       key=f"salary_save_{month}")
    if btn_cols[1].button("↩️ Сбросить изменения", key=f"salary_reset_{month}"):
        st.rerun()

    if save_clicked:
        ok, msg = _save_salary_to_excel(month, edited)
        if ok:
            st.success(msg)
            st.cache_data.clear()
            st.rerun()
        else:
            st.error(msg)

    # ── Summary footer ───────────────────────────────────────────────────
    st.divider()
    component_cols = ["fiks", "manager_bonus", "specialist_bonus",
                      "activity", "other_pay", "vacation_sick"]
    edited_num = edited.copy()
    for c in component_cols:
        if c in edited_num.columns:
            edited_num[c] = pd.to_numeric(edited_num[c], errors="coerce").fillna(0.0)
    total_now = edited_num[[c for c in component_cols if c in edited_num.columns]].sum().sum()

    s_cols = st.columns(4)
    s_cols[0].metric("Сотрудников", len([n for n in edited["name"].fillna("") if str(n).strip()]))
    s_cols[1].metric("ФИКС", money(edited_num["fiks"].sum() if "fiks" in edited_num else 0))
    s_cols[2].metric("KPI / активити", money(edited_num["activity"].sum() if "activity" in edited_num else 0))
    s_cols[3].metric("Итого начислено", money(total_now))
