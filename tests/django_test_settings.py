import os

# django settings for tests
SECRET_KEY = "test"
INSTALLED_APPS = (
    "django.contrib.contenttypes",
    "openstates.data",
)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "testdb",
        "USER": os.environ.get("PGUSER", "openstates"),
        "PASSWORD": os.environ.get("PGPASS", "openstates"),
        "HOST": os.environ.get("PGHOST", "localhost"),
        "PORT": os.environ.get("PGPORT", 5432),
    }
}
MIDDLEWARE_CLASSES = ()
