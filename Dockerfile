# Genomera API (production). Build: docker build -t genomera-api .
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 \
    GENOMERA_ENV=production GENOMERA_LOG_FORMAT=json DATABASE_URL=sqlite:////data/genomera.sqlite3
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt psutil
COPY backend ./backend
COPY ml_services ./ml_services
COPY scripts ./scripts
COPY data/seeds ./data/seeds
COPY models ./models
# The knowledge graph is generated from the committed seeds (data/processed is not versioned).
RUN python -m ml_services.etl.kg_build
RUN useradd --system --uid 10001 genomera && mkdir /data && chown genomera /data
USER genomera
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/readiness', timeout=4).status == 200 else 1)"
# --no-access-log: the application writes its own structured access log (route templates only, no query strings).
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--proxy-headers"]
