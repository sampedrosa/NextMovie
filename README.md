# 🎬 NextMovie

Recomendação de filmes por **busca semântica vetorial**: o usuário descreve em
linguagem natural o que quer assistir (um clima, uma ideia, uma sensação) e a
aplicação recomenda filmes — inclusive os não óbvios, que vão além de gênero e
diretor.

## Arquitetura

```
┌──────────────┐   POST /api/recommend   ┌──────────────┐   RPC match_*   ┌────────────────┐
│   Frontend   │ ───────────────────────▶│  API Python  │ ───────────────▶│    Supabase    │
│   Next.js    │ ◀─────────────────────── │   FastAPI    │ ◀─────────────── │   (pgvector)   │
└──────────────┘        JSON             └──────┬───────┘                 └────────────────┘
                                                │
                                  ┌─────────────┴─────────────┐
                                  │ BAAI/bge-m3 (inferência    │
                                  │ hospedada: HF/DeepInfra/CF)│
                                  │ TMDb (pôsteres, opcional)  │
                                  └───────────────────────────┘
```

| Pasta | Conteúdo |
|---|---|
| `frontend/` | Next.js 15 (App Router) + Tailwind v4 — UI da busca |
| `api/` | FastAPI — pipeline de recomendação |
| `supabase/` | DDL de referência (`schema.sql`), doc do schema e molde de ingestão |
| `supabase/supabase-vector-schema.md` | Documentação detalhada do schema e convenções de embedding |

## Como funciona a recomendação

O índice vetorial usa **BAAI/bge-m3** (1024 dims, cosseno) — multilíngue, então
prompts em português casam com sinopses em inglês. O pipeline
([api/app/retrieval.py](api/app/retrieval.py)) faz mais que um retrieval direto:

1. **Retrieval direto** — o prompt é vetorizado e buscado via `match_movie`.
2. **Expansão por keywords** — o mesmo vetor consulta `match_keyword` para
   mapear o prompt a conceitos conhecidos do catálogo (ex.: "perda de memória"
   → `amnesia`, `identity crisis`). Os conceitos acima do limiar de similaridade
   são anexados ao prompt, que é re-vetorizado e buscado de novo — isso puxa
   filmes cuja sinopse usa palavras diferentes das do usuário.
3. **Fusão RRF** — os dois rankings são combinados por Reciprocal Rank Fusion,
   que premia filmes bem ranqueados em *ambas* as listas.
4. **Re-ranking final** — o score RRF recebe um leve prior de qualidade
   (`vote_average`). No **modo descoberta**, os títulos mais populares do pool
   recebem uma penalidade suave para revelar escolhas menos óbvias.

> **Equipe/elenco:** o banco reduzido guarda só `movie` e `keyword` (sem
> `person`/`company`). Para captar a assinatura de diretor/elenco, inclua essas
> informações no **texto de embedding do filme** na ingestão (linhas `Director:`
> / `Cast:`) — o `ingest_reference.py` já tem os campos. Assim o sinal de equipe
> entra direto no vetor do filme, sem precisar de tabelas extras.

## Rodando localmente

Pré-requisitos: Python 3.11+, Node 20+, e o `.env` na raiz (veja `.env.example`).

### API

```bash
cd api
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Windows (Linux/mac: .venv/bin/pip)
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

- Docs interativas: http://localhost:8000/docs
- Health check: http://localhost:8000/api/health
- Testes do pipeline: `.venv/Scripts/python tests/test_retrieval.py`

### Frontend

```bash
cd frontend
npm install
npm run dev   # http://localhost:3000
```

## Variáveis de ambiente

| Variável | Onde | Obrigatória | Descrição |
|---|---|---|---|
| `SUPABASE_URL` | API | ✅ | URL do projeto ou do dashboard (a API deriva o REST endpoint) |
| `SUPABASE_API_SECRET_KEY` | API | ✅ | Chave secreta (server-side) |
| `EMBEDDING_PROVIDER` | API | ✅ | `hf` \| `deepinfra` \| `cloudflare` \| `mock` |
| `HF_TOKEN` | API | p/ `hf` | Token do Hugging Face Inference API |
| `DEEPINFRA_API_KEY` | API | p/ `deepinfra` | Chave DeepInfra |
| `CF_ACCOUNT_ID` + `CF_API_TOKEN` | API | p/ `cloudflare` | Workers AI |
| `TMDB_API_KEY` | API | opcional | Pôsteres + sinopses (pt-BR) nos cards |
| `FRONTEND_ORIGIN` | API | opcional | Restringe CORS (padrão `*`) |
| `NEXT_PUBLIC_API_URL` | Frontend | ✅ | URL pública da API |

> O provider `mock` gera vetores determinísticos — útil para validar a
> aplicação de ponta a ponta sem token de inferência, mas **não** produz
> recomendações reais.

## Deploy na Vercel (dois projetos)

1. **API** — importe o repositório e configure **Root Directory = `api`**.
   O `api/vercel.json` já roteia tudo para o entrypoint `index.py`
   (runtime Python). Configure as variáveis de ambiente da API.
2. **Frontend** — importe o mesmo repositório com **Root Directory =
   `frontend`** (preset Next.js detectado automaticamente). Configure
   `NEXT_PUBLIC_API_URL` com a URL do deploy da API.
3. Opcional: em `FRONTEND_ORIGIN` (projeto da API), coloque a URL do frontend
   para restringir o CORS.

## Banco de dados

Banco reduzido (Free-tier): contém apenas as 2 tabelas (`movie`, `keyword`) e
as 2 funções RPC (`match_movie`, `match_keyword`). `person`/`company` não ficam
no Supabase — dados relacionais mais ricos permanecem em parquet local. DDL de
referência em [supabase/schema.sql](supabase/schema.sql). Ao carregar os dados,
siga as convenções de texto de embedding descritas em
[supabase/supabase-vector-schema.md](supabase/supabase-vector-schema.md) e use o
**mesmo modelo (BGE-M3) e normalização** nas duas pontas. Os índices vetoriais
HNSW são opcionais no Free-tier (sem eles, o `match_*` usa scan sequencial).

**Dica para recomendações menos óbvias:** inclua diretor, roteirista e elenco
principal no texto de embedding do filme (ex.: `Director: ...` / `Cast: ...`).
O pipeline passa a capturar a "assinatura" da equipe sem nenhuma mudança na API.

## Estado atual (MVP)

- ✅ Estrutura completa frontend + API + retrieval em produção-ready
- ✅ Pipeline com expansão de keywords, RRF e modo descoberta (testado)
- ⏳ Banco vazio — aguardando carga dos dados
- ⏳ Token de inferência (HF/DeepInfra/Cloudflare) para embeddings reais
- ⏳ `TMDB_API_KEY` para pôsteres (opcional, mas melhora muito a UI)
