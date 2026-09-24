from .base import *
from decouple import config

SECRET_KEY = config('SECRET_KEY')

DEBUG = True

ALLOWED_HOSTS = ['*']

CSRF_TRUSTED_ORIGINS = [
    'https://*.loca.lt',
    'https://*.ngrok-free.app',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='esm'),
        'USER': config('DB_USER', default='postgres'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
    }
}

INTERNAL_IPS = ['127.0.0.1']
