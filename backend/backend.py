from datetime import datetime
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .db import get_supabase_client
from .fraude import avaliar_transacao, registrar_fraude

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TransacaoCreate(BaseModel):
    usuario_id: str
    valor: float
    tipo_pagamento: str
    forma_pagamento: Optional[str] = None
    banco_origem: str
    banco_destino: str
    codigo: str
    ip: Optional[str] = None


@app.get("/produtos/")
def listar_produtos():
    supabase = get_supabase_client()
    response = supabase.table("produtos").select("*").execute()
    return response.data


@app.post("/transacoes/")
def criar_transacao(transacao: TransacaoCreate):
    supabase = get_supabase_client()
    agora = datetime.now()

    tx_dict = {
        "usuario_id": transacao.usuario_id,
        "valor": transacao.valor,
        "data_transacao": agora,
        "tipo_pagamento": transacao.tipo_pagamento,
        "ip": transacao.ip,
    }

    is_fraude, score_fraude, motivo_suspeita = avaliar_transacao(tx_dict)

    payload = {
        "usuario_id": transacao.usuario_id,
        "valor": transacao.valor,
        "tipo_pagamento": transacao.tipo_pagamento,
        "forma_pagamento": transacao.forma_pagamento,
        "banco_origem": transacao.banco_origem,
        "banco_destino": transacao.banco_destino,
        "codigo": transacao.codigo,
        "data_transacao": agora.isoformat(),
        "is_fraude": is_fraude,
        "score_fraude": score_fraude,
        "motivo_suspeita": motivo_suspeita or None,
    }

    response = supabase.table("transacoes").insert(payload).execute()
    nova = response.data[0]
    tx_id = nova["id"]

    if is_fraude:
        registrar_fraude(tx_id, motivo_suspeita)

    return {
        "id": tx_id,
        "is_fraude": is_fraude,
        "score_fraude": score_fraude,
        "motivo_suspeita": motivo_suspeita or None,
    }
