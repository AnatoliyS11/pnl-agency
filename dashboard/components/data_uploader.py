"""Sidebar uploader: drop a new monthly margin file or replace the overhead file."""

import re
from pathlib import Path
import streamlit as st

DATA_DIR = Path(__file__).resolve().parent.parent.parent
OVERHEAD_NAME = "Для ИИ V2 Расчет накладных расходов для PL.xlsx"

_MONTH_RE = re.compile(
    r"^Для ИИ МП\s*\d+\.\s*\S+\s+20\d{2}\s+Отчет по марже\.xlsx$",
    re.IGNORECASE | re.UNICODE,
)
_MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
           "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]


def _existing_monthly_count() -> int:
    return len(list(DATA_DIR.glob("Для ИИ МП *.xlsx")))


def _save_monthly(uploaded) -> tuple[bool, str]:
    """Save monthly file. Returns (ok, message)."""
    name = uploaded.name
    if not _MONTH_RE.match(name):
        return False, (
            f"Имя «{name}» не соответствует шаблону «Для ИИ МП NN. <Месяц> <Год> Отчет по марже.xlsx». "
            "Переименуйте файл и загрузите заново, либо заполните поля ниже."
        )
    target = DATA_DIR / name
    try:
        target.write_bytes(uploaded.getbuffer())
    except PermissionError:
        return False, f"Не удалось записать {name} — закройте файл в Excel и попробуйте снова."
    return True, f"Сохранено: {name}"


def _save_with_meta(uploaded, idx: int, month: str, year: int) -> tuple[bool, str]:
    target_name = f"Для ИИ МП {idx:02d}. {month} {year} Отчет по марже.xlsx"
    target = DATA_DIR / target_name
    try:
        target.write_bytes(uploaded.getbuffer())
    except PermissionError:
        return False, f"Не удалось записать {target_name} — закройте файл в Excel."
    return True, f"Сохранено как: {target_name}"


def _save_overhead(uploaded) -> tuple[bool, str]:
    target = DATA_DIR / OVERHEAD_NAME
    try:
        target.write_bytes(uploaded.getbuffer())
    except PermissionError:
        return False, "Не удалось записать файл накладных — закройте его в Excel."
    return True, f"Файл накладных обновлён: {OVERHEAD_NAME}"


def render_uploader() -> None:
    """Render the uploader UI in the sidebar (caller already inside `with st.sidebar`)."""
    with st.expander("📤 Загрузить новые данные"):
        st.caption("После загрузки кеш сбрасывается и дашборд автоматически перечитывает файлы.")

        # ── Monthly margin file ────────────────────────────────────────────
        st.markdown("**Месячный отчёт по марже (.xlsx)**")
        monthly = st.file_uploader(
            "Можно несколько файлов",
            type=["xlsx"],
            accept_multiple_files=True,
            key="uploader_monthly",
            label_visibility="collapsed",
        )

        if monthly:
            rerun_needed = False
            for f in monthly:
                ok, msg = _save_monthly(f)
                if ok:
                    st.success(msg)
                    rerun_needed = True
                else:
                    st.warning(msg)
                    with st.form(f"meta_form_{f.name}"):
                        st.caption("Укажите параметры для переименования:")
                        cols = st.columns(3)
                        idx = cols[0].number_input("№", min_value=1, max_value=99,
                                                    value=_existing_monthly_count() + 1)
                        month = cols[1].selectbox("Месяц", _MONTHS)
                        year = cols[2].number_input("Год", min_value=2020, max_value=2099, value=2026)
                        if st.form_submit_button("Сохранить"):
                            ok2, msg2 = _save_with_meta(f, int(idx), month, int(year))
                            if ok2:
                                st.success(msg2)
                                rerun_needed = True
                            else:
                                st.error(msg2)

            if rerun_needed:
                st.cache_data.clear()
                st.rerun()

        # ── Overhead file ──────────────────────────────────────────────────
        st.markdown("**Файл накладных расходов (.xlsx)**")
        overhead = st.file_uploader(
            "Один файл со всеми месяцами",
            type=["xlsx"],
            key="uploader_overhead",
            label_visibility="collapsed",
        )
        if overhead:
            ok, msg = _save_overhead(overhead)
            if ok:
                st.success(msg)
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(msg)
