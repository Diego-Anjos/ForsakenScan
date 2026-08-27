"""
fraude.py – motor de regras de detecção de fraude (Supabase)
===========================================================

Cada regra devolve (flag: bool, motivo: str). A função pública
`avaliar_transacao(tx_dict)` percorre todas e retorna (suspeita, motivos).
"""
from datetime import datetime, time, timedelta

from .db import get_supabase_client

H_INI_DIA, H_FIM_DIA = time(6, 0), time(22, 59, 59)
H_INI_NOITE, H_FIM_NOITE = time(23, 0), time(5, 59, 59)

TIPOS_GASTO = ("Compra", "Pagamento", "Transferência", "Saque", "PIX")


def _sb():
    return get_supabase_client()


def _parse_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _obter_limites_usuario(user_id: int) -> tuple:
    resp = (
        _sb()
        .table("limites_usuario")
        .select("limite_dia, limite_noite")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    if not rows:
        return (10_000, 5_000)
    return (rows[0]["limite_dia"], rows[0]["limite_noite"])


def _turno(dt: datetime) -> str:
    return "dia" if H_INI_DIA <= dt.time() <= H_FIM_DIA else "noite"


def _total_turno(user_id: int, turno: str) -> float:
    hoje = datetime.now().date()
    ontem = hoje - timedelta(days=1)

    resp = (
        _sb()
        .table("transacoes")
        .select("valor, data_hora, tipo_transacao")
        .eq("user_id", user_id)
        .in_("tipo_transacao", list(TIPOS_GASTO))
        .gte("data_hora", ontem.isoformat())
        .execute()
    )
    total = 0.0
    for row in resp.data or []:
        if row.get("tipo_transacao") not in TIPOS_GASTO:
            continue
        dt = _parse_dt(row.get("data_hora"))
        if not dt:
            continue
        t = dt.time()
        if turno == "dia":
            if dt.date() == hoje and H_INI_DIA <= t <= H_FIM_DIA:
                total += float(row["valor"])
        else:
            if (dt.date() == hoje and t >= H_INI_NOITE) or (
                dt.date() == ontem and t <= H_FIM_NOITE
            ):
                total += float(row["valor"])
    return total


def _registrar_tentativa_limite(user_id: int, valor: float, limite: float, turno: str):
    _sb().table("tentativas_limite").insert(
        {
            "user_id": user_id,
            "valor_tentativa": valor,
            "limite": limite,
            "turno": turno,
            "data_hora": datetime.now().isoformat(),
        }
    ).execute()


def regra_01_limites_turno(tx: dict):
    try:
        limite_dia, limite_noite = _obter_limites_usuario(tx["user_id"])
        turno_tx = _turno(tx["data_hora"])
        limite = limite_dia if turno_tx == "dia" else limite_noite
        soma = _total_turno(tx["user_id"], turno_tx) + float(tx["valor"])
        if soma > limite:
            _registrar_tentativa_limite(tx["user_id"], soma, limite, turno_tx)
            return True, f"Limite {turno_tx} excedido (R$ {soma:,.2f} > {limite:,.2f})"
        return False, ""
    except Exception as e:
        print(f"Erro na regra de limites: {str(e)}")
        return False, ""


def regra_02_5_transacoes_5min(tx: dict):
    limite = (datetime.now() - timedelta(minutes=5)).isoformat()
    tipos = ["Compra", "Pagamento", "Transferência"]

    resp = (
        _sb()
        .table("transacoes")
        .select("id")
        .eq("user_id", tx["user_id"])
        .in_("tipo_transacao", tipos)
        .gte("data_hora", limite)
        .execute()
    )
    mesmo_usuario = len(resp.data or []) >= 4

    varios_usuarios = False
    ip = tx.get("ip")
    if ip:
        logs = (
            _sb()
            .table("logs")
            .select("user_id")
            .eq("ip", ip)
            .gte("data_hora", limite)
            .execute()
        )
        user_ids = {r["user_id"] for r in (logs.data or []) if r.get("user_id")}
        if user_ids:
            txs = (
                _sb()
                .table("transacoes")
                .select("user_id")
                .in_("user_id", list(user_ids))
                .in_("tipo_transacao", tipos)
                .gte("data_hora", limite)
                .execute()
            )
            varios_usuarios = len({r["user_id"] for r in (txs.data or [])}) >= 5

    if mesmo_usuario:
        return True, "5+ transações do mesmo usuário em 5 minutos"
    if varios_usuarios:
        return True, "5+ transações de diferentes usuários (mesmo IP) em 5 minutos"
    return False, ""


def regra_03_tentativas_login(tx: dict):
    limite = (datetime.now() - timedelta(minutes=30)).isoformat()
    resp = (
        _sb()
        .table("logs")
        .select("id")
        .eq("user_id", tx["user_id"])
        .eq("resultado", "fail")
        .gte("data_hora", limite)
        .execute()
    )
    if len(resp.data or []) >= 3:
        return True, "3+ tentativas de login falhas em 30 minutos"
    return False, ""


def regra_04_alteracao_senha(tx: dict):
    limite = (datetime.now() - timedelta(days=7)).isoformat()
    resp = (
        _sb()
        .table("fatos_usuarios")
        .select("id")
        .eq("user_id", tx["user_id"])
        .eq("acao", "Alterar senha")
        .gte("data_hora", limite)
        .execute()
    )
    alteracoes = len(resp.data or [])
    if alteracoes >= 3:
        return True, f"{alteracoes} alterações de senha em 7 dias"
    return False, ""


def regra_05_troca_dados_saque(tx: dict):
    limite = (datetime.now() - timedelta(hours=1)).isoformat()
    resp = (
        _sb()
        .table("fatos_usuarios")
        .select("id")
        .eq("user_id", tx["user_id"])
        .eq("acao", "editar_perfil")
        .in_("campo", ["email", "telefone"])
        .gte("data_hora", limite)
        .execute()
    )
    if (resp.data or []) and tx["tipo_transacao"] in ("Saque", "Transferência"):
        return True, "Alteração de dados sensíveis seguida de saque"
    return False, ""


def regra_06_cashin_sem_historico(tx: dict):
    if tx["tipo_transacao"] != "Cash-In":
        return False, ""
    dh = tx["data_hora"]
    if isinstance(dh, datetime):
        fim = dh
    else:
        fim = _parse_dt(dh) or datetime.now()
    inicio = fim - timedelta(days=7)
    resp = (
        _sb()
        .table("transacoes")
        .select("id")
        .eq("user_id", tx["user_id"])
        .lt("data_hora", fim.isoformat())
        .gte("data_hora", inicio.isoformat())
        .execute()
    )
    if len(resp.data or []) == 0 and float(tx["valor"]) > 5000:
        return True, "Cash-In alto em conta sem histórico"
    return False, ""


def regra_07_deposito_saque_rapido(tx: dict):
    if tx["tipo_transacao"] not in ("Saque", "Transferência"):
        return False, ""
    dh = tx["data_hora"] if isinstance(tx["data_hora"], datetime) else _parse_dt(tx["data_hora"])
    if not dh:
        dh = datetime.now()
    inicio = dh - timedelta(hours=1)
    resp = (
        _sb()
        .table("transacoes")
        .select("valor, data_hora")
        .eq("user_id", tx["user_id"])
        .eq("tipo_transacao", "Cash-In")
        .gte("data_hora", inicio.isoformat())
        .order("data_hora", desc=True)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    if not rows:
        return False, ""
    deposito = rows[0]
    dep_dt = _parse_dt(deposito.get("data_hora"))
    if not dep_dt:
        return False, ""
    minutos = int((dh - dep_dt).total_seconds() // 60)
    if minutos < 10 and float(tx["valor"]) >= float(deposito["valor"]) * 0.9:
        return True, f"Saque de {tx['valor']} após depósito há {minutos} minutos"
    return False, ""


REGRAS_ATIVAS = [
    regra_01_limites_turno,
    regra_02_5_transacoes_5min,
    regra_03_tentativas_login,
    regra_04_alteracao_senha,
    regra_05_troca_dados_saque,
    regra_06_cashin_sem_historico,
    regra_07_deposito_saque_rapido,
]


def avaliar_transacao(tx: dict):
    """
    Executa todas as REGRAS_ATIVAS.
    tx precisa conter: user_id, valor, data_hora, tipo_transacao.
    Retorna: (suspeita: bool, motivos: str)
    """
    resultados = []
    for regra in REGRAS_ATIVAS:
        try:
            flag, motivo = regra(tx)
            if flag:
                resultados.append((regra.__name__, motivo))
        except Exception as e:
            print(f"Erro na regra {regra.__name__}: {str(e)}")

    if resultados:
        resultados.sort(
            key=lambda x: 0
            if "limites_turno" in x[0]
            else 1
            if "5_transacoes" in x[0]
            else 2
        )
        motivos = "; ".join(m for _, m in resultados)
        return True, motivos
    return False, ""


def registrar_fraude(tx_id: int, motivos: str):
    """Registra ou atualiza uma fraude detectada."""
    sb = _sb()
    existente = (
        sb.table("fraudes_detectadas")
        .select("id")
        .eq("transacao_id", tx_id)
        .limit(1)
        .execute()
    )
    payload = {
        "transacao_id": tx_id,
        "motivos": motivos,
        "data_deteccao": datetime.now().isoformat(),
    }
    if existente.data:
        sb.table("fraudes_detectadas").update(payload).eq("transacao_id", tx_id).execute()
    else:
        sb.table("fraudes_detectadas").insert(payload).execute()
