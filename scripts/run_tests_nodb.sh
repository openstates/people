#!/bin/bash

ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"
export PYTHONPATH=$PYTHONPATH:$ROOT
poetry run pytest scripts \
    --cov scripts \
    --cov-report html \
    --ignore-glob=*to_database* \
    --ignore-glob=*migrate_people* \
    -vv
