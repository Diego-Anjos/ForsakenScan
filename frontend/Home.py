# ========================================
# home.py – Login, Cadastro e Recuperação
# ========================================
import os
import re
from datetime import date
from pathlib import Path

import streamlit as st

import bootstrap  # noqa: F401 — raiz no sys.path
from backend.db import get_supabase_client

# ────────────────────────────────────────
# Configuração da página
# ────────────────────────────────────────
st.set_page_config(page_title="Autenticação", layout="wide")

# ────────────────────────────────────────
# Cliente Supabase
# ────────────────────────────────────────
supabase = get_supabase_client()

# ────────────────────────────────────────
# Estado padrão da sessão
# ────────────────────────────────────────
_DEFAULTS = dict(
    logged_in=False,
    user_id=None,
    usuario_id=None,
    username=None,
    name=None,
    nome=None,
    email=None,
    is_admin=False,
    role=None,
    auth_uid=None,
)
for k, v in _DEFAULTS.items():
    st.session_state.setdefault(k, v)

# ────────────────────────────────────────
# CSS – escala dos elementos + sidebar
# ────────────────────────────────────────
_hide_sidebar = ""
if not st.session_state.logged_in:
    _hide_sidebar = """
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="collapsedControl"] { display: none !important; }
        section[data-testid="stSidebar"] { display: none !important; }
    """

st.markdown(
    f"""
    <style>
        {_hide_sidebar}

        /* Container principal com mais respiro no desktop */
        .main .block-container {{
            padding-top: 2rem;
            padding-bottom: 2rem;
            max-width: 1100px;
        }}

        /* Abas */
        button[data-baseweb="tab"] {{
            font-size: 1.2rem !important;
            padding: 0.85rem 1.4rem !important;
        }}
        [data-baseweb="tab-list"] {{
            gap: 0.5rem;
        }}

        /* Labels */
        .stTextInput label,
        .stNumberInput label,
        .stSelectbox label,
        .stDateInput label {{
            font-size: 1.05rem !important;
        }}

        /* Campos de input */
        .stTextInput input,
        .stNumberInput input,
        .stSelectbox [data-baseweb="select"] > div,
        .stDateInput input {{
            font-size: 1.1rem !important;
            padding: 0.75rem 0.9rem !important;
            min-height: 2.75rem !important;
        }}

        /* Botões de submit / ações */
        .stButton > button,
        .stFormSubmitButton > button {{
            width: 100% !important;
            height: 3rem !important;
            font-size: 1.2rem !important;
            font-weight: 700 !important;
        }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ────────────────────────────────────────
# Utilidades / máscaras
# ────────────────────────────────────────
only_digits = lambda x: re.sub(r"\D", "", x or "")


def parse_money_br(valor: str | float | int | None) -> float:
    """Converte 'R$ 1.234,56' (ou número) em float."""
    if valor is None:
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    s = str(valor).strip()
    s = re.sub(r"[R$\s]", "", s, flags=re.IGNORECASE)
    if not s:
        return 0.0
    # 1.234,56 → 1234.56 | 1234.56 → 1234.56
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        digits = only_digits(s)
        return float(digits) / 100.0 if digits else 0.0


def parse_date_br(valor: str | date | None) -> date | None:
    """Converte DD/MM/YYYY (ou date) em date."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, date):
        return valor
    s = str(valor).strip()
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", s)
    if not m:
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
        if m:
            y, mo, d = map(int, m.groups())
            return date(y, mo, d)
        return None
    d, mo, y = map(int, m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def registrar_login(
    uid: int | str | None, username: str | None, is_admin: bool, ok: bool
) -> None:
    """Registra cada tentativa de login na tabela logs."""
    ip, ua = None, None
    try:
        ip = os.environ.get("REMOTE_ADDR")
        ua = st.request.headers.get("user-agent")  # type: ignore[attr-defined]
    except Exception:
        pass

    try:
        supabase.table("logs").insert(
            {
                "user_id": uid if isinstance(uid, int) else None,
                "usuario": None if is_admin else username,
                "admin_user": username if is_admin else None,
                "resultado": "ok" if ok else "fail",
                "ip": ip,
                "user_agent": ua,
            }
        ).execute()
    except Exception:
        pass


def _carregar_perfil_por_email(email: str) -> dict | None:
    """Busca o perfil complementar na tabela usuarios."""
    resp = (
        supabase.table("usuarios")
        .select("*")
        .eq("email", email)
        .limit(1)
        .execute()
    )
    return (resp.data or [None])[0]


def _eh_admin(perfil: dict | None) -> bool:
    """Verifica privilégio de admin em is_admin / perfil."""
    if not perfil:
        return False
    if perfil.get("is_admin") is True:
        return True
    perfil_txt = str(perfil.get("perfil") or "").strip().lower()
    return perfil_txt in ("admin", "administrador", "administrator")


def _aplicar_sessao(perfil: dict, *, role: str, auth_uid: str | None = None) -> None:
    """Preenche session_state a partir do perfil + role."""
    uid = perfil.get("id")
    nome = perfil.get("nome")
    email = perfil.get("email")
    st.session_state.update(
        logged_in=True,
        user_id=uid,
        usuario_id=uid,
        username=perfil.get("username") or email,
        name=nome,
        nome=nome,
        email=email,
        is_admin=(role == "admin"),
        role=role,
        auth_uid=auth_uid,
    )


def _fazer_logout() -> None:
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    st.session_state.update(**_DEFAULTS)


# ────────────────────────────────────────
# JS – máscaras (IMask no documento pai)
# Streamlit renderiza widgets no parent; o iframe
# precisa acessar window.parent.document.
# ────────────────────────────────────────
st.iframe(
    """
    <script src="https://unpkg.com/imask@7.6.1/dist/imask.min.js"></script>
    <script>
    (function () {
      const doc = window.parent.document;

      function maskByPlaceholder(placeholder, opts) {
        doc.querySelectorAll('input').forEach(function (el) {
          if ((el.getAttribute('placeholder') || '') !== placeholder) return;
          if (el.dataset.imaskBound === '1') return;
          try {
            IMask(el, opts);
            el.dataset.imaskBound = '1';
          } catch (e) { /* ignore */ }
        });
      }

      function applyMasks() {
        if (typeof IMask === 'undefined') return;

        maskByPlaceholder('000.000.000-00', { mask: '000.000.000-00' });
        maskByPlaceholder('00.000.000-0', { mask: '00.000.000-0' });
        maskByPlaceholder('(00) 00000-0000', {
          mask: [
            { mask: '(00) 0000-0000' },
            { mask: '(00) 00000-0000' }
          ]
        });
        maskByPlaceholder('DD/MM/AAAA', {
          mask: '00/00/0000',
          lazy: false,
          overwrite: true
        });
        maskByPlaceholder('R$ 0,00', {
          mask: 'R$ num',
          blocks: {
            num: {
              mask: Number,
              scale: 2,
              thousandsSeparator: '.',
              padFractionalZeros: true,
              normalizeZeros: true,
              radix: ',',
              mapToRadix: ['.'],
              min: 0
            }
          }
        });
      }

      applyMasks();
      const obs = new MutationObserver(function () { applyMasks(); });
      obs.observe(doc.body, { childList: true, subtree: true });
      // reaplicação periódica leve (abas Streamlit remountam inputs)
      setInterval(applyMasks, 800);
    })();
    </script>
    """,
    height=0,
)

# ────────────────────────────────────────
# Menu lateral (apenas quando logado)
# ────────────────────────────────────────
if st.session_state.logged_in:
    if st.sidebar.button("Deslogar da conta"):
        _fazer_logout()
        st.success("Você foi deslogado com sucesso!")
        st.rerun()

# ────────────────────────────────────────
# Layout centralizado
# ────────────────────────────────────────
col1, col2, col3 = st.columns([1, 4, 1])

with col2:
    # Logo / título
    PROJECT_ROOT = Path(__file__).parent
    LOGO_PATH = PROJECT_ROOT / "Logo" / "Logo de ForsakenScan com Olho.png"

    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), width="stretch")
    else:
        st.markdown(
            "<h1 style='text-align:center; letter-spacing:0.08em;'>FORSAKENSCAN</h1>",
            unsafe_allow_html=True,
        )

    st.markdown(
        "<p style='text-align:center; color:#888; margin-top:-0.5rem; margin-bottom:1.5rem;'>"
        "Acesso seguro à plataforma</p>",
        unsafe_allow_html=True,
    )

    if st.session_state.logged_in:
        role = st.session_state.get("role") or (
            "admin" if st.session_state.get("is_admin") else "user"
        )
        painel = (
            "pages/01_Dashboard.py" if role == "admin" else "pages/03_Perfil.py"
        )
        st.success(
            f"Olá, **{st.session_state.name or st.session_state.username}**! "
            f"Você já está autenticado como **{role}**."
        )
        b1, b2 = st.columns(2, gap="large")
        with b1:
            if st.button("Ir para o meu Painel", width="stretch", key="btn_painel"):
                st.switch_page(painel)
        with b2:
            if st.button("Sair", width="stretch", key="btn_sair_home"):
                _fazer_logout()
                st.rerun()
    else:
        aba_login, aba_cadastro, aba_recuperar, aba_admin = st.tabs(
            ["Login", "Cadastro", "Recuperar Senha", "Área Restrita (Admin)"]
        )

        # ════════════════════════════════════════
        # 1) LOGIN (cliente / usuário comum)
        # ════════════════════════════════════════
        with aba_login:
            st.subheader("Entrar no Sistema")
            st.caption("Acesso para clientes e usuários cadastrados.")

            with st.form(key="frm_login"):
                ident = st.text_input(
                    "E-mail",
                    placeholder="seu@email.com",
                )
                senha = st.text_input("Senha", type="password", placeholder="••••••••")
                ok_btn = st.form_submit_button("Entrar", width="stretch")

            if ok_btn:
                email_login = (ident or "").strip()
                if not email_login or not senha:
                    st.error("Informe e-mail e senha.")
                    st.stop()

                try:
                    auth_res = supabase.auth.sign_in_with_password(
                        {"email": email_login, "password": senha}
                    )
                    auth_user = auth_res.user
                    if not auth_user:
                        raise RuntimeError("Falha ao autenticar no Supabase Auth.")

                    perfil = _carregar_perfil_por_email(email_login)
                    if not perfil:
                        supabase.auth.sign_out()
                        st.error(
                            "Conta autenticada, mas perfil não encontrado em "
                            "`usuarios`. Complete o cadastro novamente."
                        )
                        st.stop()

                    if perfil.get("conta_bloqueada"):
                        supabase.auth.sign_out()
                        st.error("Seu cadastro está bloqueado.")
                        registrar_login(perfil.get("id"), email_login, False, False)
                        st.stop()

                    _aplicar_sessao(
                        perfil, role="user", auth_uid=str(auth_user.id)
                    )
                    registrar_login(
                        perfil.get("id"),
                        perfil.get("username") or email_login,
                        False,
                        True,
                    )
                    st.success("Login efetuado!")
                    st.switch_page("pages/03_Perfil.py")
                except Exception as exc:
                    registrar_login(None, email_login, False, False)
                    msg = str(exc)
                    if "Invalid login credentials" in msg or "invalid" in msg.lower():
                        st.error("Credenciais inválidas.")
                    else:
                        st.error(f"Erro no login: {msg}")

        # ════════════════════════════════════════
        # 2) CADASTRO (Supabase Auth + perfil)
        # ════════════════════════════════════════
        with aba_cadastro:
            st.subheader("Criar Conta")

            bancos = [
                "Itaú",
                "Bradesco",
                "Nubank",
                "Inter",
                "Santander",
                "Banco do Brasil",
                "Caixa",
                "C6 Bank",
                "BTG Pactual",
            ]
            estados_civis = [
                "Solteiro(a)",
                "Casado(a)",
                "Divorciado(a)",
                "Viúvo(a)",
                "União estável",
            ]
            situacoes = [
                "Empregado",
                "Desempregado",
                "Autônomo",
                "Estudante",
                "Aposentado",
            ]

            with st.form("frm_cad"):
                c_a, c_b = st.columns(2, gap="large")
                with c_a:
                    nome = st.text_input("Nome completo")
                    cpf = st.text_input(
                        "CPF",
                        key="cpf",
                        placeholder="000.000.000-00",
                        help="Formato: 000.000.000-00",
                    )
                    email = st.text_input("E-mail")
                with c_b:
                    user = st.text_input("Usuário (nickname)")
                    p1 = st.text_input("Senha", type="password")
                    p2 = st.text_input("Confirmar senha", type="password")

                st.markdown("---")
                st.caption("Dados complementares")

                c1, c2 = st.columns(2, gap="large")
                with c1:
                    rg = st.text_input(
                        "RG",
                        key="rg",
                        placeholder="00.000.000-0",
                    )
                    dnasc = st.text_input(
                        "Data de nascimento",
                        key="dnasc",
                        placeholder="DD/MM/AAAA",
                        help="Formato: DD/MM/AAAA",
                    )
                    tel = st.text_input(
                        "Telefone",
                        key="tel",
                        placeholder="(00) 00000-0000",
                        help="Formato: (00) 00000-0000",
                    )
                    renda = st.text_input(
                        "Renda mensal",
                        key="renda",
                        placeholder="R$ 0,00",
                        help="Formato: R$ 0,00",
                    )
                    estc = st.selectbox("Estado civil", estados_civis)
                with c2:
                    banco = st.selectbox("Banco", bancos)
                    end = st.text_input("Endereço completo")
                    cidade = st.text_input("Cidade")
                    uf = st.text_input("UF", max_chars=2)
                    prof = st.text_input("Profissão")
                    sitp = st.selectbox("Situação profissional", situacoes)

                cadastro_ok = st.form_submit_button("Cadastrar", width="stretch")

            if cadastro_ok:
                if p1 != p2:
                    st.warning("As senhas não coincidem.")
                    st.stop()
                if not email or not p1 or not nome:
                    st.error("Preencha nome, e-mail e senha.")
                    st.stop()

                # Limpa máscaras antes do INSERT
                cpf_limpo = only_digits(cpf)
                rg_limpo = only_digits(rg)
                tel_limpo = only_digits(tel)
                renda_limpa = parse_money_br(renda)
                dnasc_date = parse_date_br(dnasc)

                if cpf_limpo and len(cpf_limpo) != 11:
                    st.error("CPF inválido. Use o formato 000.000.000-00.")
                    st.stop()
                if dnasc and not dnasc_date:
                    st.error("Data de nascimento inválida. Use DD/MM/AAAA.")
                    st.stop()

                try:
                    exist_cpf = (
                        supabase.table("usuarios")
                        .select("id")
                        .eq("cpf", cpf_limpo)
                        .limit(1)
                        .execute()
                    )
                    if cpf_limpo and exist_cpf.data:
                        st.error("CPF já cadastrado.")
                        st.stop()

                    # 1) Auth nativo
                    auth_res = supabase.auth.sign_up(
                        {"email": email.strip(), "password": p1}
                    )
                    auth_user = auth_res.user
                    if not auth_user:
                        st.error(
                            "Não foi possível criar a conta no Auth. "
                            "Verifique se o e-mail já está cadastrado."
                        )
                        st.stop()

                    auth_uid = str(auth_user.id)

                    # 2) Perfil complementar em usuarios
                    perfil_payload = {
                        "nome": nome,
                        "cpf": cpf_limpo,
                        "email": email.strip(),
                        "rg": rg_limpo,
                        "banco": banco,
                        "data_nascimento": (
                            dnasc_date.isoformat() if dnasc_date else None
                        ),
                        "telefone": tel_limpo,
                        "cidade": cidade,
                        "estado": (uf or "").upper(),
                        "renda": renda_limpa,
                        "username": user or email.strip().split("@")[0],
                        "endereco": end,
                        "profissao": prof,
                        "estado_civil": estc,
                        "situacao_prof": sitp,
                    }
                    extras = {"is_admin": False, "perfil": "user"}

                    def _insert_perfil(payload: dict) -> None:
                        supabase.table("usuarios").insert(payload).execute()

                    # Tenta vincular UUID do Auth; cai gradualmente se o schema for legado
                    tentativas = [
                        {**perfil_payload, **extras, "id": auth_uid},
                        {**perfil_payload, **extras, "auth_id": auth_uid},
                        {**perfil_payload, **extras},
                        {**perfil_payload, "auth_id": auth_uid},
                        perfil_payload,
                    ]
                    ultimo_erro: Exception | None = None
                    for payload in tentativas:
                        try:
                            _insert_perfil(payload)
                            ultimo_erro = None
                            break
                        except Exception as err:
                            ultimo_erro = err
                    if ultimo_erro is not None:
                        raise ultimo_erro

                    # Evita deixar sessão Auth aberta após o cadastro
                    try:
                        supabase.auth.sign_out()
                    except Exception:
                        pass

                    st.success(
                        "Conta criada com sucesso! Faça login na aba **Login** "
                        "para acessar a plataforma."
                    )
                except Exception as exc:
                    msg = str(exc)
                    if "already" in msg.lower() or "registered" in msg.lower():
                        st.error("Este e-mail já está cadastrado.")
                    else:
                        st.error(f"Erro no cadastro: {msg}")

        # ════════════════════════════════════════
        # 3) RECUPERAÇÃO DE SENHA (Auth)
        # ════════════════════════════════════════
        with aba_recuperar:
            st.subheader("Recuperar Senha")
            st.caption(
                "Enviaremos um link de redefinição para o e-mail cadastrado "
                "(Supabase Auth)."
            )

            with st.form("frm_rec"):
                mail = st.text_input("E-mail")
                rec_btn = st.form_submit_button(
                    "Enviar link de recuperação", width="stretch"
                )

            if rec_btn:
                email_rec = (mail or "").strip()
                if not email_rec:
                    st.error("Informe o e-mail.")
                else:
                    try:
                        supabase.auth.reset_password_for_email(email_rec)
                        st.success(
                            "Se o e-mail existir na base Auth, o link de "
                            "recuperação foi enviado. Verifique sua caixa de entrada."
                        )
                    except Exception as exc:
                        st.error(f"Erro ao solicitar recuperação: {exc}")

        # ════════════════════════════════════════
        # 4) ÁREA RESTRITA (ADMIN)
        # ════════════════════════════════════════
        with aba_admin:
            st.subheader("Área Restrita")
            st.warning(
                "Acesso restrito a investigadores e gerentes do ForsakenScan."
            )

            with st.form(key="frm_admin"):
                ident_adm = st.text_input(
                    "E-mail Corporativo",
                    placeholder="admin@forsakenscan.com",
                )
                senha_adm = st.text_input(
                    "Senha", type="password", placeholder="••••••••"
                )
                ok_adm = st.form_submit_button(
                    "Entrar como Admin", width="stretch"
                )

            if ok_adm:
                email_adm = (ident_adm or "").strip()
                if not email_adm or not senha_adm:
                    st.error("Informe e-mail corporativo e senha.")
                    st.stop()

                try:
                    auth_res = supabase.auth.sign_in_with_password(
                        {"email": email_adm, "password": senha_adm}
                    )
                    auth_user = auth_res.user
                    if not auth_user:
                        raise RuntimeError("Falha ao autenticar no Supabase Auth.")

                    perfil = _carregar_perfil_por_email(email_adm)
                    if not _eh_admin(perfil):
                        try:
                            supabase.auth.sign_out()
                        except Exception:
                            pass
                        registrar_login(
                            (perfil or {}).get("id"),
                            email_adm,
                            True,
                            False,
                        )
                        st.error(
                            "Acesso negado. Esta conta não possui privilégios "
                            "de administrador."
                        )
                        st.stop()

                    _aplicar_sessao(
                        perfil, role="admin", auth_uid=str(auth_user.id)
                    )
                    registrar_login(
                        perfil.get("id"),
                        perfil.get("username") or email_adm,
                        True,
                        True,
                    )
                    st.success("Login administrativo efetuado!")
                    st.switch_page("pages/01_Dashboard.py")
                except Exception as exc:
                    msg = str(exc)
                    if "Acesso negado" in msg:
                        st.error(msg)
                    elif "Invalid login credentials" in msg or "invalid" in msg.lower():
                        st.error("Credenciais administrativas inválidas.")
                    else:
                        st.error(f"Erro no login admin: {msg}")
