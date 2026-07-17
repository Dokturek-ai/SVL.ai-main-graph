# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Canonical guidance

**[AGENTS.md](./AGENTS.md) is the authoritative reference** for this repository — read it first. It covers the full module layout, the `LightRAG` mixin composition, the pipeline concurrency contract, query modes, dev/test/lint commands, and code style. Do not duplicate that content here; extend it.

**[.clinerules/01-basic.md](./.clinerules/01-basic.md)** documents hard-won runtime pitfalls specific to this deployment (embedding base64-vs-array compatibility in `lightrag/llm/openai.py`, await-before-method async ordering, deserialization field filtering, sorted relationship lock keys, event-loop shutdown handling). Consult it before touching storage backends, LLM bindings, or concurrency code.

## Fork context

- **This is a fork** of `HKUDS/LightRAG` for the Dokturek.ai project. `origin` = `petrsovadina/dokturek-LightRAG`, `upstream` = `HKUDS/LightRAG`.
- **Active development branch is `hermes`** (not `main`). `main` tracks upstream.
- When creating PRs intended to land upstream, target `HKUDS/LightRAG` — see AGENTS.md "Commit and Pull Request Guidance". Fork-internal changes stay on `origin`.

## Deployment & configuration

- **Railway** is the deployment target. Project **SVL.ai**, environment **production**. Build uses the **RAILPACK** builder (the repo `Dockerfile` is NOT used by Railway); service start command is `lightrag-server`.
- **Production config source of truth = Railway environment variables** (edit directly via Railway dashboard / `railway` CLI). Do NOT reintroduce the `make env-*` wizard flow — it is inherited from upstream and intentionally unused here. `scripts/setup/`, `docker-compose.final.yml`, and the wizard Make targets remain in the repo as legacy but are not the config path.
- `env.example` is a **reference catalog** of every available variable (keep it accurate); local `.env` (gitignored) is for local dev only.
- Railway services (production): `dokturek-LightRAG` (API), `MinerU` (parser), `pgVector-Railway` (Postgres+pgvector), `Neo4j Graph Database (Metal-Ready)`. Services talk over Railway private DNS (`*.railway.internal`); DB TCP proxies are removed (internal-only).

## Runtime configuration (current production)

- **LLM:** OpenAI `gpt-5-mini` (`LLM_BINDING=openai`).
- **Embedding:** Jina `jina-embeddings-v5-text-small`, dim 1024. `EMBEDDING_BINDING_HOST` must be the full `https://api.jina.ai/v1/embeddings` (the jina client POSTs the host as-is — a bare `/v1` returns 404).
- **Rerank:** Cohere `rerank-v4.0-pro` (`RERANK_BINDING=cohere`), with `MIN_RERANK_SCORE=0.4` score floor (drops off-topic citations; `-fast` mis-scores Czech lexical collisions).
- **Storage:** `PGKVStorage` / `PGVectorStorage` / `PGDocStatusStorage` (pgVector-Railway) + `Neo4JStorage` (Neo4j service). Not file-based.
- **Parser:** MinerU local mode, `MINERU_LOCAL_BACKEND=pipeline` — the MinerU service is CPU-only (no GPU); `hybrid-auto-engine` crashes on CPU under load (`libgomp: Thread creation failed`).
- **Language:** `SUMMARY_LANGUAGE=Czech`, `MINERU_LANGUAGE=cs` (Czech). Auth: `LIGHTRAG_API_KEY` set.

> **Pitfall:** switching the embedding model requires clearing/reingesting the vector data — existing vectors will not match the new model's space.
