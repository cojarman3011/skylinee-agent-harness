FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 skylinee \
    && mkdir -p /data /workspace \
    && chown -R skylinee:skylinee /data /workspace
USER skylinee

EXPOSE 8000
CMD ["uvicorn", "skylinee_harness.main:app", "--host", "0.0.0.0", "--port", "8000"]

