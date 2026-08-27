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
    user_id: int
    valor: float
    tipo_transacao: str
    forma_pagamento: Optional[str] = None
    localizacao: Optional[str] = None
    banco_origem: str
    banco_destino: str
    ip: Optional[str] = None


@app.get("/produtos/")
def listar_produtos():
    supabase = get_supabase_client()
    response = supabase.table("produtos").select("*").execute()
    return response.data


@app.post("/transacoes/")
def criar_transacao(transacao: TransacaoCreate):
    supabase = get_supabase_client()

    tx_dict = transacao.model_dump()
    tx_dict["data_hora"] = datetime.now()

    suspeita, motivo = avaliar_transacao(tx_dict)

    payload = {
        "user_id": transacao.user_id,
        "valor": transacao.valor,
        "tipo_transacao": transacao.tipo_transacao,
        "forma_pagamento": transacao.forma_pagamento,
        "localizacao": transacao.localizacao,
        "banco_origem": transacao.banco_origem,
        "banco_destino": transacao.banco_destino,
        "data_hora": datetime.now().isoformat(),
        "suspeita": suspeita,
        "motivo_suspeita": motivo if suspeita else None,
    }

    response = supabase.table("transacoes").insert(payload).execute()
    nova = response.data[0]
    tx_id = nova["id"]

    if suspeita:
        registrar_fraude(tx_id, motivo)

    return {
        "id": tx_id,
        "suspeita": suspeita,
        "motivo_suspeita": motivo if suspeita else None,
    }


def registrar_fato(
    user_id: int,
    acao: str,
    descricao: str,
    entidade: str = None,
    pk: str = None,
    campo: str = None,
    de=None,
    para=None,
):
    supabase = get_supabase_client()
    supabase.table("fatos_usuarios").insert(
        {
            "user_id": user_id,
            "acao": acao,
            "descricao": descricao,
            "entidade": entidade,
            "chave_primaria": pk,
            "campo": campo,
            "valor_antigo": str(de) if de is not None else None,
            "valor_novo": str(para) if para is not None else None,
        }
    ).execute()
