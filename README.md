# ForsakenScan

> **Plataforma End-to-End de Detecção de Fraudes** — do Home Banking simulado ao Back-Office de auditoria, em tempo real.

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img alt="Streamlit" src="https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white" />
  <img alt="Supabase" src="https://img.shields.io/badge/Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white" />
  <img alt="Pandas" src="https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white" />
  <img alt="Deploy" src="https://img.shields.io/badge/Deploy-Live%20on%20Render-46E3B7?style=for-the-badge&logo=render&logoColor=white" />
</p>

---

## Sobre o Projeto

O **ForsakenScan** é um **ecossistema dual** pensado para simular, de ponta a ponta, a operação de um banco digital moderno sob a ótica de risco e compliance.

| Face | Público | Função |
|------|---------|--------|
| **Home Banking** | Clientes | Cadastro, autenticação, perfil e jornada transacional (Pix, pagamentos, compras e histórico) |
| **Back-Office** | Auditores / admins | Monitoramento de KPIs, investigação de alertas e caça a padrões fraudulentos ao vivo |

Cada transação percorre um **pipeline de regras heurísticas**; suspeitas recebem score e motivo de flag e aparecem instantaneamente nos dashboards da equipe de auditoria.

> Apresentado na **Feira de Tecnologia da UNIFECAF** — um laboratório vivo para assumir o papel de cliente *ou* de auditor e caçar fraude em segundos.

---

## Principais Funcionalidades

- **Controle de Acesso RBAC** — clientes enxergam apenas o Home Banking; administradores acessam Dashboard, Painel Mestre e Gerar Dados, com sidebar filtrada por papel
- **Dashboards interativos em tempo real** — KPIs, tendências, heatmaps e radares de risco com Plotly
- **Motor de regras heurísticas antifraude** — limites por turno (dia/noite), ataques de velocidade, cash-in sem histórico, depósito → saque rápido e tentativas de login suspeitas
- **Injeção / geração de dados em massa** — população sintética de usuários e transações para demonstrações e testes de carga
- **Painel Mestre** — visão consolidada dos usuários cadastrados para a equipe de risco
- **Autenticação unificada** — Supabase Auth integrado ao fluxo de cadastro e sessão

---

## Tecnologias Utilizadas

| Camada | Stack |
|--------|--------|
| **Frontend** | [Streamlit](https://streamlit.io/) (Python) |
| **Backend / DB** | [Supabase](https://supabase.com/) (PostgreSQL + Auth) |
| **Dados** | [Pandas](https://pandas.pydata.org/) |
| **Visualização** | [Plotly](https://plotly.com/) |
| **Antifraude** | Motor próprio em Python (`backend/fraude.py`) |
| **Deploy** | [Render](https://render.com/) |

```
ForsakenScan/
├── frontend/          # UI Streamlit (Home + páginas multipage)
│   ├── Home.py        # Entrada: login, cadastro e Home Banking
│   ├── rbac.py        # Regras de acesso e sidebar
│   └── pages/         # Dashboard, Mestre, Perfil, Gerar Dados, Sobre
├── backend/           # Cliente Supabase + motor de fraude
│   ├── db.py
│   └── fraude.py
├── requirements.txt
└── Procfile           # Comando de start no Render
```

---

## Acesso em Produção

O sistema está **online** e disponível em:

### [`https://forsakenscan.onrender.com`](https://forsakenscan.onrender.com)

> Use a aplicação em produção para explorar o Home Banking e, com credenciais de administrador, o Back-Office completo.

---

## Como Rodar Localmente

### 1. Clonar o repositório

```bash
git clone https://github.com/<seu-usuario>/Forsakenscan.git
cd Forsakenscan
```

### 2. Criar e ativar o ambiente virtual

```bash
# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Linux / macOS
python -m venv .venv
source .venv/bin/activate
```

### 3. Instalar as dependências

```bash
pip install -r requirements.txt
```

### 4. Configurar o `.env`

Na raiz do projeto, crie um arquivo `.env` com as credenciais do seu projeto Supabase:

```env
SUPABASE_URL=https://<seu-projeto>.supabase.co
SUPABASE_ANON_KEY=<sua-anon-key>
SUPABASE_SERVICE_ROLE_KEY=<sua-service-role-key>
```

> A `SERVICE_ROLE_KEY` é necessária para operações administrativas (ex.: rollback de usuário no Auth). Não versionar o `.env`.

### 5. Subir a aplicação

```bash
streamlit run frontend/Home.py
```

Acesse o endereço local indicado no terminal (em geral `http://localhost:8501`).

---

## Desenvolvedores / Autores

Projeto desenvolvido para a **Feira de Tecnologia da UNIFECAF**.

| Função | Integrante |
|--------|------------|
| Back-end | **Diego Anjos** |
| Back-end | Gustavo Ribeiro |
| Banco de Dados | Ian Meirelles |
| Front-end & Documentação | Victória Santana |

---

<p align="center">
  <sub>ForsakenScan — detecção implacável de fraudes e atividades suspeitas.</sub>
</p>
