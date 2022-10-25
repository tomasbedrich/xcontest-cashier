FROM python:3.10.5-slim

RUN pip3 install --no-cache-dir pipenv
COPY Pipfile Pipfile.lock /app/
RUN cd /app && pipenv install --deploy --system
RUN pip3 uninstall -y pipenv

COPY cashier /app

HEALTHCHECK CMD test "$(find /tmp/liveness -mmin -1)" || exit 1

ENV PYTHONPATH "/app"

STOPSIGNAL SIGINT

# not using entrypoint because of PyCharm debugger
CMD ["python3", "-m", "cashier.telegram_bot"]
