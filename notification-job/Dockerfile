# notification-job. The default command runs the job once and exits (e.g. a Cloud Run Job);
# docker-compose runs ./cron.sh instead, which runs it every hour with supercronic.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# supercronic: cron for containers (passes the environment to the job, logs to stdout).
ARG SUPERCRONIC_VERSION=v0.2.33
RUN arch="$(dpkg --print-architecture)" \
    && python -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], '/usr/local/bin/supercronic')" \
        "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${arch}" \
    && chmod +x /usr/local/bin/supercronic

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "run.py"]
