import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

_FRONTEND = Path(__file__).resolve().parent.parent
if str(_FRONTEND) not in sys.path:
    sys.path.insert(0, str(_FRONTEND))

from rbac import hide_admin_pages_from_sidebar

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
# 5) Visão Geral
# ------------------------------------------------------------
st.markdown("## Visão Geral")
st.markdown(
    """
    **Detecção implacável de fraudes e atividades suspeitas**  
    O **ForsakenScan** é um ecossistema dual pensado para simular, de ponta a ponta,
    a operação de um banco digital moderno:

    - **Home Banking (cliente)** — cadastro, autenticação, perfil e jornada transacional
      completa: Pix, pagamentos, compras online e histórico financeiro em tempo real.
    - **Back-Office (auditor)** — painel administrativo robusto para equipes de risco
      monitorarem KPIs, investigarem alertas e caçar padrões fraudulentos ao vivo.

    Do cadastro à flag de suspeita, cada transação percorre o pipeline de detecção
    e aparece instantaneamente nos dashboards interativos da equipe de auditoria.
    """
)

# ------------------------------------------------------------
# 6) Evento UNIFECAF
# ------------------------------------------------------------
st.markdown("## Feira de Tecnologia — 24 de Maio de 2025 da UNIFECAF")
st.markdown(
    """
    Apresentado na **Feira de Tecnologia da UNIFECAF**, convidamos você a
    **testar a ferramenta na prática**:

    1. **Assuma o papel de cliente (ou fraudador)** — crie uma conta, gere dados
       sintéticos e execute transações normais ou suspeitas de propósito.
    2. **Mude de chapéu para auditor** — acesse o painel administrador e opere o
       Back-Office em tempo real: KPIs, gráficos interativos, radar de risco e alertas.
    3. **Caçe os fraudadores ao vivo** — veja, em segundos, como o motor de regras
       sinaliza cash-outs atípicos, ataques de velocidade e anomalias de comportamento,
       e tome decisões como um analista de fraude de verdade.
    """
)

# ------------------------------------------------------------
# 7) Stack Tecnológico
# ------------------------------------------------------------
st.markdown("## Stack Tecnológico")
st.markdown(
    """
    - **Frontend** — Streamlit (Python) aprimorado com injeções de **Vanilla JS**
      para formatação reativa (máscaras de CPF, telefone e valores em tempo real).
    - **Backend & Banco de Dados** — **Supabase** (PostgreSQL) operando como BaaS
      para autenticação unificada e persistência de transações, usuários e logs.
    - **Engenharia de Dados** — **Pandas** para tratamento pesado e cruzamento de
      matrizes de dados em memória (agregações, filtros e joins sobre o dataset transacional).
    - **Data Visualization** — **Plotly** para renderização de dashboards interativos
      e de alta performance (tendências, heatmaps, scatter plots e radares de risco).
    """
)

# ------------------------------------------------------------
# 8) Segurança & Antifraude
# ------------------------------------------------------------
st.markdown("## Segurança & Antifraude")
st.markdown(
    """
    - **RBAC (Role-Based Access Control)** — controle de acesso por papéis que blinda
      as rotas da aplicação: clientes veem apenas o Home Banking; administradores
      acessam Dashboard, Mestre e Gerar Dados. Rotas protegidas e sidebar filtrada
      por role garantem isolamento entre as duas faces do ecossistema.
    - **Motor de regras heurísticas** — cada transação é avaliada em tempo real por
      um pipeline de regras em Python que monitora:
      - **Cash-Outs atípicos** — saques ou transferências imediatamente após depósitos
        elevados, ou cash-in alto em contas sem histórico recente.
      - **Ataques de velocidade (lavagem)** — rajadas de 5+ transações em 5 minutos
        pelo mesmo usuário ou por múltiplos usuários no mesmo IP.
      - **Anomalias de geolocalização e comportamento** — limites por turno (dia/noite)
        excedidos, tentativas de login falhas em sequência e padrões fora do perfil
        habitual do cliente.
    """
)

# ------------------------------------------------------------
# 9) Passo a passo de uso
# ------------------------------------------------------------
st.markdown("## Como Funciona — passo a passo")
st.markdown(
    """
    1. **Home / Autenticação** — Cliente se cadastra via Supabase Auth e acessa sua conta.  
    2. **Gerar Dados** — Administrador popula o ambiente com usuários e transações sintéticas.  
    3. **Perfil do Usuário** — Cliente consulta saldo, histórico e executa Pix, pagamentos e compras.  
    4. **Motor de Fraude** — Cada operação passa pelas regras heurísticas; suspeitas
       recebem score e motivo de flag.  
    5. **Dashboard / Mestre** — Equipe de auditoria acompanha KPIs, gráficos Plotly
       e alertas em tempo real, caçando fraudadores conforme os dados entram.
    """
)

# ------------------------------------------------------------
# 10) Equipe
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
# 11) Agradecimentos e data de atualização
# ------------------------------------------------------------
st.markdown("## Agradecimentos")
st.markdown(
    """
    Agradecemos aos professores, mentores e colegas pelo suporte técnico  
    e pelas trocas de ideias ao longo do desenvolvimento.  
    """
)
st.markdown(f"*Última atualização: {datetime.today().strftime('%Y-%m-%d')}*")
