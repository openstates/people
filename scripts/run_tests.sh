#!/bin/bash

PYTHONPATH="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"
pytest --ds=tests.django_test_settings
