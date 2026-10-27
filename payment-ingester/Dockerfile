# payment-ingester (FastAPI, served by Gunicorn with Uvicorn workers). On Cloud Run, PORT is set
# by the platform (gunicorn.conf.py reads it).
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8001

CMD ["gunicorn", "-c", "gunicorn.conf.py", "app.routes:create_app()"]
