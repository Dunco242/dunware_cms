import os
from pathlib import Path
from dotenv import load_dotenv
import tempfile
import pymysql
from django.contrib.messages import constants as messages
pymysql.install_as_MySQLdb()

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Development mode check
DEBUG = True
DEVELOPMENT_MODE = os.getenv('DJANGO_ENV')

# Security settings - completely disabled in development
SECRET_KEY = os.getenv('SECRET_KEY')

if DEVELOPMENT_MODE:
    SECURE_SSL_REDIRECT = False
    SECURE_PROXY_SSL_HEADER = None
    SECURE_HSTS_SECONDS = 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False
    SECURE_CONTENT_TYPE_NOSNIFF = False
    SECURE_BROWSER_XSS_FILTER = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    X_FRAME_OPTIONS = 'SAMEORIGIN'
    USE_SECURE_WEBSOCKETS = False
else:
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = 'DENY'
    USE_SECURE_WEBSOCKETS = True

ALLOWED_HOSTS = [
    '127.0.0.1',
    'localhost',
    'dunware-cms.onrender.com',
    'www.dunwaresolutions.com',
    '.dunwaresolutions.com', # Include the base domain
]

CSRF_TRUSTED_ORIGINS = [
    'https://www.dunwaresolutions.com',
    'https://dunwaresolutions.com',
    'https://dunware-cms.onrender.com'
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'daphne',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django.contrib.sites',
    'channels',
    'schedule',
    'zoom_integration',
    'django_q',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'django_extensions',
    'crispy_forms',
    'crispy_tailwind',
    'widget_tweaks',
    'core.apps.CoreConfig',
    'customer_projects.apps.CustomerProjectsConfig',
    'dunware_crm',
    'document_editor.apps.DocumentEditorConfig',
    'video_conference.apps.VideoConferenceConfig',
    'onboarding',
    'route_management.apps.RouteManagementConfig',
    'downloads.apps.DownloadsConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'core.middleware.IPTrackingMiddleware',
]

ROOT_URLCONF = 'dunware_crm.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'core', 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.notification_processor',
                'django.template.context_processors.csrf',
            ],
        },
    },
]

WSGI_APPLICATION = 'dunware_crm.wsgi.application'
ASGI_APPLICATION = 'dunware_crm.asgi.application'

# if DEVELOPMENT_MODE:
#     DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.sqlite3",
#         "NAME": "mydatabase",
#     }
# }

#     CHANNEL_LAYERS = {
#         "default": {
#             "BACKEND": "channels.layers.InMemoryChannelLayer"
#         }
#     }
#     CACHES = {
#         'default': {
#             'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
#         }
#     }
# else:
DATABASES = {
    'default': {
        'ENGINE': os.getenv('DB_ENGINE', 'django.db.backends.mysql'),
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '3306'),
    }
}
# THIS IS FOR TROUBLESHOOTING AND DEBUGGING. Activate this DB if you are in need of testing for troubleshooting.
# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.sqlite3",
#         "NAME": "mydatabase",
#     }
# }

REDIS_URL = os.getenv('REDIS_URL')
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [REDIS_URL],
            "capacity": 1500,
            "expiry": 10,
        },
    },
}
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

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

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'America/New_York'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

if DEBUG:
    STATICFILES_DIRS += [os.path.join(BASE_DIR, 'assets')]

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CRISPY_ALLOWED_TEMPLATE_PACKS = 'tailwind'
CRISPY_TEMPLATE_PACK = 'tailwind'
TAILWIND_EXCLUDE_PATTERNS = [r'^/admin/.*']

ADMIN_MEDIA_PREFIX = '/static/admin/'

LOGIN_URL = '/account/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/account/login'

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

ACCOUNT_AUTHENTICATION_METHOD = 'username_email'
ACCOUNT_EMAIL_REQUIRED = False
ACCOUNT_USERNAME_REQUIRED = True
ACCOUNT_LOGIN_TEMPLATE = 'account/login.html'
ACCOUNT_FORMS = {
    'login': 'core.forms.CustomLoginForm',
}

if DEVELOPMENT_MODE:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
    EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
    EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
    EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
    EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
    DEFAULT_FROM_EMAIL = os.getenv('EMAIL_HOST_USER')


SITE_ID = 1

ZOOM_API_KEY = os.getenv('ZOOM_API_KEY')
ZOOM_API_SECRET = os.getenv('ZOOM_API_SECRET')
HERE_MAPS_API_KEY = os.getenv('HERE_MAPS_API_KEY')
HERE_MAPS_APP_ID = os.getenv('HERE_MAPS_APP_ID')

if DEVELOPMENT_MODE:
    Q_CLUSTER = {
        'name': 'DjangoQ',
        'workers': 1,
        'timeout': 90,
        'retry': 120,
        'queue_limit': 50,
        'bulk': 10,
        'orm': 'default'
    }
else:
    Q_CLUSTER = {
        'name': 'DjangoQ',
        'workers': 4,
        'timeout': 90,
        'retry': 120,
        'queue_limit': 50,
        'bulk': 10,
        'orm': 'default',
        'compress': True,
        'label': 'Django Q2',
        'redis': {
            'host': os.getenv('REDIS_HOST'),
            'port': int(os.getenv('REDIS_PORT')),
            'db': int(os.getenv('REDIS_DB')),
            'password': os.getenv('REDIS_PASSWORD'),
        }
    }

WEASYPRINT_TEMP_DIR = os.path.join(tempfile.gettempdir(), "weasyprint")
os.makedirs(WEASYPRINT_TEMP_DIR, exist_ok=True)

MESSAGE_STORAGE = 'django.contrib.messages.storage.session.SessionStorage'
MESSAGE_TAGS = {
    messages.DEBUG: 'alert-secondary',
    messages.INFO: 'alert-info',
    messages.SUCCESS: 'alert-success',
    messages.WARNING: 'alert-warning',
    messages.ERROR: 'alert-danger',
}

CSRF_HEADER_NAME = 'X-CSRFToken'
CSRF_COOKIE_NAME = 'csrftoken'

MAX_UPLOAD_SIZE = 10485760  # 10MB
CONTENT_TYPES = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']

# Simplified logging configuration for development
if DEVELOPMENT_MODE:
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
            },
        },
        'root': {
            'handlers': ['console'],
            'level': 'INFO',
        },
    }
else:
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'handlers': {
            'file': {
                'level': 'ERROR',
                'class': 'logging.FileHandler',
                'filename': os.path.join(BASE_DIR, 'django-error.log'),
            },
        },
        'root': {
            'handlers': ['file'],
            'level': 'ERROR',
        },
    }

AGORA_APP_ID = os.getenv('AGORA_APP_ID')
AGORA_APP_CERTIFICATE = os.getenv('AGORA_APP_CERTIFICATE')

ENABLE_AUTOMATION = os.getenv('ENABLE_AUTOMATION', 'True') == 'True'
APSCHEDULER_DATETIME_FORMAT = "N j, Y, f:s a"
SCHEDULER_DEFAULT_MAX_INSTANCES = 1

DEFAULT_CHARSET = 'utf-8'

GOOGLE_CREDENTIALS_FILE = os.path.join(BASE_DIR, os.getenv('GOOGLE_CREDENTIALS_FILE'))
GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEET_ID')
GOOGLE_CALENDAR_CREDENTIALS_FILE = os.getenv('GOOGLE_CALENDAR_CREDENTIALS_FILE')
