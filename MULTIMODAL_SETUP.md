# 🚀 Multimodal RAG Setup Guide

Kompletní návod pro nasazení multimodálního RAG systému s podporou obrázků, tabulek a formulí.

## 📋 Obsah

1. [Architektura](#architektura)
2. [Předpoklady](#předpoklady)
3. [Instalace](#instalace)
4. [Konfigurace](#konfigurace)
5. [Spuštění](#spuštění)
6. [Nasazení na Railway](#nasazení-na-railway)
7. [Troubleshooting](#troubleshooting)

---

## 🏗️ Architektura

```
┌─────────────────────────────────────────────────────────────┐
│                    Railway (Cloud)                          │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         LightRAG Server (WebUI + API)                │  │
│  │  - Document Management                              │  │
│  │  - Knowledge Graph Visualization                    │  │
│  │  - RAG Query Interface                              │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ↕ (HTTP/TCP)
┌─────────────────────────────────────────────────────────────┐
│              Docker Compose (Local/VPS)                     │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         Document Parsers (CPU-Only)                 │  │
│  │  ├─ MinerU (PDF/Office/Images)                      │  │
│  │  └─ Docling (Fallback + Formula Recognition)        │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         Storage Layer                               │  │
│  │  ├─ PostgreSQL (Metadata + Embeddings)              │  │
│  │  ├─ Neo4j (Knowledge Graph)                         │  │
│  │  ├─ Milvus (Vector Database)                        │  │
│  │  └─ Redis (Cache)                                   │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         External APIs (Cloud)                       │  │
│  │  ├─ LLM (OpenAI, Anthropic, etc.)                   │  │
│  │  ├─ Embedding (OpenAI, Cohere, etc.)                │  │
│  │  ├─ VLM (GPT-4 Vision, Claude, etc.)                │  │
│  │  └─ Reranking (Cohere)                              │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## ✅ Předpoklady

### Hardware
- **CPU**: 4+ cores (8+ recommended)
- **RAM**: 16GB minimum (32GB recommended)
- **Disk**: 100GB+ (SSD recommended)
- **GPU**: Optional (CPU-only mode supported)

### Software
- Docker & Docker Compose (v2.0+)
- Git
- curl/wget

### API Keys (Cloud Services)
- **LLM**: OpenAI, Anthropic, or similar
- **Embedding**: OpenAI, Cohere, or similar
- **VLM**: GPT-4 Vision, Claude, or similar
- **Reranking**: Cohere API key

---

## 📦 Instalace

### 1. Klonuj Repository

```bash
git clone https://github.com/petrsovadina/dokturek-LightRAG.git
cd dokturek-LightRAG
```

### 2. Vytvoř Adresářovou Strukturu

```bash
mkdir -p data/rag_storage data/inputs data/prompts
chmod 777 data/rag_storage data/inputs data/prompts
```

### 3. Zkopíruj Konfigurační Soubory

```bash
# Zkopíruj Docker Compose pro multimodální setup
cp docker-compose.multimodal.yml docker-compose.yml

# Zkopíruj env konfiguraci
cp .env.multimodal .env
```

---

## ⚙️ Konfigurace

### 1. Nastav API Klíče v `.env`

```bash
# LLM Configuration
LLM_BINDING=openai
LLM_BINDING_API_KEY=sk-...your-openai-key...
LLM_MODEL=gpt-4-turbo

# Embedding Configuration
EMBEDDING_BINDING=openai
EMBEDDING_BINDING_API_KEY=sk-...your-openai-key...
EMBEDDING_MODEL=text-embedding-3-large

# VLM Configuration (for image/table analysis)
VLM_LLM_MODEL=gpt-4-vision
VLM_LLM_BINDING_API_KEY=sk-...your-openai-key...

# Reranking Configuration
RERANK_BINDING_API_KEY=your-cohere-api-key
```

### 2. Nastav Database Hesla

```bash
# PostgreSQL
POSTGRES_PASSWORD=your-secure-password

# Neo4j
NEO4J_PASSWORD=your-secure-password

# Minio
MINIO_ACCESS_KEY_ID=your-access-key
MINIO_SECRET_ACCESS_KEY=your-secret-key
```

### 3. Ověř Parser Konfiguraci

```bash
# Zkontroluj LIGHTRAG_PARSER v .env
LIGHTRAG_PARSER=*:native-iteP,*:mineru-iteP,*:docling-iteP,*:legacy-R

# Vysvětlení:
# i = image analysis (VLM)
# t = table analysis (VLM)
# e = equation analysis (VLM)
# P = paragraph semantic chunking
# R = recursive chunking (fallback)
```

---

## 🚀 Spuštění

### 1. Spusť Docker Compose

```bash
# Spusť všechny služby
docker-compose up -d

# Ověř, že všechny služby běží
docker-compose ps

# Měl bys vidět:
# lightrag-server    running
# mineru-parser      running
# docling-parser     running
# postgres-db        running
# neo4j-kg           running
# milvus-vdb         running
# redis-cache        running
```

### 2. Čekej na Inicializaci

```bash
# Sleduj logy
docker-compose logs -f lightrag

# Čekej na zprávu:
# "Uvicorn running on http://0.0.0.0:9621"
```

### 3. Ověř Zdraví Služeb

```bash
# LightRAG Server
curl http://localhost:9621/health

# MinerU Parser
curl http://localhost:8000/health

# Docling Parser
curl http://localhost:5001/health

# PostgreSQL
docker-compose exec postgres pg_isready -U rag

# Neo4j
curl http://localhost:7474

# Milvus
curl http://localhost:19530/healthz
```

### 4. Přístup k WebUI

Otevři v prohlížeči:
```
http://localhost:9621
```

---

## 🌐 Nasazení na Railway

### 1. Příprava Repository

```bash
# Pushni změny do GitHub
git add docker-compose.multimodal.yml .env.multimodal MULTIMODAL_SETUP.md
git commit -m "feat: add multimodal RAG setup with MinerU and Docling"
git push origin main
```

### 2. Vytvoř Services na Railway

#### A) LightRAG Server (už máš)
- Repo: `petrsovadina/dokturek-LightRAG`
- Branch: `main`
- Dockerfile: `Dockerfile`

#### B) PostgreSQL
```bash
# Na Railway: Add Service → Database → PostgreSQL
# Jméno: postgres
# Verze: 15+
```

#### C) Neo4j
```bash
# Na Railway: Add Service → Docker Image
# Image: neo4j:5-community
# Jméno: neo4j
```

#### D) Milvus
```bash
# Na Railway: Add Service → Docker Image
# Image: milvusdb/milvus:v2.6.11-cpu
# Jméno: milvus
```

#### E) MinerU Parser
```bash
# Na Railway: Add Service → Docker Image
# Image: opendatalab/mineru:latest-cpu
# Jméno: mineru
# Port: 8000
```

#### F) Docling Parser
```bash
# Na Railway: Add Service → Docker Image
# Image: ghcr.io/docling-project/docling-serve-cpu:main
# Jméno: docling
# Port: 5001
```

### 3. Nastav Environment Variables

Na Railway pro **LightRAG Server**:

```env
# Database
POSTGRES_HOST=postgres.railway.internal
POSTGRES_PORT=5432
POSTGRES_USER=rag
POSTGRES_PASSWORD=<generated>
POSTGRES_DB=rag

NEO4J_URI=neo4j://neo4j.railway.internal:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<set-your-password>

MILVUS_URI=http://milvus.railway.internal:19530

# Parsers
MINERU_LOCAL_ENDPOINT=http://mineru.railway.internal:8000
DOCLING_ENDPOINT=http://docling.railway.internal:5001

# API Keys
LLM_BINDING_API_KEY=sk-...
EMBEDDING_BINDING_API_KEY=sk-...
VLM_LLM_BINDING_API_KEY=sk-...
RERANK_BINDING_API_KEY=...

# Other
WORKING_DIR=/app/data/rag_storage
INPUT_DIR=/app/data/inputs
```

### 4. Přidej Volume pro Persistenci

Na Railway pro **LightRAG Server**:
- Volume: `/app/data` → `lightrag-data` (100GB+)

---

## 🔧 Troubleshooting

### Problem: MinerU Parser se nespustí

```bash
# Zkontroluj logy
docker-compose logs mineru

# Zkontroluj dostupnost portu
docker-compose exec mineru curl http://localhost:8000/health

# Restartuj
docker-compose restart mineru
```

### Problem: Docling Parser timeout

```bash
# Zvyš timeout v .env
DOCLING_MAX_POLLS=300
DOCLING_POLL_INTERVAL_SECONDS=10

# Restartuj
docker-compose restart lightrag
```

### Problem: PostgreSQL connection refused

```bash
# Zkontroluj, že PostgreSQL běží
docker-compose ps postgres

# Zkontroluj heslo v .env
docker-compose logs postgres

# Restartuj
docker-compose restart postgres
```

### Problem: Milvus health check fails

```bash
# Zkontroluj Milvus logy
docker-compose logs milvus

# Zkontroluj Minio (dependency)
docker-compose logs milvus-minio

# Restartuj všechny Milvus komponenty
docker-compose restart milvus-minio milvus-etcd milvus
```

### Problem: Vysoká latence parsování

```bash
# Zvyš paralelní zpracování v .env
MAX_PARALLEL_PARSE_MINERU=4
MAX_PARALLEL_PARSE_DOCLING=4
MAX_PARALLEL_ANALYZE=8

# Restartuj
docker-compose restart lightrag
```

---

## 📊 Monitoring

### Kontrola Zdraví Systému

```bash
# Všechny služby
docker-compose ps

# Logy LightRAG
docker-compose logs -f lightrag --tail=100

# Logy Parserů
docker-compose logs -f mineru --tail=50
docker-compose logs -f docling --tail=50

# Disk usage
docker system df

# Network
docker network ls
docker network inspect lightrag-network
```

### Performance Metrics

```bash
# CPU/Memory usage
docker stats

# Database size
docker-compose exec postgres psql -U rag -d rag -c "SELECT pg_size_pretty(pg_database_size('rag'));"

# Neo4j stats
curl http://localhost:7474/db/neo4j/metrics

# Milvus stats
curl http://localhost:19530/api/v1/stats
```

---

## 🔐 Security Best Practices

1. **Změň Výchozí Hesla**
   ```bash
   POSTGRES_PASSWORD=<strong-password>
   NEO4J_PASSWORD=<strong-password>
   MINIO_ACCESS_KEY_ID=<strong-key>
   MINIO_SECRET_ACCESS_KEY=<strong-secret>
   ```

2. **Zabezpeč API Klíče**
   - Nikdy je necommituj do Git
   - Použij `.env.local` pro lokální vývoj
   - Na Railway použij Secrets

3. **Firewall Rules**
   - Omez přístup k databázím (jen z LightRAG)
   - Omez přístup k Parserům (jen z LightRAG)
   - Veřejný přístup jen na port 9621

4. **Backups**
   ```bash
   # PostgreSQL backup
   docker-compose exec postgres pg_dump -U rag rag > backup.sql

   # Neo4j backup
   docker-compose exec neo4j neo4j-admin database dump neo4j

   # Milvus backup
   # Viz Milvus dokumentace
   ```

---

## 📚 Další Zdroje

- [LightRAG Dokumentace](https://github.com/HKUDS/LightRAG)
- [MinerU GitHub](https://github.com/opendatalab/MinerU)
- [Docling GitHub](https://github.com/DS4SD/docling-serve)
- [Railway Dokumentace](https://docs.railway.com)

---

## ❓ FAQ

**Q: Mohu spustit bez GPU?**
A: Ano! Všechny služby jsou nakonfigurované pro CPU-only mode.

**Q: Jaké jsou minimální požadavky?**
A: 4 CPU cores, 16GB RAM, 100GB disk. Doporučuji 8 cores, 32GB RAM.

**Q: Mohu změnit LLM/Embedding model?**
A: Ano! Systém je agnostický. Změň `LLM_BINDING`, `EMBEDDING_BINDING` v `.env`.

**Q: Jak dlouho trvá parsování dokumentu?**
A: Závisí na velikosti. PDF 10 stran: ~30-60 sekund. Obrázky: +10-20 sekund.

**Q: Mohu spustit bez Cohere reranking?**
A: Ano! Nastav `RERANK_BINDING=null` v `.env`.

**Q: Jak zálohuju data?**
A: Zálohuj PostgreSQL, Neo4j a Milvus databáze. Viz Security section.

---

## 🎯 Příští Kroky

1. ✅ Spusť Docker Compose lokálně
2. ✅ Nahraj testovací dokumenty (PDF s obrázky/tabulkami)
3. ✅ Ověř, že se parsují správně
4. ✅ Testuj RAG queries
5. ✅ Nasaď na Railway
6. ✅ Monitoruj performance

---

**Potřebuješ pomoc?** Otevři issue na GitHub nebo se obrať na komunitu!

