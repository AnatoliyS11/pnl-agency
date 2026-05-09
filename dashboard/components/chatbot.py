"""AI assistant — position:fixed right panel."""

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
        st.session_state.chatbot_open = False  # starts as FAB bubble

    is_open = st.session_state.chatbot_open

    if is_open:
        panel_css = """
div[data-testid="column"]:has(#chatbot-col) {
    position: fixed !important;
    bottom: 90px !important;
    right: 24px !important;
    top: auto !important;
    width: 360px !important;
    height: 520px !important;
    border-radius: 16px !important;
    background: white !important;
    border: 1px solid #e0e0e0 !important;
    z-index: 9999 !important;
    box-shadow: 0 8px 40px rgba(0,0,0,0.18) !important;
    overflow-y: auto !important;
    padding: 14px 12px 8px !important;
}"""
    else:
        panel_css = """
div[data-testid="column"]:has(#chatbot-col) {
    position: fixed !important;
    bottom: 24px !important;
    right: 24px !important;
    top: auto !important;
    width: 64px !important;
    height: 64px !important;
    border-radius: 50% !important;
    background: #1a237e !important;
    z-index: 9999 !important;
    box-shadow: 0 4px 20px rgba(26,35,126,0.45) !important;
    overflow: hidden !important;
    padding: 0 !important;
}
div[data-testid="column"]:has(#chatbot-col) button {
    width: 64px !important;
    height: 64px !important;
    border-radius: 50% !important;
    background: transparent !important;
    border: none !important;
    font-size: 26px !important;
    padding: 0 !important;
    color: white !important;
}"""

    st.markdown(
        f'<div id="chatbot-col"></div><style>{panel_css}</style>',
        unsafe_allow_html=True,
    )

    # ── Closed: FAB bubble ────────────────────────────────────────────────────
    if not is_open:
        if st.button("💬", key="chat_open_btn"):
            st.session_state.chatbot_open = True
            st.rerun()
        return

    # ── Open: chat window ─────────────────────────────────────────────────────
    hdr_col, close_col = st.columns([5, 1])
    with hdr_col:
        st.markdown("**🤖 ИИ-аналитик**")
        st.caption("Задайте вопрос по данным")
    with close_col:
        if st.button("✕", key="chat_close_btn"):
            st.session_state.chatbot_open = False
            st.rerun()

    with st.container(height=310):
        if not st.session_state.chat_history:
            st.caption("Примеры вопросов:")
            st.caption("• Выручка за последний месяц?")
            st.caption("• Топ клиентов по марже?")
            st.caption("• Как изменился EBIT?")
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

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
        if st.button("🗑 Очистить", key="chat_clear_btn", use_container_width=True):
            st.session_state.chat_history = []
            st.rerun()
