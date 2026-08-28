import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.db import get_supabase_client

import re
from datetime import date

import streamlit as st

# ── Config ──────────────────────────────────────────────────────────
st.set_page_config(page_title="ForsakenScan", layout="wide")

supabase = get_supabase_client()

_SESSION = dict(
    logged_in=False,
    user_id=None,
    username=None,
    name=None,
    email=None,
    is_admin=False,
    role=None,
)
for _k, _v in _SESSION.items():
    st.session_state.setdefault(_k, _v)

# ── Helpers ─────────────────────────────────────────────────────────
only_digits = lambda x: re.sub(r"\D", "", x or "")


def parse_date_br(valor: str | date | None) -> date | None:
    if not valor:
        return None
    if isinstance(valor, date):
        return valor
    s = str(valor).strip()
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        d, mo, y = map(int, m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    return None


def _logout() -> None:
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    st.session_state.update(_SESSION)


def _sessao_cliente(perfil: dict) -> None:
    st.session_state.update(
        logged_in=True,
        user_id=perfil.get("id"),
        username=perfil.get("username") or perfil.get("email"),
        name=perfil.get("nome"),
        email=perfil.get("email"),
        is_admin=False,
        role="user",
    )


def _sessao_admin(admin: dict) -> None:
    st.session_state.update(
        logged_in=True,
        user_id=admin.get("id"),
        username=admin.get("username") or admin.get("email"),
        name=admin.get("nome"),
        email=admin.get("email"),
        is_admin=True,
        role="admin",
    )


def _buscar_usuario(email: str) -> dict | None:
    resp = (
        supabase.table("usuarios")
        .select("*")
        .eq("email", email.strip())
        .limit(1)
        .execute()
    )
    return (resp.data or [None])[0]


def _buscar_admin(email: str) -> dict | None:
    resp = (
        supabase.table("administradores")
        .select("*")
        .eq("email", email.strip())
        .limit(1)
        .execute()
    )
    return (resp.data or [None])[0]


# ── Sidebar oculta sem login ────────────────────────────────────────
if not st.session_state.logged_in:
    st.markdown(
        """
        <style>
            [data-testid="stSidebar"], [data-testid="collapsedControl"] {
                display: none !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

if st.session_state.logged_in and st.sidebar.button("Sair"):
    _logout()
    st.rerun()

# ── Layout ──────────────────────────────────────────────────────────
_, centro, _ = st.columns([1, 3, 1])

with centro:
    logo = Path(__file__).parent / "Logo" / "Logo de ForsakenScan com Olho.png"
    if logo.exists():
        st.image(str(logo), width="stretch")
    else:
        st.title("FORSAKENSCAN")

    st.caption("Plataforma de monitoramento e perfil bancário")

    # ── Já autenticado ─────────────────────────────────────────────
    if st.session_state.logged_in:
        destino = (
            "pages/01_Dashboard.py"
            if st.session_state.is_admin
            else "pages/03_Perfil.py"
        )
        st.success(f"Olá, **{st.session_state.name or st.session_state.username}**!")
        c1, c2 = st.columns(2)
        if c1.button("Ir para o painel", width="stretch"):
            st.switch_page(destino)
        if c2.button("Sair da conta", width="stretch"):
            _logout()
            st.rerun()
        st.stop()

    # ── Abas de autenticação ───────────────────────────────────────
    tab_cliente, tab_cadastro, tab_admin = st.tabs(
        ["Acesso Cliente", "Criar Conta", "Acesso Corporativo (Admin)"]
    )

    # ── 1) Acesso Cliente ──────────────────────────────────────────
    with tab_cliente:
        st.subheader("Login do cliente")

        with st.form("login_cliente"):
            email = st.text_input("E-mail")
            senha = st.text_input("Senha", type="password")
            enviar = st.form_submit_button("Entrar", width="stretch")

        if enviar:
            email = (email or "").strip()
            if not email or not senha:
                st.error("Informe e-mail e senha.")
            else:
                try:
                    auth = supabase.auth.sign_in_with_password(
                        {"email": email, "password": senha}
                    )
                    if not auth.user:
                        st.error("Falha na autenticação.")
                    else:
                        perfil = _buscar_usuario(email)
                        if not perfil:
                            supabase.auth.sign_out()
                            st.error("Conta Auth encontrada, mas perfil não existe em `usuarios`.")
                        elif perfil.get("conta_bloqueada"):
                            supabase.auth.sign_out()
                            st.error("Conta bloqueada. Entre em contato com o suporte.")
                        else:
                            _sessao_cliente(perfil)
                            st.switch_page("pages/03_Perfil.py")
                except Exception as exc:
                    msg = str(exc)
                    if "Invalid login credentials" in msg:
                        st.error("E-mail ou senha inválidos.")
                    else:
                        st.error(f"Erro no login: {msg}")

    # ── 2) Criar Conta ─────────────────────────────────────────────
    with tab_cadastro:
        st.subheader("Cadastro de cliente")

        bancos = [
            "Itaú", "Bradesco", "Nubank", "Inter", "Santander",
            "Banco do Brasil", "Caixa", "C6 Bank", "BTG Pactual",
        ]
        estados_civis = [
            "Solteiro(a)", "Casado(a)", "Divorciado(a)", "Viúvo(a)", "União estável",
        ]
        situacoes = [
            "Empregado", "Desempregado", "Autônomo", "Estudante", "Aposentado",
        ]

        col_a, col_b = st.columns(2)
        with col_a:
            st.text_input("Nome completo", key="cad_nome")
            st.text_input("CPF", key="cad_cpf", placeholder="000.000.000-00")
            st.text_input("E-mail", key="cad_email")
            st.text_input("Usuário", key="cad_username")
        with col_b:
            st.text_input("Senha", type="password", key="cad_senha")
            st.text_input("Confirmar senha", type="password", key="cad_senha_conf")
            st.text_input("RG (apenas números)", key="cad_rg", placeholder="000000000")
            st.text_input("Telefone", key="cad_telefone", placeholder="(00) 00000-0000")

        col_c, col_d = st.columns(2)
        with col_c:
            st.text_input(
                "Data de nascimento", key="cad_data_nasc", placeholder="DD/MM/AAAA"
            )
            st.text_input("Renda mensal", key="cad_renda", placeholder="R$ 0,00")
            st.selectbox("Banco", bancos, key="cad_banco")
            st.text_input("Endereço", key="cad_endereco")
        with col_d:
            st.text_input("Cidade", key="cad_cidade")
            st.text_input("UF", max_chars=2, key="cad_uf")
            st.text_input("Profissão", key="cad_profissao")
            st.selectbox("Estado civil", estados_civis, key="cad_estado_civil")
            st.selectbox("Situação profissional", situacoes, key="cad_situacao_prof")

        cadastrar = st.button("Criar conta", type="primary", width="stretch")

        if cadastrar:
            nome = (st.session_state.cad_nome or "").strip()
            email_cad = (st.session_state.cad_email or "").strip()
            senha_cad = st.session_state.cad_senha or ""
            senha_conf = st.session_state.cad_senha_conf or ""
            cpf = st.session_state.cad_cpf or ""
            rg = st.session_state.cad_rg or ""
            telefone = st.session_state.cad_telefone or ""
            data_nasc = st.session_state.cad_data_nasc or ""
            renda = st.session_state.cad_renda or ""
            username = st.session_state.cad_username or ""
            banco = st.session_state.cad_banco
            endereco = st.session_state.cad_endereco or ""
            cidade = st.session_state.cad_cidade or ""
            uf = st.session_state.cad_uf or ""
            profissao = st.session_state.cad_profissao or ""
            estado_civil = st.session_state.cad_estado_civil
            situacao_prof = st.session_state.cad_situacao_prof

            if not nome or not email_cad or not senha_cad:
                st.error("Preencha nome, e-mail e senha.")
            elif senha_cad != senha_conf:
                st.warning("As senhas não coincidem.")
            else:
                cpf_limpo = only_digits(cpf)
                rg_limpo = only_digits(rg)
                tel_limpo = only_digits(telefone)
                renda_str = (renda or "").strip()
                if renda_str:
                    renda_val = float(
                        renda_str.replace("R$", "")
                        .replace(".", "")
                        .replace(",", ".")
                        .strip()
                    )
                else:
                    renda_val = 0.0
                nasc_val = parse_date_br(data_nasc)
                usuario_val = (username or email_cad.split("@")[0]).strip()

                if cpf_limpo and len(cpf_limpo) != 11:
                    st.error("CPF inválido.")
                elif data_nasc and not nasc_val:
                    st.error("Data de nascimento inválida. Use DD/MM/AAAA.")
                else:
                    try:
                        dup = (
                            supabase.table("usuarios")
                            .select("id")
                            .eq("email", email_cad)
                            .limit(1)
                            .execute()
                        )
                        if dup.data:
                            st.error("E-mail já cadastrado.")
                        else:
                            auth = supabase.auth.sign_up(
                                {"email": email_cad, "password": senha_cad}
                            )
                            if not auth.user:
                                st.error("Não foi possível criar a conta no Auth.")
                            else:
                                payload = {
                                    "nome": nome,
                                    "username": usuario_val,
                                    "cpf": cpf_limpo,
                                    "email": email_cad,
                                    "rg": rg_limpo,
                                    "telefone": tel_limpo,
                                    "data_nascimento": nasc_val.isoformat() if nasc_val else None,
                                    "cidade": cidade,
                                    "renda": renda_val,
                                    "estado": (uf or "").upper(),
                                    "banco": banco,
                                    "profissao": profissao,
                                    "endereco": endereco,
                                    "estado_civil": estado_civil,
                                    "situacao_prof": situacao_prof,
                                }
                                supabase.table("usuarios").insert(payload).execute()
                                try:
                                    supabase.auth.sign_out()
                                except Exception:
                                    pass
                                st.success("Conta criada! Faça login na aba **Acesso Cliente**.")
                    except Exception as exc:
                        msg = str(exc)
                        if "already" in msg.lower():
                            st.error("E-mail já cadastrado no Auth.")
                        else:
                            st.error(f"Erro no cadastro: {msg}")

        st.html(
            """
            <script>
            const doc = window.parent.document;
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;

            function updateReactInput(element, value) {
                nativeInputValueSetter.call(element, value);
                element.dispatchEvent(new Event('input', { bubbles: true }));
            }

            function applyMask(selector, type) {
                const inputs = doc.querySelectorAll(selector);
                inputs.forEach(input => {
                    if (input.dataset.masked) return;
                    input.dataset.masked = 'true';

                    input.addEventListener('input', function(e) {
                        let v = e.target.value.replace(/\\D/g, '');
                        let formatted = v;

                        if (type === 'cpf') {
                            v = v.substring(0, 11);
                            formatted = v.replace(/(\\d{3})(\\d)/, '$1.$2').replace(/(\\d{3})(\\d)/, '$1.$2').replace(/(\\d{3})(\\d{1,2})$/, '$1-$2');
                        } else if (type === 'phone') {
                            v = v.substring(0, 11);
                            formatted = v.replace(/(\\d{2})(\\d)/, '($1) $2').replace(/(\\d{5})(\\d{1,4})$/, '$1-$2');
                        } else if (type === 'date') {
                            v = v.substring(0, 8);
                            formatted = v.replace(/(\\d{2})(\\d)/, '$1/$2').replace(/(\\d{2})(\\d)/, '$1/$2');
                        } else if (type === 'money') {
                            v = v.replace(/^0+/, '');
                            if (v === '') v = '0';
                            let num = parseInt(v) / 100;
                            formatted = num.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
                        }

                        if (e.target.value !== formatted) {
                            updateReactInput(e.target, formatted);
                        }
                    });
                });
            }

            setTimeout(() => {
                applyMask('input[aria-label="CPF"]', 'cpf');
                applyMask('input[aria-label="Telefone"]', 'phone');
                applyMask('input[aria-label="Data de nascimento"]', 'date');
                applyMask('input[aria-label="Renda mensal"]', 'money');
            }, 500);
            </script>
            """,
            unsafe_allow_javascript=True,
        )

    # ── 3) Acesso Corporativo ──────────────────────────────────────
    with tab_admin:
        st.subheader("Login corporativo")
        st.warning("Acesso restrito a investigadores e gerentes do ForsakenScan.")

        with st.form("login_admin"):
            email_adm = st.text_input("E-mail corporativo")
            senha_adm = st.text_input("Senha", type="password")
            enviar_adm = st.form_submit_button("Entrar como admin", width="stretch")

        if enviar_adm:
            email_adm = (email_adm or "").strip()
            if not email_adm or not senha_adm:
                st.error("Informe e-mail e senha.")
            else:
                try:
                    response = supabase.auth.sign_in_with_password(
                        {"email": email_adm, "password": senha_adm}
                    )
                    if not response.user:
                        st.error("Falha na autenticação.")
                    else:
                        user_id = response.user.id
                        admin_data = (
                            get_supabase_client()
                            .table("administradores")
                            .select("*")
                            .eq("id", user_id)
                            .execute()
                        )
                        if not admin_data.data:
                            supabase.auth.sign_out()
                            st.error(
                                f"Debug: Autenticado com sucesso, mas o ID {user_id} "
                                "não foi encontrado na tabela 'administradores'. "
                                "Verifique se o ID no Table Editor é exatamente este."
                            )
                        else:
                            _sessao_admin(admin_data.data[0])
                            st.switch_page("pages/01_Dashboard.py")
                except Exception as exc:
                    msg = str(exc)
                    if "Invalid login credentials" in msg:
                        st.error("E-mail ou senha inválidos.")
                    else:
                        st.error(f"Erro no login: {msg}")
