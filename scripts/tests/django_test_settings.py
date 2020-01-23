import os

# django settings for tests
SECRET_KEY = "test"
INSTALLED_APPS = (
    "django.contrib.contenttypes",
    "opencivicdata.core.apps.BaseConfig",
    "opencivicdata.legislative.apps.BaseConfig",
)
DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": "testdb",
        "USER": os.environ.get("PGUSER", "openstates"),
        "PASSWORD": os.environ.get("PGPASS", "openstates"),
        "HOST": os.environ.get("PGHOST", "localhost"),
    }
}
MIDDLEWARE_CLASSES = ()
