"""
Django settings for pjsautolit project.

Generated by 'django-admin startproject' using Django 5.0.7.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.0/ref/settings/
"""

# Build paths inside the project like this: BASE_DIR / 'subdir'.
import os
from pathlib import Path

# ... other settings ...

BASE_DIR = Path(__file__).resolve().parent.parent
print(f"Base direct: {BASE_DIR}")
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'products')],
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

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-ydu@0gbnw*q_q*+^k!&vn!%zcmz(d)%&+%l6&wcsh46!k5c()b'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['ebay-to-web-store-1.onrender.com', '127.0.0.1', 'localhost','0.0.0.0']



# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'products',
]
EBAY_APP_ID = 'YASHWANT-pjauto-PRD-7c6937daa-890b1640'
EBAY_AUTH_TOKEN = "v^1.1#i^1#f^0#r^0#p^3#I^3#t^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"
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'pjsautolit.urls'


WSGI_APPLICATION = 'pjsautolit.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases
import dj_database_url

DATABASES = {
    'default': dj_database_url.config(default="postgresql://products_icpj_user:yoMTBiYQ0GfDCONDTjFbuIgj7ceWwUnD@dpg-cqp4lsij1k6c73dd27ng-a.oregon-postgres.render.com/products_icpj", conn_max_age=1800),
    # 'default': {
    #     'ENGINE': 'django.db.backends.sqlite3',
    #     'NAME': BASE_DIR / 'db.sqlite3',
    # }
}


# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/

STATIC_URL = 'static/'

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
