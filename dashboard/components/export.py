"""Export P&L data to Excel."""

import io
import pandas as pd


def to_excel_bytes(
    pl_df: pd.DataFrame,
    project_df: pd.DataFrame,
    overhead_df: pd.DataFrame,
    salary_df: pd.DataFrame,
) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        wb = writer.book
        header_fmt = wb.add_format({"bold": True, "bg_color": "#1976D2", "font_color": "white", "border": 1})
        number_fmt = wb.add_format({"num_format": "#,##0", "border": 1})
        pct_fmt = wb.add_format({"num_format": "0.0%", "border": 1})
        total_fmt = wb.add_format({"bold": True, "num_format": "#,##0", "bg_color": "#E3F2FD", "border": 1})

        # Sheet 1: Consolidated P&L
        pl_display = pl_df[[
            "month", "turnover_vat", "turnover", "revenue", "direct_expenses",
            "gross_margin", "gross_margin_pct", "fot", "contribution_margin",
            "contribution_margin_pct", "overhead", "ebit", "ebit_pct",
        ]].copy()
        pl_display.columns = [
            "Месяц", "Оборот с НДС", "Оборот без НДС", "Выручка (работы)", "Прямые расходы",
            "Валовая маржа", "Валовая маржа %", "ФОТ", "Маржа вклада",
            "Маржа вклада %", "Накладные расходы", "EBIT", "EBIT %",
        ]
        pl_display.to_excel(writer, sheet_name="P&L сводный", index=False)
        ws = writer.sheets["P&L сводный"]
        for col_num, col_name in enumerate(pl_display.columns):
            ws.write(0, col_num, col_name, header_fmt)
        ws.set_column("A:A", 22)
        ws.set_column("B:M", 18)

        # Sheet 2: Projects
        if not project_df.empty:
            proj_display = project_df[[
                "month", "entity", "project", "platform", "manager", "specialist",
                "turnover_vat", "turnover", "works", "expenses", "margin", "margin_pct",
                "allocated_fot", "allocated_overhead", "ebit", "ebit_pct",
            ]].copy()
            proj_display.columns = [
                "Месяц", "Компания", "Проект", "Площадка", "Менеджер МП", "Специалист",
                "Оборот с НДС", "Оборот без НДС", "Выручка", "Расходы", "Маржа", "Маржа %",
                "ФОТ (аллок)", "Накладные (аллок)", "EBIT", "EBIT %",
            ]
            proj_display.to_excel(writer, sheet_name="Проекты", index=False)
            ws2 = writer.sheets["Проекты"]
            for col_num, col_name in enumerate(proj_display.columns):
                ws2.write(0, col_num, col_name, header_fmt)
            ws2.set_column("A:B", 16)
            ws2.set_column("C:C", 30)
            ws2.set_column("D:F", 16)
            ws2.set_column("G:P", 15)

        # Sheet 3: Overhead
        if not overhead_df.empty:
            overhead_df.to_excel(writer, sheet_name="Накладные расходы", index=False)
            ws3 = writer.sheets["Накладные расходы"]
            for col_num, col_name in enumerate(overhead_df.columns):
                ws3.write(0, col_num, col_name, header_fmt)
            ws3.set_column("A:B", 28)
            ws3.set_column("C:H", 14)

        # Sheet 4: Salary
        if not salary_df.empty:
            salary_df.to_excel(writer, sheet_name="ФОТ (ЗП)", index=False)
            ws4 = writer.sheets["ФОТ (ЗП)"]
            for col_num, col_name in enumerate(salary_df.columns):
                ws4.write(0, col_num, col_name, header_fmt)
            ws4.set_column("A:C", 18)
            ws4.set_column("D:N", 14)

    return buf.getvalue()
