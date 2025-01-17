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



BASE_DIR = Path(__file__).resolve().parent.parent
print(f"Base direct: {BASE_DIR}")
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            os.path.join(BASE_DIR, "products", "pages"),
            os.path.join(BASE_DIR, "products"),
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/
SECURE_CROSS_ORIGIN_OPENER_POLICY='same-origin-allow-popups'
# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-ydu@0gbnw*q_q*+^k!&vn!%zcmz(d)%&+%l6&wcsh46!k5c()b"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = ["*"]


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "products",
    "django_celery_results",
    "django.contrib.sitemaps",
]

EBAY_APP_ID = "PJsAutoL-keyset-PRD-d2986db2a-865af761"
EBAY_AUTH_TOKEN = "v^1.1#i^1#f^0#I^3#p^3#r^0#t^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"
# Fischer
# EBAY_AUTH_TOKEN = "v^1.1#i^1#r^0#f^0#p^1#I^3#t^H4sIAAAAAAAAAOVYa2wUVRTe3W7RAhWNUkl5uAw1as3s3pl9TSfd1d0+6GLZLuxaHkLK7Myd7cA8lrl3aRc0botBjYkK0UIUTTXxh49ofPAwGp6BQvQHYsIPI4L4Q42GCAmSoDHOTJeyrQSQbmIT989mzj333O/7zjn33hlQmFRVv6lt08Vq+y2OwQIoOOx2agqomlT54G0VjtpKGyhxsA8W6grO/oqfGhGnyFl2MURZTUXQ1avIKmItY4jI6SqrcUhCrMopELGYZ5ORhe0s7QZsVtewxmsy4Yo1hwhB8DPQG2jgaSYd5GjDqF4OmdJCRMAneBlOFClvkEmLomCMI5SDMRVhTsUhgga0jwQMSftTlJ/1Miyg3VQALCdcnVBHkqYaLm5AhC20rDVXL4F6baQcQlDHRhAiHIu0JjsiseaWeKrRUxIrXJQhiTmcQ6OfmjQBujo5OQevvQyyvNlkjuchQoQnPLzC6KBs5DKYm4BvKc1xwBekmWAACIAWxWBZpGzVdIXD18ZhWiSBFC1XFqpYwvnrKWqokV4NeVx8ihshYs0u829RjpMlUYJ6iGiJRpZFEgkiHIcy0tQ2SCYWJCM5rLWTicXNZBr4aeATGUDS3qAQFAJccaHhaEWZx6zUpKmCZIqGXHENR6GBGo7Vhi7RxnDqUDv0iIhNRKV+wcsa+n3LzaQOZzGHu1Uzr1AxhHBZj9fPwMhsjHUpncNwJMLYAUsiI9fZrCQQYwetWiyWTy8KEd0YZ1mPp6enx93jdWt6xkMDQHmWLmxP8t1Q4QjT1+x1y1+6/gRSsqjw0JiJJBbnswaWXqNWDQBqhgj7gZEQUNR9NKzwWOs/DCWcPaM7olwdAnk/YBgf3UD5KDFI+8vRIeFikXpMHDDN5UmF09dAnJU5HpK8UWc5BeqSwHr9Iu1lREgKgQaR9DWIIpn2CwGSEiEEEKbTfAPzf2qUGy31JOR1iMtT6+Wqc3ld9/xukcqsn895W9YmlyrRBV65U5VW92YWRpc2pCMZxZeJyZH0spbQjXbDVck3yZKhTMpYvywCmL1eNhHaNIShMC56SV7LwoQmS3x+YiXYqwsJTsf5JJRlwzAukpFsNlamvbpc9P7lNnFzvMt4Rv0359NVWSGzZCcWK3M+MgJwWcltnkBuXlM8mtnrnHH9MM1dFupx8ZaMm+uEYm2QHGYrCcNXTrdm0nWjdbxbh0jL6cZt291h3sBS2hqoGucZ1jVZhnonNe5+VpQc5tIynGiNXYYCl7gJdthSQdoXAIBm6HHx4q2jtGuibUll2YqdrTd3rfaMfscP26wf1W8/APrtexx2O2gE91LzwNxJFY86K6bWIglDt8SJbiRlVOPdVYfuNTCf5STdcaft/JsvtzXVtnQM1G9I5Y+9OmSbWvKJYXAlmDHykaGqgppS8sUBzLoyUklNu7ua9gGG9lN+LwPo5WDelVEnVeO868AqW2HGib35t9LdZ/AP/THil2d+BtUjTnZ7pc3Zb7c98PDhQ/tmHbrnlaZ9Havqhr77a86hrXXsqcRLm7fZ9C01jUdWDC0+d/RgYEXmnEdrrT2zWlnSt2EtdxbHnad75mz0vTtt48Ha59Vb906uj33xwoIfv6L3zWxOeQOf3ddzNvrb/a22+sfWLpqdWHmps7A+tJ3aQVzYunvm24kPLjramZ1vPM19VBPdcUfVh0OxJdVPPD6l2vFa36f7G/+AR7ad6PvVl9kzePTS7Hhb9dauLkasPDmwOfj9sZMznKejA1t2TV5Zc7zvncTn7w1O32WPfxP/88mKZ/cPTH5k++1SXY2+c+5u+mjlJ8e/fm7TefT+i6uW/R5Xvz0/GP3S8TE49ZDy1IXX26cfTrQHhnP5N95U+0r8EQAA"
# Yashwanth
# EBAY_AUTH_TOKEN = "v^1.1#i^1#I^3#p^3#r^0#f^0#t^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"

# # production
SQUARE_APPLICATION_ID = "sq0idp-7LFQTI11K3Jp8QJbrd0oBg"
SQUARE_ACCESS_TOKEN = "EAAAlskbGe5jzHDcQawpHkCqx21HqiQeevqv9NvRF1IuGtJ_kZgQzWhkwJzErsoh"
SQUARE_LOCATION_ID = "1CYN2MHX8D40J"

# # sandbox
# SQUARE_APPLICATION_ID = "sandbox-sq0idb-0fuCLASC_zEwmy6QHy3-rA"
# SQUARE_ACCESS_TOKEN = "EAAAlzyKG0eMV2-LTS3JJHqrEN_CtarZm7r-Is11_xozI3_ssAV8We3jueT2-592"
# SQUARE_LOCATION_ID = "LH3QV6GWVA32W"

PAYPAL_CLIENT_ID = "AYfg3k8qH8o96bwGi5NZgB8DzLYsKxaDKHAd-oluuzNb_9HlpBBspytNOR8gl2E_ARiFzH-wrw6j7VKJ"
PAYPAL_CLIENT_SECRET = "EJplgEiegxZgCQXs977oppMcUxoCVrcGhZAVSVv_7iFcGpbUNROWmyukBdJqHWNIhM0l1m6VcZja3pN2"


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    # 'django.middleware.csrf.CsrfViewMiddleware',
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "pjsautolit.urls"


# settings.py

ASGI_APPLICATION = "pjsautolit.asgi.application"
WSGI_APPLICATION = "pjsautolit.wsgi.application"
# Celery settings
CELERY_BROKER_URL = os.environ.get(
    "CELERY_BROKER_URL",
    "redis://:pjsautolit@172.31.21.137:6379/0",
    # "CELERY_BROKER_URL",
    # "rediss://red-crts7tggph6c73daq840:dEPiQFWEmuEz7s6cZdcCA1Te0kuwnTdK@oregon-redis.render.com:6379",
)
CELERY_RESULT_BACKEND = "django-db"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"

# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases
import dj_database_url

DATABASES = {
    # render
    # 'default': dj_database_url.config(default="postgresql://pjs_user:hdvgbJ1SaZaf8B0AOq7sfcknzGK5M970@dpg-crdf4gd2ng1s73ftvg7g-a.oregon-postgres.render.com/pjs", conn_max_age=1800),
    # sqlite
    # 'default': {
    #     'ENGINE': 'django.db.backends.sqlite3',
    #     'NAME': BASE_DIR / 'db.sqlite3',
    # }
    # aiven
    "default": dj_database_url.config(
        default="postgres://avnadmin:AVNS_zMc7r76SFXAIO99_PQb@pjsautolit-freshnco.e.aivencloud.com:26164/pjsauto",
        conn_max_age=1800,
    ),
}


# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
