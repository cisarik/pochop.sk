"""
Django settings for astro_project project.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env
load_dotenv(BASE_DIR / '.env')

# Security
SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-2e)kl%n+s&*r1()2j1y1%+d32q8tzlh_jv#s8b@jv*5ys$n1%4'
)

# AI providers (model-agnostic runtime)
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-3.1-pro-preview')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4.1-mini')
DEFAULT_PROVIDER = os.environ.get('DEFAULT_PROVIDER', 'gemini')
DEFAULT_MODEL = os.environ.get('DEFAULT_MODEL', GEMINI_MODEL)
AI_MAX_CALLS_DAILY = int(
    os.environ.get('AI_MAX_CALLS_DAILY', os.environ.get('GEMINI_MAX_CALLS_DAILY', '500'))
)
AI_MODEL_SWITCH_EAGER_USERS_REFRESH = os.environ.get(
    'AI_MODEL_SWITCH_EAGER_USERS_REFRESH',
    'False',
).lower() in ('true', '1', 'yes')
AI_RESPONSE_CACHE_ENABLED = os.environ.get('AI_RESPONSE_CACHE_ENABLED', 'True').lower() in ('true', '1', 'yes')
AI_RESPONSE_CACHE_TTL_SECONDS = int(os.environ.get('AI_RESPONSE_CACHE_TTL_SECONDS', '86400'))

# E-mail (password reset)
EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend',
)
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '25'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'False').lower() in ('true', '1', 'yes')
EMAIL_USE_SSL = os.environ.get('EMAIL_USE_SSL', 'False').lower() in ('true', '1', 'yes')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@pochop.sk')
MOMENT_REPORT_ADMIN_EMAILS = os.environ.get('MOMENT_REPORT_ADMIN_EMAILS', '')
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', '')

# PII encryption (birth_place)
PII_ENCRYPTION_PASSWORD = os.environ.get('PII_ENCRYPTION_PASSWORD', SECRET_KEY)

DEBUG = os.environ.get('DEBUG', 'True').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '*').split(',')

CSRF_TRUSTED_ORIGINS = os.environ.get(
    'CSRF_TRUSTED_ORIGINS', ''
).split(',') if os.environ.get('CSRF_TRUSTED_ORIGINS') else []

# Production security (active when DEBUG=False)
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'transits',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'transits.middleware.GeminiQuotaMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'astro_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'transits.context_processors.ai_runtime_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'astro_project.wsgi.application'


# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# Internationalization
LANGUAGE_CODE = 'sk'
TIME_ZONE = 'Europe/Bratislava'
USE_I18N = True
USE_TZ = True


# Static files
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
IS_TEST = 'test' in sys.argv

if DEBUG or IS_TEST:
    STORAGES = {
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }
else:
    STORAGES = {
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
        },
    }

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Auth
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/timeline/'
LOGOUT_REDIRECT_URL = '/'
