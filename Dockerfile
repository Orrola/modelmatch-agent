FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 LITELLM_LOCAL_MODEL_COST_MAP=True PORT=8080 \
    MODELMATCH_OFFLINE=0 UV_PYTHON_DOWNLOADS=never
RUN pip install --no-cache-dir uv==0.12.12
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
COPY app.py context_panel.py ./
COPY orchestration.py modelmatch_agents.py modelmatch_schemas.py recommendation.py vertex_runtime.py modelmatch_web.py offline_model.py ./
COPY tools ./tools
COPY static ./static
COPY examples ./examples
RUN useradd --uid 10001 --create-home appuser
USER appuser
EXPOSE 8080
CMD ["sh", "-c", "exec .venv/bin/uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1 --timeout-keep-alive 5"]
