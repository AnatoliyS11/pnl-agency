"""AI assistant — floating FAB + chat panel, position:fixed via CSS :has()."""

import streamlit as st
import pandas as pd
from dashboard.components.charts import money, pct

# CSS targeting the stVerticalBlock that directly contains our anchor marker.
# :has(> div.element-container:has(#anchor-id)) means "the stVerticalBlock whose
# direct child element-container contains the anchor" — targets the innermost block.
_CHAT_CSS = """
<style>
/* ── FAB mode: tiny fixed circle at bottom-right ── */
div[data-testid="stVerticalBlock"]:has(
    > div.element-container > div[data-testid="stMarkdownContainer"] > #chatbot-fab-anchor
) {
    position: fixed !important;
    bottom: 24px !important;
    right: 24px !important;
    z-index: 9999 !important;
    width: auto !important;
    background: transparent !important;
    padding: 0 !important;
}
div[data-testid="stVerticalBlock"]:has(
    > div.element-container > div[data-testid="stMarkdownContainer"] > #chatbot-fab-anchor
) button {
    width: 56px !important;
    height: 56px !important;
    border-radius: 50% !important;
    background: #1a237e !important;
    color: white !important;
    font-size: 24px !important;
    line-height: 1 !important;
    padding: 0 !important;
    border: none !important;
    box-shadow: 0 4px 16px rgba(26,35,126,0.40) !important;
    cursor: pointer !important;
    min-height: unset !important;
}

/* ── Panel mode: card fixed at bottom-right ── */
div[data-testid="stVerticalBlock"]:has(
    > div.element-container > div[data-testid="stMarkdownContainer"] > #chatbot-panel-anchor
) {
    position: fixed !important;
    bottom: 24px !important;
    right: 24px !important;
    z-index: 9999 !important;
    width: 370px !important;
    background: white !important;
    border-radius: 16px !important;
    box-shadow: 0 8px 32px rgba(0,0,0,0.18) !important;
    padding: 16px 16px 12px !important;
    max-height: 600px !important;
    overflow-y: auto !important;
}
</style>
"""


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
    if "chatbot_open" not in st.session_state:
        st.session_state.chatbot_open = False
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Inject CSS once
    st.markdown(_CHAT_CSS, unsafe_allow_html=True)

    # ── FAB (закрыт) ──────────────────────────────────────────────────────────
    if not st.session_state.chatbot_open:
        st.markdown('<div id="chatbot-fab-anchor"></div>', unsafe_allow_html=True)
        if st.button("💬", key="chat_open_btn", help="Открыть ИИ-аналитик"):
            st.session_state.chatbot_open = True
            st.rerun()
        return

    # ── Панель (открыта) ──────────────────────────────────────────────────────
    st.markdown('<div id="chatbot-panel-anchor"></div>', unsafe_allow_html=True)

    hdr_l, hdr_r = st.columns([5, 1])
    with hdr_l:
        st.markdown("**🤖 ИИ-аналитик**")
    with hdr_r:
        if st.button("✕", key="chat_close_btn", help="Закрыть"):
            st.session_state.chatbot_open = False
            st.rerun()

    st.divider()

    with st.container(height=380):
        if not st.session_state.chat_history:
            st.caption("Спросите, например:")
            st.caption("• «Выручка за последний месяц?»")
            st.caption("• «Топ клиентов по марже?»")
            st.caption("• «Как изменился EBIT?»")
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    if prompt := st.chat_input("Спросите о данных...", key="chatbot_input"):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        context = _build_data_context(pl_df, margin_df, salary_df, overhead_df, months)
        answer = _ask_claude(prompt, context, st.session_state.chat_history[:-1])
        st.session_state.chat_history.append({"role": "assistant", "content": answer})
        st.rerun()

    if st.session_state.chat_history:
        if st.button("🗑 Очистить чат", key="chat_clear_btn", use_container_width=True):
            st.session_state.chat_history = []
            st.rerun()
