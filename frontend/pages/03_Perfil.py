# ========================================
# 03_Perfil.py – Área do usuário (Supabase)
# ========================================
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from uuid import uuid4
import secrets, string, re

import sys
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parent.parent
if str(_FRONTEND) not in sys.path:
    sys.path.insert(0, str(_FRONTEND))
import bootstrap  # noqa: F401 — raiz no sys.path
from backend.db import get_supabase_client
from backend.fraude import avaliar_transacao

supabase = get_supabase_client()


# ------------------------------------------------------------------
# Listas fixas
# ------------------------------------------------------------------
BANCOS_OPTS = [
    "Itaú","Bradesco","Nubank","Inter","Santander",
    "Banco do Brasil","Caixa","C6 Bank","BTG Pactual",
    "Banco Original","Next","Neon","PagBank","Banco Pan",
    "Banco BMG","Sicredi","Sicoob","Banrisul","BRB",
    "Banco Safra","Banco Daycoval","BV (Votorantim)"
]
EST_CIVIL_OPTS = ["Solteiro(a)","Casado(a)","Divorciado(a)","Viúvo(a)","União estável"]
SIT_PROF_OPTS  = ["Empregado","Desempregado","Autônomo","Estudante","Aposentado"]
FORMAS_PG      = ("Pix","Transferência","Cartão",
                  "Boleto pagamento","Boleto depósito")
LOJAS          = ["Amazon","Mercado Livre","Magalu","Shein",
                  "Kabum","Netshoes","Steam","Outro"]
CATEGORIAS     = ["Eletrônicos","Vestuário","Casa","Alimentos",
                  "Beleza","Games","Outros"]

# ------------------------------------------------------------------
# Funções auxiliares
# ------------------------------------------------------------------
fmt_moeda = lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X",".")

def barcode44() -> str:
    return "".join(secrets.choice(string.digits) for _ in range(44))

def prox_uteis(n=3):
    d = datetime.now().date(); add = 0
    while add < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            add += 1
    return d

def validar_cpf(cpf: str) -> bool:
    """Validação básica de CPF (apenas formato)"""
    cpf = re.sub(r'[^0-9]', '', cpf)
    return len(cpf) == 11

def only_digits(x: str) -> str:
    return re.sub(r"\D", "", x or "")

def _as_date(val):
    """Normaliza data vinda da API (str/date/datetime) para date."""
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    return pd.to_datetime(val).date()

def registrar_fato(acao, desc, campo=None, valor_antigo=None, valor_novo=None):
    try:
        row = {
            "user_id": user_id,
            "acao": acao,
            "descricao": desc,
        }
        if campo:
            row["campo"] = campo
            row["valor_antigo"] = valor_antigo
            row["valor_novo"] = valor_novo
        supabase.table("fatos_usuarios").insert(row).execute()
    except Exception as e:
        st.error(f"Erro ao registrar ação: {str(e)}")

# ------------------------------------------------------------------
# Autenticação
# ------------------------------------------------------------------
if not st.session_state.get("logged_in"):
    st.warning("⚠️ Faça login.")
    st.stop()

if st.session_state.get("is_admin"):
    st.info("Área de perfil indisponível para contas **administrador**. "
            "Use o menu **Mestre** para monitorar o sistema.")
    st.stop()

user_id   = st.session_state.user_id
username  = st.session_state.username
email     = st.session_state.email

# ------------------------------------------------------------------
# Carrega transações do cliente
# ------------------------------------------------------------------
_TX_COLS = [
    "tipo", "valor", "data_transacao", "codigo",
    "banco_origem", "banco_destino", "forma_pagamento",
    "suspeita", "motivo_suspeita",
]
_EMP_COLS = [
    "id", "user_id", "valor", "taxa_juros", "prazo_meses", "status", "criado_em",
]


def _empty_tx_df() -> pd.DataFrame:
    return pd.DataFrame(columns=_TX_COLS)


def _empty_emp_df() -> pd.DataFrame:
    return pd.DataFrame(columns=_EMP_COLS)


df = _empty_tx_df()
tot_tx = tot_out = tot_in = saldo = 0

try:
    resp = (
        supabase.table("transacoes")
        .select(
            "tipo_pagamento, valor, data_transacao, codigo, "
            "banco_origem, banco_destino, forma_pagamento, "
            "suspeita, motivo_suspeita"
        )
        .eq("user_id", user_id)
        .order("data_transacao", desc=True)
        .execute()
    )
    rows = resp.data or []
    if rows:
        df = pd.DataFrame(rows)
        df = df.rename(columns={"tipo_pagamento": "tipo"})
        df["data_transacao"] = pd.to_datetime(df["data_transacao"])
        tot_tx = len(df)
        tot_out = df[df["tipo"].isin(["Compra", "Pagamento", "Transferência"])]["valor"].sum()
        tot_in = df[df["tipo"].isin(["Recebimento", "Cash-In"])]["valor"].sum()
        saldo = tot_in - tot_out
except Exception as e:
    st.error(f"Erro ao carregar transações: {e}")
    df = _empty_tx_df()

# ------------------------------------------------------------------
# Layout
# ------------------------------------------------------------------
st.set_page_config(page_title="Meu Perfil", layout="wide")
st.markdown("""
<style>
body{background:linear-gradient(to right,#0f2027,#203a43,#2c5364)}
.card{background:#0d1117;border-radius:18px;padding:26px;text-align:center;
      box-shadow:0 0 10px #00000040}
.card h6{margin:0;font-size:1rem;color:#9ca3af;font-weight:400}
.card h3{margin:0;font-size:2.2rem}
</style>""", unsafe_allow_html=True)

st.markdown("<h1 style='display:flex;gap:8px;align-items:center'>👤 Meu Perfil</h1>",
            unsafe_allow_html=True)
st.markdown(f"**Usuário:** `{username}` | **Email:** `{email}`")

cor_saldo = "#2ecc71" if saldo >= 0 else "#e74c3c"
c1,c2,c3,c4 = st.columns(4, gap="large")
c1.markdown(f"<div class='card'><h6>Total de Transações</h6><h3>{tot_tx}</h3></div>",
            unsafe_allow_html=True)
c2.markdown(f"<div class='card'><h6>Total Gasto</h6>"
            f"<h3 style='color:#e74c3c'>{fmt_moeda(tot_out)}</h3></div>",
            unsafe_allow_html=True)
c3.markdown(f"<div class='card'><h6>Total Recebido</h6>"
            f"<h3 style='color:#2ecc71'>{fmt_moeda(tot_in)}</h3></div>",
            unsafe_allow_html=True)
c4.markdown(f"<div class='card'><h6>Saldo Disponível</h6>"
            f"<h3 style='color:{cor_saldo}'>{fmt_moeda(saldo)}</h3></div>",
            unsafe_allow_html=True)

# ------------------------------------------------------------------
# Tabs
# ------------------------------------------------------------------
tab_transf, tab_shop, tab_extrato, tab_loan = st.tabs(
    ("💸 Pagamentos / Boletos", "🛒 Compras Online",
     "📊 Extrato Detalhado",    "💳 Ofertas de Empréstimo")
)


# ---------- TAB 1 (Pagamentos/Boleto) -----------------------------
with tab_transf:
    if df.empty:
        st.info("Nenhuma transação registrada ainda. Realize sua primeira operação abaixo.")
    st.markdown("### Realizar Pagamento/Transferência")

    c_forma,c_cpf,c_val,c_pwd,c_btn = st.columns([2,2,1,1,1])
    with c_forma:
        forma = st.selectbox("Forma", FORMAS_PG, key="pg_forma")
    with c_cpf:
        cpf_dest = st.text_input("CPF destinatário (opcional)", key="pg_cpf",
                                help="Somente números, sem pontos ou traços")
    with c_val:
        valor = st.number_input("Valor (R$)", min_value=0.01, step=10.0,
                                format="%.2f", key="pg_val")
    with c_pwd:
        pwd = st.text_input("Senha", type="password", key="pg_pwd")
    with c_btn:
        if st.button("Enviar/Emitir", key="btn_pg",
                    help="Confirme os dados antes de enviar"):
            if valor <= 0:
                st.warning("Informe valor > 0."); st.stop()

            if cpf_dest.strip() and not validar_cpf(cpf_dest):
                st.error("CPF inválido. Digite apenas os 11 números."); st.stop()

            try:
                senha_resp = (
                    supabase.table("usuarios")
                    .select("senha")
                    .eq("id", user_id)
                    .limit(1)
                    .execute()
                )
            except Exception as e:
                st.error(f"Erro ao validar senha: {e}")
                st.stop()

            if not senha_resp.data or pwd != senha_resp.data[0]["senha"]:
                st.error("Senha incorreta."); st.stop()

            agora = datetime.now()
            tx = {"user_id": user_id, "valor": valor, "data_hora": agora}
            suspeita, motivo = avaliar_transacao(tx)

            # Boleto depósito
            if forma == "Boleto depósito":
                codigo = barcode44(); venc = prox_uteis(3)
                try:
                    supabase.table("transacoes").insert({
                        "user_id": user_id,
                        "valor": valor,
                        "tipo_pagamento": "Cash-In",
                        "forma_pagamento": "Boleto",
                        "codigo": codigo,
                        "data_transacao": agora.isoformat(),
                        "localizacao": "On-line",
                        "banco_origem": "Boleto",
                        "banco_destino": "Conta Corrente",
                        "suspeita": suspeita,
                        "motivo_suspeita": motivo,
                    }).execute()
                    registrar_fato("Cash-In", f"Boleto {fmt_moeda(valor)} gerado")

                    st.success("Boleto gerado com sucesso!")
                    st.markdown(f"""
                    **Comprovante de Boleto**  
                    **Código:** `{codigo}`  
                    **Valor:** {fmt_moeda(valor)}  
                    **Vencimento:** {venc.strftime('%d/%m/%Y')}  
                    **Status:** Gerado
                    """)
                    st.stop()
                except Exception as e:
                    st.error(f"Erro ao gerar boleto: {str(e)}")
                    st.stop()

            # Transferências normais
            if forma in ("Pix","Transferência") and not cpf_dest.strip():
                st.warning("Informe CPF destinatário."); st.stop()
            if saldo < valor and forma != "Cartão":
                st.error("Saldo insuficiente."); st.stop()

            dest = None
            cpf_limpo = only_digits(cpf_dest)
            if cpf_limpo:
                try:
                    dest_resp = (
                        supabase.table("usuarios")
                        .select("id, banco")
                        .eq("cpf", cpf_limpo)
                        .limit(1)
                        .execute()
                    )
                    dest = (dest_resp.data or [None])[0]
                    if forma in ("Pix","Transferência") and not dest:
                        st.error("CPF não encontrado."); st.stop()
                except Exception as e:
                    st.error(f"Erro ao verificar destinatário: {str(e)}")
                    st.stop()

            cod = uuid4().hex[:10]
            banco_rem = "Conta Corrente"

            try:
                supabase.table("transacoes").insert({
                    "user_id": user_id,
                    "valor": valor,
                    "tipo_pagamento": "Transferência" if dest else "Pagamento",
                    "forma_pagamento": forma,
                    "codigo": cod,
                    "data_transacao": agora.isoformat(),
                    "localizacao": "On-line",
                    "banco_origem": banco_rem,
                    "banco_destino": dest["banco"] if dest else "Estabelecimento",
                    "suspeita": suspeita,
                    "motivo_suspeita": motivo,
                }).execute()

                if dest:
                    supabase.table("transacoes").insert({
                        "user_id": dest["id"],
                        "valor": valor,
                        "tipo_pagamento": "Recebimento",
                        "forma_pagamento": forma,
                        "codigo": cod,
                        "data_transacao": agora.isoformat(),
                        "localizacao": "On-line",
                        "banco_origem": banco_rem,
                        "banco_destino": dest["banco"],
                        "suspeita": suspeita,
                        "motivo_suspeita": motivo,
                    }).execute()

                registrar_fato("Pagamento", f"{forma} {fmt_moeda(valor)}")

                st.success("Transação realizada com sucesso!")
                st.markdown(f"""
                **Comprovante de Transação**  
                **Código:** `{cod}`  
                **Tipo:** {forma}  
                **Valor:** {fmt_moeda(valor)}  
                **Data/Hora:** {agora.strftime('%d/%m/%Y %H:%M')}  
                **Status:** Concluído
                """)
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao registrar transação: {str(e)}")
                st.stop()

# ---------- TAB 2 (Compras Online) --------------------------------
with tab_shop:
    compras_vazias = df[df["tipo"] == "Compra"].empty if not df.empty else True
    if compras_vazias:
        st.info("Nenhuma compra online registrada ainda.")
    st.markdown("### Nova compra")
    s_loja, s_cat = st.columns(2)
    with s_loja:
        loja_sel = st.selectbox("Loja", LOJAS, key="loja")
        loja = st.text_input("Nome da loja", key="loja_out") if loja_sel=="Outro" else loja_sel
    with s_cat:
        categoria = st.selectbox("Categoria", CATEGORIAS, key="cat")

    prod = st.text_input("Produto / Descrição", key="produto")
    q_col, q_val = st.columns(2)
    with q_col:
        qtd = st.number_input("Qtd", min_value=1, step=1, key="qtd")
    with q_val:
        v_unit = st.number_input("Valor unitário (R$)", min_value=0.01,
                                 step=10.0, format="%.2f", key="vunit")

    total = qtd * v_unit
    st.markdown(f"**Total:** {fmt_moeda(total)}")

    pwd_shop = st.text_input("Senha", type="password", key="pwd_shop")
    if st.button("Comprar", key="btn_shop"):
        if not prod.strip():
            st.warning("Descreva o produto."); st.stop()
        if total <= 0:
            st.warning("Valor inválido."); st.stop()

        try:
            senha_resp = (
                supabase.table("usuarios")
                .select("senha")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )
            if not senha_resp.data or pwd_shop != senha_resp.data[0]["senha"]:
                st.error("Senha incorreta."); st.stop()
            if saldo < total:
                st.error("Saldo insuficiente."); st.stop()

            codigo = uuid4().hex[:10]
            agora = datetime.now()
            supabase.table("transacoes").insert({
                "user_id": user_id,
                "valor": total,
                "tipo_pagamento": "Compra",
                "forma_pagamento": "Online",
                "codigo": codigo,
                "data_transacao": agora.isoformat(),
                "localizacao": "On-line",
                "banco_origem": "Conta Corrente",
                "banco_destino": loja,
                "suspeita": 0,
            }).execute()
            supabase.table("compras_online").insert({
                "user_id": user_id,
                "codigo_tx": codigo,
                "loja": loja,
                "categoria": categoria,
                "produto": prod,
                "qtd": qtd,
                "valor_unit": v_unit,
                "valor_total": total,
                "data_hora": agora.isoformat(),
            }).execute()
            registrar_fato("Compra online", f"{loja} {fmt_moeda(total)}")

            st.success("Compra realizada com sucesso!")
            st.markdown(f"""
            **Comprovante de Compra**  
            **Loja:** {loja}  
            **Produto:** {prod}  
            **Quantidade:** {qtd}  
            **Valor Unitário:** {fmt_moeda(v_unit)}  
            **Total:** {fmt_moeda(total)}  
            **Código:** `{codigo}`  
            **Data/Hora:** {agora.strftime('%d/%m/%Y %H:%M')}
            """)
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao registrar compra: {str(e)}")
            st.stop()

# ---------- TAB 3 (Extrato Detalhado) -----------------------------
with tab_extrato:
    st.markdown("### Filtros do Extrato")

    if df.empty:
        st.info("Nenhuma transação neste período.")

    col1, col2, col3 = st.columns(3)
    with col1:
        data_inicio = st.date_input("Data inicial",
                                  value=datetime.now().date() - timedelta(days=30))
    with col2:
        data_fim = st.date_input("Data final",
                               value=datetime.now().date())
    with col3:
        filtro_tipos = st.multiselect("Tipo de transação",
                                      ["Todos", "Compra", "Pagamento", "Transferência",
                                       "Recebimento", "Cash-In", "Boleto"])

    if st.button("Aplicar Filtros"):
        df_filtrado = _empty_tx_df()
        try:
            resp = (
                supabase.table("transacoes")
                .select(
                    "tipo_pagamento, valor, data_transacao, codigo, "
                    "banco_origem, banco_destino, forma_pagamento, "
                    "suspeita, motivo_suspeita"
                )
                .eq("user_id", user_id)
                .gte("data_transacao", data_inicio.isoformat())
                .lte("data_transacao", f"{data_fim.isoformat()}T23:59:59")
                .order("data_transacao", desc=True)
                .execute()
            )
            rows = resp.data or []
            if rows:
                df_filtrado = pd.DataFrame(rows)
                df_filtrado = df_filtrado.rename(columns={"tipo_pagamento": "tipo"})
                if "Todos" not in filtro_tipos and filtro_tipos:
                    df_filtrado = df_filtrado[
                        df_filtrado["tipo"].isin(filtro_tipos)
                    ]

            if df_filtrado.empty:
                st.info("Nenhuma transação neste período.")
            else:
                df_filtrado["data_transacao"] = pd.to_datetime(df_filtrado["data_transacao"])
                st.markdown(f"**Total de transações:** {len(df_filtrado)}")

                for _, r in df_filtrado.iterrows():
                    cor = "#2ecc71" if r.tipo in ("Recebimento","Cash-In") else \
                          "#e67e22" if r.tipo=="Transferência" else "#e74c3c"
                    st.markdown(f"""
                    <div style='background:#0d1117;padding:10px 14px;border-radius:10px;margin-bottom:10px;'>
                    <b>{r.tipo}</b> | <span style='color:{cor}'>{fmt_moeda(r.valor)}</span> | {r.data_transacao.strftime('%d/%m/%Y %H:%M')}<br>
                    <small>Código: <code>{r.codigo or '—'}</code> | Forma: {r.forma_pagamento or '—'} |
                    {r.banco_origem or '—'} ▶ {r.banco_destino or '—'}</small>
                    </div>
                    """, unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Erro ao filtrar transações: {e}")

# ---------- TAB 4 (Ofertas de Empréstimo) ---------------------------
with tab_loan:
    import random
    st.markdown("### 💳 Ofertas Personalizadas de Empréstimo")

    todas_ofertas: list[dict] = []
    oferta_ativa = None
    historico_ofertas: list[dict] = []
    df_emprestimos = _empty_emp_df()

    try:
        emp_resp = (
            supabase.table("emprestimos")
            .select("*")
            .eq("user_id", user_id)
            .order("criado_em", desc=True)
            .execute()
        )
        todas_ofertas = emp_resp.data or []
        if todas_ofertas:
            df_emprestimos = pd.DataFrame(todas_ofertas)
        oferta_ativa = next(
            (o for o in todas_ofertas if o.get("status") == "oferta"), None
        )
        historico_ofertas = [
            o for o in todas_ofertas if o.get("status") != "oferta"
        ]
    except Exception as e:
        st.error(f"Erro ao carregar empréstimos: {e}")
        df_emprestimos = _empty_emp_df()

    if df_emprestimos.empty and not oferta_ativa:
        st.info("Nenhum empréstimo solicitado.")

    # Se não tem oferta ativa, verifica se precisa gerar nova
    if not oferta_ativa:
        dias_ref = 30
        desde = (datetime.now().date() - timedelta(days=dias_ref)).isoformat()
        entradas = 0.0
        saidas = 0.0
        try:
            tx_resp = (
                supabase.table("transacoes")
                .select("tipo_pagamento, valor")
                .eq("user_id", user_id)
                .gte("data_transacao", desde)
                .execute()
            )
            for row in tx_resp.data or []:
                tipo = row.get("tipo_pagamento")
                v = float(row.get("valor") or 0)
                if tipo in ("Recebimento", "Cash-In"):
                    entradas += v
                elif tipo in ("Compra", "Pagamento", "Transferência", "Saque"):
                    saidas += v
        except Exception as e:
            st.error(f"Erro ao analisar transações para oferta de crédito: {e}")

        precisa_limite = saidas > entradas * 1.2

        if precisa_limite:
            ultima_recusa = next(
                (o for o in historico_ofertas if o.get("status") == "recusado"), None
            )
            dias_desde_recusa = None
            if ultima_recusa and ultima_recusa.get("criado_em"):
                criado_dt = pd.to_datetime(ultima_recusa["criado_em"])
                dias_desde_recusa = (pd.Timestamp.now() - criado_dt).days
            if not ultima_recusa or (
                dias_desde_recusa is not None and dias_desde_recusa > 7
            ):
                try:
                    valor_oferta = random.randint(1000, 20000) // 100 * 100
                    taxa = random.choice([1.69, 1.79, 1.89, 1.99])
                    prazo = random.choice([12, 24, 36])
                    ins = (
                        supabase.table("emprestimos")
                        .insert({
                            "user_id": user_id,
                            "valor": valor_oferta,
                            "taxa_juros": taxa,
                            "prazo_meses": prazo,
                            "status": "oferta",
                        })
                        .execute()
                    )
                    oferta_ativa = (ins.data or [None])[0]
                except Exception as e:
                    st.error(f"Erro ao gerar oferta de crédito: {e}")

    # Exibição da oferta ativa (se houver)
    if oferta_ativa:
        try:
            parc = (
                oferta_ativa["valor"]
                * oferta_ativa["taxa_juros"]
                / 100
                / (1 - (1 + oferta_ativa["taxa_juros"] / 100) ** (-oferta_ativa["prazo_meses"]))
            )
        except (KeyError, TypeError, ZeroDivisionError):
            parc = 0.0
            st.error("Dados da oferta de crédito estão incompletos.")

        st.success("🎯 Temos uma oferta especial para você!")
        st.markdown(f"""
        **Valor:** {fmt_moeda(oferta_ativa.get('valor', 0))}  
        **Taxa:** {oferta_ativa.get('taxa_juros', '—')}% a.m  
        **Prazo:** {oferta_ativa.get('prazo_meses', '—')} meses  
        **Parcela estimada:** **{fmt_moeda(parc)}**
        """)

        col_aceita, col_recusa = st.columns(2)
        with col_aceita:
            if st.button("✅ Aceitar Oferta", key="btn_emprestimo_ok"):
                try:
                    supabase.table("emprestimos").update(
                        {"status": "aceito"}
                    ).eq("id", oferta_ativa["id"]).execute()
                    cod = uuid4().hex[:10]
                    supabase.table("transacoes").insert({
                        "user_id": user_id,
                        "valor": oferta_ativa["valor"],
                        "tipo_pagamento": "Cash-In",
                        "forma_pagamento": "Crédito",
                        "codigo": cod,
                        "data_transacao": datetime.now().isoformat(),
                        "localizacao": "Sistema",
                        "banco_origem": "Banco",
                        "banco_destino": "Conta Corrente",
                        "suspeita": 0,
                        "motivo_suspeita": None,
                    }).execute()
                    registrar_fato(
                        "Empréstimo",
                        f"Oferta aceita e crédito de {fmt_moeda(oferta_ativa['valor'])}",
                    )
                    st.success("Oferta aceita e valor creditado na conta!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao processar empréstimo: {e}")

        with col_recusa:
            if st.button("❌ Recusar Oferta", key="btn_emprestimo_no"):
                try:
                    supabase.table("emprestimos").update(
                        {"status": "recusado"}
                    ).eq("id", oferta_ativa["id"]).execute()
                    registrar_fato("Empréstimo", "Oferta recusada")
                    st.info(
                        "Oferta recusada. Você poderá receber novas propostas futuramente."
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao recusar oferta: {e}")
    elif not df_emprestimos.empty:
        st.warning("🚫 Nenhuma oferta disponível no momento.")
        st.info(
            "Continue movimentando sua conta para aumentar seu limite e "
            "receber novas propostas de crédito futuramente!"
        )

    if historico_ofertas:
        st.markdown("---")
        st.markdown("### Histórico de Ofertas")
        for oferta in historico_ofertas:
            status_cor = (
                "#2ecc71"
                if oferta.get("status") == "aceito"
                else "#e74c3c"
                if oferta.get("status") == "recusado"
                else "#f39c12"
            )
            criado_fmt = "—"
            if oferta.get("criado_em"):
                criado_fmt = pd.to_datetime(oferta["criado_em"]).strftime("%d/%m/%Y %H:%M")
            st.markdown(f"""
            <div style='background:#0d1117;padding:10px 14px;border-radius:10px;margin-bottom:10px;'>
            <b>Oferta de {fmt_moeda(oferta.get('valor', 0))}</b> | 
            <span style='color:{status_cor}'>{str(oferta.get('status', '—')).capitalize()}</span> | 
            {criado_fmt}<br>
            <small>Taxa: {oferta.get('taxa_juros', '—')}% a.m | Prazo: {oferta.get('prazo_meses', '—')} meses</small>
            </div>
            """, unsafe_allow_html=True)


# ------------------------------------------------------------------
# Histórico
# ------------------------------------------------------------------
st.markdown("<hr style='margin-top:28px;border:1px solid #ffffff22'>",
            unsafe_allow_html=True)
st.markdown("## 🗒️ Últimas Transações")

if df.empty:
    st.info("Nenhuma transação encontrada para este usuário.")
else:
    for _, r in df.head(15).iterrows():
        cor = "#2ecc71" if r.tipo in ("Recebimento","Cash-In") else \
              "#e67e22" if r.tipo=="Transferência" else "#e74c3c"
        st.markdown(f"""
<div style='background:#0d1117;padding:10px 14px;border-radius:10px;margin-bottom:10px;'>
<b>{r.tipo}</b> | <span style='color:{cor}'>{fmt_moeda(r.valor)}</span> | {r.data_transacao.strftime('%d/%m/%Y %H:%M')}<br>
<small>Código: <code>{r.codigo or '—'}</code> | Forma: {r.forma_pagamento or '—'} |
{r.banco_origem or '—'} ▶ {r.banco_destino or '—'}</small>
</div>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# Configurações – Editar Dados / Alterar Senha
# ------------------------------------------------------------------
st.markdown("## ⚙️ Configurações da Conta")
tab_edit, tab_pwd = st.tabs(("✏️ Editar Dados", "🔑 Alterar Senha"))

# ---------- EDITAR DADOS ------------------------------------------
with tab_edit:
    try:
        dados_resp = (
            supabase.table("usuarios")
            .select(
                "nome,email,banco,cpf,rg,data_nascimento,endereco,"
                "cidade,estado,telefone,renda,profissao,"
                "estado_civil,situacao_prof"
            )
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        dados_atuais = (dados_resp.data or [None])[0]
        if not dados_atuais:
            st.error("Usuário não encontrado.")
            st.stop()

        nasc_val = _as_date(dados_atuais["data_nascimento"])

        c1,c2 = st.columns(2, gap="large")
        with c1:
            nome_n  = st.text_input("Nome completo", value=dados_atuais["nome"])
            cpf_n   = st.text_input("CPF", value=dados_atuais["cpf"], disabled=True)
            rg_n    = st.text_input("RG",  value=dados_atuais["rg"],  disabled=True)
            nasc_n  = st.date_input("Data nasc.", value=nasc_val)
            tel_n   = st.text_input("Telefone", value=dados_atuais["telefone"])
            renda_n = st.number_input("Renda (R$)", value=float(dados_atuais["renda"] or 0),
                                      step=100.0, format="%.2f")
            est_civ = st.selectbox("Estado civil", EST_CIVIL_OPTS,
                                   index=EST_CIVIL_OPTS.index(dados_atuais["estado_civil"]))
        with c2:
            email_n = st.text_input("Email", value=dados_atuais["email"])

            bancos = BANCOS_OPTS.copy()
            if dados_atuais["banco"] not in bancos:
                bancos.insert(0, dados_atuais["banco"])
            banco_n = st.selectbox("Banco", bancos,
                                   index=bancos.index(dados_atuais["banco"]))

            end_n    = st.text_input("Endereço", value=dados_atuais["endereco"])
            cidade_n = st.text_input("Cidade", value=dados_atuais["cidade"])
            uf_n     = st.text_input("UF", value=dados_atuais["estado"], max_chars=2)
            prof_n   = st.text_input("Profissão", value=dados_atuais["profissao"])
            sit_prof = st.selectbox("Situação prof.", SIT_PROF_OPTS,
                                    index=SIT_PROF_OPTS.index(dados_atuais["situacao_prof"]))

        if st.button("Salvar alterações"):
            if not validar_cpf(cpf_n):
                st.error("CPF inválido. Digite apenas os 11 números."); st.stop()

            try:
                supabase.table("usuarios").update({
                    "nome": nome_n,
                    "email": email_n,
                    "banco": banco_n,
                    "cpf": cpf_n,
                    "rg": rg_n,
                    "data_nascimento": nasc_n.isoformat(),
                    "endereco": end_n,
                    "cidade": cidade_n,
                    "estado": uf_n,
                    "telefone": tel_n,
                    "renda": renda_n,
                    "profissao": prof_n,
                    "estado_civil": est_civ,
                    "situacao_prof": sit_prof,
                }).eq("id", user_id).execute()

                campos_alterados = []

                if nome_n != dados_atuais['nome']:
                    registrar_fato("editar_perfil", "Alteração de nome", "nome", dados_atuais['nome'], nome_n)
                    campos_alterados.append("nome")

                if email_n != dados_atuais['email']:
                    registrar_fato("editar_perfil", "Alteração de email", "email", dados_atuais['email'], email_n)
                    campos_alterados.append("email")

                if banco_n != dados_atuais['banco']:
                    registrar_fato("editar_perfil", "Alteração de banco", "banco", dados_atuais['banco'], banco_n)
                    campos_alterados.append("banco")

                if cpf_n != dados_atuais['cpf']:
                    registrar_fato("editar_perfil", "Alteração de CPF", "cpf", dados_atuais['cpf'], cpf_n)
                    campos_alterados.append("cpf")

                if rg_n != dados_atuais['rg']:
                    registrar_fato("editar_perfil", "Alteração de RG", "rg", dados_atuais['rg'], rg_n)
                    campos_alterados.append("rg")

                if nasc_n != nasc_val:
                    registrar_fato("editar_perfil", "Alteração de data de nascimento", "data_nascimento",
                                  str(dados_atuais['data_nascimento']), str(nasc_n))
                    campos_alterados.append("data_nascimento")

                if end_n != dados_atuais['endereco']:
                    registrar_fato("editar_perfil", "Alteração de endereço", "endereco", dados_atuais['endereco'], end_n)
                    campos_alterados.append("endereco")

                if cidade_n != dados_atuais['cidade']:
                    registrar_fato("editar_perfil", "Alteração de cidade", "cidade", dados_atuais['cidade'], cidade_n)
                    campos_alterados.append("cidade")

                if uf_n != dados_atuais['estado']:
                    registrar_fato("editar_perfil", "Alteração de estado", "estado", dados_atuais['estado'], uf_n)
                    campos_alterados.append("estado")

                if tel_n != dados_atuais['telefone']:
                    registrar_fato("editar_perfil", "Alteração de telefone", "telefone", dados_atuais['telefone'], tel_n)
                    campos_alterados.append("telefone")

                if float(renda_n) != float(dados_atuais['renda'] or 0):
                    registrar_fato("editar_perfil", "Alteração de renda", "renda", str(dados_atuais['renda']), str(renda_n))
                    campos_alterados.append("renda")

                if prof_n != dados_atuais['profissao']:
                    registrar_fato("editar_perfil", "Alteração de profissão", "profissao", dados_atuais['profissao'], prof_n)
                    campos_alterados.append("profissao")

                if est_civ != dados_atuais['estado_civil']:
                    registrar_fato("editar_perfil", "Alteração de estado civil", "estado_civil",
                                  dados_atuais['estado_civil'], est_civ)
                    campos_alterados.append("estado_civil")

                if sit_prof != dados_atuais['situacao_prof']:
                    registrar_fato("editar_perfil", "Alteração de situação profissional", "situacao_prof",
                                  dados_atuais['situacao_prof'], sit_prof)
                    campos_alterados.append("situacao_prof")

                if campos_alterados:
                    registrar_fato("Update perfil", f"Dados pessoais alterados: {', '.join(campos_alterados)}")
                st.success("Dados atualizados com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao atualizar dados: {str(e)}")
    except Exception as e:
        st.error(f"Erro ao carregar dados do usuário: {str(e)}")

# ---------- ALTERAR SENHA -----------------------------------------
with tab_pwd:
    pwd_old = st.text_input("Senha atual", type="password")
    pwd_new = st.text_input("Nova senha",  type="password")
    pwd_cnf = st.text_input("Confirmar nova senha", type="password")

    if st.button("Alterar senha"):
        try:
            senha_resp = (
                supabase.table("usuarios")
                .select("senha")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )
            senha_atual = (senha_resp.data or [{}])[0].get("senha")
            if pwd_old != senha_atual:
                st.error("Senha atual incorreta.")
            elif pwd_new != pwd_cnf:
                st.warning("As senhas não coincidem.")
            elif len(pwd_new) < 6:
                st.warning("Use ao menos 6 caracteres.")
            else:
                supabase.table("usuarios").update(
                    {"senha": pwd_new}
                ).eq("id", user_id).execute()
                registrar_fato("Alterar senha","Senha atualizada")
                st.success("Senha alterada com sucesso!")
                st.session_state.logged_in = False  # Força novo login
                st.rerun()
        except Exception as e:
            st.error(f"Erro ao alterar senha: {str(e)}")
