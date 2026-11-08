FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY ctu-chatbot-be/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY ctu-chatbot-be/app ./app
COPY ctu-chatbot-be/alembic ./alembic
COPY ctu-chatbot-be/alembic.ini ./alembic.ini
COPY vector-docs /vector-docs

RUN mkdir -p /app/chroma_db /app/data/documents /app/data/donate \
    && useradd --system --uid 10001 --create-home appuser \
    && chown -R appuser:appuser /app/chroma_db /app/data

USER appuser

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
