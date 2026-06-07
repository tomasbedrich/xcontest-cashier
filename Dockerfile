FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY cashier /app

HEALTHCHECK CMD test "$(find /tmp/liveness -mmin -1)" || exit 1

ENV PYTHONPATH="/app"
ENV PATH="/app/.venv/bin:$PATH"

STOPSIGNAL SIGINT

# not using entrypoint because of PyCharm debugger
CMD ["python3", "-m", "cashier.telegram_bot"]
