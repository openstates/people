FROM python:3.7

RUN pip install poetry

ADD . /opt/people
WORKDIR /opt/people
RUN poetry install

ENTRYPOINT ["poetry", "run"]
