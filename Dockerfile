FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "export WEBHOOK_SECRET=$(printf '%s' \"${WEBHOOK_SECRET:-lastkeeper}\" | sha256sum | cut -d' ' -f1); exec uvicorn main:web --host 0.0.0.0 --port ${PORT:-8000}"]
