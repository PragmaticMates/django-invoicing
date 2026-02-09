"""
Minimal Django settings for testing.
"""
from decimal import Decimal

DEBUG = True
SECRET_KEY = 'test-secret-key-for-testing-only'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.admin',
    'django_countries',
    'djmoney',
    'model_utils',
    'invoicing',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

ROOT_URLCONF = 'invoicing.tests.test_urls'

USE_TZ = True
TIME_ZONE = 'UTC'
LANGUAGE_CODE = 'en-us'

STATIC_URL = '/static/'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# INVOICING SETTINGS
INVOICING_TAX_RATE = Decimal(20)
INVOICING_COUNTER_PERIOD = 'YEARLY'
INVOICING_NUMBER_START_FROM = 1
INVOICING_NUMBER_FORMAT = "{{ invoice.date_issue|date:'Y' }}/{{ invoice.sequence }}"

INVOICING_SUPPLIER = {
    'name': 'Test Supplier Ltd.',
    'street': 'Test Street 1',
    'city': 'Test City',
    'zip': '12345',
    'country_code': 'SK',
    'registration_id': '123456789',
    'tax_id': '111222333',
    'vat_id': 'SK111222333',
    'bank': {
        'name': 'Test Bank',
        'street': 'Bank Street',
        'city': 'Bank City',
        'zip': '11111',
        'country_code': 'SK',
        'iban': 'SK0000000000000000000028',
        'swift_bic': 'TESTBANK'
    }
}

