# django settings for tests
SECRET_KEY = 'test'
INSTALLED_APPS = ('django.contrib.contenttypes',
                  'opencivicdata.core.apps.BaseConfig',
                  'opencivicdata.legislative.apps.BaseConfig')
DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': 'test',
        'USER': 'test',
        'PASSWORD': 'test',
        'HOST': 'localhost',
    }
}
MIDDLEWARE_CLASSES = ()
