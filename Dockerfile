FROM python:3.9-slim

RUN pip3 install --no-cache-dir pipenv
COPY Pipfile Pipfile.lock /app/
RUN cd /app && pipenv install --deploy --system
RUN pip3 uninstall -y pipenv

COPY cashier /app

HEALTHCHECK CMD test "$(find /tmp/liveness -mtime -30s)" || exit 1

ENV PYTHONPATH "/app"

STOPSIGNAL SIGINT

# not using entrypoint because of PyCharm debugger
CMD ["python3", "-m", "cashier.telegram_bot"]
