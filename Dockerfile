FROM python:3.8

WORKDIR /app

ENV PYTHONPATH "/app"

RUN pip3 install pipenv
COPY Pipfile Pipfile.lock ./
RUN pipenv install --deploy --system

COPY ./cashier cashier

CMD ["python3", "/app/cashier/main.py"]
