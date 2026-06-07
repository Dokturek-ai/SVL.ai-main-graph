# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Canonical guidance

**[AGENTS.md](./AGENTS.md) is the authoritative reference** for this repository — read it first. It covers the full module layout, the `LightRAG` mixin composition, the pipeline concurrency contract, query modes, dev/test/lint commands, and code style. Do not duplicate that content here; extend it.

**[.clinerules/01-basic.md](./.clinerules/01-basic.md)** documents hard-won runtime pitfalls specific to this deployment (embedding base64-vs-array compatibility in `lightrag/llm/openai.py`, await-before-method async ordering, deserialization field filtering, sorted relationship lock keys, event-loop shutdown handling). Consult it before touching storage backends, LLM bindings, or concurrency code.

## Fork context

- **This is a fork** of `HKUDS/LightRAG` for the Dokturek.ai project. `origin` = `petrsovadina/dokturek-LightRAG`, `upstream` = `HKUDS/LightRAG`.
- **Active development branch is `hermes`** (not `main`). `main` tracks upstream.
- When creating PRs intended to land upstream, target `HKUDS/LightRAG` — see AGENTS.md "Commit and Pull Request Guidance". Fork-internal changes stay on `origin`.

## Deployment

- **Railway** is the deployment target (the `railway` MCP plugin is configured; `Dockerfile` uses `--mount=type=cache` build cache directives — each cache mount requires a unique `id=`, per recent fixes).
- `docker-compose.final.yml` is **generated output** assembled from `scripts/setup/templates/*.yml` by the setup wizard. Do not hand-edit it as a source of truth; regenerate via `make env-base-rewrite` / `make env-storage-rewrite`. It mounts `./data/{rag_storage,inputs,prompts}` and `./.env` into the container on port `9621`.
- `.env` is present and configured (host-usable). Keep container-only hostnames and staged SSL paths in the wizard-managed compose layer, not in `.env`.

## Runtime configuration (current)

Per `.clinerules`: Gemini 2.5 Flash + `BAAI/bge-m3` embeddings via custom OpenAI-compatible endpoints, default file-persistence storage (`JsonKVStorage` / `NetworkXStorage` / `NanoVectorDBStorage`), workspace `space1` for data isolation, JWT auth.

> **Pitfall:** switching the embedding model requires clearing the data directory — existing vectors will not match the new model's space (keep `kv_store_llm_response_cache.json` if you want to preserve LLM cache).
