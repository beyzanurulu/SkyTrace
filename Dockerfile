# SkyTrace app image (CLI + web UI). The models run in a separate Ollama
# container, see docker-compose.yml. Offline mode is on by default.
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# dependencies first (cached while only the code changes)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-default-groups --extra web --no-install-project
COPY src ./src
COPY docker ./docker
RUN uv sync --frozen --no-default-groups --extra web

ENV PATH="/app/.venv/bin:$PATH" SKYTRACE_MODE=offline
EXPOSE 8000
CMD ["skytrace", "serve", "--host", "0.0.0.0"]
