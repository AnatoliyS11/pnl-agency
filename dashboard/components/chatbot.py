"""AI assistant panel — right-column chat, scrolls with page."""

import streamlit as st
import pandas as pd
from dashboard.components.charts import money, pct


def _build_data_context(
    pl_df: pd.DataFrame,
    margin_df: pd.DataFrame | None,
    salary_df: pd.DataFrame | None,
    overhead_df: pd.DataFrame | None,
    months: list[str],
) -> str:
    lines = [f"Данные за период: {', '.join(months)}", ""]

    lines.append("=== P&L ===")
    for _, row in pl_df[pl_df["month"].isin(months)].iterrows():
        lines.append(
            f"{row['month']}: выручка {money(row['revenue'])}, "
            f"EBIT {money(row['ebit'])} ({pct(row['ebit_pct'])}), "
            f"ФОТ {money(row['fot'])}, "
            f"маржа вклада {money(row['contribution_margin'])}"
        )

    if margin_df is not None and not margin_df.empty:
        lines.append("\n=== Топ-5 клиентов по выручке ===")
        top = (
            margin_df[margin_df["month"].isin(months)]
            .groupby("project")["works"].sum()
            .nlargest(5)
        )
        for proj, v in top.items():
            lines.append(f"  {proj}: {money(v)}")

        lines.append("\n=== Топ-5 клиентов по марже ===")
        top_m = (
            margin_df[margin_df["month"].isin(months)]
            .groupby("project")["margin"].sum()
            .nlargest(5)
        )
        for proj, v in top_m.items():
            lines.append(f"  {proj}: {money(v)}")

        lines.append("\n=== По платформам (выручка) ===")
        by_plat = (
            margin_df[margin_df["month"].isin(months)]
            .groupby("platform")["works"].sum()
            .nlargest(5)
        )
        for plat, v in by_plat.items():
            lines.append(f"  {plat}: {money(v)}")

    if salary_df is not None and not salary_df.empty:
        lines.append("\n=== Зарплаты ===")
        sal = salary_df[salary_df["month"].isin(months)]
        hc = sal["name"].nunique()
        total_sal = float(sal["total_accrued"].sum())
        avg_sal = total_sal / hc if hc else 0.0
        lines.append(
            f"Сотрудников: {hc}, итого начислено: {money(total_sal)}, "
            f"средняя ЗП: {money(avg_sal)}"
        )
        if "role" in sal.columns:
            by_role = sal.groupby("role")["total_accrued"].sum().nlargest(5)
            for role, v in by_role.items():
                lines.append(f"  {role}: {money(v)}")

    if overhead_df is not None and not overhead_df.empty:
        lines.append("\n=== Накладные (топ-3 категории) ===")
        top_oh = (
            overhead_df[overhead_df["month"].isin(months)]
            .groupby("category")["actual"].sum()
            .nlargest(3)
        )
        for cat, v in top_oh.items():
            lines.append(f"  {cat}: {money(v)}")

    return "\n".join(lines)


def _ask_claude(user_message: str, data_context: str, history: list[dict]) -> str:
    try:
        import anthropic
        api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return "⚠️ API ключ не настроен. Добавьте ANTHROPIC_API_KEY в Streamlit Secrets."
        client = anthropic.Anthropic(api_key=api_key)
        system = (
            "Ты финансовый аналитик агентства «Шелковый путь». "
            "Отвечай строго на основе данных ниже. "
            "Язык ответов — русский. Будь краток и конкретен. "
            "Используй цифры из данных. Если данных недостаточно — честно скажи.\n\n"
            + data_context
        )
        messages = [{"role": m["role"], "content": m["content"]} for m in history[-6:]]
        messages.append({"role": "user", "content": user_message})
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=system,
            messages=messages,
        )
        return resp.content[0].text
    except Exception as e:
        return f"⚠️ Ошибка API: {e}"


def render_chatbot(
    pl_df: pd.DataFrame,
    margin_df: pd.DataFrame | None,
    salary_df: pd.DataFrame | None,
    overhead_df: pd.DataFrame | None,
    months: list[str],
) -> None:
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "chatbot_open" not in st.session_state:
        st.session_state.chatbot_open = True

    # position:fixed — работает как левый сайдбар, но справа.
    # Ширина и отступ основного контента меняются в зависимости от open/closed.
    panel_w = "300px" if st.session_state.chatbot_open else "52px"
    content_mr = "316px" if st.session_state.chatbot_open else "68px"
    st.markdown(
        f"""<div id="chatbot-col"></div>
<style>
div[data-testid="column"]:has(#chatbot-col) {{
    position: fixed !important;
    top: 0 !important;
    right: 0 !important;
    width: {panel_w} !important;
    height: 100vh !important;
    overflow-y: auto !important;
    background: #FAFAFA !important;
    border-left: 1px solid #e0e0e0 !important;
    z-index: 999 !important;
    padding: 0.75rem 0.5rem !important;
    box-shadow: -2px 0 8px rgba(0,0,0,0.06) !important;
}}
div[data-testid="stHorizontalBlock"]:has(#chatbot-col) {{
    padding-right: {content_mr} !important;
}}
</style>""",
        unsafe_allow_html=True,
    )

    btn_label = "◀" if st.session_state.chatbot_open else "▶"
    btn_help = "Свернуть" if st.session_state.chatbot_open else "Развернуть ИИ-аналитик"
    if st.button(btn_label, key="chat_toggle_btn", help=btn_help):
        st.session_state.chatbot_open = not st.session_state.chatbot_open
        st.rerun()

    if not st.session_state.chatbot_open:
        return

    st.markdown("### 🤖 ИИ-аналитик")
    st.caption("Задайте вопрос по данным")

    # История сообщений
    with st.container(height=380):
        if not st.session_state.chat_history:
            st.caption("Примеры вопросов:")
            st.caption("• Выручка за последний месяц?")
            st.caption("• Топ клиентов по марже?")
            st.caption("• Как изменился EBIT?")
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    # Форма ввода — работает внутри колонки
    with st.form(key="chat_form", clear_on_submit=True):
        user_input = st.text_input(
            "", placeholder="Введите вопрос...", label_visibility="collapsed"
        )
        submitted = st.form_submit_button("Отправить →", use_container_width=True)

    if submitted and user_input.strip():
        st.session_state.chat_history.append({"role": "user", "content": user_input.strip()})
        context = _build_data_context(pl_df, margin_df, salary_df, overhead_df, months)
        answer = _ask_claude(user_input.strip(), context, st.session_state.chat_history[:-1])
        st.session_state.chat_history.append({"role": "assistant", "content": answer})
        st.rerun()

    if st.session_state.chat_history:
        if st.button("🗑 Очистить чат", key="chat_clear_btn", use_container_width=True):
            st.session_state.chat_history = []
            st.rerun()
