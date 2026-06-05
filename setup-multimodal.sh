#!/bin/bash

# Multimodal RAG Setup Script
# Automatizuje inicializaci a konfiguraci

set -e

echo "🚀 Multimodal RAG Setup"
echo "======================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check prerequisites
echo -e "${BLUE}[1/6] Checking prerequisites...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ Docker Compose is not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Docker and Docker Compose found${NC}"
echo ""

# Create directories
echo -e "${BLUE}[2/6] Creating directory structure...${NC}"

mkdir -p data/rag_storage data/inputs data/prompts
chmod 777 data/rag_storage data/inputs data/prompts

echo -e "${GREEN}✓ Directories created${NC}"
echo ""

# Copy configuration files
echo -e "${BLUE}[3/6] Setting up configuration files...${NC}"

if [ ! -f "docker-compose.yml" ]; then
    if [ -f "docker-compose.multimodal.yml" ]; then
        cp docker-compose.multimodal.yml docker-compose.yml
        echo -e "${GREEN}✓ Docker Compose configured${NC}"
    else
        echo -e "${RED}❌ docker-compose.multimodal.yml not found${NC}"
        exit 1
    fi
fi

if [ ! -f ".env" ]; then
    if [ -f ".env.multimodal" ]; then
        cp .env.multimodal .env
        echo -e "${GREEN}✓ Environment file created${NC}"
    else
        echo -e "${RED}❌ .env.multimodal not found${NC}"
        exit 1
    fi
fi

echo ""

# Prompt for API keys
echo -e "${BLUE}[4/6] Configuring API keys...${NC}"
echo ""

read -p "Enter OpenAI API Key (for LLM): " openai_key
if [ ! -z "$openai_key" ]; then
    sed -i "s|sk-...your-api-key...|$openai_key|g" .env
    echo -e "${GREEN}✓ OpenAI API key configured${NC}"
fi

read -p "Enter Cohere API Key (for reranking): " cohere_key
if [ ! -z "$cohere_key" ]; then
    sed -i "s|your-cohere-api-key|$cohere_key|g" .env
    echo -e "${GREEN}✓ Cohere API key configured${NC}"
fi

echo ""

# Generate secure passwords
echo -e "${BLUE}[5/6] Generating secure passwords...${NC}"

POSTGRES_PASS=$(openssl rand -base64 32)
NEO4J_PASS=$(openssl rand -base64 32)
MINIO_KEY=$(openssl rand -base64 16)
MINIO_SECRET=$(openssl rand -base64 32)

sed -i "s|POSTGRES_PASSWORD=rag_password|POSTGRES_PASSWORD=$POSTGRES_PASS|g" .env
sed -i "s|NEO4J_PASSWORD=neo4j_password|NEO4J_PASSWORD=$NEO4J_PASS|g" .env
sed -i "s|MINIO_ACCESS_KEY_ID=minioadmin|MINIO_ACCESS_KEY_ID=$MINIO_KEY|g" .env
sed -i "s|MINIO_SECRET_ACCESS_KEY=minioadmin|MINIO_SECRET_ACCESS_KEY=$MINIO_SECRET|g" .env

echo -e "${GREEN}✓ Secure passwords generated${NC}"
echo ""

# Start services
echo -e "${BLUE}[6/6] Starting Docker services...${NC}"
echo ""

docker-compose up -d

echo ""
echo -e "${GREEN}✓ Services started${NC}"
echo ""

# Wait for services to be healthy
echo -e "${YELLOW}Waiting for services to be healthy...${NC}"
echo ""

max_attempts=60
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if docker-compose ps | grep -q "lightrag.*running"; then
        echo -e "${GREEN}✓ LightRAG Server is running${NC}"
        break
    fi
    attempt=$((attempt + 1))
    sleep 2
done

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Multimodal RAG Setup Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""

echo "📊 Service Status:"
docker-compose ps
echo ""

echo "🌐 Access Points:"
echo "  • LightRAG WebUI: http://localhost:9621"
echo "  • MinerU Parser: http://localhost:8000"
echo "  • Docling Parser: http://localhost:5001"
echo "  • Neo4j Browser: http://localhost:7474"
echo ""

echo "📝 Configuration:"
echo "  • Environment file: .env"
echo "  • Docker Compose: docker-compose.yml"
echo "  • Data directory: ./data/"
echo ""

echo "📚 Next Steps:"
echo "  1. Open http://localhost:9621 in your browser"
echo "  2. Upload a PDF with images/tables"
echo "  3. Wait for parsing and indexing"
echo "  4. Query your knowledge base"
echo ""

echo "🔍 Monitoring:"
echo "  • View logs: docker-compose logs -f lightrag"
echo "  • Check health: docker-compose ps"
echo "  • Stop services: docker-compose down"
echo ""

echo "📖 Documentation:"
echo "  • Setup Guide: MULTIMODAL_SETUP.md"
echo "  • LightRAG Docs: https://github.com/HKUDS/LightRAG"
echo ""

echo -e "${YELLOW}⚠️  Important:${NC}"
echo "  • Save your API keys securely"
echo "  • Backup your .env file"
echo "  • Monitor disk space (100GB+ recommended)"
echo ""

