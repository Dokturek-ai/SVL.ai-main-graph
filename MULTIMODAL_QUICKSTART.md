# ⚡ Multimodal RAG - Quick Start (5 minut)

## 🎯 Cíl
Spustit kompletní multimodální RAG systém s podporou obrázků, tabulek a formulí.

---

## 📋 Checklist

- [ ] Docker & Docker Compose nainstalované
- [ ] API klíče připravené (OpenAI, Cohere)
- [ ] 16GB+ RAM dostupné
- [ ] 100GB+ disk dostupný

---

## 🚀 Instalace (5 minut)

### 1. Klonuj a Přejdi do Adresáře

```bash
git clone https://github.com/petrsovadina/dokturek-LightRAG.git
cd dokturek-LightRAG
```

### 2. Spusť Setup Script

```bash
chmod +x setup-multimodal.sh
./setup-multimodal.sh
```

**Script automaticky:**
- ✅ Vytvoří adresářovou strukturu
- ✅ Zkopíruje konfigurační soubory
- ✅ Vyzve tě na API klíče
- ✅ Vygeneruje bezpečná hesla
- ✅ Spustí všechny Docker služby

### 3. Čekej na Inicializaci

```bash
# Sleduj logy
docker-compose logs -f lightrag

# Čekej na:
# "Uvicorn running on http://0.0.0.0:9621"
```

### 4. Otevři WebUI

```
http://localhost:9621
```

---

## 📤 Nahraj Testovací Dokument

1. Klikni na **"Upload Document"**
2. Vyber PDF s obrázky/tabulkami
3. Čekej na parsování (2-5 minut)
4. Vidíš progress v **"Pipeline Status"**

---

## 🔍 Testuj RAG Query

1. Klikni na **"Query"**
2. Zadej otázku (např. "What are the main findings in the tables?")
3. Systém vrátí odpověď s citacemi

---

## 🛑 Zastavení

```bash
# Zastavit všechny služby
docker-compose down

# Zastavit a smazat data
docker-compose down -v
```

---

## ⚙️ Konfigurace (Pokud Potřebuješ Změnit)

### Změnit LLM Model

```bash
# V .env
LLM_BINDING=openai
LLM_MODEL=gpt-4-turbo  # Změň na gpt-4-mini, gpt-3.5-turbo, atd.
```

### Změnit Embedding Model

```bash
# V .env
EMBEDDING_BINDING=openai
EMBEDDING_MODEL=text-embedding-3-large  # Nebo text-embedding-3-small
```

### Vypnout Reranking

```bash
# V .env
RERANK_BINDING=null
```

### Zvýšit Paralelní Zpracování

```bash
# V .env
MAX_PARALLEL_PARSE_MINERU=4
MAX_PARALLEL_PARSE_DOCLING=4
MAX_PARALLEL_ANALYZE=8
```

---

## 🔧 Troubleshooting

### Problem: "Connection refused"

```bash
# Zkontroluj, že všechny služby běží
docker-compose ps

# Restartuj všechno
docker-compose restart
```

### Problem: "Out of memory"

```bash
# Zvyš Docker memory limit
# V Docker Desktop: Settings → Resources → Memory: 32GB+
```

### Problem: "Parser timeout"

```bash
# V .env zvyš timeout
DOCLING_MAX_POLLS=300
MINERU_MAX_POLLS=180

# Restartuj
docker-compose restart lightrag
```

### Problem: "Disk full"

```bash
# Zkontroluj disk
df -h

# Vyčisti Docker
docker system prune -a
```

---

## 📊 Monitoring

```bash
# Logy
docker-compose logs -f lightrag

# Status
docker-compose ps

# Resource usage
docker stats

# Database size
docker-compose exec postgres psql -U rag -d rag -c "SELECT pg_size_pretty(pg_database_size('rag'));"
```

---

## 🌐 Nasazení na Railway

### 1. Pushni do GitHub

```bash
git add .
git commit -m "feat: multimodal RAG setup"
git push origin main
```

### 2. Na Railway

1. Jdi na https://railway.com
2. Vytvoř nový projekt
3. Připoj GitHub repo
4. Přidej services:
   - LightRAG (z Dockerfile)
   - PostgreSQL (template)
   - Neo4j (Docker image)
   - Milvus (Docker image)
   - MinerU (Docker image)
   - Docling (Docker image)

5. Nastav environment variables (viz `.env`)
6. Deploy!

---

## 📚 Další Informace

- **Detailní Setup**: `MULTIMODAL_SETUP.md`
- **LightRAG Docs**: https://github.com/HKUDS/LightRAG
- **MinerU Docs**: https://github.com/opendatalab/MinerU
- **Docling Docs**: https://github.com/DS4SD/docling-serve

---

## ✅ Hotovo!

Máš funkční multimodální RAG systém! 🎉

**Příští kroky:**
1. Nahraj své dokumenty
2. Testuj queries
3. Optimalizuj konfiguraci
4. Nasaď na produkci

---

**Potřebuješ pomoc?** Otevři issue na GitHub!

