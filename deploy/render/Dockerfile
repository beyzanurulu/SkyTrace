# Public demo on Render (free web service, 512 MB). Built from this repository,
# so the sample flights and their recorded answers are included. The secret
# GEMINI_API_KEY is set in Render's dashboard; Render sets PORT.
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md LICENSE NOTICE ./
RUN uv sync --frozen --no-default-groups --extra web --no-install-project
COPY src ./src
RUN uv sync --frozen --no-default-groups --extra web
COPY samples ./samples
COPY deploy/render/config.yaml ./config.yaml

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 10000
CMD ["sh", "-c", "exec skytrace serve -c config.yaml --host 0.0.0.0 --port ${PORT:-10000}"]
