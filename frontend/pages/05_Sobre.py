import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

_FRONTEND = Path(__file__).resolve().parent.parent
if str(_FRONTEND) not in sys.path:
    sys.path.insert(0, str(_FRONTEND))

from rbac import hide_admin_pages_from_sidebar

if not st.session_state.get("is_admin"):
    hide_admin_pages_from_sidebar()

# ------------------------------------------------------------
# 1) Calcula o caminho absoluto para a pasta raiz do projeto
# ------------------------------------------------------------
# Path(__file__)   --> frontend/pages/05_Sobre.py
# .parent           --> frontend/pages
# .parent.parent    --> frontend
FRONTEND_ROOT = Path(__file__).parent.parent

# ------------------------------------------------------------
# 2) Define o path completo para o logo
# ------------------------------------------------------------
LOGO_PATH = FRONTEND_ROOT / "Logo" / "Logo de ForsakenScan com Olho.png"

# ------------------------------------------------------------
# 3) Exibe o logo
# ------------------------------------------------------------
if LOGO_PATH.exists():
    st.image(str(LOGO_PATH), use_container_width=True)
else:
    st.warning(f"Logo não encontrado em: {LOGO_PATH}")

# ------------------------------------------------------------
# 4) Título gigantesco
# ------------------------------------------------------------
st.markdown("<h1 style='text-align:center;'>FORSAKENSCAN</h1>", unsafe_allow_html=True)

# ------------------------------------------------------------
# 5) Descrição principal
# ------------------------------------------------------------
st.markdown(
    """
    **Detecção Implacável de Fraudes e Atividades Suspeitas**  
    Plataforma end-to-end para bancos e fintechs monitorarem,  
    em tempo real, toda a jornada do cliente:  
    - **Cadastro** de usuários  
    - **Transações** financeiras  
    - **Módulo de regras** para flag de comportamentos de risco  
    - **Dashboard administrativo** com KPIs, gráficos interativos e alertas  
    """
)

# ------------------------------------------------------------
# 6) Evento UNIFECAF
# ------------------------------------------------------------
st.markdown("## Feira de Tecnologia — 24 de Maio de 2025")
st.markdown(
    """
    Apresentado na **Feira de Tecnologia da UNIFECAF**, onde  
    visitantes poderão:
    - Criar uma conta **na hora** (CPF fictício) e executar transações.
    - Ver, em **segundos**, como o dashboard sinaliza atividades suspeitas.
    - Acompanhar **ao vivo** painéis de tendência, radar de risco e heatmaps.
    - **Simular** decisões de bloqueio/desbloqueio como um analista de fraude.
    """
)

# ------------------------------------------------------------
# 7) Tecnologias e Ferramentas
# ------------------------------------------------------------
st.markdown("## Principais Ferramentas & Bibliotecas")
st.markdown(
    """
    | Camada               | Tecnologias                                                                 |
    |----------------------|------------------------------------------------------------------------------|
    | Front-end            | Streamlit (UI & roteamento), Plotly Express (gráficos), IMask.js (máscaras) |
    | Back-end             | FastAPI (REST API), SQLAlchemy (ORM)                                         |
    | Banco de Dados       | MySQL 8 (InnoDB)                                                             |
    | Dados Sintéticos     | Faker, NumPy, pandas                                                         |
    | Detecção de Fraude   | Motor de regras em Python (`fraude.py`)                                      |
    | Dev-Ops              | Docker & Docker-Compose, GitHub Actions (CI)                                 |
    """
)

# ------------------------------------------------------------
# 8) Passo a passo de uso
# ------------------------------------------------------------
st.markdown("## Como Funciona — passo a passo")
st.markdown(
    """
    1. **Home / Autenticação** — Usuário se cadastra e acessa sua conta.  
    2. **Gerar Dados** — Gera um dataset de teste (3 000 usuários + 11 000 transações, ~10% marcadas).  
    3. **Dashboard / Mestre** — Equipe de risco acompanha KPIs e alertas em tempo real.  
    4. **Perfil do Usuário** — Cliente vê histórico, faz pagamentos/Pix, compras online.  
    5. **Motor de Fraude** — Cada transação passa por 7 regras (limites por turno, 
       cash-in sem histórico, trocas de dados + saque, etc.).  
       Se alguma regra dispara, a transação chega sinalizada no dashboard.
    """
)

# ------------------------------------------------------------
# 9) Equipe
# ------------------------------------------------------------
st.markdown("## Equipe")
st.markdown(
    """
    | Função                       | Integrante          |
    |------------------------------|---------------------|
    | Back-end                     | Diego Anjos         |
    | Back-end                     | Gustavo Ribeiro     |
    | Banco de Dados               | Ian Meirelles       |
    | Front-end, Documentação      | Victória Santana    |
    """
)

# ------------------------------------------------------------
# 10) Agradecimentos e data de atualização
# ------------------------------------------------------------
st.markdown("## Agradecimentos")
st.markdown(
    """
    Agradecemos aos professores, mentores e colegas pelo suporte técnico  
    e pelas trocas de ideias ao longo do desenvolvimento.  
    """
)
st.markdown(f"*Última atualização: {datetime.today().strftime('%Y-%m-%d')}*")
