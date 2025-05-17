# GG - Seu Guia Gamer para Encontrar o Squad Perfeito! 🚀

Bem-vindo ao **GG**! Um protótipo de plataforma inteligente de matchmaking para jogadores, projetada para te ajudar a encontrar os parceiros ideais para suas gameplays. Utilizando Python com Flask para o backend, Inteligência Artificial com Google Gemini para um chatbot de perfil dinâmico e interativo, e uma interface web amigável, o GG visa transformar a maneira como você encontra seu próximo squad.

## 🎯 Objetivo

Conectar jogadores com base em compatibilidade de jogos, nível de habilidade, estilo de jogo, disponibilidade e preferências de comunicação, tornando a experiência de jogar online mais social, divertida e menos solitária.

## ✨ Funcionalidades Implementadas

* **Cadastro e Login de Usuários:** Sistema de autenticação seguro utilizando tokens JWT.
* **Chatbot de Perfil Inteligente (Agente GG):** Coleta de preferências detalhadas do jogador de forma conversacional e natural.
* **Matchmaking Avançado:** Algoritmo que sugere jogadores compatíveis, considerando múltiplos critérios e aprendizado implícito.
* **Sistema de "Likes" e Matches Mútuos:** Permite que usuários expressem interesse e sejam notificados sobre matches recíprocos.
* **Avaliação de Jogadores (Estrelas):** Usuários podem avaliar uns aos outros após interações, influenciando a "popularidade" e as futuras sugestões de match.
* **Envio de Primeira Mensagem (Simulado):** Uma forma de iniciar o contato após um match mútuo.
* **Agente Analista de Dados (Versão Inicial):** Script para extrair métricas básicas sobre a comunidade e o sistema.

## 🤖 Agentes de Inteligência Artificial (IA) em Ação

O coração do GG reside nos seus agentes de IA, que trabalham para criar a melhor experiência possível:

### 1. Agente "GG" de Personalidade e Suporte (Chatbot de Perfil) 💬

* **Missão Principal:**
    * Coletar as preferências de jogo dos usuários de forma interativa, dinâmica e humana para construir um perfil gamer rico e detalhado.
    * Atuar como a interface amigável e a "personalidade" da plataforma, guiando o usuário durante o onboarding.
* **Habilidades (Como Funciona):**
    * **Geração de Diálogo Dinâmico:** Utiliza a API do **Google Gemini** para gerar as perguntas do chatbot. Em vez de frases fixas, o Gemini recebe:
        * Uma descrição da personalidade "GG" (amigável, gamer, natural, prestativo, com comentários contextuais).
        * O histórico da conversa (respostas anteriores do usuário).
        * O próximo campo de informação a ser coletado (ex: "nível de habilidade").
        Com isso, o Gemini formula a próxima pergunta e um breve comentário de reconhecimento sobre a resposta anterior do usuário, tornando o diálogo mais fluido, menos repetitivo e mais humano.
    * **Entendimento de Linguagem Natural (NLU) para Extração Precisa:** As respostas em linguagem natural dos usuários são enviadas ao Gemini com prompts específicos para extrair as informações chave relevantes para cada campo do perfil (Jogo Principal, Nível de Habilidade, Estilo de Jogo, Disponibilidade, Identidade de Gênero, Estilo de Comunicação em Jogo).
    * **Mapeamento Inteligente para Categorias:** Para campos que possuem categorias pré-definidas (como Nível de Habilidade, Estilo de Jogo, Gênero, Estilo de Comunicação), o Gemini é instruído a classificar a resposta do usuário dentro dessas categorias, mesmo que o usuário utilize sinônimos, gírias leves ou frases descritivas (ex: "comecei a jogar agora" é corretamente mapeado para "Iniciante"). Se a informação não for clara, ele retorna "Não especificado".
* **Armazenamento dos Dados:** As preferências e informações coletadas são salvas de forma estruturada no banco de dados SQLite, associadas ao perfil do usuário logado.
* **Impacto:** Cria uma experiência de configuração de perfil muito mais agradável e menos mecânica, incentivando os usuários a fornecerem dados mais completos e precisos, o que, por sua vez, melhora drasticamente a qualidade do matchmaking.

### 2. Agente de Matchmaking Avançado 🎯

* **Missão Principal:**
    * Sugerir os jogadores mais compatíveis para o usuário logado, aumentando significativamente a probabilidade de interações de jogo positivas e formação de squads duradouros.
* **Habilidades (Como Funciona):**
    * **Análise Multicritério:** Lê os perfis completos dos usuários (incluindo os novos campos de gênero e estilo de comunicação) do banco de dados SQLite.
    * **Cálculo de Score de Compatibilidade Ponderado:** Avalia a compatibilidade entre o usuário logado ("viewer") e outros jogadores ("potential match profiles") usando um sistema de pesos para diversos critérios:
        * **Jogo Principal:** Critério fundamental e obrigatório para um match ser considerado.
        * **Nível de Habilidade:** Proximidade entre os níveis declarados.
        * **Estilo de Jogo:** Preferência por estilos de jogo idênticos.
        * **Disponibilidade:** Lógica que busca por sobreposição de palavras-chave nos horários.
        * **Identidade de Gênero:** Lógica simples de compatibilidade ou neutralidade.
        * **Estilo de Comunicação:** Compatibilidade entre as preferências de comunicação em jogo.
    * **"Popularidade" Inteligente com Avaliações por Estrelas:**
        * Após uma interação (match mútuo), os usuários podem (funcionalidade de *dar* a avaliação a ser implementada no front-end) avaliar uns aos outros com 1 a 5 estrelas. Essas avaliações são salvas no banco de dados.
        * O Agente de Matchmaking consulta essas avaliações e calcula uma **média de estrelas** para cada `potential_match_profile`.
        * Um **"Boost de Popularidade"** é adicionado ao score de compatibilidade, sendo proporcional a essa avaliação média (com um limite para não supervalorizar). Jogadores bem avaliados pela comunidade (especialmente dentro do mesmo jogo) tornam-se sugestões mais fortes.
* **Saída:** Fornece uma lista dos top N matches (atualmente top 3) para o front-end, incluindo o score total de compatibilidade e as "razões" (os critérios que mais contribuíram para aquele match específico, incluindo o boost por boa avaliação).
* **Impacto:** Gera sugestões de matchmaking que não são apenas baseadas em preferências auto-declaradas, mas também no feedback social e na reputação dentro da comunidade do jogo, levando a conexões mais significativas.

### 3. Agente Analista de Dados da Comunidade (Versão Inicial) 📊

* **Missão Principal:**
    * Coletar métricas e gerar insights sobre a base de usuários, o uso da plataforma e a eficácia do sistema de matchmaking para informar decisões de negócios e desenvolvimento da plataforma GG (ou Trexx Club).
* **Habilidades (Como Funciona - Versão Atual):**
    * Um script Python dedicado (`analise_dados_gg.py`) que se conecta diretamente ao banco de dados SQLite (`tinder_gamer.db`).
    * Executa consultas SQL (via SQLAlchemy) para agregar e analisar dados das tabelas `User`, `UserProfile`, `Like` e `MatchRating`.
* **Análises Chave Geradas (Exemplos):**
    * Número total de usuários e taxa de crescimento.
    * Percentagem de perfis completos vs. incompletos.
    * Distribuição e popularidade de jogos principais, níveis, estilos, etc.
    * Volume de "likes" dados e taxa de conversão para "matches mútuos".
    * Média de estrelas recebidas pelos jogadores e identificação de jogadores com alta/baixa popularidade.
* **Saída:** Atualmente, imprime um relatório textual diretamente no console do terminal.
* **Impacto:** Fornece uma visão quantitativa do comportamento da comunidade e da performance do sistema, permitindo identificar pontos fortes, áreas de melhoria, e oportunidades para novas funcionalidades ou otimizações.
* **Próximos Passos para este Agente:** Evoluir para gerar gráficos visuais (com `Matplotlib`, `Seaborn`), exportar relatórios para CSV/HTML, ou até mesmo criar um dashboard web de administração.

## 🛠️ Tecnologias Utilizadas

* **Backend:** Python 3, Flask, Flask-SQLAlchemy, Flask-JWT-Extended, Flask-CORS, python-dotenv, Werkzeug, Gunicorn (para produção futura).
* **Inteligência Artificial:** Google Gemini API.
* **Banco de Dados:** SQLite (para desenvolvimento).
* **Front-end:** HTML5, CSS3 (Tailwind CSS), JavaScript (Vanilla).
* **Versionamento:** Git, GitHub.

## 📁 Estrutura do Projeto (Simplificada)


gg-tinder-gamer/
├── backend/
│   ├── venv/                     # Ambiente virtual Python (ignorado)
│   ├── instance/                 # Pode conter o DB se não for explícito o path
│   ├── app.py                    # Aplicação principal Flask (backend)
│   ├── analise_dados_gg.py       # Script do Agente Analista de Dados
│   ├── tinder_gamer.db           # Banco de dados SQLite (ignorado)
│   ├── google_credentials.json   # Credenciais Google Service Account (ignorado)
│   ├── .env                      # Variáveis de ambiente (ignorado)
│   └── requirements.txt          # Dependências Python
├── frontend/
│   ├── images/
│   │   └── mascote_gg.png        # Imagem do mascote
│   └── index.html                # Arquivo principal do front-end
├── .gitignore                    # Arquivos e pastas a serem ignorados pelo Git
└── README.md                     # Este arquivo


## 🚀 Como Rodar Localmente

1.  **Pré-requisitos:**
    * Git instalado.
    * Python 3.8+ instalado e adicionado ao PATH.
    * `pip` (gestor de pacotes Python) instalado.

2.  **Clonar o Repositório:**
    ```bash
    git clone [https://github.com/0xlari/tinder-gamer-gg.git](https://github.com/0xlari/tinder-gamer-gg.git) # Substitua pelo URL do seu repositório
    cd tinder-gamer-gg
    ```

3.  **Configurar o Backend:**
    * Navegue até a pasta `backend`: `cd backend`
    * Crie e ative um ambiente virtual:
        ```bash
        python -m venv venv
        # Windows:
        .\venv\Scripts\activate
        # macOS/Linux:
        # source venv/bin/activate
        ```
    * Instale as dependências:
        ```bash
        pip install -r requirements.txt
        ```
    * Crie um arquivo chamado `.env` na pasta `backend` com o seguinte conteúdo, substituindo pelos seus valores reais:
        ```env
        GEMINI_API_KEY="SUA_CHAVE_API_DO_GEMINI_AQUI"
        JWT_SECRET_KEY="UMA_CHAVE_SECRETA_FORTE_E_ALEATORIA_PARA_JWT"
        ```
    * (Se for usar Google Sheets para algo) Coloque o seu arquivo `google_credentials.json` na pasta `backend`.

4.  **Rodar o Servidor Backend Flask:**
    * No terminal, dentro da pasta `backend` e com o ambiente virtual ativado:
        ```bash
        python app.py
        ```
    * O servidor deverá iniciar em `http://127.0.0.1:5000`. Mantenha este terminal rodando.

5.  **Servir o Front-end:**
    * Abra um **novo terminal**.
    * Navegue até a pasta `frontend`: `cd frontend` (ou `cd ../frontend` se estiver na pasta backend).
    * Inicie um servidor HTTP simples:
        ```bash
        python -m http.server 8000
        ```
    * Mantenha este terminal rodando.

6.  **Acessar a Aplicação:**
    * Abra seu navegador e vá para `http://localhost:8000`.

## 💡 Ideias Futuras e Próximos Desafios

* Desenvolver um sistema de chat em tempo real inicialmente, entre matches mútuos.
* Refinar continuamente os prompts do Gemini para o chatbot e para extração de dados.
* Expandir as análises do Agente de Dados e criar um dashboard visual.
* Permitir que usuários editem seus perfis após a criação.
* Adicionar mais critérios de matchmaking e filtros avançados.

