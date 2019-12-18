#!/usr/bin/env python
import os
# import glob
# from functools import lru_cache
import django
from django import conf
from django.db import transaction
import click
# from utils import (
#     get_data_dir,
#     get_jurisdiction_id,
#     get_all_abbreviations,
#     get_districts,
#     get_settings,
# )

def init_django():  # pragma: no cover
    conf.settings.configure(
        conf.global_settings,
        SECRET_KEY="not-important",
        DEBUG=False,
        INSTALLED_APPS=(
            "django.contrib.contenttypes",
            "opencivicdata.core.apps.BaseConfig",
            "opencivicdata.legislative.apps.BaseConfig",
        ),
        DATABASES={
            "default": {
                "ENGINE": "django.contrib.gis.db.backends.postgis",
                "NAME": "openstates",
                "USER": "openstates",
                "PASSWORD": "openstates",
                "URL": "postgres://openstates:openstates@db/openstatesorg",
            }
        },
        MIDDLEWARE_CLASSES=(),
    )
    django.setup()

@click.command()
@click.argument("session", nargs=-1)
def archive_leg_to_csv(session):
    session = session[0]
    init_django()
    from opencivicdata.legislative.models import BillSponsorship
    print("Session:", session)


if __name__ == "__main__":
    archive_leg_to_csv()
