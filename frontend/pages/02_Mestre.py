# ========================================
# 02_Mestre.py – Área do Administrador (Supabase)
# ========================================
import streamlit as st
if not hasattr(st, "rerun"):
    st.rerun = st.experimental_rerun  # alias p/ versões antigas

import pandas as pd
import plotly.express as px
from datetime import datetime, date, timedelta
import sys
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parent.parent
if str(_FRONTEND) not in sys.path:
    sys.path.insert(0, str(_FRONTEND))
import bootstrap  # noqa: F401 — raiz no sys.path
from backend.db import get_supabase_client, fetch_all_df

supabase = get_supabase_client()

st.set_page_config(page_title="Relatórios – Mestre", layout="wide")


# ── helpers ──
def _truthy_mask(series: pd.Series) -> pd.Series:
    """True/False, 1/0, 'true'/'false' → boolean mask."""
    if series.empty:
        return series.astype(bool)
    return series.map(lambda x: bool(x) if pd.notna(x) else False)


def _parse_dt(df: pd.DataFrame, cols) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        if c in out.columns:
            out[c] = pd.to_datetime(out[c], errors="coerce")
    return out


def _fmt_dh(s: pd.Series) -> pd.Series:
    return s.dt.strftime("%d/%m/%Y %H:%M")


def _in_date_range(df: pd.DataFrame, col: str, ini, fim) -> pd.DataFrame:
    if df.empty or col not in df.columns:
        return df.iloc[0:0]
    d = df[col].dt.date
    return df[(d >= ini) & (d <= fim)]


def registrar_fato(acao, descricao, user_id=None, entidade=None):
    """Registra um fato no banco de dados (Supabase)."""
    try:
        row = {
            "acao": acao,
            "descricao": descricao,
            "data_hora": datetime.now().isoformat(sep=" ", timespec="seconds"),
        }
        if user_id is not None:
            row["user_id"] = int(user_id)
        if entidade is not None:
            row["entidade"] = entidade
        supabase.table("fatos_usuarios").insert(row).execute()
    except Exception as e:
        st.error(f"Erro ao registrar fato: {str(e)}")


def _find_lavagem_pairs(df_tx: pd.DataFrame, df_usuarios: pd.DataFrame) -> pd.DataFrame:
    """Pares entrada→saída em ≤ 5 min (equivalente ao self-join SQL)."""
    if df_tx.empty:
        return pd.DataFrame()

    in_types = {"Recebimento", "Cash-In"}
    out_types = {"Cash-Out", "Saída", "Transferência", "Saque"}

    tin = df_tx[df_tx["tipo_transacao"].isin(in_types)][
        ["user_id", "data_hora", "valor"]
    ].rename(columns={"data_hora": "entrada", "valor": "val_in"})
    tout = df_tx[df_tx["tipo_transacao"].isin(out_types)][
        ["user_id", "data_hora", "valor"]
    ].rename(columns={"data_hora": "saida", "valor": "val_out"})

    if tin.empty or tout.empty:
        return pd.DataFrame()

    pairs = tin.merge(tout, on="user_id")
    pairs = pairs[
        (pairs["saida"] > pairs["entrada"])
        & (pairs["saida"] <= pairs["entrada"] + pd.Timedelta(minutes=5))
    ].copy()
    if pairs.empty:
        return pd.DataFrame()

    pairs["dif_min"] = (pairs["saida"] - pairs["entrada"]).dt.total_seconds() / 60.0
    cpf_map = df_usuarios.set_index("id")["cpf"] if "cpf" in df_usuarios.columns else pd.Series(dtype=object)
    pairs["cpf"] = pairs["user_id"].map(cpf_map)
    return pairs.sort_values("entrada").reset_index(drop=True)


def _cashin_sem_historico(
    df_tx: pd.DataFrame,
    df_usuarios: pd.DataFrame,
    ini,
    fim,
    min_valor: float,
    tipo: str = "Cash-In",
) -> pd.DataFrame:
    """Cash-In ≥ min_valor sem qualquer TX nos 7 dias anteriores."""
    if df_tx.empty:
        return pd.DataFrame()

    cand = _in_date_range(df_tx, "data_hora", ini, fim)
    cand = cand[(cand["tipo_transacao"] == tipo) & (cand["valor"] >= min_valor)].copy()
    if cand.empty:
        return pd.DataFrame()

    prior = df_tx[["id", "user_id", "data_hora"]].rename(
        columns={"id": "prior_id", "data_hora": "dh"}
    )
    m = cand.merge(prior, on="user_id")
    has_prior = m[
        (m["dh"] < m["data_hora"])
        & (m["dh"] >= m["data_hora"] - pd.Timedelta(days=7))
    ]["id"].unique()
    out = cand[~cand["id"].isin(has_prior)].copy()
    out["transacoes_anteriores"] = 0

    u = df_usuarios.rename(columns={"id": "user_id"})[["user_id", "username", "banco"]]
    out = out.merge(u, on="user_id", how="left")
    return out.sort_values("valor", ascending=False).reset_index(drop=True)


# ── validação de acesso ──
if not (st.session_state.get("logged_in") and st.session_state.get("is_admin")):
    st.warning("Acesso restrito a administradores.")
    st.stop()

# ── carga base (uma vez) ──
with st.spinner("Carregando dados …"):
    df_fatos_raw = fetch_all_df("fatos_usuarios")
    df_tx_raw = fetch_all_df("transacoes")
    df_usuarios = fetch_all_df("usuarios")
    df_logs_raw = fetch_all_df("logs")
    df_limites_raw = fetch_all_df("limites_usuario")
    df_tentativas_raw = fetch_all_df("tentativas_limite")
    try:
        df_hist_bloq = fetch_all_df("historico_bloqueios")
    except Exception:
        df_hist_bloq = pd.DataFrame()

df_fatos_raw = _parse_dt(df_fatos_raw, ["data_hora"])
df_tx_raw = _parse_dt(df_tx_raw, ["data_hora"])
df_logs_raw = _parse_dt(df_logs_raw, ["data_hora"])
df_tentativas_raw = _parse_dt(df_tentativas_raw, ["data_hora"])
if not df_hist_bloq.empty:
    df_hist_bloq = _parse_dt(df_hist_bloq, ["data_hora"] if "data_hora" in df_hist_bloq.columns else [])

if not df_tx_raw.empty and "suspeita" in df_tx_raw.columns:
    df_tx_raw = df_tx_raw.copy()
    df_tx_raw["_suspeita"] = _truthy_mask(df_tx_raw["suspeita"])
else:
    if not df_tx_raw.empty:
        df_tx_raw = df_tx_raw.copy()
        df_tx_raw["_suspeita"] = False

# ── KPIs no topo ──
st.title("🔒 Relatórios de Atividades dos Usuários")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Fatos do Sistema", len(df_fatos_raw))
c2.metric("Transações", len(df_tx_raw))
c3.metric(
    "Transações suspeitas",
    int(df_tx_raw["_suspeita"].sum()) if not df_tx_raw.empty else 0,
)
c4.metric("Usuários cadastrados", len(df_usuarios))

aba_fatos, aba_tx, aba_fraude, aba_edit, aba_logs, aba_senhas, aba_padrao5, aba_cashin, aba_lavagem, aba_compras, aba_compras_baixo, aba_limites, aba_fluxo, aba_risco = st.tabs(
    ["🗂️ Fatos", "💵 Transações", "🚩 Fraudes", "📝 Edições", "🛂 Logins", "🔑 Senhas",
     "🔍 Padrão 5", "💰 Cash-In Sem Histórico", "💸 Lavagem de Dinheiro",
     "🛍️ Compras Iguais", "🧾 Compras de Baixo Valor", "🛑 Limites",
     "📈 Fluxo Anômalo",
     "⚠️ Contas de Risco"]
)

# ==== CONTROLE DE LIMITES ====
with aba_limites:
    st.header("🛑 Controle de Limites por Turno")

    with st.expander("⚙️ Configurar Limites por Usuário"):
        col1, col2 = st.columns(2)
        with col1:
            user_id = st.number_input("ID do Usuário", min_value=1, key="limite_user_id")
            username = "N/A"
            if user_id and not df_usuarios.empty:
                hit = df_usuarios.loc[df_usuarios["id"] == user_id, "username"]
                if not hit.empty:
                    username = hit.iloc[0]
            st.write(f"Usuário: {username}")

        with col2:
            limite_dia = st.number_input("Limite Diurno (R$)", min_value=0.0, value=10000.0, step=100.0, key="limite_dia")
            limite_noite = st.number_input("Limite Noturno (R$)", min_value=0.0, value=5000.0, step=100.0, key="limite_noite")

        if st.button("Salvar Limites", key="salvar_limites"):
            try:
                supabase.table("limites_usuario").upsert(
                    {
                        "user_id": int(user_id),
                        "limite_dia": float(limite_dia),
                        "limite_noite": float(limite_noite),
                    },
                    on_conflict="user_id",
                ).execute()
                st.success("Limites atualizados com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao atualizar limites: {str(e)}")

    with st.expander("📊 Visualizar Todos os Limites"):
        if df_usuarios.empty:
            st.info("Nenhum usuário cadastrado.")
        else:
            u = df_usuarios[["id", "username"]].rename(columns={"id": "user_id"})
            lim = df_limites_raw if not df_limites_raw.empty else pd.DataFrame(columns=["user_id", "limite_dia", "limite_noite"])
            df_limites = u.merge(lim[["user_id", "limite_dia", "limite_noite"]] if "user_id" in lim.columns else lim, on="user_id", how="left")
            df_limites["limite_dia"] = df_limites["limite_dia"].fillna(10000)
            df_limites["limite_noite"] = df_limites["limite_noite"].fillna(5000)
            df_limites = df_limites.sort_values("username")
            st.dataframe(df_limites.style.format({
                "limite_dia": "R$ {:.2f}",
                "limite_noite": "R$ {:.2f}",
            }), use_container_width=True)

    with st.expander("🚨 Histórico de Tentativas de Exceder Limites"):
        if df_tentativas_raw.empty:
            st.info("Nenhuma tentativa de exceder limites registrada")
        else:
            df_tentativas = df_tentativas_raw.merge(
                df_usuarios[["id", "username"]].rename(columns={"id": "user_id"}),
                on="user_id",
                how="left",
            )
            df_tentativas = df_tentativas.sort_values("data_hora", ascending=False).head(200)
            df_tentativas["excedente"] = df_tentativas["valor_tentativa"] - df_tentativas["limite"]
            df_tentativas["data_hora_fmt"] = _fmt_dh(df_tentativas["data_hora"])

            st.write(f"Total de tentativas: {len(df_tentativas)}")
            show = df_tentativas.rename(columns={"data_hora_fmt": "data_hora"})[
                [c for c in ["id", "user_id", "username", "valor_tentativa", "limite", "turno", "data_hora", "excedente"] if c in df_tentativas.columns or c == "data_hora"]
            ]
            # rebuild display cols
            disp = df_tentativas.copy()
            disp["data_hora"] = disp["data_hora_fmt"]
            cols_show = [c for c in ["id", "user_id", "username", "valor_tentativa", "limite", "turno", "data_hora", "excedente"] if c in disp.columns]
            st.dataframe(disp[cols_show].style.format({
                "valor_tentativa": "R$ {:.2f}",
                "limite": "R$ {:.2f}",
                "excedente": "R$ {:.2f}",
            }), use_container_width=True)

            tab1, tab2 = st.tabs(["Por Usuário", "Por Turno"])
            with tab1:
                vc = df_tentativas["username"].value_counts().reset_index()
                vc.columns = ["username", "count"]
                fig_user = px.bar(vc, x="username", y="count", title="Tentativas por Usuário")
                st.plotly_chart(fig_user, use_container_width=True)
            with tab2:
                fig_turno = px.pie(df_tentativas, names="turno", title="Distribuição por Turno")
                st.plotly_chart(fig_turno, use_container_width=True)

# ==== FATOS ====
with aba_fatos:
    st.header("🗂️ Histórico Completo de Atividades")
    st.markdown("""
    **Registro de todas as ações realizadas no sistema:**  
    • Acompanhamento completo de atividades dos usuários  
    • Alterações, cadastros, exclusões e outras operações  
    """)

    if df_fatos_raw.empty:
        st.info("Nenhum fato registrado.")
    else:
        df_fatos = df_fatos_raw.merge(
            df_usuarios[["id", "username"]].rename(columns={"id": "user_id"}),
            on="user_id",
            how="left",
        ).sort_values("id", ascending=False).head(1000)
        df_fatos = df_fatos.assign(
            data_hora=_fmt_dh(df_fatos["data_hora"]),
            entidade=df_fatos["entidade"].fillna("–") if "entidade" in df_fatos.columns else "–",
        )
        cols = [c for c in ["id", "data_hora", "username", "acao", "entidade", "descricao"] if c in df_fatos.columns]
        st.dataframe(df_fatos[cols], use_container_width=True)

# ==== TRANSACOES ====
with aba_tx:
    st.header("💵 Todas as Transações Financeiras")
    st.markdown("""
    **Registro completo de movimentações financeiras:**  
    • Compras, transferências, pagamentos e outras operações  
    • Identificação de transações marcadas como suspeitas  
    """)

    if df_tx_raw.empty:
        st.info("Nenhuma transação.")
    else:
        df_tx = df_tx_raw.merge(
            df_usuarios[["id", "username"]].rename(columns={"id": "user_id"}),
            on="user_id",
            how="left",
        ).sort_values("id", ascending=False).head(1000).copy()
        df_tx["flag"] = df_tx["_suspeita"].map(lambda x: "🚩" if x else "")
        df_tx["data_hora"] = _fmt_dh(df_tx["data_hora"])
        df_tx["forma"] = df_tx["forma_pagamento"].fillna("–") if "forma_pagamento" in df_tx.columns else "–"
        df_tx["tipo"] = df_tx["tipo_transacao"]
        st.dataframe(df_tx[["id", "data_hora", "username", "tipo", "forma", "valor", "flag"]], use_container_width=True)
        fig_tx = px.pie(df_tx, names="tipo", title="Distribuição por Tipo de Transação")
        st.plotly_chart(fig_tx, use_container_width=True)

# ==== FRAUDES ====
with aba_fraude:
    st.subheader("🚩 Transações marcadas como suspeitas")
    col_ini, col_fim = st.columns(2)
    ini = col_ini.date_input("De", date.today() - timedelta(days=30), key="fraude_ini_date")
    fim = col_fim.date_input("Até", date.today(), key="fraude_fim_date")

    df_fraud = _in_date_range(df_tx_raw[df_tx_raw["_suspeita"]], "data_hora", ini, fim) if not df_tx_raw.empty else pd.DataFrame()
    if not df_fraud.empty:
        df_fraud = df_fraud.merge(
            df_usuarios[["id", "username"]].rename(columns={"id": "user_id"}),
            on="user_id",
            how="left",
        ).sort_values("id", ascending=False)
        show = df_fraud.assign(
            data_hora=_fmt_dh(df_fraud["data_hora"]),
            tipo=df_fraud["tipo_transacao"],
            motivo=df_fraud["motivo_suspeita"] if "motivo_suspeita" in df_fraud.columns else None,
        )
        cols = [c for c in ["id", "data_hora", "username", "tipo", "valor", "motivo"] if c in show.columns]
        st.write(f"➤ Encontradas {len(show)} transações suspeitas")
        st.dataframe(show[cols], use_container_width=True)
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(px.pie(show, names="tipo", title="Tipos de Transações Suspeitas"), use_container_width=True)
        with col2:
            st.plotly_chart(px.histogram(show, x="valor", title="Distribuição de Valores"), use_container_width=True)
    else:
        st.write("➤ Encontradas 0 transações suspeitas")
        st.dataframe(pd.DataFrame(), use_container_width=True)

# ==== EDIÇÕES DE PERFIL ====
with aba_edit:
    st.subheader("📝 Histórico de Edições de Perfil")
    col1, col2 = st.columns(2)
    with col1:
        data_ini = st.date_input("De", date.today() - timedelta(days=30), key="edit_ini_date")
    with col2:
        data_fim = st.date_input("Até", date.today(), key="edit_fim_date")

    if df_fatos_raw.empty:
        df_edit = pd.DataFrame()
    else:
        mask = df_fatos_raw["acao"] == "editar_perfil" if "acao" in df_fatos_raw.columns else False
        df_edit = _in_date_range(df_fatos_raw[mask], "data_hora", data_ini, data_fim)
        if not df_edit.empty:
            df_edit = df_edit.merge(
                df_usuarios[["id", "username"]].rename(columns={"id": "user_id"}),
                on="user_id",
                how="left",
            ).sort_values("id", ascending=False).head(500)
            df_edit = df_edit.assign(
                data_hora=_fmt_dh(df_edit["data_hora"]),
                de=df_edit["valor_antigo"] if "valor_antigo" in df_edit.columns else None,
                para=df_edit["valor_novo"] if "valor_novo" in df_edit.columns else None,
            )

    if df_edit.empty:
        st.dataframe(pd.DataFrame(), use_container_width=True)
    else:
        cols = [c for c in ["id", "data_hora", "username", "campo", "de", "para"] if c in df_edit.columns]
        st.dataframe(df_edit[cols], use_container_width=True)
        vc = df_edit["campo"].value_counts().reset_index()
        vc.columns = ["campo", "count"]
        st.plotly_chart(px.bar(vc, x="campo", y="count", title="Campos Mais Editados"), use_container_width=True)

# ==== ALTERAÇÕES DE SENHA ====
with aba_senhas:
    st.subheader("🔑 Histórico de Alterações de Senha")
    col1, col2 = st.columns(2)
    with col1:
        senha_ini = st.date_input("De", date.today() - timedelta(days=30), key="senha_ini_date")
    with col2:
        senha_fim = st.date_input("Até", date.today(), key="senha_fim_date")

    if df_fatos_raw.empty:
        df_senhas = pd.DataFrame()
    else:
        mask = df_fatos_raw["acao"] == "Alterar senha"
        df_senhas = _in_date_range(df_fatos_raw[mask], "data_hora", senha_ini, senha_fim)
        if not df_senhas.empty:
            df_senhas = df_senhas.merge(
                df_usuarios[["id", "username"]].rename(columns={"id": "user_id"}),
                on="user_id",
                how="left",
            ).sort_values("id", ascending=False).head(500)
            df_senhas = df_senhas.assign(data_hora=_fmt_dh(df_senhas["data_hora"]))

    if df_senhas.empty:
        st.dataframe(pd.DataFrame(), use_container_width=True)
    else:
        cols = [c for c in ["id", "data_hora", "username", "descricao"] if c in df_senhas.columns]
        st.dataframe(df_senhas[cols], use_container_width=True)
        vc = df_senhas["username"].value_counts().reset_index()
        vc.columns = ["username", "count"]
        st.plotly_chart(px.bar(vc, x="username", y="count", title="Alterações por Usuário"), use_container_width=True)

# ==== LOGINS ====
with aba_logs:
    st.subheader("Tentativas de Login")
    col1, col2, col3 = st.columns(3)
    with col1:
        data_inicio = st.date_input("Data inicial", value=date.today() - timedelta(days=30), key="log_ini_date")
    with col2:
        data_fim = st.date_input("Data final", value=date.today(), key="log_fim_date")
    with col3:
        resultado = st.selectbox("Resultado", ["Todos", "Sucesso", "Falha"], key="log_result_select")

    df_logs = _in_date_range(df_logs_raw, "data_hora", data_inicio, data_fim) if not df_logs_raw.empty else pd.DataFrame()
    if not df_logs.empty and resultado != "Todos":
        want = "ok" if resultado == "Sucesso" else "fail"
        df_logs = df_logs[df_logs["resultado"] == want]

    if df_logs.empty:
        st.dataframe(pd.DataFrame(), use_container_width=True)
    else:
        df_logs = df_logs.merge(
            df_usuarios[["id", "username"]].rename(columns={"id": "user_id"}),
            on="user_id",
            how="left",
        ).sort_values("id", ascending=False).head(1000)
        df_logs = df_logs.assign(
            data_hora=_fmt_dh(df_logs["data_hora"]),
            usuario=df_logs["username"].fillna("–"),
        )
        cols = [c for c in ["id", "data_hora", "usuario", "resultado", "ip", "user_agent"] if c in df_logs.columns]
        st.dataframe(df_logs[cols], use_container_width=True)
        st.plotly_chart(px.pie(df_logs, names="resultado", title="Resultado das Tentativas"), use_container_width=True)

# ==== PADRÃO 5 ====
with aba_padrao5:
    st.header("🔍 Padrão 5: Troca de Dados + Pagamentos")
    st.markdown(
        """
        **Esta análise identifica possível lavagem de dinheiro ou conta tomada**  
        quando um usuário altera dados sensíveis (e-mail / telefone) e, dentro de poucas horas, 
        realiza pagamentos ou transferências de valor. O objetivo é sinalizar contas que mudam 
        o canal de contato antes de movimentar dinheiro, um comportamento típico de fraude.
        """
    )

    st.subheader("Todas as Alterações de Dados Sensíveis")
    if df_fatos_raw.empty:
        df_alteracoes = pd.DataFrame()
    else:
        mask = (
            (df_fatos_raw["acao"] == "editar_perfil")
            & (df_fatos_raw["campo"].isin(["email", "telefone"]))
        )
        df_alteracoes = df_fatos_raw[mask].merge(
            df_usuarios[["id", "username"]].rename(columns={"id": "user_id"}),
            on="user_id",
            how="left",
        ).sort_values("data_hora", ascending=False).head(1000)

    if not df_alteracoes.empty:
        show_alt = df_alteracoes.assign(data_hora=_fmt_dh(df_alteracoes["data_hora"]))
        cols = [c for c in ["id", "username", "campo", "acao", "data_hora", "valor_antigo", "valor_novo"] if c in show_alt.columns]
        st.dataframe(show_alt[cols], use_container_width=True, height=400)
        col1, col2 = st.columns(2)
        col1.metric("Total de Alterações", len(df_alteracoes))
        col2.metric("Última Alteração", show_alt["data_hora"].iloc[0])
    else:
        st.info("Nenhuma alteração de dados sensíveis encontrada")

    st.subheader("Pagamentos Realizados Após Alteração de Dados")
    st.markdown("""
    **Lista de transações realizadas até 24 horas após alteração de e-mail/telefone:**
    """)

    pay_types_upper = {"SAQUE", "TRANSFERENCIA", "TRANSFERÊNCIA", "PAGAMENTO", "TED", "DOC", "PIX", "CASH-OUT"}
    if df_fatos_raw.empty or df_tx_raw.empty:
        df_padrao5 = pd.DataFrame()
    else:
        alts = df_fatos_raw[
            (df_fatos_raw["acao"] == "editar_perfil")
            & (df_fatos_raw["campo"].isin(["email", "telefone"]))
        ]
        ult_alt = alts.groupby("user_id", as_index=False)["data_hora"].max().rename(columns={"data_hora": "alt_time"})
        pay = df_tx_raw[df_tx_raw["tipo_transacao"].astype(str).str.upper().isin(pay_types_upper)][
            ["user_id", "data_hora", "valor", "tipo_transacao", "forma_pagamento", "banco"]
            if "banco" in df_tx_raw.columns
            else ["user_id", "data_hora", "valor", "tipo_transacao", "forma_pagamento"]
        ].copy()
        if "banco" not in pay.columns:
            pay["banco"] = None
        merged = ult_alt.merge(pay, on="user_id")
        merged = merged[
            (merged["data_hora"] > merged["alt_time"])
            & (merged["data_hora"] <= merged["alt_time"] + pd.Timedelta(hours=24))
        ].copy()
        if merged.empty:
            df_padrao5 = pd.DataFrame()
        else:
            merged["horas_apos_alteracao"] = (
                (merged["data_hora"] - merged["alt_time"]).dt.total_seconds() / 3600.0
            )
            u = df_usuarios[["id", "username", "banco"]].rename(columns={"id": "user_id", "banco": "banco_u"})
            merged = merged.merge(u, on="user_id", how="left")
            merged["banco"] = merged["banco"].fillna(merged["banco_u"])
            df_padrao5 = merged.assign(
                usuario=merged["username"],
                alteracao=_fmt_dh(merged["alt_time"]),
                pagamento=_fmt_dh(merged["data_hora"]),
                tipo=merged["tipo_transacao"],
                forma=merged["forma_pagamento"],
            ).sort_values("data_hora", ascending=False).head(1000)

    if not df_padrao5.empty:
        st.markdown("### Resumo Financeiro")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total de Casos", len(df_padrao5))
        col2.metric("Valor Total", f"R$ {df_padrao5['valor'].sum():,.2f}")
        col3.metric("Valor Médio", f"R$ {df_padrao5['valor'].mean():,.2f}")
        col4.metric("Tempo Médio", f"{df_padrao5['horas_apos_alteracao'].mean():.1f} horas")

        st.markdown("### Top 5 Maiores Valores")
        top5 = df_padrao5.nlargest(5, "valor")[["usuario", "banco", "valor", "tipo", "horas_apos_alteracao"]]
        st.dataframe(
            top5.style.format({"valor": "R$ {:.2f}", "horas_apos_alteracao": "{:.1f} horas"}),
            use_container_width=True,
        )
        csv = df_padrao5.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Exportar CSV",
            csv,
            file_name=f"padrao5_troca_dados_pagamentos_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )
    else:
        st.success("✅ Nenhum caso de pagamento após alteração de dados encontrado")

# ==== REGRA 6: CASH-IN SEM HISTÓRICO ====
with aba_cashin:
    st.header("💰 Regra 6: Cash-In Sem Histórico")
    st.markdown("""
    **Detecta transações de entrada de dinheiro (Cash-In) em contas:**  
    1. Sem transações anteriores nos últimos 7 dias  
    2. Com valores acima de R$ 5.000  
    """)

    col1, col2 = st.columns(2)
    with col1:
        cashin_ini = st.date_input("Data inicial", date.today() - timedelta(days=30), key="cashin_ini_date")
    with col2:
        cashin_fim = st.date_input("Data final", date.today(), key="cashin_fim_date")

    min_valor = st.number_input("Valor mínimo (R$)", min_value=5000, value=5000, step=1000, key="cashin_min_valor")

    if st.button("Analisar Cash-In Suspeitos", key="cashin_analisar_btn"):
        try:
            df_cashin = _cashin_sem_historico(df_tx_raw, df_usuarios, cashin_ini, cashin_fim, min_valor, tipo="Cash-In")
            if not df_cashin.empty:
                st.success(f"✅ {len(df_cashin)} transações suspeitas encontradas")
                col1, col2, col3 = st.columns(3)
                col1.metric("Total de Casos", len(df_cashin))
                col2.metric("Maior Valor", f"R$ {df_cashin['valor'].max():,.2f}")
                col3.metric("Média de Valor", f"R$ {df_cashin['valor'].mean():,.2f}")

                st.dataframe(
                    df_cashin.style.format({
                        "valor": "R$ {:.2f}",
                        "transacoes_anteriores": "{:,}",
                        "data_hora": lambda x: x.strftime("%d/%m/%Y %H:%M") if not pd.isnull(x) else "",
                    }),
                    use_container_width=True,
                )

                tab1, tab2 = st.tabs(["Por Banco", "Distribuição de Valores"])
                with tab1:
                    vc = df_cashin["banco"].value_counts().reset_index()
                    vc.columns = ["banco", "count"]
                    st.plotly_chart(px.bar(vc, x="banco", y="count", title="Cash-In Suspeitos por Banco"), use_container_width=True)
                with tab2:
                    st.plotly_chart(px.histogram(df_cashin, x="valor", title="Distribuição de Valores", nbins=20), use_container_width=True)

                csv = df_cashin.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "📥 Exportar CSV",
                    csv,
                    file_name=f"cashin_suspeito_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    key="cashin_export_btn",
                )
            else:
                st.info("Nenhuma transação de Cash-In suspeita encontrada")
        except Exception as e:
            st.error(f"Erro na análise: {str(e)}")

# ==== LAVAGEM ====
with aba_lavagem:
    st.header("💸 Lavagem de Dinheiro – Entradas e Saídas Imediatas")
    st.markdown("""
    São exibidos todos os pares de entrada (Recebimento / Cash-In)  
    e saída (Cash-Out, Transferência, Saque) ocorrendo em até 5 minutos  
    entre as transações, sem filtro de valor.  
    """)

    df_lav = _find_lavagem_pairs(df_tx_raw, df_usuarios)

    if df_lav.empty:
        st.info("✅ Nenhum par suspeito encontrado.")
    else:
        df_tbl = (
            df_lav.assign(
                entrada=lambda d: d["entrada"].dt.strftime("%d/%m/%Y %H:%M:%S"),
                saida=lambda d: d["saida"].dt.strftime("%d/%m/%Y %H:%M:%S"),
            ).rename(columns={
                "cpf": "CPF",
                "val_in": "Valor Entrada (R$)",
                "val_out": "Valor Saída (R$)",
                "dif_min": "Intervalo (min)",
            })
        )
        st.subheader(f"Pares suspeitos encontrados: {len(df_tbl)}")
        st.dataframe(df_tbl, use_container_width=True)

        st.markdown("---")
        fig_scatter = px.scatter(
            df_lav,
            x="dif_min",
            y="val_out",
            color="cpf",
            size="val_out",
            hover_data=["entrada", "saida"],
            labels={"dif_min": "Intervalo (min)", "val_out": "Valor Saída (R$)", "cpf": "CPF"},
            title="Intervalo entre Entrada → Saída vs Valor de Saída",
            template="plotly_dark",
        )
        fig_scatter.update_layout(height=350, margin=dict(t=40, b=20))
        st.plotly_chart(fig_scatter, use_container_width=True, key="mestre_lav_scatter")

        st.markdown("---")
        df_top = (
            df_lav.groupby("cpf", as_index=False)["val_out"]
            .sum()
            .rename(columns={"val_out": "Total Saída (R$)"})
            .sort_values("Total Saída (R$)", ascending=False)
        )
        max_users = st.slider(
            "Exibir top N CPFs no gráfico",
            min_value=1,
            max_value=max(1, len(df_top)),
            value=min(10, len(df_top)),
            step=1,
            key="mestre_lav_top_n",
        )
        df_plot = df_top.head(max_users)
        fig_bar = px.bar(
            df_plot,
            x="Total Saída (R$)",
            y="cpf",
            orientation="h",
            text="Total Saída (R$)",
            labels={"cpf": "CPF"},
            title=f"Top {max_users} CPFs por Total de Saída",
            template="plotly_dark",
        )
        fig_bar.update_traces(texttemplate="R$ %{text:,.2f}", textposition="outside")
        fig_bar.update_layout(
            yaxis_categoryorder="total ascending",
            height=30 * max_users + 150,
            margin=dict(l=120, r=20, t=50, b=20),
        )
        st.plotly_chart(fig_bar, use_container_width=True, key="mestre_lav_bar")

        csv = df_lav.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Exportar pares como CSV",
            csv,
            file_name="lavagem_pares.csv",
            mime="text/csv",
            key="mestre_lav_export",
        )

# ==== COMPRAS IGUAIS ====
with aba_compras:
    st.header("🛍️ Regra: Compras Iguais em Curto Período")
    st.markdown("""
    Esta visualização mostra **todas as compras repetidas por valor, loja e forma de pagamento**,  
    realizadas por um mesmo usuário, sem aplicar filtros de tempo ou quantidade mínima.
    """)

    try:
        compras = df_tx_raw[df_tx_raw["tipo_transacao"] == "Compra"].copy() if not df_tx_raw.empty else pd.DataFrame()
        if compras.empty:
            st.info("Nenhum padrão de compras repetidas encontrado.")
        else:
            g = (
                compras.groupby(["user_id", "forma_pagamento", "valor"], dropna=False)
                .agg(
                    total_compras=("id", "count"),
                    primeira_compra=("data_hora", "min"),
                    ultima_compra=("data_hora", "max"),
                    ids_transacoes=("id", lambda s: ", ".join(map(str, s))),
                )
                .reset_index()
            )
            g = g[g["total_compras"] > 1].copy()
            g["minutos_entre"] = (g["ultima_compra"] - g["primeira_compra"]).dt.total_seconds() / 60.0
            g = g.merge(
                df_usuarios[["id", "username", "banco"]].rename(columns={"id": "user_id"}),
                on="user_id",
                how="left",
            ).sort_values(["total_compras", "minutos_entre"], ascending=[False, True])

            if g.empty:
                st.info("Nenhum padrão de compras repetidas encontrado.")
            else:
                st.success(f"Total de padrões de compras repetidas: {len(g)}")
                st.dataframe(
                    g.style.format({
                        "valor": "R$ {:.2f}",
                        "minutos_entre": "{:.1f} min",
                        "primeira_compra": lambda x: x.strftime("%d/%m/%Y %H:%M") if not pd.isnull(x) else "",
                        "ultima_compra": lambda x: x.strftime("%d/%m/%Y %H:%M") if not pd.isnull(x) else "",
                    }),
                    use_container_width=True,
                )
                csv = g.to_csv(index=False).encode("utf-8")
                st.download_button("📥 Exportar CSV", csv, file_name="compras_repetidas.csv", mime="text/csv")
    except Exception as e:
        st.error(f"Erro ao buscar dados: {str(e)}")

# ==== BAIXO VALOR ====
with aba_compras_baixo:
    st.header("🧾 Regra: Tentativas de simulação com valores mínimos")
    st.markdown("""
    Esta visualização mostra **todas as transações com valor entre R$ 0,01 e R$ 1,00**, sem aplicar filtros.  
    Os dados já estão disponíveis no sistema e são exibidos para análise completa.
    """)

    try:
        if df_tx_raw.empty:
            st.info("Nenhuma transação de baixo valor encontrada.")
        else:
            df_baixo = df_tx_raw[(df_tx_raw["valor"] >= 0.01) & (df_tx_raw["valor"] <= 1.00)].copy()
            df_baixo = df_baixo.merge(
                df_usuarios[["id", "username"]].rename(columns={"id": "user_id"}),
                on="user_id",
                how="left",
            ).sort_values("data_hora", ascending=False)

            if df_baixo.empty:
                st.info("Nenhuma transação de baixo valor encontrada.")
            else:
                st.success(f"Total de transações encontradas: {len(df_baixo)}")
                cols = [c for c in ["id", "user_id", "username", "tipo_transacao", "valor", "data_hora", "forma_pagamento", "banco", "motivo_suspeita"] if c in df_baixo.columns]
                st.dataframe(
                    df_baixo[cols].style.format({
                        "valor": "R$ {:.2f}",
                        "data_hora": lambda x: x.strftime("%d/%m/%Y %H:%M") if not pd.isnull(x) else "",
                    }),
                    use_container_width=True,
                )
                csv = df_baixo.to_csv(index=False).encode("utf-8")
                st.download_button("📥 Exportar CSV", csv, file_name="transacoes_baixo_valor.csv", mime="text/csv")
    except Exception as e:
        st.error(f"Erro ao buscar dados: {str(e)}")

# ==== FLUXO ANÔMALO ====
with aba_fluxo:
    st.header("📈 Fluxo Anômalo de Gastos")
    st.markdown("""
    **O que esta aba faz?**  
    • Calcula, por usuário, o total de **saídas** (gastos) e **entradas** em um período selecionado.  
    • Compara o total de saídas deste período com as saídas do **período anterior** de mesmo tamanho.  
    • Se o usuário gastar **≥ 2 ×** o total do período anterior, gera um alerta.  
    """)

    col1, col2 = st.columns(2)
    with col1:
        ini = st.date_input("Data inicial", date.today() - timedelta(days=30), key="fluxo_ini")
    with col2:
        fim = st.date_input("Data final", date.today(), key="fluxo_fim")

    dias = (fim - ini).days + 1
    prev_ini = ini - timedelta(days=dias)
    prev_fim = ini - timedelta(days=1)

    if st.button("Analisar Fluxo", key="btn_fluxo"):
        try:
            saidas_tipos = {"Compra", "Pagamento", "Transferência", "Saque"}
            entradas_tipos = {"Recebimento", "Cash-In"}

            def _sum_by_user(df, tipos, d0, d1):
                sub = _in_date_range(df[df["tipo_transacao"].isin(tipos)], "data_hora", d0, d1)
                if sub.empty:
                    return pd.DataFrame(columns=["user_id", "valor"])
                return sub.groupby("user_id", as_index=False)["valor"].sum()

            sa = _sum_by_user(df_tx_raw, saidas_tipos, ini, fim).rename(columns={"valor": "saidas"})
            sp = _sum_by_user(df_tx_raw, saidas_tipos, prev_ini, prev_fim).rename(columns={"valor": "saidas_prev"})
            en = _sum_by_user(df_tx_raw, entradas_tipos, ini, fim).rename(columns={"valor": "entradas"})

            df_fluxo = df_usuarios[["id", "username", "banco"]].rename(columns={"id": "user_id"})
            df_fluxo = df_fluxo.merge(sa, on="user_id", how="left")
            df_fluxo = df_fluxo.merge(sp, on="user_id", how="left")
            df_fluxo = df_fluxo.merge(en, on="user_id", how="left")
            df_fluxo[["entradas", "saidas", "saidas_prev"]] = df_fluxo[["entradas", "saidas", "saidas_prev"]].fillna(0)

            def _razao(row):
                if row["saidas_prev"] == 0 and row["saidas"] > 0:
                    return 9999
                if row["saidas_prev"] == 0:
                    return 0
                return row["saidas"] / row["saidas_prev"]

            df_fluxo["razao"] = df_fluxo.apply(_razao, axis=1)
            df_fluxo = df_fluxo[df_fluxo["razao"] >= 2].sort_values("razao", ascending=False)

            if df_fluxo.empty:
                st.success("✅ Nenhum alerta de fluxo encontrado.")
            else:
                st.success(f"🚨 {len(df_fluxo)} usuários com gasto ≥ 2× o período anterior")
                st.dataframe(
                    df_fluxo.style.format({
                        "entradas": "R$ {:.2f}",
                        "saidas": "R$ {:.2f}",
                        "saidas_prev": "R$ {:.2f}",
                        "razao": "{:.2f}×",
                    }),
                    use_container_width=True,
                )
                fig = px.bar(
                    df_fluxo,
                    x="username",
                    y="razao",
                    color="razao",
                    color_continuous_scale="RdYlGn_r",
                    title="Razão de Saída Atual ÷ Saída Anterior",
                )
                st.plotly_chart(fig, use_container_width=True)
                csv = df_fluxo.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "⬇️ Exportar CSV",
                    csv,
                    file_name=f"fluxo_anomalo_{datetime.now():%Y%m%d_%H%M%S}.csv",
                    mime="text/csv",
                )
        except Exception as e:
            st.error(f"Erro na análise: {e}")

# ==== CONTAS DE RISCO ====
with aba_risco:
    st.header("⚠️ Contas com Alto Risco de Fraude")
    st.markdown("""
    Lista consolidada dos usuários com maior incidência de violações.  
    Use os botões para **Bloquear / Desbloquear / Encerrar** a conta  
    (todas as ações ficam registradas em *historico_bloqueios* e *fatos_usuarios*).
    """)

    # agregações em pandas
    if df_tx_raw.empty:
        fraudes = pd.DataFrame(columns=["user_id", "fraudes", "valor_fraudes"])
    else:
        fsub = df_tx_raw[df_tx_raw["_suspeita"]]
        fraudes = (
            fsub.groupby("user_id", as_index=False)
            .agg(fraudes=("id", "count"), valor_fraudes=("valor", "sum"))
            if not fsub.empty
            else pd.DataFrame(columns=["user_id", "fraudes", "valor_fraudes"])
        )

    if df_tentativas_raw.empty:
        tent = pd.DataFrame(columns=["user_id", "tentativas_limite"])
    else:
        tent = df_tentativas_raw.groupby("user_id", as_index=False).size().rename(columns={"size": "tentativas_limite"})

    if df_hist_bloq.empty or "acao" not in df_hist_bloq.columns:
        hist = pd.DataFrame(columns=["user_id", "bloqueios", "desbloqueios"])
    else:
        hist = df_hist_bloq.groupby("user_id").agg(
            bloqueios=("acao", lambda s: (s == "BLOQUEIO").sum()),
            desbloqueios=("acao", lambda s: (s == "DESBLOQUEIO").sum()),
        ).reset_index()

    df_risco = df_usuarios.rename(columns={"id": "user_id"}).copy()
    df_risco = df_risco.merge(fraudes, on="user_id", how="left")
    df_risco = df_risco.merge(tent, on="user_id", how="left")
    df_risco = df_risco.merge(hist, on="user_id", how="left")
    for c in ["fraudes", "valor_fraudes", "tentativas_limite", "bloqueios", "desbloqueios"]:
        if c not in df_risco.columns:
            df_risco[c] = 0
        df_risco[c] = df_risco[c].fillna(0)

    keep = (
        (df_risco["fraudes"] > 0)
        | (df_risco["tentativas_limite"] > 0)
        | (df_risco["saldo_pendente"].fillna(0) != 0 if "saldo_pendente" in df_risco.columns else False)
    )
    df_risco = df_risco[keep].sort_values(
        ["fraudes", "tentativas_limite"], ascending=[False, False]
    ).head(50)

    if df_risco.empty:
        st.warning("Nenhuma conta de risco foi identificada.")
        st.stop()

    st.dataframe(df_risco, use_container_width=True)
    st.download_button(
        "📥 Exportar CSV",
        df_risco.to_csv(index=False).encode("utf-8"),
        file_name="contas_risco.csv",
        mime="text/csv",
    )

    st.markdown("---")
    st.subheader("🔧 Ações Administrativas")

    for _, row in df_risco.iterrows():
        col1, col2, col3, _ = st.columns([4, 1, 1, 0.5])

        with col1:
            st.write(
                f"**{row.get('nome') or row.get('username')}** `({row.user_id})` • "
                f"{row.get('cidade')}/{row.get('estado')} | "
                f"Fraudes: **{int(row.fraudes)}** | "
                f"Limite: **{int(row.tentativas_limite)}** | "
                f"Saldo pendente: **R$ {row.get('saldo_pendente') or 0:,.2f}**"
            )

        with col2:
            bloqueada = bool(row.get("conta_bloqueada"))
            if bloqueada:
                if st.button("🔓 Desbloq.", key=f"unblock_{row.user_id}"):
                    try:
                        supabase.table("usuarios").update({"conta_bloqueada": False}).eq("id", int(row.user_id)).execute()
                        supabase.table("historico_bloqueios").insert({
                            "user_id": int(row.user_id),
                            "acao": "DESBLOQUEIO",
                            "motivo": "Revisão administrativa",
                        }).execute()
                        registrar_fato("DESBLOQUEIO", "Revisão administrativa", user_id=row.user_id, entidade="usuarios")
                        st.success("Usuário desbloqueado.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
            else:
                if st.button("🔒 Bloquear", key=f"block_{row.user_id}"):
                    try:
                        supabase.table("usuarios").update({"conta_bloqueada": True}).eq("id", int(row.user_id)).execute()
                        supabase.table("historico_bloqueios").insert({
                            "user_id": int(row.user_id),
                            "acao": "BLOQUEIO",
                            "motivo": "Alto risco detectado",
                        }).execute()
                        registrar_fato("BLOQUEIO", "Alto risco detectado", user_id=row.user_id, entidade="usuarios")
                        st.warning("Usuário bloqueado.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

        with col3:
            if st.button("🚫 Encerrar", key=f"close_{row.user_id}"):
                saldo = row.get("saldo_pendente") or 0
                try:
                    if saldo > 0:
                        st.warning(
                            f"Conta NÃO encerrada: saldo pendente de R$ {saldo:,.2f}. "
                            "O time responsável irá analisar a destinação dos valores."
                        )
                        registrar_fato(
                            "Encerrar – saldo pendente",
                            "Encerramento impedido por saldo pendente",
                            user_id=row.user_id,
                        )
                    else:
                        supabase.table("usuarios").update({
                            "ativo": False,
                            "motivo_inativacao": "Encerrada pela área de risco (fraudes)",
                            "data_inativacao": datetime.now().isoformat(sep=" ", timespec="seconds"),
                        }).eq("id", int(row.user_id)).execute()
                        registrar_fato("Encerrar conta", "Encerrada pela área de risco", user_id=row.user_id)
                        st.success("Conta encerrada definitivamente (saldo zerado).")
                        st.rerun()
                except Exception as e:
                    st.error(str(e))
