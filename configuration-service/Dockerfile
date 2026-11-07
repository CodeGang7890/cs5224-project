# configuration-service (Django) for local development. Run it with the repo's docker-compose.yml,
# which provides PostgreSQL; docker-entrypoint.sh resets the database and loads the fixtures.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x docker-entrypoint.sh
# The admin's CSS / JS, into STATIC_ROOT, for WhiteNoise (served even with DEBUG off).
RUN python manage.py collectstatic --noinput

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
