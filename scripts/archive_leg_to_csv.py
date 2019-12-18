#!/usr/bin/env python
import os
# import glob
# from functools import lru_cache
import django
from django import conf
from django.db import transaction
import click
from utils import (
    get_data_dir,
    get_jurisdiction_id,
    get_all_abbreviations,
    get_districts,
    get_settings,
)

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
                "NAME": "openstatesorg",
                "USER": "openstates",
                "PASSWORD": "openstates",
                "HOST": "localhost",
                # "URL": "postgres://openstates:openstates@db/openstatesorg",
                "PORT": "5405"
            }
        },
        MIDDLEWARE_CLASSES=(),
    )
    django.setup()

@click.command()
@click.argument("session", nargs=-1)
def archive_leg_to_csv(session):
    session=session[0]
    abbr = "nc"

    init_django()
    abbreviations = get_all_abbreviations()
    settings = get_settings()
    jurisdiction_id = get_jurisdiction_id(abbr)
    print("jurisdiction_id:", jurisdiction_id, "session:", session)
    print("\n\n")

    from opencivicdata.legislative.models import Bill
    bills = Bill.objects.filter(
        legislative_session__identifier=session)
    print("Number of votes give session:", len(bills))


if __name__ == "__main__":
    archive_leg_to_csv()
