"""
Pioneer P&L tree for the Owner view.

Renders a full P&L table matching the template structure, with drill-down expanders
for each major section so the owner can trace every ruble to its source.
"""

import json
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from dashboard.components.charts import money, money_compact, pct

# Overhead group → P&L section mapping
_COMMERCIAL_GROUPS  = {"Продажи", "Маркетинг"}
_OPERATIONAL_GROUPS = {"Административные", "Офис", "IT и бизнес-процессы", "Персонал"}
_FINANCIAL_GROUPS   = {"Финансовые расходы"}
_SERVICES_GROUPS    = {"Сервисы"}

EMPLOYER_TAX_RATE = 0.302  # insurance contributions paid by employer


# ── Helpers ──────────────────────────────────────────────────────────────────

def _oh_sum(overhead_df: pd.DataFrame, month: str, groups: set, calc: str) -> float:
    if overhead_df.empty:
        return 0.0
    mask = (overhead_df["month"] == month) & (overhead_df["group"].isin(groups))
    return float(overhead_df.loc[mask, calc].sum())


def _oh_by_cat(overhead_df: pd.DataFrame, month: str, groups: set, calc: str) -> dict:
    if overhead_df.empty:
        return {}
    mask = (overhead_df["month"] == month) & (overhead_df["group"].isin(groups))
    sub = overhead_df.loc[mask].groupby("category")[calc].sum()
    return sub.to_dict()


def _salary_bd(salary_df: pd.DataFrame | None, month: str) -> dict:
    zero = {"total_accrued": 0.0, "fiks": 0.0, "activity": 0.0, "taxes": 0.0, "fot_total": 0.0}
    if salary_df is None or salary_df.empty:
        return zero
    sdf = salary_df[salary_df["month"] == month]
    if sdf.empty:
        return zero
    accrued = float(sdf["total_accrued"].sum())
    return {
        "total_accrued": accrued,
        "fiks":          float(sdf["fiks"].sum()),
        "activity":      float(sdf["activity"].sum()),
        "taxes":         accrued * EMPLOYER_TAX_RATE,
        "fot_total":     accrued * (1 + EMPLOYER_TAX_RATE),
    }


def _fmt(v, is_pct: bool = False) -> str:
    if v is None:
        return ""
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return str(v)
    return pct(fv) if is_pct else money_compact(fv)


# ── HTML table builder ────────────────────────────────────────────────────────

_TABLE_STYLE = """
<style>
*{box-sizing:border-box;}
body{margin:0;font-family:Inter,Arial,sans-serif;background:#fff;}
.pl-pioneer{width:100%;border-collapse:collapse;font-size:13px;}
.pl-pioneer th{padding:8px 12px;text-align:right;
  background:#1a237e;color:#fff;font-weight:600;border:1px solid #283593;}
.pl-pioneer th:first-child{text-align:left;min-width:300px;}
.pl-pioneer td{padding:6px 12px;border-bottom:1px solid #eeeeee;white-space:nowrap;}
.pl-pioneer .lbl{text-align:left;}
.pl-pioneer .val{text-align:right;font-variant-numeric:tabular-nums;}
.pl-pioneer .row-header td{background:#1a237e;color:#fff;font-weight:700;
  border-top:2px solid #0d1457;}
.pl-pioneer .row-total  td{background:#E3F2FD;font-weight:700;
  border-top:2px solid #90CAF9;}
.pl-pioneer .row-subtotal td{background:#E8F5E9;font-weight:600;}
.pl-pioneer .row-data   td{background:#fff;}
.pl-pioneer .row-sep    td{background:#f5f5f5;height:6px;padding:0;}
.pl-pioneer .row-note   td{background:#fafafa;color:#9E9E9E;
  font-style:italic;font-size:11px;}
.pl-pioneer .i1{padding-left:32px!important;}
.pl-pioneer .i2{padding-left:60px!important;}
.pos-val{color:#2E7D32;}.neg-val{color:#C62828;}

/* Toggle buttons */
.toggle{display:inline-block;width:14px;height:14px;line-height:14px;
  text-align:center;margin-right:8px;cursor:pointer;user-select:none;
  font-size:11px;color:#1a237e;font-weight:700;
  border:1px solid #1a237e;border-radius:3px;background:#fff;}
.toggle.collapsed{background:#fff;color:#1a237e;}
.toggle.expanded{background:#1a237e;color:#fff;}
.row-header .toggle{border-color:#fff;color:#fff;background:transparent;}
.row-header .toggle.expanded{background:#fff;color:#1a237e;}
.row-spacer{display:inline-block;width:22px;}
tr.hidden{display:none;}
</style>
"""


def _assign_hierarchy(rows: list[dict]) -> None:
    """In-place: assign row_id, parent_id and has_children to each row."""
    parent_stack: list[tuple[int, int]] = []  # (indent, row_id)

    for i, r in enumerate(rows):
        r["row_id"] = i
        r["parent_id"] = None
        r["has_children"] = False

        if r["row_type"] == "sep":
            continue

        indent = r.get("indent", 0)
        # Pop ancestors with indent >= current
        while parent_stack and parent_stack[-1][0] >= indent:
            parent_stack.pop()
        if parent_stack:
            r["parent_id"] = parent_stack[-1][1]

        if r["row_type"] in ("header", "subtotal"):
            parent_stack.append((indent, i))

    # Mark which parents actually have children
    has_kids = {r["row_id"]: False for r in rows}
    for r in rows:
        pid = r.get("parent_id")
        if pid is not None:
            has_kids[pid] = True
    for r in rows:
        r["has_children"] = has_kids.get(r["row_id"], False)


def _html_table(rows: list[dict], months: list[str], init_level: int = 2) -> str:
    """Static HTML for non-interactive contexts (kept for backward compat)."""
    return _html_table_collapsible(rows, months, init_level=init_level, interactive=False)


def _html_table_collapsible(
    rows: list[dict],
    months: list[str],
    init_level: int = 2,
    interactive: bool = True,
) -> str:
    """
    Render rows as an HTML table with optional Excel-style collapse toggles.
    `init_level` (0/1/2) sets initial visibility — rows with indent > level start hidden.
    """
    col_heads = "".join(f"<th>{m}</th>" for m in months)
    thead = f"<thead><tr><th>Статья</th>{col_heads}</tr></thead>"

    body_rows = []
    for r in rows:
        rtype  = r.get("row_type", "data")
        indent = r.get("indent", 0)
        is_pct = r.get("is_pct", False)
        is_prof = r.get("is_profit", False)
        label  = r.get("label", "")
        rid    = r.get("row_id", -1)
        pid    = r.get("parent_id")
        has_ch = r.get("has_children", False)

        if rtype == "sep":
            empty = "".join("<td></td>" for _ in months)
            body_rows.append(f"<tr class='row-sep' data-row-id='{rid}'><td></td>{empty}</tr>")
            continue

        indent_cls = f" i{indent}" if indent else ""

        # Toggle / spacer prefix
        if interactive and has_ch:
            toggle_html = f"<span class='toggle expanded' data-target='{rid}'>−</span>"
        else:
            toggle_html = "<span class='row-spacer'></span>"

        val_cells = []
        for m in months:
            v = r.get(m)
            text = _fmt(v, is_pct)
            cc = ""
            if v is not None and (is_prof or is_pct):
                try:
                    cc = "pos-val" if float(v) >= 0 else "neg-val"
                except (TypeError, ValueError):
                    pass
            val_cells.append(f"<td class='val'><span class='{cc}'>{text}</span></td>")

        # Initial visibility based on init_level
        hidden_cls = " hidden" if indent > init_level and rtype != "sep" else ""

        pid_str = "" if pid is None else str(pid)
        attrs = (f"data-row-id='{rid}' "
                 f"data-parent-id='{pid_str}' "
                 f"data-indent='{indent}'")
        cells = (f"<td class='lbl{indent_cls}'>{toggle_html}{label}</td>"
                 + "".join(val_cells))
        body_rows.append(f"<tr class='row-{rtype}{hidden_cls}' {attrs}>{cells}</tr>")

    tbody = "<tbody>" + "".join(body_rows) + "</tbody>"
    table = f"<table class='pl-pioneer'>{thead}{tbody}</table>"

    if not interactive:
        return f"{_TABLE_STYLE}{table}"

    js = """
<script>
(function(){
  function descendantIds(rootId){
    const direct = document.querySelectorAll(`tr[data-parent-id="${rootId}"]`);
    let ids = [];
    direct.forEach(tr => {
      const cid = tr.getAttribute('data-row-id');
      ids.push(cid);
      ids = ids.concat(descendantIds(cid));
    });
    return ids;
  }
  function setSubtreeHidden(rootId, hide){
    descendantIds(rootId).forEach(id => {
      const tr = document.querySelector(`tr[data-row-id="${id}"]`);
      if (tr) tr.classList.toggle('hidden', hide);
      const tg = document.querySelector(`.toggle[data-target="${id}"]`);
      if (tg){
        tg.classList.toggle('collapsed', hide);
        tg.classList.toggle('expanded', !hide);
        tg.textContent = hide ? '+' : '−';
      }
    });
  }
  document.querySelectorAll('.toggle').forEach(t => {
    t.addEventListener('click', () => {
      const target = t.getAttribute('data-target');
      const collapsing = t.classList.contains('expanded');
      // Toggle direct children only
      document.querySelectorAll(`tr[data-parent-id="${target}"]`).forEach(tr => {
        tr.classList.toggle('hidden', collapsing);
      });
      t.classList.toggle('collapsed', collapsing);
      t.classList.toggle('expanded', !collapsing);
      t.textContent = collapsing ? '+' : '−';
      // If collapsing, also collapse descendants visually
      if (collapsing) {
        descendantIds(target).forEach(id => {
          const tr2 = document.querySelector(`tr[data-row-id="${id}"]`);
          if (tr2) tr2.classList.add('hidden');
          const tg2 = document.querySelector(`.toggle[data-target="${id}"]`);
          if (tg2){ tg2.classList.add('collapsed'); tg2.classList.remove('expanded'); tg2.textContent='+'; }
        });
      }
    });
  });
})();
</script>
"""
    return f"{_TABLE_STYLE}{table}{js}"


# ── Data builder ──────────────────────────────────────────────────────────────

def build_owner_pl_lines(
    pl_df: pd.DataFrame,
    overhead_df: pd.DataFrame,
    salary_df: pd.DataFrame | None,
    margin_df: pd.DataFrame | None,
    months: list[str],
    overhead_calc: str = "actual",
) -> list[dict]:
    """
    Returns flat list of row dicts for the Pioneer P&L table.
    Each dict: label, row_type, indent, is_pct, is_profit, {month: value, ...}
    """
    pl_idx = {r["month"]: r for _, r in pl_df.iterrows()} if not pl_df.empty else {}

    def _pl(m, col, default=0.0):
        row = pl_idx.get(m)
        return float(row.get(col, default) or default) if row is not None else default

    # Pre-compute overhead sums per month per section
    srv_m  = {m: _oh_sum(overhead_df, m, _SERVICES_GROUPS,    overhead_calc) for m in months}
    com_m  = {m: _oh_sum(overhead_df, m, _COMMERCIAL_GROUPS,  overhead_calc) for m in months}
    ops_m  = {m: _oh_sum(overhead_df, m, _OPERATIONAL_GROUPS, overhead_calc) for m in months}
    fin_m  = {m: _oh_sum(overhead_df, m, _FINANCIAL_GROUPS,   overhead_calc) for m in months}

    sal_m  = {m: _salary_bd(salary_df, m) for m in months}

    # Derived P&L lines
    # МАРЖА = gross_margin - fot - services   (gross_margin = revenue - direct_expenses)
    margin_m   = {m: _pl(m, "gross_margin") - _pl(m, "fot") - srv_m[m]         for m in months}
    com_prof_m = {m: margin_m[m] - com_m[m]                                     for m in months}
    ops_prof_m = {m: com_prof_m[m] - ops_m[m]                                   for m in months}
    pbt_m      = {m: ops_prof_m[m] - fin_m[m]                                   for m in months}
    net_m      = pbt_m  # tax data not available → net ≈ profit before tax
    all_exp_m  = {m: _pl(m, "direct_expenses") + _pl(m, "fot")
                     + srv_m[m] + com_m[m] + ops_m[m] + fin_m[m]               for m in months}

    # Revenue by platform (from margin_df)
    rev_by_platform: dict[str, dict[str, float]] = {}
    if margin_df is not None and not margin_df.empty and "platform" in margin_df.columns:
        for platform, grp in margin_df.groupby("platform"):
            d: dict[str, float] = {}
            for mth, mgrp in grp.groupby("month"):
                if mth in months:
                    d[mth] = float(mgrp["works"].sum())
            if d:
                rev_by_platform[str(platform)] = d
    platform_order = sorted(
        rev_by_platform,
        key=lambda p: sum(rev_by_platform[p].values()),
        reverse=True,
    )

    # Overhead category breakdowns
    srv_cats  = {m: _oh_by_cat(overhead_df, m, _SERVICES_GROUPS,    overhead_calc) for m in months}
    com_cats  = {m: _oh_by_cat(overhead_df, m, _COMMERCIAL_GROUPS,  overhead_calc) for m in months}
    ops_cats  = {m: _oh_by_cat(overhead_df, m, _OPERATIONAL_GROUPS, overhead_calc) for m in months}
    fin_cats  = {m: _oh_by_cat(overhead_df, m, _FINANCIAL_GROUPS,   overhead_calc) for m in months}

    def _all_cats(cats_by_month):
        s = set()
        for d in cats_by_month.values():
            s.update(d.keys())
        return sorted(s)

    # ── Build rows ─────────────────────────────────────────────────────────────
    rows: list[dict] = []

    def R(label, rtype, indent=0, is_pct=False, is_profit=False, val_dict=None):
        d = {"label": label, "row_type": rtype, "indent": indent,
             "is_pct": is_pct, "is_profit": is_profit}
        for m in months:
            d[m] = (val_dict or {}).get(m)
        return d

    def SEP():
        return {"label": "", "row_type": "sep", **{m: None for m in months}}

    # SUMMARY
    rows.append(R("Выручка + доп фин доходы", "total",
                  val_dict={m: _pl(m, "revenue") for m in months}))
    rows.append(R("Все расходы", "total",
                  val_dict=all_exp_m))
    rows.append(R("ИТОГО ЧИСТАЯ ПРИБЫЛЬ", "header", is_profit=True, val_dict=net_m))
    rows.append(R("Рентабельность бизнеса", "total", is_pct=True, is_profit=True,
                  val_dict={m: (net_m[m] / _pl(m, "revenue") * 100)
                            if _pl(m, "revenue") else 0.0 for m in months}))
    rows.append(SEP())

    # ВЫРУЧКА
    rows.append(R("ВЫРУЧКА", "header",
                  val_dict={m: _pl(m, "revenue") for m in months}))
    rows.append(R("Работы", "subtotal", indent=1,
                  val_dict={m: _pl(m, "revenue") for m in months}))
    for platform in platform_order:
        rows.append(R(f"Работы {platform}", "data", indent=2,
                      val_dict={m: rev_by_platform[platform].get(m, 0.0) for m in months}))

    if any(_pl(m, "direct_expenses") > 0 for m in months):
        rows.append(SEP())
        rows.append(R("(−) Комиссии / прямые расходы проектов", "data", indent=1,
                      val_dict={m: _pl(m, "direct_expenses") for m in months}))
    rows.append(SEP())

    # СЕБЕСТОИМОСТЬ
    cogs_m = {m: _pl(m, "direct_expenses") + _pl(m, "fot") + srv_m[m] for m in months}
    rows.append(R("СЕБЕСТОИМОСТЬ", "header", val_dict=cogs_m))
    rows.append(R("ФОТ производства", "subtotal", indent=1,
                  val_dict={m: _pl(m, "fot") for m in months}))
    rows.append(R("ФОТ начисленный", "data", indent=2,
                  val_dict={m: sal_m[m]["total_accrued"] for m in months}))
    rows.append(R("Налоги с ФОТ (30,2%)", "data", indent=2,
                  val_dict={m: sal_m[m]["taxes"] for m in months}))
    rows.append(R("Сервисы производства", "subtotal", indent=1, val_dict=srv_m))
    for cat in _all_cats(srv_cats):
        rows.append(R(cat, "data", indent=2,
                      val_dict={m: srv_cats[m].get(cat, 0.0) for m in months}))
    rows.append(SEP())

    # МАРЖА
    rows.append(R("МАРЖА", "header", is_profit=True, val_dict=margin_m))
    rows.append(SEP())

    # КОММЕРЧЕСКИЕ РАСХОДЫ
    rows.append(R("КОММЕРЧЕСКИЕ РАСХОДЫ", "header", val_dict=com_m))
    for cat in _all_cats(com_cats):
        rows.append(R(cat, "data", indent=1,
                      val_dict={m: com_cats[m].get(cat, 0.0) for m in months}))
    rows.append(SEP())

    # КОММЕРЧЕСКАЯ ПРИБЫЛЬ
    rows.append(R("КОММЕРЧЕСКАЯ ПРИБЫЛЬ", "total", is_profit=True, val_dict=com_prof_m))
    rows.append(SEP())

    # ОПЕРАЦИОННЫЕ РАСХОДЫ
    rows.append(R("ОПЕРАЦИОННЫЕ РАСХОДЫ", "header", val_dict=ops_m))
    for cat in _all_cats(ops_cats):
        rows.append(R(cat, "data", indent=1,
                      val_dict={m: ops_cats[m].get(cat, 0.0) for m in months}))
    rows.append(SEP())

    # ОПЕРАЦИОННАЯ ПРИБЫЛЬ / EBITDA
    rows.append(R("ОПЕРАЦИОННАЯ ПРИБЫЛЬ / EBITDA", "total", is_profit=True, val_dict=ops_prof_m))
    rows.append(SEP())

    # ФИНАНСОВЫЕ ОПЕРАЦИИ
    rows.append(R("ФИНАНСОВЫЕ ОПЕРАЦИИ", "header", val_dict=fin_m))
    rows.append(R("Финансовые доходы (%)", "note", indent=1,
                  val_dict={m: 0.0 for m in months}))
    for cat in _all_cats(fin_cats):
        rows.append(R(cat, "data", indent=1,
                      val_dict={m: fin_cats[m].get(cat, 0.0) for m in months}))
    rows.append(R("Финансовые инвестиции", "note", indent=1,
                  val_dict={m: 0.0 for m in months}))
    rows.append(SEP())

    # ПРИБЫЛЬ ДО НАЛОГООБЛОЖЕНИЯ
    rows.append(R("ПРИБЫЛЬ ДО НАЛОГООБЛОЖЕНИЯ", "total", is_profit=True, val_dict=pbt_m))
    rows.append(R("Налог на прибыль", "note", indent=1,
                  val_dict={m: 0.0 for m in months}))
    rows.append(R("ЧИСТАЯ ПРИБЫЛЬ", "header", is_profit=True, val_dict=net_m))

    return rows


# ── Drill-down helpers ────────────────────────────────────────────────────────

def _drilldown_pivot(df: pd.DataFrame, group_col: str, value_col: str,
                     months: list[str]) -> None:
    """Pivot df by group_col × months, format as money, display."""
    if df is None or df.empty:
        st.info("Нет данных для детализации")
        return
    df_m = df[df["month"].isin(months)].copy()
    if df_m.empty:
        st.info("Нет данных за выбранные месяцы")
        return
    pivot = (
        df_m.groupby([group_col, "month"])[value_col]
        .sum()
        .unstack("month")
        .reindex(columns=months, fill_value=0)
    )
    pivot["Итого"] = pivot.sum(axis=1)
    pivot = pivot.sort_values("Итого", ascending=False)
    st.dataframe(pivot.style.format({c: money for c in pivot.columns}),
                 use_container_width=True)


def _salary_structure(salary_df: pd.DataFrame, months: list[str]) -> None:
    """Show FOT split: ФИКС / KPI / Налоги per month."""
    rows = []
    for m in months:
        sdf = salary_df[salary_df["month"] == m]
        if sdf.empty:
            continue
        accrued = float(sdf["total_accrued"].sum())
        rows += [
            {"Структура": "ФИКС",           "month": m, "v": float(sdf["fiks"].sum())},
            {"Структура": "KPI / Активити", "month": m, "v": float(sdf["activity"].sum())},
            {"Структура": "Налоги (30,2%)", "month": m, "v": accrued * EMPLOYER_TAX_RATE},
        ]
    if not rows:
        st.info("Нет данных")
        return
    pivot = (
        pd.DataFrame(rows)
        .groupby(["Структура", "month"])["v"]
        .sum()
        .unstack("month")
        .reindex(columns=months, fill_value=0)
    )
    pivot["Итого"] = pivot.sum(axis=1)
    st.dataframe(pivot.style.format({c: money for c in pivot.columns}),
                 use_container_width=True)


def _salary_role_structure(salary_df: pd.DataFrame, months: list[str]) -> None:
    """Show FOT split by role + ФИКС/KPI/Налоги."""
    rows = []
    for m in months:
        sdf = salary_df[salary_df["month"] == m]
        for role, grp in sdf.groupby("role"):
            accrued = float(grp["total_accrued"].sum())
            rows += [
                {"Разрез": f"{role} / ФИКС",  "month": m, "v": float(grp["fiks"].sum())},
                {"Разрез": f"{role} / KPI",    "month": m, "v": float(grp["activity"].sum())},
                {"Разрез": f"{role} / Налоги", "month": m, "v": accrued * EMPLOYER_TAX_RATE},
            ]
    if not rows:
        st.info("Нет данных")
        return
    pivot = (
        pd.DataFrame(rows)
        .groupby(["Разрез", "month"])["v"]
        .sum()
        .unstack("month")
        .reindex(columns=months, fill_value=0)
    )
    pivot["Итого"] = pivot.sum(axis=1)
    st.dataframe(pivot.style.format({c: money for c in pivot.columns}),
                 use_container_width=True)


# ── Main render ───────────────────────────────────────────────────────────────

def render_owner_pl_tree(
    pl_df: pd.DataFrame,
    overhead_df: pd.DataFrame,
    margin_df: pd.DataFrame | None,
    salary_df: pd.DataFrame | None,
    months: list[str],
    overhead_calc: str = "actual",
    show_inline_drilldown: bool = True,
) -> None:
    """Render the Pioneer P&L tree + drill-down expanders."""
    if pl_df.empty or not months:
        st.info("Нет данных для отображения")
        return

    # ── Detail level selector ────────────────────────────────────────────
    level_labels = {
        0: "0 — только итоги",
        1: "1 — до подкатегорий",
        2: "2 — полная детализация",
    }
    sel_cols = st.columns([2, 5])
    init_level = sel_cols[0].selectbox(
        "Уровень детализации",
        options=[0, 1, 2],
        format_func=lambda v: level_labels[v],
        index=2,
        key="pl_detail_level",
        help="Глобальный переключатель: какие уровни строк показывать. "
             "Внутри можно сворачивать секции по «±».",
    )
    sel_cols[1].caption(
        "В таблице ниже у каждой секции есть кнопка ± для сворачивания/разворачивания "
        "(как группировка строк в Excel)."
    )

    # ── Build rows + hierarchy ───────────────────────────────────────────
    rows = build_owner_pl_lines(pl_df, overhead_df, salary_df, margin_df, months, overhead_calc)
    _assign_hierarchy(rows)

    html = _html_table_collapsible(rows, months, init_level=init_level, interactive=True)
    visible_rows = sum(1 for r in rows
                       if not (r.get("indent", 0) > init_level and r["row_type"] != "sep"))
    height = min(50 + 32 * visible_rows + 80, 1400)
    components.html(html, height=int(height), scrolling=True)

    if not show_inline_drilldown:
        return

    st.markdown("#### Детализация по разделам")
    st.caption("Раскройте раздел и выберите измерение, чтобы увидеть исходные данные.")

    # 1. ВЫРУЧКА
    with st.expander("🔍 Детализация: ВЫРУЧКА"):
        if margin_df is not None and not margin_df.empty:
            dim = st.selectbox(
                "Детализация по:",
                ["Без детализации", "По платформе / сервису", "По клиенту (проект)", "По менеджеру"],
                key="dd_revenue",
            )
            if dim == "По платформе / сервису":
                _drilldown_pivot(margin_df, "platform", "works", months)
            elif dim == "По клиенту (проект)":
                _drilldown_pivot(margin_df, "project", "works", months)
            elif dim == "По менеджеру":
                _drilldown_pivot(margin_df, "manager", "works", months)
        else:
            st.info("Нет данных по проектам")

    # 2. ФОТ
    with st.expander("🔍 Детализация: ФОТ производства"):
        if salary_df is not None and not salary_df.empty:
            dim = st.selectbox(
                "Детализация по:",
                ["Без детализации", "По сотруднику (ФИО)", "По роли / должности",
                 "По структуре (ФИКС/KPI/Налоги)", "По роли + структура"],
                key="dd_fot",
            )
            if dim == "По сотруднику (ФИО)":
                _drilldown_pivot(salary_df, "name", "total_accrued", months)
            elif dim == "По роли / должности":
                _drilldown_pivot(salary_df, "role", "total_accrued", months)
            elif dim == "По структуре (ФИКС/KPI/Налоги)":
                _salary_structure(salary_df, months)
            elif dim == "По роли + структура":
                _salary_role_structure(salary_df, months)
        else:
            st.info("Нет данных по сотрудникам")

    # 3. Коммерческие расходы
    with st.expander("🔍 Детализация: Коммерческие расходы"):
        if not overhead_df.empty:
            sub = overhead_df[overhead_df["group"].isin(_COMMERCIAL_GROUPS)]
            dim = st.selectbox("Детализация по:", ["По категории", "По группе"], key="dd_com")
            _drilldown_pivot(sub, "category" if dim == "По категории" else "group",
                             overhead_calc, months)
        else:
            st.info("Нет данных по накладным расходам")

    # 4. Операционные расходы
    with st.expander("🔍 Детализация: Операционные расходы"):
        if not overhead_df.empty:
            sub = overhead_df[overhead_df["group"].isin(_OPERATIONAL_GROUPS)]
            dim = st.selectbox("Детализация по:", ["По категории", "По группе"], key="dd_ops")
            _drilldown_pivot(sub, "category" if dim == "По категории" else "group",
                             overhead_calc, months)
        else:
            st.info("Нет данных по накладным расходам")

    # 5. Финансовые расходы
    with st.expander("🔍 Детализация: Финансовые расходы"):
        if not overhead_df.empty:
            sub = overhead_df[overhead_df["group"].isin(_FINANCIAL_GROUPS)]
            if not sub.empty:
                _drilldown_pivot(sub, "category", overhead_calc, months)
            else:
                st.info("Финансовые расходы отсутствуют в данных")
        else:
            st.info("Нет данных по накладным расходам")
