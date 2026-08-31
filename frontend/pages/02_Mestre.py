# ========================================
# 02_Mestre.py – Painel Administrativo de Usuários (Supabase)
# ========================================
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

if not hasattr(st, "rerun"):
    st.rerun = st.experimental_rerun  # alias p/ versões antigas

_FRONTEND = Path(__file__).resolve().parent.parent
if str(_FRONTEND) not in sys.path:
    sys.path.insert(0, str(_FRONTEND))
import bootstrap  # noqa: F401 — raiz no sys.path
from backend.db import fetch_all_df
from rbac import aplicar_regras_sidebar, require_admin

st.set_page_config(page_title="Mestre – Usuários", layout="wide")
aplicar_regras_sidebar()
require_admin()

_COLUNAS_EXIBICAO = [
    "nome",
    "cpf",
    "email",
    "banco",
    "data_nascimento",
    "telefone",
    "cidade",
    "estado",
    "renda",
    "criado_em",
]


def _formatar_exibicao(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ("data_nascimento", "criado_em"):
        if col in out.columns:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
    if "renda" in out.columns:
        out["renda"] = out["renda"].apply(
            lambda v: f"R$ {float(v):,.2f}" if pd.notna(v) else "—"
        )
    return out[[c for c in _COLUNAS_EXIBICAO if c in out.columns]]


st.title("Painel Mestre – Usuários Cadastrados")

# ── carga de dados ──
df_usuarios = pd.DataFrame()
try:
    with st.spinner("Carregando usuários …"):
        df_usuarios = fetch_all_df("usuarios")
except Exception:
    df_usuarios = pd.DataFrame()

if df_usuarios.empty:
    st.info("Nenhum usuário cadastrado no sistema ainda.")
    st.stop()

# ── métricas ──
total = len(df_usuarios)
bancos = df_usuarios["banco"].nunique() if "banco" in df_usuarios.columns else 0
renda_media = (
    pd.to_numeric(df_usuarios["renda"], errors="coerce").mean()
    if "renda" in df_usuarios.columns
    else None
)

c1, c2, c3 = st.columns(3)
c1.metric("Total de usuários", f"{total:,}")
c2.metric("Bancos distintos", f"{bancos:,}")
c3.metric(
    "Renda média",
    f"R$ {renda_media:,.2f}" if renda_media is not None and pd.notna(renda_media) else "—",
)

st.divider()

st.subheader("Cadastro de usuários")
st.caption("Visão consolidada dos perfis registrados no sistema.")

df_exibir = _formatar_exibicao(df_usuarios)
st.dataframe(df_exibir, use_container_width=True, hide_index=True)

st.caption(f"Exibindo {len(df_exibir)} registro(s).")
