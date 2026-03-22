# Dockerfile para PocketOption Trading API
# Multi-stage build para otimização

FROM python:3.13-slim as builder

# Instalar dependências de build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Criar diretório de trabalho
WORKDIR /app

# Copiar arquivos de dependências
COPY requirements.txt pyproject.toml ./

# Instalar dependências Python
RUN pip install --no-cache-dir --user setuptools wheel -r requirements.txt

# Stage final
FROM python:3.13-slim as production

# Evitar prompts do apt
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONFAULTHANDLER=1

# Criar usuário não-root para segurança
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Instalar apenas dependências runtime necessárias
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Criar diretório de trabalho
WORKDIR /app

# Copiar dependências instaladas do stage builder
COPY --from=builder /root/.local /home/appuser/.local

# Instalar setuptools no stage final para fornecer distutils (necessário para aioredis)
RUN pip install --no-cache-dir --user setuptools

# Copiar código da aplicação
COPY --chown=appuser:appuser . .

# Criar diretórios necessários
RUN mkdir -p logs logs/ws && chown -R appuser:appuser logs

# Mudar para usuário não-root
USER appuser

# Adicionar .local ao PATH
ENV PATH=/home/appuser/.local/bin:$PATH

# Expor porta da API
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Comando para iniciar a aplicação
CMD ["python", "main.py"]
