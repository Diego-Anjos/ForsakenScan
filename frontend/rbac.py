"""Controle de acesso (RBAC) — páginas admin e sidebar."""
import streamlit as st

def aplicar_regras_sidebar():
    """Aplica regras de CSS para esconder links da sidebar baseado na role."""
    is_admin = st.session_state.get("is_admin", False)
    if is_admin:
        st.markdown("""
            <style>
            [data-testid="stSidebarNav"] a[href*="Perfil"] { display: none !important; }
            </style>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
            <style>
            [data-testid="stSidebarNav"] a[href*="Dashboard"] { display: none !important; }
            [data-testid="stSidebarNav"] a[href*="Mestre"] { display: none !important; }
            [data-testid="stSidebarNav"] a[href*="Gerar_Dados"] { display: none !important; }
            </style>
        """, unsafe_allow_html=True)

def hide_admin_pages_from_sidebar() -> None:
    """Alias retrocompatível para `aplicar_regras_sidebar`."""
    aplicar_regras_sidebar()

def require_admin() -> None:
    """Bloqueia a página atual se o usuário não for administrador."""
    aplicar_regras_sidebar()
    if not st.session_state.get("is_admin"):
        st.error("Acesso restrito. Esta página é exclusiva para administradores.")
        st.stop()