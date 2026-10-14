FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev
COPY configs ./configs
COPY data/corpus.jsonl data/gold.jsonl data/manifest.json data/NOTICE.md ./data/
RUN useradd --create-home --uid 10001 appuser && mkdir -p /app/runtime && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "groundwork", "serve", "--host", "0.0.0.0", "--port", "8000"]
