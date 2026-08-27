"""
db.py – cliente Supabase reutilizável
------------------------------------
Carrega SUPABASE_URL e a chave publishable/anon (preferencial) ou
service role do .env e expõe get_supabase_client().
"""
import os
from typing import Any

import certifi
import pandas as pd
from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

_client: Client | None = None


def get_supabase_client() -> Client:
    """Retorna o cliente Supabase ativo (singleton).

    Preferência de chave (Auth nativo + REST):
    1) SUPABASE_ANON_KEY / SUPABASE_KEY (publishable) — ideal para sign_up / sign_in
    2) SUPABASE_SERVICE_ROLE_KEY — fallback administrativo
    """
    global _client
    if _client is None:
        # Certificados CA atualizados (evita SSL: certificate verify failed)
        os.environ["SSL_CERT_FILE"] = certifi.where()

        url = os.getenv("SUPABASE_URL")
        key = (
            os.getenv("SUPABASE_ANON_KEY")
            or os.getenv("SUPABASE_KEY")
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        )
        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL e SUPABASE_ANON_KEY (ou SUPABASE_KEY / "
                "SUPABASE_SERVICE_ROLE_KEY) devem estar definidos no .env"
            )
        _client = create_client(url, key)
    return _client


def fetch_df(table: str, columns: str = "*", filters: dict[str, Any] | None = None) -> pd.DataFrame:
    """SELECT simples → DataFrame (lista de dicts em .data)."""
    q = get_supabase_client().table(table).select(columns)
    if filters:
        for col, val in filters.items():
            q = q.eq(col, val)
    rows = q.execute().data or []
    return pd.DataFrame(rows)


def fetch_all_df(table: str, columns: str = "*", page_size: int = 1000) -> pd.DataFrame:
    """Pagina o SELECT para contornar o limite padrão do PostgREST."""
    sb = get_supabase_client()
    rows: list[dict] = []
    start = 0
    while True:
        end = start + page_size - 1
        chunk = (
            sb.table(table)
            .select(columns)
            .range(start, end)
            .execute()
            .data
            or []
        )
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
        start += page_size
    return pd.DataFrame(rows)
