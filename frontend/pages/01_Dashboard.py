# ========================================
# DASHBOARD – Visão Geral de Transações & Segurança (Supabase)
# ========================================
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
if not hasattr(st, "rerun"):
    st.rerun = st.experimental_rerun  # alias p/ versões antigas

import sys
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parent.parent
if str(_FRONTEND) not in sys.path:
    sys.path.insert(0, str(_FRONTEND))
import bootstrap  # noqa: F401 — raiz no sys.path
from backend.db import get_supabase_client, fetch_all_df

# ────────────────────────────────────────
# Config
# ────────────────────────────────────────
st.set_page_config(page_title="Dashboard – Visão Geral", layout="wide")
supabase = get_supabase_client()


# ── helpers ──
def _truthy_mask(series: pd.Series) -> pd.Series:
    if series is None or (hasattr(series, "empty") and series.empty):
        return pd.Series(dtype=bool)
    return series.map(lambda x: bool(x) if pd.notna(x) else False)


def _parse_dt(df: pd.DataFrame, cols) -> pd.DataFrame:
    out = df.copy() if not df.empty else df
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
    return df[(d >= pd.Timestamp(ini).date()) & (d <= pd.Timestamp(fim).date())]


def _since_days(df: pd.DataFrame, col: str, days: int) -> pd.DataFrame:
    if df.empty or col not in df.columns:
        return df.iloc[0:0]
    cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=int(days))
    return df[df[col] >= cutoff]


def _compra_valor(row) -> float:
    vt = row.get("valor_total")
    if pd.notna(vt):
        return float(vt)
    vu = row.get("valor_unit")
    qtd = row.get("qtd")
    if pd.isna(vu):
        return 0.0
    q = 1.0 if pd.isna(qtd) else float(qtd)
    return float(vu) * q


def _find_lavagem_pairs(df_tx: pd.DataFrame) -> pd.DataFrame:
    """Entrada → saída em ≤ 5 min (self-join em pandas)."""
    if df_tx.empty:
        return pd.DataFrame()
    in_types = {"Recebimento", "Cash-In"}
    tin = df_tx[df_tx["tipo_transacao"].isin(in_types)][
        ["user_id", "cpf", "data_hora", "valor"]
    ].rename(columns={"data_hora": "entrada", "valor": "val_in"})
    tout = df_tx[~df_tx["tipo_transacao"].isin(in_types)][
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
    return pairs.sort_values("entrada").reset_index(drop=True)


def _cashin_sem_historico_agg(df_tx: pd.DataFrame, min_valor: float = 5000) -> pd.DataFrame:
    """Recebimento ≥ min_valor sem TX nos 7d anteriores; agrega por CPF."""
    if df_tx.empty:
        return pd.DataFrame()
    cand = df_tx[(df_tx["tipo_transacao"] == "Recebimento") & (df_tx["valor"] >= min_valor)].copy()
    if cand.empty:
        return pd.DataFrame()
    prior = df_tx[["id", "user_id", "data_hora"]].rename(columns={"id": "prior_id", "data_hora": "dh"})
    m = cand.merge(prior, on="user_id")
    has_prior = m[
        (m["dh"] < m["data_hora"]) & (m["dh"] >= m["data_hora"] - pd.Timedelta(days=7))
    ]["id"].unique()
    out = cand[~cand["id"].isin(has_prior)]
    if out.empty:
        return pd.DataFrame()
    return (
        out.groupby("cpf", as_index=False)
        .agg(qtd_casos=("id", "count"), total_valor=("valor", "sum"))
        .rename(columns={"cpf": "CPF"})
        .sort_values("qtd_casos", ascending=False)
        .head(10)
    )


# ────────────────────────────────────────
# Autorização mínima – admin
# ────────────────────────────────────────
sess = st.session_state
if "logged_in" not in sess or not sess.logged_in or not sess.is_admin:  # type: ignore[attr-defined]
    st.warning("⚠️ Apenas administradores podem visualizar o dashboard.")
    st.stop()

st.title("Visão Geral - Monitoramento")

# ════════════════════════════════════════
# Dados principais (carga única)
# ════════════════════════════════════════
df_tx_raw = pd.DataFrame()
try:
    with st.spinner("Carregando transações …"):
        df_tx_raw = fetch_all_df("transacoes")
except Exception:
    df_tx_raw = pd.DataFrame()

if df_tx_raw.empty:
    st.info(
        "Ainda não há transações registradas no sistema. "
        "Utilize a tela 'Gerar Dados' para simular o fluxo."
    )
    st.stop()

with st.spinner("Carregando dados auxiliares …"):
    try:
        df_usuarios = fetch_all_df("usuarios")
    except Exception:
        df_usuarios = pd.DataFrame()
    try:
        df_fatos = fetch_all_df("fatos_usuarios")
    except Exception:
        df_fatos = pd.DataFrame()
    try:
        df_logs = fetch_all_df("logs")
    except Exception:
        df_logs = pd.DataFrame()
    try:
        df_compras = fetch_all_df("compras_online")
    except Exception:
        df_compras = pd.DataFrame()

df_tx_raw = _parse_dt(df_tx_raw, ["data_hora"])
df_fatos = _parse_dt(df_fatos, ["data_hora"])
df_logs = _parse_dt(df_logs, ["data_hora"])
df_compras = _parse_dt(df_compras, ["data_hora"])

# merge tx + usuarios (banco/cpf/nome/etc.)
if not df_tx_raw.empty and not df_usuarios.empty:
    u_cols = [c for c in ["id", "banco", "cpf", "nome", "username", "email", "estado", "saldo_pendente"] if c in df_usuarios.columns]
    df_tx = df_tx_raw.merge(
        df_usuarios[u_cols].rename(columns={"id": "user_id"}),
        on="user_id",
        how="left",
        suffixes=("", "_u"),
    )
else:
    df_tx = df_tx_raw.copy() if not df_tx_raw.empty else pd.DataFrame()

if not df_tx.empty:
    df_tx["_suspeita"] = _truthy_mask(df_tx["suspeita"]) if "suspeita" in df_tx.columns else False
else:
    df_tx["_suspeita"] = pd.Series(dtype=bool)

if not df_compras.empty:
    df_compras = df_compras.copy()
    df_compras["valor_calc"] = df_compras.apply(_compra_valor, axis=1)

# KPIs
c1, c2, c3 = st.columns(3)
c1.metric("Total de transações", f"{len(df_tx):,}")
c2.metric("Volume financeiro", f"R$ {df_tx['valor'].sum():,.2f}" if not df_tx.empty else "R$ 0,00")
c3.metric("Marcadas suspeitas", f"{int(df_tx['_suspeita'].sum()):,}" if not df_tx.empty else "0")

st.divider()

# ────────────────────────────────────────
# GRÁFICO 1 – valor por tipo
# ────────────────────────────────────────
if not df_tx.empty:
    fig_tipo = px.bar(
        df_tx.groupby("tipo_transacao")["valor"].sum().reset_index(),
        x="tipo_transacao",
        y="valor",
        title="Soma de valores por tipo de transação",
        labels={"valor": "Valor (R$)", "tipo_transacao": "Tipo"},
    )
    st.plotly_chart(fig_tipo, use_container_width=True)

    # ────────────────────────────────────────
    # GRÁFICO 2 – distribuição por banco
    # ────────────────────────────────────────
    if "banco" in df_tx.columns:
        fig_banco = px.pie(df_tx, names="banco", values="valor", title="Valores por banco")
        st.plotly_chart(fig_banco, use_container_width=True)

# ════════════════════════════════════════
# GRÁFICO 3 – explosão de transações por minuto
# ════════════════════════════════════════
with st.expander("⚡ Explosão de transações por minuto", expanded=True):
    col_f1, col_f2, col_f3 = st.columns([2, 2, 1])
    with col_f1:
        dt_ini = st.date_input("De", value=pd.Timestamp.now().date() - pd.Timedelta(days=1))
    with col_f2:
        dt_fim = st.date_input("Até", value=pd.Timestamp.now().date())
    with col_f3:
        thr_cpf = st.number_input("Mínimo p/ destacar CPF", 2, 40, value=3, step=1)

    if st.button("Gerar gráficos ⚡", key="btn_explosao"):
        sub = _in_date_range(df_tx, "data_hora", dt_ini, dt_fim)
        if sub.empty:
            st.info("Sem transações no intervalo selecionado.")
        else:
            sub = sub.copy()
            sub["minuto"] = sub["data_hora"].dt.floor("min")
            df_tot = sub.groupby("minuto", as_index=False).size().rename(columns={"size": "total"})
            df_tot = df_tot.dropna(subset=["minuto"])

            fig_tot = go.Figure(
                go.Scatter(x=df_tot["minuto"], y=df_tot["total"], mode="lines+markers", fill="tozeroy")
            )
            fig_tot.update_layout(
                title="Volume total de transações por minuto",
                xaxis_title="Timestamp",
                yaxis_title="Qtd",
                hovermode="x unified",
            )
            st.plotly_chart(fig_tot, use_container_width=True)

            if "cpf" in sub.columns:
                df_cpf = (
                    sub.groupby(["minuto", "cpf"], as_index=False)
                    .size()
                    .rename(columns={"size": "qtd"})
                )
                df_cpf = df_cpf[df_cpf["qtd"] >= thr_cpf]
                if not df_cpf.empty:
                    fig_cpf = px.scatter(
                        df_cpf,
                        x="minuto",
                        y="qtd",
                        color="cpf",
                        size="qtd",
                        title=f"CPFs com ≥ {thr_cpf} transações/min",
                        labels={"minuto": "Timestamp", "qtd": "Qtd"},
                    )
                    st.plotly_chart(fig_cpf, use_container_width=True)

# ════════════════════════════════════════
# 5) Alterações de dados sensíveis + Cash-Out
# ════════════════════════════════════════
with st.expander("🛡️ Alterações de dados sensíveis & Cash-Out", expanded=True):
    if df_fatos.empty:
        df_chg = pd.DataFrame()
    else:
        mask = df_fatos["campo"].isin(["email", "telefone"]) if "campo" in df_fatos.columns else False
        df_chg = df_fatos[mask].merge(
            df_usuarios[["id", "cpf"]].rename(columns={"id": "user_id"}) if not df_usuarios.empty else pd.DataFrame(),
            on="user_id",
            how="left",
        )
        df_chg = df_chg.assign(evento="Alteração")

    if not df_tx.empty:
        df_co = df_tx[df_tx["tipo_transacao"].isin(["Cash-Out", "Saque"])][
            ["user_id", "data_hora", "valor"]
        ].assign(evento="Cash-Out")
    else:
        df_co = pd.DataFrame()

    if df_chg.empty:
        st.info("Nenhuma alteração de e-mail ou telefone registrada.")
    else:
        st.subheader("🗒️ Ocorrências de alteração")
        st.dataframe(df_chg.head(5), use_container_width=True)

        st.subheader("📊 Contagem de alterações por campo")
        df_cnt = df_chg["campo"].value_counts().reset_index()
        df_cnt.columns = ["Campo", "Quantidade"]
        fig_cnt = px.bar(
            df_cnt,
            x="Campo",
            y="Quantidade",
            text_auto=True,
            color="Campo",
            title="Total de alterações por tipo de dado",
            template="plotly_dark",
        )
        fig_cnt.update_layout(showlegend=False)
        st.plotly_chart(fig_cnt, use_container_width=True)

        st.subheader("📌 Timeline Alteração vs Cash-Out (janela 24h)")
        parts = []
        if not df_chg.empty:
            parts.append(df_chg[["user_id", "data_hora", "evento"]])
        if not df_co.empty:
            parts.append(df_co[["user_id", "data_hora", "evento"]])
        df_timeline = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
        if not df_usuarios.empty and not df_timeline.empty:
            df_timeline = df_timeline.merge(
                df_usuarios[["id", "cpf"]].rename(columns={"id": "user_id"}),
                on="user_id",
                how="left",
            )
            df_timeline.dropna(subset=["cpf"], inplace=True)
            fig = px.scatter(
                df_timeline,
                x="data_hora",
                y="cpf",
                color="evento",
                symbol="evento",
                title="⏱️ Timeline de Alterações e Saques (Cash-Out)",
                labels={"data_hora": "Data/Hora", "cpf": "Usuário"},
                template="plotly_dark",
            )
            fig.update_traces(marker=dict(size=9))
            fig.update_layout(yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True)

# ════════════════════════════════════════
# 6) Entradas & Saídas em ≤ 5 min (lavagem)
# ════════════════════════════════════════
with st.expander("💸 Entradas & Saídas em ≤ 5 min (lavagem)", expanded=True):
    df_lav = _find_lavagem_pairs(df_tx)

    if df_lav.empty:
        st.info("Nenhum par suspeito encontrado.")
    else:
        df_tbl = (
            df_lav.assign(
                entrada=lambda d: d["entrada"].dt.strftime("%d/%m/%Y %H:%M:%S"),
                saida=lambda d: d["saida"].dt.strftime("%d/%m/%Y %H:%M:%S"),
            ).rename(columns={
                "cpf": "CPF",
                "val_in": "Valor Entrada (R$)",
                "val_out": "Valor Saída (R$)",
                "dif_min": "Δ Tempo (min)",
            })
        )
        st.subheader(f"Pares suspeitos encontrados ({len(df_tbl)})")
        st.dataframe(df_tbl, use_container_width=True)

        st.markdown("---")
        fig_scatter = px.scatter(
            df_lav,
            x="dif_min",
            y="val_out",
            color="cpf",
            size="val_out",
            hover_data=["entrada", "saida"],
            labels={"dif_min": "Tempo entre (min)", "val_out": "Valor Saída (R$)", "cpf": "CPF"},
            title="Saídas em até 5 min após entrada",
            template="plotly_dark",
        )
        fig_scatter.update_layout(height=350, margin=dict(t=40, b=20))
        st.plotly_chart(fig_scatter, use_container_width=True, key="lav_scatter")

        st.markdown("---")
        df_top = (
            df_lav.groupby("cpf", as_index=False)["val_out"]
            .sum()
            .rename(columns={"val_out": "Total Saída (R$)"})
            .sort_values("Total Saída (R$)", ascending=False)
        )
        max_users = st.slider(
            "Exibir top N usuários no gráfico",
            min_value=1,
            max_value=max(1, len(df_top)),
            value=min(10, len(df_top)),
            step=1,
            key="lav_top_n",
        )
        df_plot = df_top.head(max_users)
        fig_bar = px.bar(
            df_plot,
            x="Total Saída (R$)",
            y="cpf",
            orientation="h",
            text="Total Saída (R$)",
            labels={"cpf": "CPF"},
            title=f"Top {max_users} Usuários por Total de Saída Suspeita",
            template="plotly_dark",
        )
        fig_bar.update_traces(texttemplate="R$ %{text:,.2f}", textposition="outside")
        fig_bar.update_layout(
            yaxis_categoryorder="total ascending",
            height=30 * max_users + 150,
            margin=dict(l=120, r=20, t=50, b=20),
        )
        st.plotly_chart(fig_bar, use_container_width=True, key="lav_bar")

# ════════════════════════════════════════
# 7) Alterações de senha múltiplas vezes
# ════════════════════════════════════════
with st.expander("🔑 Alterações de senha múltiplas vezes", expanded=False):
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        dias_ref = st.number_input(
            "Período analisado (dias)", min_value=1, max_value=90, value=30, step=1, key="pwd_dias_ref_7"
        )
    with col_t2:
        thr_pwd = st.number_input(
            "Mínimo de trocas para alertar", min_value=2, max_value=20, value=3, step=1, key="pwd_thr_pwd_7"
        )

    if st.button("Verificar trocas de senha", key="btn_pwd_7"):
        if df_fatos.empty:
            st.success("Nenhuma troca de senha registrada no período.")
        else:
            mask = (df_fatos["campo"] == "senha") | (df_fatos["acao"] == "Alterar senha")
            df_pwd = _since_days(df_fatos[mask], "data_hora", dias_ref)
            if not df_usuarios.empty and not df_pwd.empty:
                df_pwd = df_pwd.merge(
                    df_usuarios[["id", "cpf"]].rename(columns={"id": "user_id"}),
                    on="user_id",
                    how="left",
                )
            if df_pwd.empty:
                st.success("Nenhuma troca de senha registrada no período.")
            else:
                cnt = (
                    df_pwd.groupby(["user_id", "cpf"]).size().reset_index(name="qtd")
                    .query("qtd >= @thr_pwd")
                    .sort_values("qtd", ascending=False)
                )
                st.metric("Usuários acima do limite", f"{cnt.shape[0]}")
                if cnt.empty:
                    st.info(f"Nenhum usuário com ≥ {thr_pwd} trocas de senha nos últimos {dias_ref} dias.")
                else:
                    fig_bar_pwd = px.bar(
                        cnt.head(15),
                        x="qtd",
                        y="cpf",
                        orientation="h",
                        text="qtd",
                        labels={"qtd": "Trocas", "cpf": "CPF"},
                        title=f"Top usuários por trocas de senha (últimos {dias_ref} dias)",
                    )
                    fig_bar_pwd.update_layout(yaxis_categoryorder="total ascending")
                    st.plotly_chart(fig_bar_pwd, use_container_width=True)

# ════════════════════════════════════════
# 8) Top 5 maiores valores recebidos
# ════════════════════════════════════════
with st.expander("💰 Top 5 maiores valores recebidos", expanded=False):
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        dias_receb = st.number_input("Período (dias)", min_value=1, max_value=365, value=30, step=1)
    with col_r2:
        forma_in = st.selectbox(
            "Filtrar forma",
            ["Todas", "Recebimento", "Cash-In", "Pix", "Transferência"],
            index=0,
        )

    if st.button("Gerar ranking", key="btn_top_receb"):
        filtros_in = ("Recebimento", "Cash-In") if forma_in == "Todas" else (forma_in,)
        df_in = _since_days(df_tx[df_tx["tipo_transacao"].isin(filtros_in)], "data_hora", dias_receb) if not df_tx.empty else pd.DataFrame()
        if df_in.empty:
            st.info("Nenhuma entrada no período selecionado.")
        else:
            top_in = (
                df_in.groupby(["user_id", "cpf", "nome"])["valor"]
                .sum()
                .sort_values(ascending=False)
                .head(5)
                .reset_index()
            )
            view = st.radio("Visualização", ["Pizza", "Ranking (barra)"], horizontal=True)
            if view == "Pizza":
                fig_pie = px.pie(
                    top_in,
                    names="cpf",
                    values="valor",
                    hover_data=["nome", "valor"],
                    hole=0.45,
                    title=f"Top 5 CPFs por valor de entrada (últimos {dias_receb} dias)",
                )
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                fig_bar = px.bar(
                    top_in,
                    x="valor",
                    y="cpf",
                    text="valor",
                    orientation="h",
                    labels={"valor": "Valor Recebido (R$)", "cpf": "CPF"},
                    title=f"Top 5 CPFs por valor de entrada (últimos {dias_receb} dias)",
                )
                fig_bar.update_layout(yaxis_categoryorder="total ascending")
                st.plotly_chart(fig_bar, use_container_width=True)
            st.dataframe(top_in.rename(columns={"valor": "Valor Recebido (R$)"}), use_container_width=True)

# ════════════════════════════════════════
# 9) Compras on-line – soma por categoria
# ════════════════════════════════════════
with st.expander("🛒 Compras por categoria (on-line)", expanded=False):
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        dias_comp = st.number_input("Período (dias)", min_value=1, max_value=365, value=90, step=1)
    with col_c2:
        top_n = st.number_input("Mostrar Top-N categorias", min_value=3, max_value=30, value=10, step=1)

    if st.button("Gerar gráfico", key="btn_cat"):
        if df_compras.empty:
            st.info("Nenhuma compra encontrada no período selecionado.")
        else:
            sub = _since_days(df_compras, "data_hora", dias_comp)
            if sub.empty:
                st.info("Nenhuma compra encontrada no período selecionado.")
            else:
                sub = sub.copy()
                sub["categoria"] = sub["categoria"].fillna("(Sem categoria)") if "categoria" in sub.columns else "(Sem categoria)"
                df_cat = (
                    sub.groupby("categoria", as_index=False)["valor_calc"]
                    .sum()
                    .rename(columns={"valor_calc": "total"})
                    .sort_values("total", ascending=False)
                    .head(int(top_n))
                )
                fig_cat = px.bar(
                    df_cat,
                    x="total",
                    y="categoria",
                    orientation="h",
                    text="total",
                    labels={"total": "Valor total (R$)", "categoria": "Categoria"},
                    title=f"Top {len(df_cat)} categorias – soma de compras on-line (últimos {dias_comp} dias)",
                )
                fig_cat.update_layout(yaxis_categoryorder="total ascending")
                st.plotly_chart(fig_cat, use_container_width=True)
                st.dataframe(df_cat.rename(columns={"total": "Valor total (R$)"}), use_container_width=True)

# ════════════════════════════════════════
# 10) Top usuários por valor de compras
# ════════════════════════════════════════
with st.expander("💳 Top usuários que mais gastam em compras", expanded=False):
    col_u1, col_u2 = st.columns(2)
    with col_u1:
        dias_usr = st.number_input(
            "Período (dias)", min_value=1, max_value=365, value=90, step=1, key="top_comp_dias_usr"
        )
    with col_u2:
        top_u = st.number_input(
            "Mostrar Top-N usuários", min_value=3, max_value=50, value=10, step=1, key="top_comp_n_usr"
        )

    if st.button("Gerar ranking de gastos", key="btn_top_user_comp"):
        parts = []
        if not df_compras.empty:
            on = _since_days(df_compras, "data_hora", dias_usr)[["user_id", "valor_calc"]].rename(
                columns={"valor_calc": "valor"}
            )
            parts.append(on)
        if not df_tx.empty:
            txc = _since_days(df_tx[df_tx["tipo_transacao"] == "Compra"], "data_hora", dias_usr)[
                ["user_id", "valor"]
            ]
            parts.append(txc)
        df_comb = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
        if df_comb.empty:
            st.info("Nenhuma compra encontrada no período selecionado.")
        else:
            df_top = (
                df_comb.groupby("user_id")["valor"]
                .sum()
                .sort_values(ascending=False)
                .head(int(top_u))
                .reset_index()
            )
            if not df_usuarios.empty:
                df_top = df_top.merge(
                    df_usuarios[["id", "cpf", "nome"]].rename(columns={"id": "user_id"}),
                    on="user_id",
                    how="left",
                )
            fig_topu = px.bar(
                df_top,
                x="valor",
                y="cpf",
                orientation="h",
                text="valor",
                hover_data=["nome"] if "nome" in df_top.columns else None,
                labels={"valor": "Gasto total (R$)", "cpf": "CPF"},
                title=f"Top {len(df_top)} usuários por gastos em compras (últimos {dias_usr} dias)",
            )
            fig_topu.update_layout(yaxis_categoryorder="total ascending")
            st.plotly_chart(fig_topu, use_container_width=True)
            df_disp = (
                df_top.rename(columns={"cpf": "CPF", "nome": "Nome", "valor": "Gasto total (R$)"})
                .loc[:, [c for c in ["CPF", "Nome", "Gasto total (R$)"] if c in df_top.rename(columns={"cpf": "CPF", "nome": "Nome", "valor": "Gasto total (R$)"}).columns]]
            )
            st.dataframe(df_disp, use_container_width=True)

# ════════════════════════════════════════
# 11) Média de valor por categoria
# ════════════════════════════════════════
with st.expander("📊 Média de pagamentos por categoria", expanded=False):
    dias_media = st.number_input(
        "Dias para média", min_value=1, max_value=365, value=90, step=1, key="media_cat_dias"
    )
    if st.button("Calcular média", key="btn_media_cat"):
        if df_compras.empty:
            st.info("Nenhuma compra encontrada no período selecionado.")
        else:
            sub = _since_days(df_compras, "data_hora", dias_media)
            if sub.empty:
                st.info("Nenhuma compra encontrada no período selecionado.")
            else:
                sub = sub.copy()
                sub["categoria"] = sub["categoria"].fillna("(Sem categoria)") if "categoria" in sub.columns else "(Sem categoria)"
                df_avg = (
                    sub.groupby("categoria", as_index=False)["valor_calc"]
                    .mean()
                    .rename(columns={"valor_calc": "media"})
                    .sort_values("media", ascending=False)
                )
                fig_avg = px.bar(
                    df_avg,
                    x="categoria",
                    y="media",
                    text="media",
                    labels={"categoria": "Categoria", "media": "Média (R$)"},
                    title=f"Média de pagamentos por categoria (últimos {dias_media} dias)",
                    template="plotly_dark",
                )
                fig_avg.update_traces(texttemplate="R$ %{text:,.2f}", textposition="outside")
                fig_avg.update_layout(xaxis_tickangle=-30, yaxis_title="Média (R$)")
                st.plotly_chart(fig_avg, use_container_width=True)
                st.dataframe(df_avg.rename(columns={"media": "Média (R$)"}), use_container_width=True)

# ════════════════════════════════════════
# 12) Radar de risco – usuários suspeitos
# ════════════════════════════════════════
with st.expander("🕵️ Radar de Risco - Usuários Suspeitos", expanded=False):
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        dias_risk = st.number_input(
            "Período de análise (dias)", min_value=1, max_value=365, value=30, step=1, key="radar_periodo_suspeitos"
        )
    with col_r2:
        min_suspeitas = st.number_input(
            "Mínimo de transações suspeitas",
            min_value=1,
            value=3,
            step=1,
            help="Filtra apenas usuários com N ou mais transações suspeitas",
        )

    if st.button("Buscar usuários suspeitos", key="btn_buscar_suspeitos"):
        if df_tx.empty:
            st.warning(f"Nenhum usuário com {min_suspeitas} ou mais transações suspeitas nos últimos {dias_risk} dias.")
        else:
            sus = _since_days(df_tx[df_tx["_suspeita"]], "data_hora", dias_risk)
            df_suspeitos = (
                sus.groupby(["user_id", "cpf"], as_index=False)
                .agg(qtd_suspeitas=("id", "count"), valor_total_suspeitas=("valor", "sum"))
                .query("qtd_suspeitas >= @min_suspeitas")
                .sort_values("qtd_suspeitas", ascending=False)
                .rename(columns={"user_id": "id"})
            ) if not sus.empty else pd.DataFrame()

            if df_suspeitos.empty:
                st.warning(f"Nenhum usuário com {min_suspeitas} ou mais transações suspeitas nos últimos {dias_risk} dias.")
            else:
                usuario_selecionado = st.selectbox(
                    "Selecione um usuário para análise detalhada",
                    df_suspeitos["cpf"].tolist(),
                    key="select_suspeito",
                )
                user_id = int(df_suspeitos.loc[df_suspeitos["cpf"] == usuario_selecionado, "id"].iloc[0])

                with st.spinner("Calculando métricas de risco..."):
                    if not df_fatos.empty:
                        fp = _since_days(df_fatos[df_fatos["user_id"] == user_id], "data_hora", dias_risk)
                        qtd_perfil = int(
                            (
                                fp["campo"].isin(["email", "telefone"])
                                | fp["acao"].astype(str).str.startswith("Alterar")
                            ).sum()
                        ) if not fp.empty else 0
                    else:
                        qtd_perfil = 0

                    if not df_compras.empty:
                        total_comp = float(
                            _since_days(df_compras[df_compras["user_id"] == user_id], "data_hora", dias_risk)[
                                "valor_calc"
                            ].sum()
                        )
                    else:
                        total_comp = 0.0

                    saldo_pend = 0.0
                    if not df_usuarios.empty:
                        hit = df_usuarios.loc[df_usuarios["id"] == user_id, "saldo_pendente"]
                        if not hit.empty and pd.notna(hit.iloc[0]):
                            saldo_pend = float(hit.iloc[0])

                    qtd_suspeitas = int(
                        df_suspeitos.loc[df_suspeitos["cpf"] == usuario_selecionado, "qtd_suspeitas"].iloc[0]
                    )
                    valor_suspeitas = float(
                        df_suspeitos.loc[df_suspeitos["cpf"] == usuario_selecionado, "valor_total_suspeitas"].iloc[0]
                    )

                    df_radar = pd.DataFrame({
                        "theta": [
                            "Alterações de perfil",
                            "Total compras (R$)",
                            "Saldo pendente (R$)",
                            "Transações suspeitas",
                            "Valor suspeitas (R$)",
                        ],
                        "r": [qtd_perfil, total_comp, saldo_pend, qtd_suspeitas, valor_suspeitas],
                    })
                    fig_radar = px.line_polar(
                        df_radar,
                        r="r",
                        theta="theta",
                        color="theta",
                        line_close=True,
                        markers=True,
                        color_discrete_sequence=px.colors.qualitative.Set2,
                        title=f"Radar de risco para {usuario_selecionado} (últimos {dias_risk}d)",
                    )
                    fig_radar.update_traces(fill="toself")
                    fig_radar.update_layout(
                        legend_title_text="Métrica",
                        polar=dict(radialaxis=dict(visible=True, tickangle=45)),
                    )
                    st.plotly_chart(fig_radar, use_container_width=True)

                    st.markdown("**Valores das métricas**")
                    st.dataframe(df_radar.set_index("theta").rename(columns={"r": "Valor"}), use_container_width=True)

                    st.markdown("**Transações suspeitas recentes**")
                    df_tx_suspeitas = _since_days(
                        df_tx[(df_tx["user_id"] == user_id) & df_tx["_suspeita"]],
                        "data_hora",
                        dias_risk,
                    ).sort_values("data_hora", ascending=False)
                    show = df_tx_suspeitas.rename(columns={
                        "tipo_transacao": "tipo",
                        "motivo_suspeita": "motivo",
                    })
                    cols = [c for c in ["id", "tipo", "valor", "data_hora", "motivo"] if c in show.columns]
                    st.dataframe(show[cols], use_container_width=True)

# ════════════════════════════════════════
# 13) Renda média e gastos por usuário
# ════════════════════════════════════════
with st.expander("💸 Renda média e gastos por usuário", expanded=False):
    dias_renda = st.number_input(
        "Período (dias)", min_value=1, max_value=365, value=30, step=1, key="med_renda_periodo_all"
    )
    if st.button("Calcular renda e gastos", key="btn_med_renda_all"):
        if df_tx.empty:
            st.info("Nenhum registro encontrado no período selecionado.")
        else:
            sub = _since_days(df_tx, "data_hora", dias_renda)
            df_inc = (
                sub[sub["tipo_transacao"] != "Compra"]
                .groupby(["user_id", "cpf"], as_index=False)["valor"]
                .mean()
                .rename(columns={"valor": "renda_media", "cpf": "CPF"})
            )
            df_out = (
                sub[sub["tipo_transacao"] == "Compra"]
                .groupby("user_id", as_index=False)["valor"]
                .sum()
                .rename(columns={"valor": "gasto_total"})
            )
            df_merge = (
                df_inc.merge(df_out, on="user_id", how="left")
                .fillna(0)
                .sort_values("gasto_total", ascending=False)
            )
            df_merge["renda_media"] = df_merge["renda_media"].round(2)
            df_merge["gasto_total"] = df_merge["gasto_total"].round(2)

            if df_merge.empty:
                st.info("Nenhum registro encontrado no período selecionado.")
            else:
                st.subheader(f"Renda média vs gasto total (últimos {dias_renda} dias)")
                st.dataframe(
                    df_merge.rename(columns={
                        "renda_media": "Renda média (R$)",
                        "gasto_total": "Gasto total (R$)",
                    }).set_index("CPF"),
                    use_container_width=True,
                )
                max_users = st.number_input(
                    "Qtd. de usuários no gráfico",
                    min_value=1,
                    max_value=len(df_merge),
                    value=min(15, len(df_merge)),
                    step=1,
                    key="limite_usuarios",
                )
                df_plot = df_merge.head(max_users)
                df_melt = df_plot.reset_index().melt(
                    id_vars="CPF",
                    value_vars=["renda_media", "gasto_total"],
                    var_name="Métrica",
                    value_name="Valor",
                )
                fig_cmp = px.bar(
                    df_melt,
                    x="Valor",
                    y="CPF",
                    color="Métrica",
                    orientation="h",
                    text="Valor",
                    labels={"Valor": "R$ período", "CPF": "Usuário", "Métrica": ""},
                    title=f"Comparativo: Renda média vs Gasto total (top {max_users} usuários)",
                    template="plotly_dark",
                )
                fig_cmp.update_traces(texttemplate="R$ %{text:,.2f}", textposition="outside")
                fig_cmp.update_layout(yaxis_categoryorder="total ascending", height=30 * max_users + 200)
                st.plotly_chart(fig_cmp, use_container_width=True)

# ════════════════════════════════════════
# 14) Timeline de Fatos do Sistema
# ════════════════════════════════════════
with st.expander("📜 Timeline de Fatos do Sistema & Atividades Suspeitas", expanded=False):
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        dt_inicio = st.date_input(
            label="Data início", value=date.today() - timedelta(days=30), key="fatos_data_inicio"
        )
    with col_f2:
        dt_fim = st.date_input(label="Data fim", value=date.today(), key="fatos_data_fim")

    if st.button("Gerar timeline completa", key="btn_fatos_completo"):
        if dt_fim < dt_inicio:
            st.error("⚠️ A data final deve ser maior ou igual à data inicial.")
        else:
            parts = []
            if not df_fatos.empty:
                f = _in_date_range(df_fatos, "data_hora", dt_inicio, dt_fim).copy()
                if not f.empty:
                    f["dt"] = f["data_hora"].dt.date
                    parts.append(
                        f.groupby(["dt", "acao"], as_index=False).size()
                        .rename(columns={"acao": "evento", "size": "qtd"})
                    )
            if not df_tx.empty:
                t = _in_date_range(df_tx[df_tx["_suspeita"]], "data_hora", dt_inicio, dt_fim).copy()
                if not t.empty:
                    t["dt"] = t["data_hora"].dt.date
                    t["evento"] = t["motivo_suspeita"].fillna("Transação suspeita") if "motivo_suspeita" in t.columns else "Transação suspeita"
                    parts.append(
                        t.groupby(["dt", "evento"], as_index=False).size().rename(columns={"size": "qtd"})
                    )
            df_fatos_tl = pd.concat(parts, ignore_index=True).sort_values("dt") if parts else pd.DataFrame()

            if df_fatos_tl.empty:
                st.info("Nenhum fato ou transação suspeita no período selecionado.")
            else:
                fig_fatos = px.line(
                    df_fatos_tl,
                    x="dt",
                    y="qtd",
                    color="evento",
                    markers=True,
                    labels={"dt": "Data", "qtd": "Quantidade", "evento": "Evento"},
                    title=f"Fatos & Suspeitas por dia ({dt_inicio} → {dt_fim})",
                )
                st.plotly_chart(fig_fatos, use_container_width=True, key="chart_fatos_timeline")

                df_tot_ev = (
                    df_fatos_tl.groupby("evento", as_index=False)["qtd"].sum().sort_values("qtd", ascending=True)
                )
                total_all = df_tot_ev["qtd"].sum()
                df_tot_ev["label"] = (
                    df_tot_ev["qtd"].astype(str)
                    + " ("
                    + (df_tot_ev["qtd"] / total_all * 100).round(1).astype(str)
                    + "%)"
                )
                fig_bar = px.bar(
                    df_tot_ev,
                    x="qtd",
                    y="evento",
                    orientation="h",
                    text="label",
                    labels={"evento": "Evento", "qtd": "Total"},
                    title="Total de fatos & suspeitas no período",
                )
                fig_bar.update_layout(yaxis_categoryorder="total ascending")
                st.plotly_chart(fig_bar, use_container_width=True, key="chart_fatos_bar")

# ════════════════════════════════════════
# 15) Fatos de Transações Suspeitas
# ════════════════════════════════════════
with st.expander("🚩 Fatos de transações suspeitas", expanded=False):
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        dt_inicio_tx = st.date_input(
            "De", value=pd.Timestamp.now().date() - timedelta(days=30), key="fatos_tx_de"
        )
    with col_f2:
        dt_fim_tx = st.date_input("Até", value=pd.Timestamp.now().date(), key="fatos_tx_ate")

    if st.button("Gerar gráfico", key="btn_fatos_tx"):
        if df_tx.empty:
            st.info("Nenhuma transação suspeita no período selecionado.")
        else:
            sub = _in_date_range(df_tx[df_tx["_suspeita"]], "data_hora", dt_inicio_tx, dt_fim_tx).copy()
            if sub.empty:
                st.info("Nenhuma transação suspeita no período selecionado.")
            else:
                sub["dia"] = sub["data_hora"].dt.date
                sub["motivo"] = sub["motivo_suspeita"] if "motivo_suspeita" in sub.columns else None
                df_fatos_tx = sub.groupby(["dia", "motivo"], as_index=False).size().rename(columns={"size": "qtd"})
                fig_fatos_tx = px.bar(
                    df_fatos_tx,
                    x="dia",
                    y="qtd",
                    color="motivo",
                    text="qtd",
                    labels={"dia": "Data", "qtd": "Quantidade", "motivo": "Motivo da suspeita"},
                    title=f"Transações suspeitas por motivo ({dt_inicio_tx} a {dt_fim_tx})",
                )
                fig_fatos_tx.update_layout(barmode="group", xaxis_title="Data", yaxis_title="Qtd de transações")
                st.plotly_chart(fig_fatos_tx, use_container_width=True)

# ════════════════════════════════════════
# 16) Transações marcadas como suspeitas
# ════════════════════════════════════════
with st.expander("🚩 Transações marcadas como suspeitas", expanded=False):
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        fra_ini = st.date_input("De", value=pd.Timestamp.now().date() - timedelta(days=30), key="fraudes_de")
    with col_f2:
        fra_fim = st.date_input("Até", value=pd.Timestamp.now().date(), key="fraudes_ate")

    if st.button("Gerar relatórios de fraudes", key="btn_fraudes"):
        if df_tx.empty:
            df_fraud = pd.DataFrame()
        else:
            df_fraud = _in_date_range(df_tx[df_tx["_suspeita"]], "data_hora", fra_ini, fra_fim).sort_values(
                "data_hora", ascending=False
            )
            if not df_fraud.empty:
                df_fraud = df_fraud.assign(
                    data_hora=_fmt_dh(df_fraud["data_hora"]),
                    tipo=df_fraud["tipo_transacao"],
                    motivo=df_fraud["motivo_suspeita"] if "motivo_suspeita" in df_fraud.columns else None,
                )
        st.write(f"➤ Encontradas **{len(df_fraud)}** transações suspeitas")
        cols = [c for c in ["id", "data_hora", "username", "tipo", "valor", "motivo"] if c in df_fraud.columns]
        st.dataframe(df_fraud[cols] if cols else df_fraud, use_container_width=True)
        if not df_fraud.empty:
            col_a, col_b = st.columns(2)
            with col_a:
                st.plotly_chart(
                    px.pie(df_fraud, names="tipo", title="Tipos de Transações Suspeitas", hole=0.4),
                    use_container_width=True,
                )
            with col_b:
                st.plotly_chart(
                    px.histogram(df_fraud, x="valor", nbins=20, title="Distribuição de Valores Suspeitos",
                                 labels={"valor": "Valor (R$)"}),
                    use_container_width=True,
                )

# ════════════════════════════════════════
# 17) Histórico de Edições de Perfil
# ════════════════════════════════════════
with st.expander("📝 Histórico de Edições de Perfil", expanded=False):
    c1, c2 = st.columns(2)
    with c1:
        ed_de = st.date_input("De", value=pd.Timestamp.now().date() - timedelta(days=30), key="edicoes_de")
    with c2:
        ed_ate = st.date_input("Até", value=pd.Timestamp.now().date(), key="edicoes_ate")

    if st.button("Gerar histórico de edições", key="btn_edicoes"):
        if df_fatos.empty:
            df_ed = pd.DataFrame()
        else:
            mask = df_fatos["entidade"] == "usuarios" if "entidade" in df_fatos.columns else True
            df_ed = _in_date_range(df_fatos[mask], "data_hora", ed_de, ed_ate)
            if not df_ed.empty and not df_usuarios.empty:
                df_ed = df_ed.merge(
                    df_usuarios[["id", "username"]].rename(columns={"id": "user_id"}),
                    on="user_id",
                    how="left",
                ).sort_values("data_hora", ascending=False)
                df_ed = df_ed.assign(
                    data_hora=_fmt_dh(df_ed["data_hora"]),
                    de=df_ed["valor_antigo"] if "valor_antigo" in df_ed.columns else None,
                    para=df_ed["valor_novo"] if "valor_novo" in df_ed.columns else None,
                )
        st.write(f"➤ Encontradas **{len(df_ed)}** edições de perfil")
        cols = [c for c in ["id", "data_hora", "username", "campo", "de", "para"] if c in df_ed.columns]
        st.dataframe(df_ed[cols] if cols else df_ed, use_container_width=True)
        if not df_ed.empty and "campo" in df_ed.columns:
            df_cnt = df_ed.groupby("campo").size().reset_index(name="qtd").sort_values("qtd", ascending=False)
            fig_ed = px.bar(
                df_cnt,
                x="campo",
                y="qtd",
                text="qtd",
                labels={"campo": "Campo editado", "qtd": "Nº de edições"},
                title="Campos de perfil mais editados",
            )
            fig_ed.update_layout(xaxis_title=None, yaxis_title="Edições")
            st.plotly_chart(fig_ed, use_container_width=True)

# ════════════════════════════════════════
# 18) Tentativas de Login OK vs FAIL
# ════════════════════════════════════════
with st.expander("🔐 Tentativas de Login", expanded=False):
    lcol1, lcol2 = st.columns(2)
    with lcol1:
        login_de = st.date_input(
            "Data inicial", value=pd.Timestamp.now().date() - timedelta(days=30), key="login_de"
        )
    with lcol2:
        login_ate = st.date_input("Data final", value=pd.Timestamp.now().date(), key="login_ate")

    if st.button("Gerar gráfico de logins", key="btn_logins"):
        if df_logs.empty:
            df_log = pd.DataFrame(columns=["resultado", "qtd"])
        else:
            sub = _in_date_range(df_logs, "data_hora", login_de, login_ate)
            df_log = sub.groupby("resultado", as_index=False).size().rename(columns={"size": "qtd"})
        total = int(df_log["qtd"].sum()) if not df_log.empty else 0
        st.write(f"▶️ Total de tentativas: **{total}**")
        st.dataframe(df_log, use_container_width=True)
        if not df_log.empty:
            fig_log = px.bar(
                df_log,
                x="resultado",
                y="qtd",
                color="resultado",
                text="qtd",
                labels={"resultado": "Resultado", "qtd": "Quantidade"},
                title="Tentativas de Login: OK vs FAIL",
            )
            fig_log.update_traces(textposition="outside")
            fig_log.update_layout(
                xaxis_title=None,
                yaxis_title="Número de tentativas",
                showlegend=False,
                margin=dict(t=50, b=20, l=20, r=20),
            )
            st.plotly_chart(fig_log, use_container_width=True)

# ════════════════════════════════════════
# 19) Alterações de senha (duplicata Mestre-style)
# ════════════════════════════════════════
with st.expander("🔑 Alterações de senha múltiplas vezes", expanded=False):
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        dias_ref = st.number_input(
            "Período analisado (dias)", min_value=1, max_value=90, value=30, step=1, key="pwd_dias_ref_19"
        )
    with col_t2:
        thr_pwd = st.number_input(
            "Mínimo de trocas para alertar", min_value=2, max_value=20, value=3, step=1, key="pwd_thr_pwd_19"
        )

    if st.button("Verificar trocas de senha", key="btn_pwd_19"):
        if df_fatos.empty:
            st.success("Nenhuma troca de senha registrada no período.")
        else:
            mask = (df_fatos["campo"] == "senha") | (df_fatos["acao"] == "Alterar senha")
            df_pwd = _since_days(df_fatos[mask], "data_hora", dias_ref)
            if not df_pwd.empty and not df_usuarios.empty:
                df_pwd = df_pwd.merge(
                    df_usuarios[["id", "cpf"]].rename(columns={"id": "user_id"}),
                    on="user_id",
                    how="left",
                )
            if df_pwd.empty:
                st.success("Nenhuma troca de senha registrada no período.")
            else:
                cnt = (
                    df_pwd.groupby(["user_id", "cpf"]).size().reset_index(name="qtd")
                    .query("qtd >= @thr_pwd")
                    .sort_values("qtd", ascending=False)
                )
                st.metric("Usuários acima do limite", f"{cnt.shape[0]}")
                if cnt.empty:
                    st.info(f"Nenhum usuário com ≥ {thr_pwd} trocas de senha nos últimos {dias_ref} dias.")
                else:
                    fig_bar_pwd = px.bar(
                        cnt.head(15),
                        x="qtd",
                        y="cpf",
                        orientation="h",
                        text="qtd",
                        labels={"qtd": "Trocas", "cpf": "CPF"},
                        title=f"Top usuários por trocas de senha (últimos {dias_ref} dias)",
                    )
                    fig_bar_pwd.update_layout(yaxis_categoryorder="total ascending")
                    st.plotly_chart(fig_bar_pwd, use_container_width=True)

# ════════════════════════════════════════
# 20) Cash-In Sem Histórico
# ════════════════════════════════════════
with st.expander("💰 Regra 6: Cash-In Sem Histórico", expanded=False):
    df_cashin = _cashin_sem_historico_agg(df_tx, min_valor=5000)
    if df_cashin.empty:
        st.info("Nenhuma transação suspeita encontrada.")
    else:
        fig = px.bar(
            df_cashin,
            x="qtd_casos",
            y="CPF",
            orientation="h",
            text="qtd_casos",
            labels={"qtd_casos": "Casos sem histórico", "CPF": "Usuário"},
            title="Top 10 Usuários com Cash-In Sem Histórico (≥ R$ 5 000)",
            template="plotly_dark",
        )
        fig.update_layout(yaxis=dict(autorange="reversed"), margin=dict(l=100, t=50, r=20, b=20))
        fig.update_traces(texttemplate="%{text}", textposition="outside")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(
            df_cashin.rename(columns={"qtd_casos": "Casos sem histórico", "total_valor": "Valor total (R$)"}),
            use_container_width=True,
        )

# ════════════════════════════════════════
# 21) Contas com Alto Risco de Fraude
# ════════════════════════════════════════
with st.expander("⚠️ Contas com Alto Risco de Fraude", expanded=False):
    risco_de = st.date_input("Data inicial", key="dash_risco_de")
    risco_ate = st.date_input("Data final", key="dash_risco_ate")
    top_n = st.number_input("Top N usuários", min_value=1, value=10, step=1, key="dash_risco_topn")

    if st.button("Gerar lista de risco", key="dash_btn_risco"):
        if df_tx.empty:
            df_risco = pd.DataFrame()
        else:
            sub = _in_date_range(df_tx[df_tx["_suspeita"]], "data_hora", risco_de, risco_ate)
            if sub.empty:
                df_risco = pd.DataFrame()
            else:
                agg_kw = {
                    "total_suspeitas": ("id", "count"),
                    "valor_total_suspeitas": ("valor", "sum"),
                    "ultima_suspeita": ("data_hora", "max"),
                }
                for col in ("username", "email", "banco"):
                    if col in sub.columns:
                        agg_kw[col] = (col, "first")
                df_risco = (
                    sub.groupby("user_id", as_index=False)
                    .agg(**agg_kw)
                    .sort_values(["total_suspeitas", "valor_total_suspeitas"], ascending=[False, False])
                    .head(int(top_n))
                )

        if df_risco.empty:
            st.info("Nenhuma conta com transações suspeitas nesse período.")
        else:
            st.success(f"{len(df_risco)} contas com transações suspeitas")
            c1, c2, c3 = st.columns(3)
            c1.metric("Contas suspeitas", len(df_risco))
            c2.metric("Máx. Suspeitas", int(df_risco["total_suspeitas"].max()))
            c3.metric("Valor Médio (R$)", f"R$ {df_risco['valor_total_suspeitas'].mean():,.2f}")

            df_tabela = df_risco.assign(
                valor_total_suspeitas=lambda d: d["valor_total_suspeitas"].map("R$ {:,.2f}".format),
                ultima_suspeita=lambda d: d["ultima_suspeita"].dt.strftime("%d/%m/%Y %H:%M"),
            )
            st.dataframe(df_tabela, use_container_width=True)

            fig = px.bar(
                df_risco.sort_values("total_suspeitas", ascending=True),
                x="total_suspeitas",
                y="username",
                orientation="h",
                labels={"total_suspeitas": "Qtd. Suspeitas", "username": "Usuário"},
                title=f"Top {top_n} contas por transações suspeitas",
                hover_data=["valor_total_suspeitas", "ultima_suspeita"],
            )
            fig.update_layout(margin=dict(t=40, b=20, l=120, r=20), yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True)

# ════════════════════════════════════════
# Estatísticas de Valores de Transação
# ════════════════════════════════════════
with st.expander("📊 Estatísticas de Valores de Transação", expanded=False):
    df_stats = df_tx[["valor", "_suspeita"]].rename(columns={"_suspeita": "suspeita"}) if not df_tx.empty else pd.DataFrame(columns=["valor", "suspeita"])

    if df_stats.empty:
        st.info("Sem transações para estatísticas.")
    else:
        média = df_stats["valor"].mean()
        mediana = df_stats["valor"].median()
        std_dev = df_stats["valor"].std()
        cv_rel = (std_dev / média * 100) if média else 0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Média (R$)", f"R$ {média:,.2f}")
        k2.metric("Mediana (R$)", f"R$ {mediana:,.2f}")
        k3.metric("Desvio-Padrão (R$)", f"R$ {std_dev:,.2f}")
        k4.metric("Coef. Var (%)", f"{cv_rel:.1f}%")

        st.markdown("---")
        fig = px.histogram(
            df_stats,
            x="valor",
            nbins=30,
            title="Distribuição de Valores de Transação",
            labels={"valor": "Valor (R$)"},
        )
        st.plotly_chart(fig, use_container_width=True)

        resumo = pd.DataFrame({
            "Estatística": ["Média", "Mediana", "Desvio-Padrão", "Coef. Var (%)"],
            "Valor": [
                f"R$ {média:,.2f}",
                f"R$ {mediana:,.2f}",
                f"R$ {std_dev:,.2f}",
                f"{cv_rel:.1f}%",
            ],
        }).set_index("Estatística")
        st.table(resumo)

# ════════════════════════════════════════
# Fraudes Detectadas por Banco
# ════════════════════════════════════════
with st.expander("🚨 Fraudes Detectadas por Banco", expanded=False):
    if df_tx.empty or "banco" not in df_tx.columns:
        st.info("Nenhuma fraude detectada.")
    else:
        df_fraud_bank = (
            df_tx[df_tx["_suspeita"]]
            .groupby("banco", as_index=False)
            .size()
            .rename(columns={"size": "qtd"})
            .sort_values("qtd", ascending=False)
        )
        if df_fraud_bank.empty:
            st.info("Nenhuma fraude detectada.")
        else:
            st.metric("Bancos afetados", df_fraud_bank["banco"].nunique())
            fig_fb = px.bar(
                df_fraud_bank,
                x="qtd",
                y="banco",
                orientation="h",
                text="qtd",
                labels={"qtd": "Qtd de fraudes", "banco": "Banco"},
                title="Quantidade de fraudes por banco",
                template="plotly_dark",
            )
            fig_fb.update_layout(
                yaxis_categoryorder="total ascending",
                margin=dict(l=120, r=40, t=50, b=40),
                height=400,
            )
            fig_fb.update_traces(texttemplate="%{text}", textposition="outside")
            st.plotly_chart(fig_fb, use_container_width=True)
            st.dataframe(df_fraud_bank.rename(columns={"qtd": "Qtd de fraudes"}), use_container_width=True)

# ════════════════════════════════════════
# Tendências (Últimos N dias)
# ════════════════════════════════════════
with st.expander("📈 Tendências (Últimos N dias)", expanded=False):
    col_per, col_met = st.columns(2)
    with col_per:
        n_dias = st.slider("Período (dias)", 7, 90, 30)
    with col_met:
        metricas = st.multiselect(
            "Indicadores",
            ["Total transações", "Volume (R$)", "Fraudes (qtd)", "Volume fraudado (R$)"],
            default=["Total transações", "Fraudes (qtd)"],
        )

    if df_tx.empty or not metricas:
        st.info("Sem dados para tendência.")
    else:
        cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=n_dias - 1)
        df_per = df_tx[df_tx["data_hora"].dt.date >= cutoff.date()].copy()
        df_per["dia"] = df_per["data_hora"].dt.date
        df_per["fraud_val"] = df_per["valor"].where(df_per["_suspeita"], 0)

        daily = (
            df_per.groupby("dia", as_index=False)
            .agg(
                total_tx=("id", "count"),
                volume=("valor", "sum"),
                fraud_qtd=("_suspeita", "sum"),
                fraud_vol=("fraud_val", "sum"),
            )
            .sort_values("dia")
        )

        map_cols = {
            "Total transações": "total_tx",
            "Volume (R$)": "volume",
            "Fraudes (qtd)": "fraud_qtd",
            "Volume fraudado (R$)": "fraud_vol",
        }
        df_long = daily.melt(
            id_vars="dia",
            value_vars=[map_cols[m] for m in metricas],
            var_name="Métrica",
            value_name="valor",
        )
        df_long["Métrica"] = df_long["Métrica"].map({v: k for k, v in map_cols.items()})

        fig_trend = px.line(
            df_long,
            x="dia",
            y="valor",
            color="Métrica",
            markers=True,
            labels={"dia": "Data", "valor": "Valor"},
            title=f"Tendência diária (últimos {n_dias} dias)",
        )
        st.plotly_chart(fig_trend, use_container_width=True)

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Tx/dia (média)", f"{daily['total_tx'].mean():,.0f}")
        k2.metric("Vol/dia (R$)", f"{daily['volume'].mean():,.2f}")
        tot_tx = daily["total_tx"].sum()
        k3.metric("% fraudes", f"{(daily['fraud_qtd'].sum() / tot_tx * 100) if tot_tx else 0:.2f}%")
        k4.metric("Vol. fraudado (R$)", f"{daily['fraud_vol'].sum():,.2f}")

# ════════════════════════════════════════
# Fraudes por Estado
# ════════════════════════════════════════
with st.expander("📍 Fraudes por Estado", expanded=False):
    if df_tx.empty:
        st.info("Nenhuma fraude detectada por estado.")
    else:
        # estado pode vir só de usuarios — já mergeado se existir
        if "estado" not in df_tx.columns and not df_usuarios.empty and "estado" in df_usuarios.columns:
            df_tx_est = df_tx.merge(
                df_usuarios[["id", "estado"]].rename(columns={"id": "user_id"}),
                on="user_id",
                how="left",
            )
        else:
            df_tx_est = df_tx

        if "estado" not in df_tx_est.columns:
            st.info("Nenhuma fraude detectada por estado.")
        else:
            sub = df_tx_est[df_tx_est["_suspeita"]].copy()
            sub["estado"] = sub["estado"].fillna("(Ignorado)")
            df_est = (
                sub.groupby("estado", as_index=False)
                .size()
                .rename(columns={"size": "qtd_fraudes"})
                .sort_values("qtd_fraudes", ascending=False)
            )
            if df_est.empty:
                st.info("Nenhuma fraude detectada por estado.")
            else:
                fig_est = px.bar(
                    df_est,
                    x="qtd_fraudes",
                    y="estado",
                    orientation="h",
                    text="qtd_fraudes",
                    labels={"estado": "Estado", "qtd_fraudes": "Número de Fraudes"},
                    title="Quantidade de Fraudes por Estado",
                    template="plotly_dark",
                )
                fig_est.update_layout(
                    yaxis=dict(autorange="reversed"),
                    margin=dict(l=100, t=50, r=20, b=20),
                    height=400,
                )
                fig_est.update_traces(texttemplate="%{text}", textposition="outside")
                st.plotly_chart(fig_est, use_container_width=True, key="chart_fraudes_estado")
                st.dataframe(
                    df_est.rename(columns={"qtd_fraudes": "Número de Fraudes"}),
                    use_container_width=True,
                )
