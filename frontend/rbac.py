"""Controle de acesso (RBAC) — páginas admin e sidebar."""
import streamlit as st

_ADMIN_PAGE_HREF_FRAGMENTS = ("Dashboard", "Mestre", "Gerar_Dados")


def hide_admin_pages_from_sidebar() -> None:
    """Oculta links de páginas admin no menu lateral para não-administradores."""
    rules = "\n".join(
        f'[data-testid="stSidebarNav"] a[href*="{frag}"] {{ display: none; }}'
        for frag in _ADMIN_PAGE_HREF_FRAGMENTS
    )
    st.markdown(f"<style>{rules}</style>", unsafe_allow_html=True)


def require_admin() -> None:
    """Bloqueia a página atual se o usuário não for administrador."""
    if not st.session_state.get("is_admin"):
        hide_admin_pages_from_sidebar()
        st.error("Acesso restrito. Esta página é exclusiva para administradores.")
        st.stop()
