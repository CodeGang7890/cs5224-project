# mock_whatsapp (FastAPI). Run it with the repo's docker-compose.yml, which points it at
# messaging-ingester and configuration-service at it. PORT can be set by the platform (e.g. Cloud Run).
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 9000

CMD ["sh", "-c", "exec uvicorn app:create_app --factory --host 0.0.0.0 --port ${PORT:-9000}"]
