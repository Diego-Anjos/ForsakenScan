import os
from typing import Any

import certifi
import pandas as pd
from dotenv import load_dotenv
from supabase import Client, create_client

# Certificados SSL antes de qualquer módulo de rede (Windows / httpx)
_cert = certifi.where()
os.environ["SSL_CERT_FILE"] = _cert
os.environ["REQUESTS_CA_BUNDLE"] = _cert
os.environ["CURL_CA_BUNDLE"] = _cert

load_dotenv()

_client: Client | None = None
_admin_client: Client | None = None


def get_supabase_client(*, admin: bool = False) -> Client:
    """Retorna o cliente Supabase (singleton).

    Usa SUPABASE_ANON_KEY por padrão. Passe admin=True para SUPABASE_SERVICE_ROLE_KEY.
    """
    global _client, _admin_client

    url = os.getenv("SUPABASE_URL")
    if not url:
        raise RuntimeError("Defina SUPABASE_URL no .env")

    if admin:
        if _admin_client is None:
            key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            if not key:
                raise RuntimeError(
                    "Defina SUPABASE_SERVICE_ROLE_KEY no .env para operações admin"
                )
            _admin_client = create_client(url, key)
        return _admin_client

    if _client is None:
        key = os.getenv("SUPABASE_ANON_KEY")
        if not key:
            raise RuntimeError("Defina SUPABASE_ANON_KEY no .env")
        _client = create_client(url, key)
    return _client


def fetch_df(
    table: str, columns: str = "*", filters: dict[str, Any] | None = None
) -> pd.DataFrame:
    """SELECT simples → DataFrame."""
    q = get_supabase_client().table(table).select(columns)
    if filters:
        for col, val in filters.items():
            q = q.eq(col, val)
    return pd.DataFrame(q.execute().data or [])


def fetch_all_df(table: str, columns: str = "*", page_size: int = 1000) -> pd.DataFrame:
    """Pagina o SELECT para contornar o limite padrão do PostgREST."""
    sb = get_supabase_client()
    rows: list[dict] = []
    start = 0
    while True:
        chunk = (
            sb.table(table)
            .select(columns)
            .range(start, start + page_size - 1)
            .execute()
            .data
            or []
        )
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
        start += page_size
    return pd.DataFrame(rows)
