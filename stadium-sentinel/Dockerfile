FROM python:3.11-slim AS builder
WORKDIR /build
COPY pyproject.toml ./
COPY app/ ./app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -e .

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY app/ ./app/
COPY alembic.ini ./
COPY migrations/ ./migrations/
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
