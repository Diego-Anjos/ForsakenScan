import random
import sys
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import streamlit as st

if not hasattr(st, "rerun"):
    st.rerun = st.experimental_rerun

_FRONTEND = Path(__file__).resolve().parent.parent
if str(_FRONTEND) not in sys.path:
    sys.path.insert(0, str(_FRONTEND))
import bootstrap  # noqa: F401 — raiz no sys.path

from backend.db import get_supabase_client
from backend.fraude import avaliar_transacao
from rbac import aplicar_regras_sidebar, require_admin

st.set_page_config(page_title="Gerar Dados", layout="wide")
aplicar_regras_sidebar()
require_admin()

TIPOS_PAGAMENTO = ["PIX", "Cartão de Crédito", "Boleto", "TED"]
LOCALIZACOES = [
    "São Paulo, SP",
    "Rio de Janeiro, RJ",
    "Belo Horizonte, MG",
    "Curitiba, PR",
    "Salvador, BA",
]
CHUNK_SIZE = 500


def _montar_registro(usuario_id: str) -> dict:
    agora = datetime.now()
    valor = round(random.uniform(10.0, 5000.0), 2)
    tipo_pagamento = random.choice(TIPOS_PAGAMENTO)
    tx = {
        "usuario_id": usuario_id,
        "valor": valor,
        "data_transacao": agora,
        "tipo_pagamento": tipo_pagamento,
    }
    is_fraude, score_fraude, motivo_suspeita = avaliar_transacao(tx)
    return {
        "usuario_id": usuario_id,
        "valor": valor,
        "tipo_pagamento": tipo_pagamento,
        "data_transacao": agora.isoformat(),
        "banco_origem": "Conta Corrente",
        "banco_destino": random.choice(LOCALIZACOES),
        "forma_pagamento": tipo_pagamento,
        "codigo": uuid4().hex[:10],
        "is_fraude": is_fraude,
        "score_fraude": score_fraude,
        "motivo_suspeita": motivo_suspeita or None,
    }

st.title("Gerar Dados Simulados")
st.caption("Injeta transações fictícias para usuários já cadastrados no Supabase.")

supabase = get_supabase_client()

try:
    resp = supabase.table("usuarios").select("id").execute()
    user_ids = [row["id"] for row in (resp.data or [])]
except Exception:
    user_ids = []

if not user_ids:
    st.warning(
        "Você precisa criar pelo menos um usuário cliente "
        "(na tela de Cadastro) antes de gerar transações."
    )
    st.stop()

st.info(f"{len(user_ids):,} usuário(s) disponível(is) para receber transações simuladas.")

qtd = st.slider(
    "Quantidade de transações a gerar",
    min_value=100,
    max_value=10_000,
    value=1_000,
    step=100,
)

if st.button("🚀 Gerar Transações Simuladas", type="primary", use_container_width=True):
    registros: list[dict] = []
    gen_progress = st.progress(0.0, text="Avaliando transações com o motor de fraude…")

    for i in range(qtd):
        registros.append(_montar_registro(random.choice(user_ids)))
        if (i + 1) % 50 == 0 or i + 1 == qtd:
            gen_progress.progress((i + 1) / qtd, text=f"Avaliando {i + 1:,}/{qtd:,}…")

    gen_progress.empty()

    lotes = [
        registros[i : i + CHUNK_SIZE]
        for i in range(0, len(registros), CHUNK_SIZE)
    ]
    total_lotes = len(lotes)
    progresso = st.progress(0.0, text="Preparando inserção…")

    try:
        for idx, lote in enumerate(lotes, start=1):
            get_supabase_client().table("transacoes").insert(lote).execute()
            progresso.progress(
                idx / total_lotes,
                text=f"Lote {idx}/{total_lotes} enviado ({len(lote)} registros)…",
            )
            time.sleep(0.05)
    except Exception as exc:
        st.error(f"Erro ao inserir transações: {exc}")
        st.stop()

    progresso.progress(1.0, text="Concluído!")
    st.success(
        f"✅ {qtd:,} transações simuladas foram injetadas com sucesso! "
        "Acesse a página **Dashboard** para visualizar gráficos e métricas."
    )
