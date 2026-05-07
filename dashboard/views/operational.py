"""Operational view: full data, manual overrides, forecast, export."""

import streamlit as st
import pandas as pd
from dashboard.components.charts import fmt, money, pct, overhead_breakdown_chart
from dashboard.components.export import to_excel_bytes
from dashboard.components.pl_tree import render_pl_tree


def _rub(v) -> str:
    """Metric-style money: '1 234 567,89 ₽'."""
    return money(v)


def _rub_fmt(v) -> str:
    """Table-cell money (no ₽): '1 234 567,89'."""
    if pd.isna(v):
        return "—"
    return money(v, unit="")


def _pct_fmt(v) -> str:
    if pd.isna(v):
        return "—"
    return pct(v)


def _apply_month_filter(df: pd.DataFrame, months: list[str]) -> pd.DataFrame:
    """Return df filtered by months; empty selection = all months."""
    if df is None or df.empty or not months or "month" not in df.columns:
        return df
    return df[df["month"].isin(months)].copy()


def render(
    pl_df: pd.DataFrame,
    project_df: pd.DataFrame,
    overhead_df: pd.DataFrame,
    salary_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    fot_scenario: str = "employee",
):
    st.header("Операционный вид — Полные данные")

    # ── Global month filter (applies to all tabs + export) ───────────────────
    all_months: list[str] = []
    for df in (pl_df, project_df, overhead_df, salary_df):
        if df is not None and not df.empty and "month" in df.columns:
            for m in df["month"].unique():
                if m not in all_months:
                    all_months.append(m)

    filter_cols = st.columns([3, 1])
    sel_months = filter_cols[0].multiselect(
        "📅 Фильтр по месяцам (применяется ко всем вкладкам и экспорту)",
        all_months,
        default=all_months,
        key="ops_months_global",
        help="Снимите галочки, чтобы исключить месяцы из всех таблиц и выгрузок."
    )
    filter_cols[1].metric("Выбрано месяцев", f"{len(sel_months)} из {len(all_months)}")

    if not sel_months:
        st.warning("Выберите хотя бы один месяц в фильтре выше.")
        return

    pl_df_f       = _apply_month_filter(pl_df, sel_months)
    project_df_f  = _apply_month_filter(project_df, sel_months)
    overhead_df_f = _apply_month_filter(overhead_df, sel_months)
    salary_df_f   = _apply_month_filter(salary_df, sel_months)

    tabs = st.tabs([
        "📋 P&L дерево",
        "📊 P&L сводный",
        "📁 Проекты",
        "💼 Накладные расходы",
        "👥 ФОТ (ЗП)",
        "⚙️ Ручные корректировки",
        "⬇️ Экспорт",
    ])

    # ── Tab 0: P&L tree (hierarchical) ───────────────────────────────────────
    with tabs[0]:
        st.subheader("Иерархический P&L — план / факт / прогноз")
        st.caption("Формат как в файле накладных расходов: раскрывающиеся разделы, "
                   "план и факт по каждому месяцу.")
        if not pl_df_f.empty:
            render_pl_tree(pl_df_f, overhead_df_f, salary_df_f, fot_scenario, forecast_df)
        else:
            st.info("Нет данных для построения P&L")

    # ── Tab 1: P&L flat summary ──────────────────────────────────────────────
    with tabs[1]:
        st.subheader("Сводный P&L с прогнозом")

        combined = (pd.concat([pl_df_f, forecast_df], ignore_index=True)
                    if not forecast_df.empty else pl_df_f)
        display_cols = {
            "month": "Месяц",
            "turnover_vat": "Оборот с НДС",
            "turnover": "Оборот без НДС",
            "revenue": "Выручка (работы)",
            "direct_expenses": "Прямые расходы",
            "gross_margin": "Валовая маржа",
            "gross_margin_pct": "Валовая маржа %",
            "fot": "ФОТ",
            "contribution_margin": "Маржа вклада",
            "contribution_margin_pct": "Маржа вклада %",
            "overhead": "Накладные расходы",
            "ebit": "EBIT",
            "ebit_pct": "EBIT %",
        }
        tbl = combined[[c for c in display_cols if c in combined.columns]].rename(columns=display_cols)
        money_cols = ["Оборот с НДС", "Оборот без НДС", "Выручка (работы)", "Прямые расходы",
                      "Валовая маржа", "ФОТ", "Маржа вклада", "Накладные расходы", "EBIT"]
        pct_cols = ["Валовая маржа %", "Маржа вклада %", "EBIT %"]
        fmt_dict = {c: _rub_fmt for c in money_cols if c in tbl.columns}
        fmt_dict.update({c: _pct_fmt for c in pct_cols if c in tbl.columns})

        def highlight_forecast(row):
            if "прогноз" in str(row.get("Месяц", "")):
                return ["background-color: #E8F5E9"] * len(row)
            return [""] * len(row)

        styled = tbl.style.format(fmt_dict).apply(highlight_forecast, axis=1)
        st.dataframe(styled, use_container_width=True, hide_index=True)
        st.caption("🟢 Строки с прогнозом выделены зелёным.")

    # ── Tab 2: Projects full table ───────────────────────────────────────────
    with tabs[2]:
        st.subheader("Все проекты по месяцам")
        if not project_df_f.empty:
            tab_months = ["Все"] + sorted(project_df_f["month"].unique().tolist())
            sel = st.selectbox("Месяц (внутри фильтра)", tab_months, key="ops_month")
            show_df = project_df_f if sel == "Все" else project_df_f[project_df_f["month"] == sel]

            cols_to_show = ["month", "entity", "project", "platform", "manager",
                            "specialist", "turnover_vat", "works", "expenses",
                            "margin", "margin_pct", "allocated_fot",
                            "allocated_overhead", "ebit", "ebit_pct"]
            cols_to_show = [c for c in cols_to_show if c in show_df.columns]
            disp = show_df[cols_to_show].rename(columns={
                "month": "Месяц", "entity": "Компания", "project": "Проект",
                "platform": "Площадка", "manager": "Менеджер МП",
                "specialist": "Специалист", "turnover_vat": "Оборот с НДС",
                "works": "Выручка", "expenses": "Расходы",
                "margin": "Валовая маржа", "margin_pct": "Маржа %",
                "allocated_fot": "ФОТ (аллок)",
                "allocated_overhead": "Накладные (аллок)",
                "ebit": "EBIT", "ebit_pct": "EBIT %",
            })
            proj_money_cols = ["Оборот с НДС", "Выручка", "Расходы", "Валовая маржа",
                               "ФОТ (аллок)", "Накладные (аллок)", "EBIT"]
            proj_pct_cols = ["Маржа %", "EBIT %"]
            fmt_d = {c: _rub_fmt for c in proj_money_cols if c in disp.columns}
            fmt_d.update({c: _pct_fmt for c in proj_pct_cols if c in disp.columns})
            st.dataframe(
                disp.style.format(fmt_d),
                use_container_width=True, height=500, hide_index=True,
            )
        else:
            st.info("Нет данных по проектам")

    # ── Tab 3: Overhead detail ───────────────────────────────────────────────
    with tabs[3]:
        st.subheader("Накладные расходы — детализация")
        if not overhead_df_f.empty:
            st.plotly_chart(overhead_breakdown_chart(overhead_df_f), use_container_width=True)
            oh_disp = overhead_df_f.copy()
            # Rename for display clarity
            oh_disp = oh_disp.rename(columns={
                "category": "Категория", "group": "Группа", "month": "Месяц",
                "plan": "План", "forecast": "Прогноз", "actual": "Факт",
            })
            fmt_oh = {c: _rub_fmt for c in ["План", "Прогноз", "Факт"] if c in oh_disp.columns}
            st.dataframe(oh_disp.style.format(fmt_oh),
                         use_container_width=True, height=400, hide_index=True)
        else:
            st.info("Файл накладных расходов не найден (или не попал в фильтр)")

    # ── Tab 4: Salary ────────────────────────────────────────────────────────
    with tabs[4]:
        st.subheader("ФОТ — данные из листа ЗП")
        if not salary_df_f.empty:
            months_sal = ["Все"] + sorted(salary_df_f["month"].unique().tolist())
            sel_m = st.selectbox("Месяц (внутри фильтра)", months_sal, key="ops_sal_month")
            sdf = salary_df_f if sel_m == "Все" else salary_df_f[salary_df_f["month"] == sel_m]
            sal_disp = sdf.rename(columns={
                "month": "Месяц", "group": "Группа", "role": "Роль", "name": "ФИО",
                "fiks": "ФИКС", "manager_bonus": "Бонус менеджера",
                "specialist_bonus": "Бонус специалиста", "activity": "Активити (KPI)",
                "other_pay": "Прочие доплаты", "vacation_sick": "Отпуск/Больничный",
                "total_accrued": "Итого начислено", "paid_1c": "Выдано (1С)",
            })
            money_cols_sal = ["ФИКС", "Бонус менеджера", "Бонус специалиста",
                              "Активити (KPI)", "Прочие доплаты", "Отпуск/Больничный",
                              "Итого начислено", "Выдано (1С)"]
            fmt_sal = {c: _rub_fmt for c in money_cols_sal if c in sal_disp.columns}
            st.dataframe(sal_disp.style.format(fmt_sal),
                         use_container_width=True, hide_index=True)
            totals = sdf[[c for c in ["fiks", "manager_bonus", "specialist_bonus",
                                      "activity", "other_pay", "vacation_sick",
                                      "total_accrued", "paid_1c"] if c in sdf.columns]].sum()
            st.write("**Итого по выбранному периоду:**")
            tcols = st.columns(4)
            tcols[0].metric("ФИКС", _rub(totals.get("fiks", 0)))
            tcols[1].metric("KPI + активити", _rub(totals.get("activity", 0)))
            tcols[2].metric("Итого начислено", _rub(totals.get("total_accrued", 0)))
            tcols[3].metric("Выдано (1С)", _rub(totals.get("paid_1c", 0)))
        else:
            st.info("Нет данных ФОТ в текущем фильтре месяцев")

    # ── Tab 5: Manual overrides ──────────────────────────────────────────────
    with tabs[5]:
        st.subheader("Ручные корректировки")
        st.caption("Корректировки применяются только к отображению — не изменяют исходные файлы.")

        if not forecast_df.empty:
            fc_label = str(forecast_df.iloc[0].get("month", "прогноз"))
            st.markdown(f"#### Корректировки прогноза — {fc_label}")
            row = forecast_df.iloc[0]

            col1, col2 = st.columns(2)
            adj_revenue = col1.number_input(
                "Выручка (работы)", value=float(row.get("revenue", 0)),
                step=10000.0, format="%.0f")
            adj_fot = col1.number_input(
                "ФОТ", value=float(row.get("fot", 0)),
                step=10000.0, format="%.0f")
            adj_overhead = col2.number_input(
                "Накладные расходы", value=float(row.get("overhead", 0)),
                step=10000.0, format="%.0f")
            adj_expenses = col2.number_input(
                "Прямые расходы", value=float(row.get("direct_expenses", 0)),
                step=5000.0, format="%.0f")

            adj_gross = adj_revenue - adj_expenses
            adj_cm    = adj_gross - adj_fot
            adj_ebit  = adj_cm - adj_overhead

            st.markdown("#### Скорректированный результат:")
            res_cols = st.columns(4)
            res_cols[0].metric("Валовая маржа", _rub(adj_gross),
                               delta=pct(adj_gross/adj_revenue*100) if adj_revenue else None)
            res_cols[1].metric("Маржа вклада", _rub(adj_cm),
                               delta=pct(adj_cm/adj_revenue*100) if adj_revenue else None)
            res_cols[2].metric("EBIT", _rub(adj_ebit),
                               delta=pct(adj_ebit/adj_revenue*100) if adj_revenue else None)
            if adj_ebit < 0:
                res_cols[3].error("⚠️ Прогноз убыточен")
            else:
                res_cols[3].success("✅ Прогноз прибыльный")
        else:
            st.info("Прогноз недоступен (нужны данные минимум за 2 месяца)")

    # ── Tab 6: Export (respects the month filter) ────────────────────────────
    with tabs[6]:
        st.subheader("Экспорт данных")
        st.caption(f"Экспорт с учётом фильтра: **{', '.join(sel_months)}** "
                   f"({len(sel_months)} из {len(all_months)} месяцев).")

        # ── Full Excel workbook ──────────────────────────────────────────────
        st.markdown("#### 📥 Excel-книга со всеми листами")
        if st.button("Сформировать Excel-файл", key="ops_build_xlsx"):
            with st.spinner("Формирую Excel..."):
                xlsx_bytes = to_excel_bytes(pl_df_f, project_df_f, overhead_df_f, salary_df_f)
            st.session_state["ops_xlsx_bytes"] = xlsx_bytes
            st.success("Файл готов, нажмите «Скачать».")

        if "ops_xlsx_bytes" in st.session_state:
            st.download_button(
                label="⬇️ Скачать PnL_Agency.xlsx",
                data=st.session_state["ops_xlsx_bytes"],
                file_name=f"PnL_Agency_{'_'.join(sel_months).replace(' ', '-')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="ops_xlsx_dl",
            )

        st.divider()

        # ── CSV downloads (one per dataset) ──────────────────────────────────
        st.markdown("#### 📋 Отдельные датасеты (CSV, UTF-8 с BOM для Excel)")
        csv_rows = st.columns(2)
        col_a, col_b = csv_rows[0], csv_rows[1]

        if not pl_df_f.empty:
            pl_csv = pl_df_f.to_csv(index=False, sep=";").encode("utf-8-sig")
            col_a.download_button(
                "💰 P&L сводный (CSV)", pl_csv,
                f"pl_summary_{'_'.join(sel_months).replace(' ', '-')}.csv",
                "text/csv", key="ops_csv_pl",
            )
        if not forecast_df.empty:
            fc_csv = forecast_df.to_csv(index=False, sep=";").encode("utf-8-sig")
            col_b.download_button(
                "🔮 Прогноз (CSV)", fc_csv,
                "forecast.csv", "text/csv", key="ops_csv_fc",
            )
        if not project_df_f.empty:
            csv_projects = project_df_f.to_csv(index=False, sep=";").encode("utf-8-sig")
            col_a.download_button(
                "📁 Проекты (CSV)", csv_projects,
                f"projects_{'_'.join(sel_months).replace(' ', '-')}.csv",
                "text/csv", key="ops_csv_proj",
            )
        if not overhead_df_f.empty:
            csv_oh = overhead_df_f.to_csv(index=False, sep=";").encode("utf-8-sig")
            col_b.download_button(
                "💼 Накладные (CSV)", csv_oh,
                f"overhead_{'_'.join(sel_months).replace(' ', '-')}.csv",
                "text/csv", key="ops_csv_oh",
            )
        if not salary_df_f.empty:
            csv_sal = salary_df_f.to_csv(index=False, sep=";").encode("utf-8-sig")
            col_a.download_button(
                "👥 ФОТ — ведомость ЗП (CSV)", csv_sal,
                f"salary_{'_'.join(sel_months).replace(' ', '-')}.csv",
                "text/csv", key="ops_csv_sal",
            )

        st.caption("CSV с разделителем «;» и BOM — открывается в Excel по двойному клику без танцев с кодировкой.")
