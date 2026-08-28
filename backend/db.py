import os

import certifi

# Certificados SSL antes de qualquer módulo de rede (Windows / httpx)
_cert = certifi.where()
os.environ["SSL_CERT_FILE"] = _cert
os.environ["REQUESTS_CA_BUNDLE"] = _cert
os.environ["CURL_CA_BUNDLE"] = _cert

import ssl
from typing import Any

ssl._create_default_https_context = ssl._create_unverified_context

import httpx
import warnings

# Suprime os avisos de segurança sobre SSL desativado no terminal
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

# Monkey-patch para forçar o httpx (usado pelo Supabase) a ignorar a verificação de SSL local
original_init = httpx.Client.__init__
original_async_init = httpx.AsyncClient.__init__

def patched_init(self, *args, **kwargs):
    kwargs['verify'] = False
    original_init(self, *args, **kwargs)
    
def patched_async_init(self, *args, **kwargs):
    kwargs['verify'] = False
    original_async_init(self, *args, **kwargs)

httpx.Client.__init__ = patched_init
httpx.AsyncClient.__init__ = patched_async_init

import pandas as pd
from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

_client: Client | None = None


def get_supabase_client() -> Client:
    """Retorna o cliente Supabase (singleton)."""
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL")
        key = (
            os.getenv("SUPABASE_ANON_KEY")
            or os.getenv("SUPABASE_KEY")
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        )
        if not url or not key:
            raise RuntimeError(
                "Defina SUPABASE_URL e SUPABASE_ANON_KEY (ou SUPABASE_KEY) no .env"
            )
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
