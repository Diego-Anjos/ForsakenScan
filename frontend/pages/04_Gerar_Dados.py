"""
04_Gerar_Dados.py
-----------------
Popula a base via Supabase com dados sintéticos:
• 3 000 usuários + limites
• 11 000 transações (≈10 % suspeitas) + compras
• ofertas de empréstimo
• tentativas de exceder limite
"""
import random
import re
from uuid import uuid4
from decimal import Decimal

import streamlit as st
if not hasattr(st, "rerun"):
    st.rerun = st.experimental_rerun  # alias p/ versões antigas


from faker import Faker

import sys
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parent.parent
if str(_FRONTEND) not in sys.path:
    sys.path.insert(0, str(_FRONTEND))
import bootstrap  # noqa: F401 — raiz no sys.path
from backend.db import get_supabase_client

fake = Faker("pt_BR")
supabase = get_supabase_client()

CHUNK_SIZE = 400

# ─────────────────────────  LISTAS FIXAS  ─────────────────────────
BANCOS      = ["Itaú", "Bradesco", "Nubank", "Inter", "Santander",
               "Banco do Brasil", "Caixa", "C6 Bank", "BTG Pactual"]
FORMAS_PG   = ["Pix", "Transferência", "Cartão", "Boleto"]
LOJAS       = ["Amazon", "Mercado Livre", "Magalu", "Shein",
               "Kabum", "Netshoes", "Steam"]
CATEGORIAS  = ["Eletrônicos", "Vestuário", "Casa", "Alimentos",
               "Beleza", "Games"]
EST_CIVIL   = ["Solteiro(a)", "Casado(a)", "Divorciado(a)",
               "Viúvo(a)", "União estável"]
SIT_PROF    = ["Empregado", "Desempregado", "Autônomo",
               "Estudante", "Aposentado"]

# ─────────────────────────  HELPERS  ─────────────────────────
def _username_unico(vistos: set[str]) -> str:
    while True:
        cand = fake.user_name() + str(random.randint(10, 99))
        if cand not in vistos:
            vistos.add(cand)
            return cand

def _to_float(v):
    return float(v) if isinstance(v, Decimal) else float(v or 0)

def _only_digits(x: str) -> str:
    return re.sub(r"\D", "", x or "")

def _chunked_insert(table: str, rows: list[dict], chunk_size: int = CHUNK_SIZE) -> list[dict]:
    """Insere em lotes e devolve todas as linhas retornadas."""
    inserted: list[dict] = []
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        resp = supabase.table(table).insert(chunk).execute()
        inserted.extend(resp.data or [])
    return inserted

def _fetch_all(table: str, columns: str, page_size: int = 1000) -> list[dict]:
    """Pagina selects para contornar o limite padrão do PostgREST."""
    rows: list[dict] = []
    start = 0
    while True:
        resp = (
            supabase.table(table)
            .select(columns)
            .range(start, start + page_size - 1)
            .execute()
        )
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return rows

# ─────────────────────────  1) USUÁRIOS + LIMITES  ─────────────────────────
def gerar_usuarios(qtd: int = 3_000) -> None:
    st.info(f"🔄 Inserindo {qtd:,} usuários…")

    data_usr: list[dict] = []
    users_vistos: set[str] = set()

    while len(data_usr) < qtd:
        try:
            cpf = _only_digits(fake.unique.cpf())
        except Exception:
            fake.unique.clear()
            continue

        renda = round(random.uniform(1_200, 20_000), 2)
        nasc = fake.date_of_birth(minimum_age=18, maximum_age=75)
        data_usr.append({
            "nome": fake.name(),
            "email": fake.free_email(),
            "banco": random.choice(BANCOS),
            "cidade": fake.city(),
            "estado": fake.estado_sigla(),
            "username": _username_unico(users_vistos),
            "senha": fake.password(length=10),
            "tipo": "normal",
            "cpf": cpf,
            "rg": str(random.randint(1_000_000, 9_999_999)),
            "data_nascimento": nasc.isoformat(),
            "endereco": fake.address()[:240],
            "telefone": fake.phone_number(),
            "renda": renda,
            "profissao": fake.job()[:90],
            "estado_civil": random.choice(EST_CIVIL),
            "situacao_prof": random.choice(SIT_PROF),
        })

    try:
        inseridos = _chunked_insert("usuarios", data_usr)
    except Exception as e:
        st.error(f"Erro ao inserir usuários: {e}")
        return

    if not inseridos:
        # Fallback: busca os mais recentes se o insert não retornou linhas
        inseridos = (
            supabase.table("usuarios")
            .select("id, renda")
            .order("id", desc=True)
            .limit(qtd)
            .execute()
        ).data or []

    data_lim = []
    for u in inseridos:
        renda = _to_float(u.get("renda"))
        lim_dia = round(renda * random.uniform(1.5, 4.0), 2)
        lim_noite = round(lim_dia / 2, 2)
        data_lim.append({
            "user_id": u["id"],
            "limite_pagamento": round(renda * 3, 2),
            "limite_dia": lim_dia,
            "limite_noite": lim_noite,
        })

    if data_lim:
        try:
            _chunked_insert("limites_usuario", data_lim)
        except Exception as e:
            st.error(f"Erro ao inserir limites: {e}")
            return

    st.success("✅ Usuários e limites gerados com sucesso!")

# ─────────────────────────  2) TRANSAÇÕES + COMPRAS  ─────────────────────────
def gerar_transacoes(qtd: int = 11_000) -> None:
    st.info(f"🔄 Inserindo {qtd:,} transações…")

    user_rows = _fetch_all("usuarios", "id")
    user_ids = [x["id"] for x in user_rows]
    if not user_ids:
        st.error("Não há usuários na base."); return

    tipos = ["Compra", "Pagamento", "Transferência", "PIX",
             "Recebimento", "Cash-In", "Saque"]

    tx_data, shop_data = [], []
    suspeitos = 0
    for _ in range(qtd):
        uid   = random.choice(user_ids)
        tipo  = random.choice(tipos)
        valor = round(random.uniform(1, 20_000), 2)
        forma = random.choice(FORMAS_PG) if tipo in ("Compra", "Pagamento",
                                                     "Transferência", "PIX", "Saque") else "Interno"
        codigo    = uuid4().hex[:10]
        data_h    = fake.date_time_between(start_date="-90d", end_date="now")
        suspeita  = 1 if random.random() < 0.10 else 0
        motivo    = "valor atípico" if suspeita else None
        if suspeita:
            suspeitos += 1

        tx_data.append({
            "user_id": uid,
            "valor": valor,
            "tipo_transacao": tipo,
            "forma_pagamento": forma,
            "codigo": codigo,
            "data_hora": data_h.isoformat(),
            "localizacao": fake.city(),
            "banco_origem": fake.swift(length=11) if random.random() < 0.5 else None,
            "banco_destino": fake.swift(length=11) if random.random() < 0.5 else None,
            "suspeita": suspeita,
            "motivo_suspeita": motivo,
        })

        if tipo == "Compra":
            qtd_prod = random.randint(1, 5)
            v_unit   = round(valor / qtd_prod, 2)
            shop_data.append({
                "user_id": uid,
                "codigo_tx": codigo,
                "loja": random.choice(LOJAS),
                "categoria": random.choice(CATEGORIAS),
                "produto": fake.word().title(),
                "qtd": qtd_prod,
                "valor_unit": v_unit,
                "valor_total": valor,
            })

    try:
        _chunked_insert("transacoes", tx_data)
        if shop_data:
            _chunked_insert("compras_online", shop_data)
    except Exception as e:
        st.error(f"Erro ao inserir transações: {e}")
        return

    st.success(f"✅ Transações inseridas (🚩 {suspeitos:,} suspeitas).")

# ─────────────────────────  3) EMPRÉSTIMOS  ─────────────────────────
def gerar_emprestimos(taxa_oferta: float = 0.25) -> None:
    st.info("🔄 Gerando ofertas de empréstimo…")

    dados = _fetch_all("usuarios", "id, renda")

    emp_data = []
    for u in dados:
        if random.random() > taxa_oferta:
            continue
        renda = _to_float(u.get("renda"))
        valor  = round(random.uniform(renda * 0.5, renda * 5), 2)
        status = random.choices(("oferta", "aceito", "recusado"),
                                weights=(50, 30, 20))[0]
        emp_data.append({
            "user_id": u["id"],
            "valor": valor,
            "taxa_juros": random.choice((1.8, 2.2, 2.5, 3.0)),
            "prazo_meses": random.choice((12, 24, 36, 48)),
            "status": status,
        })
    if emp_data:
        try:
            _chunked_insert("emprestimos", emp_data)
        except Exception as e:
            st.error(f"Erro ao inserir empréstimos: {e}")
            return
    st.success(f"✅ Empréstimos gerados: {len(emp_data):,}")

# ─────────────────────────  4) TENTATIVAS DE LIMITE  ─────────────────────────
def gerar_tentativas_limite() -> None:
    st.info("🔄 Registrando tentativas de exceder limite…")

    dados = _fetch_all("limites_usuario", "user_id, limite_dia")

    linhas = []
    for u in dados:
        lim = _to_float(u.get("limite_dia"))
        if random.random() < 0.20:
            for _ in range(random.randint(1, 3)):
                linhas.append({
                    "user_id": u["user_id"],
                    "valor_tentativa": round(lim * random.uniform(1.1, 2.0), 2),
                    "limite": lim,
                    "turno": random.choice(("dia", "noite")),
                })
    if linhas:
        try:
            _chunked_insert("tentativas_limite", linhas)
        except Exception as e:
            st.error(f"Erro ao inserir tentativas: {e}")
            return
    st.success(f"✅ Tentativas registradas: {len(linhas):,}")

# ─────────────────────────  INTERFACE  ─────────────────────────
def main() -> None:
    st.title("🚀 Gerador de Dados – Ambiente de Teste")

    if st.button("Popular Banco (⚠️ 3 000 usuários & 11 000 transações)",
                 type="primary"):
        gerar_usuarios()
        gerar_transacoes()
        gerar_emprestimos()
        gerar_tentativas_limite()
        st.balloons()
        st.success("🎉 Base de testes criada com sucesso!")

if __name__ == "__main__":
    main()
