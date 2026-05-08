"""
P&L Dashboard - Marketplace direction, agency Shelkovy Put.

Run: streamlit run dashboard/app.py
(from project root: d:/Мoя папка/Разное/PNL агентства/)
"""

import sys
import pathlib

# Ensure project root is on path when running from any directory
ROOT = pathlib.Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="P&L Агентства — Маркетплейс",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Password protection ──────────────────────────────────────────────────────
import os
APP_PASSWORD = os.environ.get("APP_PASSWORD", "sHjjJP*9@1S6FTKj")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 P&L Агентства")
    pwd = st.text_input("Введите пароль", type="password")
    if st.button("Войти"):
        if pwd == APP_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Неверный пароль")
    st.stop()
# ────────────────────────────────────────────────────────────────────────────

# ── Custom CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #FAFAFA; }
    .stMetric { background: white; border-radius: 8px; padding: 12px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
    .stMetric label { font-size: 13px !important; color: #607D8B !important; }
    div[data-testid="stSidebarContent"] { background: #1a237e; color: white; }
    div[data-testid="stSidebarContent"] .stSelectbox label,
    div[data-testid="stSidebarContent"] .stRadio label { color: white !important; }
    div[data-testid="stSidebarContent"] p { color: #90CAF9; }
    h1, h2, h3 { color: #1a237e; }
    .stTabs [data-baseweb="tab"] { font-size: 14px; }
    .stAlert { border-radius: 8px; }

</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=300)
def load_data():
    from parser.margin_report import load_all_months
    from parser.overhead import parse_overhead
    from parser.refunds import load_all_refunds
    margin_df, salary_df = load_all_months()
    overhead_df = parse_overhead()
    refunds_df = load_all_refunds()
    return margin_df, salary_df, overhead_df, refunds_df


def _available_months(margin_df, overhead_df) -> list[str]:
    """Chronologically ordered list of months available in data."""
    names = set()
    if not margin_df.empty and "month" in margin_df.columns:
        names |= set(margin_df["month"].unique())
    if not overhead_df.empty and "month" in overhead_df.columns:
        names |= set(overhead_df["month"].unique())

    month_order = ["январь","февраль","март","апрель","май","июнь",
                   "июль","август","сентябрь","октябрь","ноябрь","декабрь"]
    def key(label: str):
        try:
            n, y = label.rsplit(" ", 1)
            return (int(y), month_order.index(n.lower()))
        except (ValueError, IndexError):
            return (9999, 99)
    return sorted(names, key=key)


# ── Load data first (so sidebar options are driven by actual data) ──────────
with st.spinner("Загрузка данных..."):
    try:
        margin_df, salary_df, overhead_df, refunds_df = load_data()
        load_error = None
    except Exception as e:
        margin_df = salary_df = overhead_df = refunds_df = pd.DataFrame()
        load_error = str(e)

all_months = _available_months(margin_df, overhead_df)

# ── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📊 P&L Агентства")
    st.markdown("**Маркетплейс-направление**")
    st.markdown("*Шелковый путь*")
    st.divider()

    from dashboard.components.data_uploader import render_uploader
    render_uploader()
    st.divider()

    view = st.radio(
        "Режим просмотра",
        ["👁 Собственник", "📋 Руководитель направления", "⚙️ Операционный"],
        key="view_mode",
    )

    st.divider()

    if "Собственник" not in view:
        fot_scenario = st.radio(
            "Сценарий ФОТ",
            ["employee", "ip"],
            format_func=lambda x: "👤 Сотрудник (с налогами)" if x == "employee" else "🏢 ИП (ФИКС + KPI)",
            key="fot_scenario",
            help="Сотрудник: оклад × 1.302 (НДФЛ + страховые 30.2%).\nИП: только ФИКС + KPI."
        )
    else:
        fot_scenario = "employee"

    overhead_calc = st.selectbox(
        "Тип накладных расходов",
        ["actual", "plan", "forecast"],
        format_func=lambda x: {"actual": "✅ Факт", "plan": "📋 План", "forecast": "🔮 Прогноз"}[x],
        key="overhead_calc",
    )

    month_filter = st.multiselect(
        "Месяцы",
        all_months,
        default=all_months,
        key="month_filter",
        help="Данные берутся из файлов «Для ИИ МП NN. <Месяц> <Год>». Добавьте новый файл — месяц появится сам.",
    )

    st.divider()
    st.caption("📁 Источники данных:")
    for m in all_months:
        st.caption(f"• МП {m}")
    st.caption("• Накладные расходы (V2)")
    st.divider()
    st.caption("🔄 Данные обновляются при перезагрузке страницы.")
    if st.button("♻️ Обновить данные"):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.caption("🔍 Сверка данных — см. ниже после загрузки")


if load_error:
    st.error(f"Ошибка загрузки данных: {load_error}")
    st.stop()

if margin_df.empty:
    st.warning("Файлы данных не найдены. Убедитесь, что xlsx-файлы находятся в папке проекта.")
    st.stop()

# Filter by selected months
months = month_filter or all_months
margin_filtered = margin_df[margin_df["month"].isin(months)] if not margin_df.empty else margin_df
salary_filtered = salary_df[salary_df["month"].isin(months)] if not salary_df.empty else salary_df

# Build P&L
from parser.data_model import build_pl, build_project_pl, build_forecast

pl_df = build_pl(
    margin_filtered, salary_filtered, overhead_df,
    fot_scenario=fot_scenario,
    overhead_calc=overhead_calc,
    months=months,
)

project_df = build_project_pl(
    margin_filtered, salary_filtered, overhead_df,
    fot_scenario=fot_scenario,
    overhead_calc=overhead_calc,
)

forecast_df = build_forecast(pl_df)

# ── Data validation (shown in sidebar) ───────────────────────────────────────
from dashboard.components.data_validator import validate_data as _validate
_validation = _validate(margin_filtered, salary_filtered, overhead_df, pl_df)
with st.sidebar:
    st.divider()
    _errors   = [r for r in _validation if r["level"] == "error"]
    _warnings = [r for r in _validation if r["level"] == "warning"]
    _oks      = [r for r in _validation if r["level"] == "ok"]
    if _errors:
        st.error(f"Сверка: {len(_errors)} ошибок, {len(_warnings)} предупреждений")
    elif _warnings:
        st.warning(f"Сверка: {len(_warnings)} предупреждений")
    else:
        st.success(f"Сверка: всё в норме ({len(_oks)} проверок)")
    with st.expander("Детали сверки"):
        for r in _validation:
            if r["level"] == "error":
                st.error(r["msg"])
            elif r["level"] == "warning":
                st.warning(r["msg"])
            else:
                st.caption(f"✅ {r['msg']}")

# ── Render view + AI Chatbot (right column) ──────────────────────────────────
from dashboard.components.chatbot import render_chatbot
main_col, chat_col = st.columns([3, 1], gap="medium")

with main_col:
    if "Собственник" in view:
        from dashboard.views.owner import render
        refunds_filtered = (refunds_df[refunds_df["month"].isin(months)]
                            if not refunds_df.empty else refunds_df)
        render(pl_df, overhead_df, margin_df=margin_filtered, salary_df=salary_filtered,
               months=months, overhead_calc=overhead_calc, refunds_df=refunds_filtered)

    elif "Руководитель" in view:
        from dashboard.views.director import render
        render(project_df, pl_df, months, salary_df=salary_filtered,
               fot_scenario=fot_scenario)

    else:
        from dashboard.views.operational import render
        render(pl_df, project_df, overhead_df, salary_filtered, forecast_df,
               fot_scenario=fot_scenario)

with chat_col:
    render_chatbot(pl_df, margin_filtered, salary_filtered, overhead_df, months)
