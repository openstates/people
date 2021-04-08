FROM python:3.9

RUN apt update && apt install -y libgdal-dev
RUN pip install poetry

ADD . /opt/people
WORKDIR /opt/people
RUN poetry install

ENTRYPOINT ["poetry", "run"]
