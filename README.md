# 🎬 NextMovie

Recomendação de filmes por busca semântica. Descreva o que você quer assistir 
(um clima, uma vibe, uma ideia) e receba sugestões que captem a essência do seu 
prompt, não só gênero e diretor óbvio.

![Demonstração do NextMovie](frontend/images/readme.gif)

## Como funciona

Você digita o que quer assistir. O backend vetoriza o texto (BAAI/bge-m3) e busca
os filmes mais próximos semanticamente. O pipeline ([api/app/retrieval.py](api/app/retrieval.py)) 
não é só um retrieval direto:

1. **Retrieval direto** - vetoriza o prompt (BAAI/bge-m3, 1024 dims) e busca via `match_movie`.
2. **Expansão por keywords** - consulta `match_keyword` pra mapear conceitos 
   do catálogo (ex.: "perda de memória" -> `amnesia`, `identity crisis`); 
   re-vetoriza os keywords e busca de novo, achando filmes que usam outras palavras.
3. **Fusão RRF** - combina os dois rankings com *Reciprocal Rank Fusion*, 
   priorizando filmes bem posicionados nas duas listas.
4. **Re-ranking + enriquecimento** - um prior suave de qualidade (`vote_average`) 
   ajusta; TMDb adiciona pôsteres e sinopses em pt-BR.
5. **Filtro de qualidade** - se a relevância cair muito (prompt sem sentido), 
   mostra um aviso em vez de resultados ruins.

O modelo é multilíngue, então prompts em português casam com sinopses em inglês 
direto, sem tradução intermediária.

## Base de dados

Um banco vetorial (Supabase/pgvector) com dados de múltiplas fontes:

- **APIs do TMDb, IMDb e Wikidata** para metadados (títulos, gêneros, notas, países)
- **Scraping de páginas web**, principalmente Wikipédia, enriquecendo sinopses

Cada filme vira um texto único (título + data + gêneros + keywords + sinopse + contexto) 
que é convertido em vetor de 1024 dims com BAAI/bge-m3. Os ~20 mil filmes mais populares 
e seus keywords ficam indexados em duas tabelas (`movie`, `keyword`) com buscas de 
similaridade por cosseno. Ver [supabase/supabase-vector-schema.md](supabase/supabase-vector-schema.md) 
para convenções e schema.

## Arquitetura

```
┌──────────────┐  POST /api/recommend  ┌──────────────┐  RPC match_*  ┌────────────────┐
│   Frontend   │ ─────────────────────▶│  API Python  │ ─────────────▶│    Supabase    │
│   Next.js    │ ◀──────────────────── │   FastAPI    │ ◀──────────── │   (pgvector)   │
└──────────────┘        JSON           └──────┬───────┘               └────────────────┘
                                              │  BGE-M3 (inferência hospedada: Cloudflare/HF)
                                              │  TMDb (pôsteres + sinopses)
```

| Pasta | Conteúdo |
|---|---|
| `frontend/` | Next.js 15 (App Router) + Tailwind v4 — UI da busca |
| `api/` | FastAPI — pipeline de recomendação |
| `supabase/` | DDL de referência, doc do schema e molde de ingestão |

## Rodando localmente

Precisa de Python 3.11+, Node 20+ e um `.env` na raiz (copie `.env.example`).

```bash
# API
cd api
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # Linux/mac: .venv/bin/...
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# Frontend (em outro terminal)
cd frontend
npm install
npm run dev                                          # http://localhost:3000
```

## Env vars

| Variável | Onde | Obrigatória | Descrição |
|---|---|---|---|
| `SUPABASE_URL` | API | ✅ | URL do projeto |
| `SUPABASE_API_SECRET_KEY` | API | ✅ | Chave secreta |
| `EMBEDDING_PROVIDER` | API | ✅ | `cloudflare`, `hf`, `deepinfra` ou `mock` |
| `CF_ACCOUNT_ID` + `CF_API_TOKEN` | API | p/ cloudflare | Workers AI |
| `HF_TOKEN` | API | p/ hf | Hugging Face |
| `TMDB_API_KEY` | API | opcional | Pôsteres + sinopses |
| `FRONTEND_ORIGIN` | API | opcional | CORS (padrão `*`) |
| `NEXT_PUBLIC_API_URL` | Frontend | ✅ | URL da API |

## Deploy (Vercel, dois projetos)

1. **API** - importe com `Root Directory = api` (Python) e configure as env vars
2. **Frontend** - importe com `Root Directory = frontend` (Next.js) e set `NEXT_PUBLIC_API_URL`
3. Na API, configure `FRONTEND_ORIGIN` com a URL do frontend pra travar CORS

---

Desenvolvido por Samuel Pedrosa.
