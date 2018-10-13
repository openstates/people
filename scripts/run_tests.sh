#!/bin/bash

PYTHONPATH="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"
pytest --cov scripts --cov-report html --ds=tests.django_test_settings
