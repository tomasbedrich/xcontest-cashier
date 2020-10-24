FROM python:3.9

RUN pip3 install pipenv
COPY Pipfile Pipfile.lock /app/
RUN cd /app && pipenv install --deploy --system

COPY cashier /app

HEALTHCHECK CMD test "$(find /tmp/liveness -mtime -30s)" || exit 1

ENV PYTHONPATH "/app"

STOPSIGNAL SIGINT

# not using entrypoint because of PyCharm debugger
CMD ["python3", "-m", "cashier.telegram_bot"]
