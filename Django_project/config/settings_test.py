"""Налаштування для pytest: SQLite у памʼяті та локальний кеш, щоб тести не залежали від Postgres і Redis."""
from .settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# Швидкий хешер — тести створюють багато користувачів
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

STRIPE_SECRET_KEY = 'sk_test_dummy'
STRIPE_WEBHOOK_SECRET = 'whsec_dummy'
STRIPE_CURRENCY = 'uah'

# RequestLogMiddleware друкує кожен запит — у тестах це лише шум
MIDDLEWARE = [m for m in MIDDLEWARE if m != 'books.middleware.RequestLogMiddleware']  # noqa: F405
