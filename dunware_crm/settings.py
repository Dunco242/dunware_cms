from pathlib import Path
import os
from dotenv import load_dotenv
import tempfile
import pymysql
pymysql.install_as_MySQLdb()


load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = 'DENY'

ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'dunware-cms.onrender.com']


# Application definition

INSTALLED_APPS = [

    # Django Core Apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'daphne',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django.contrib.sites',

    # Channels and ASGI Apps
    'channels',


    # Third Party Apps (move crispy to the end of third-party)
    'schedule',
    'zoom_integration',
    'django_q',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'django_extensions',

    # Styling Apps (moved to end of third-party)
    'crispy_forms',
    'crispy_tailwind',
    'widget_tweaks',

    # Local Apps
    'core',
    'customer_projects.apps.CustomerProjectsConfig',
    'dunware_crm',
    'document_editor.apps.DocumentEditorConfig',
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
    'core.middleware.PrivacyPolicyMiddleware',

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
            ],
        },
    },
]

WSGI_APPLICATION = 'dunware_crm.wsgi.application'
# Channels Configuration
ASGI_APPLICATION = 'dunware_crm.asgi.application'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [os.getenv('REDIS_URL')],
            "capacity": 1500,  # Optional: default channel layer message capacity
            "expiry": 10,      # Optional: message expiry in seconds
        },
    },
}
# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

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



REDIS_URL = os.getenv('REDIS_URL')
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

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
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'America/New_York'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

BASE_DIR = Path(__file__).resolve().parent.parent

# Static files settings
STATIC_URL = '/static/'

# Corrected: STATICFILES_DIRS should NOT include STATIC_ROOT
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),  # This is only for development
]

# Change STATIC_ROOT to avoid overlap
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')  # Now it's a separate directory

# Add this for more efficient static file handling
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'
# Media files settings
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Ensure DEBUG only modifies STATICFILES_DIRS but does not redefine it
if DEBUG:
    STATICFILES_DIRS += [os.path.join(BASE_DIR, 'assets')]
# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CRISPY_ALLOWED_TEMPLATE_PACKS = 'tailwind'
CRISPY_TEMPLATE_PACK = 'tailwind'
TAILWIND_EXCLUDE_PATTERNS = [
    r'^/admin/.*',  # Exclude admin URLs
]

ADMIN_MEDIA_PREFIX = '/static/admin/'


ACCOUNT_FORMS = {
    'login': 'core.forms.CustomLoginForm',  # If you have a custom form
}


# Authentication settings
LOGIN_URL = '/account/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/account/login'

# Django AllAuth settings
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

ACCOUNT_AUTHENTICATION_METHOD = 'username_email'
ACCOUNT_EMAIL_REQUIRED = False
ACCOUNT_USERNAME_REQUIRED = True
# ACCOUNT_EMAIL_VERIFICATION = 'mandatory'
# ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_LOGIN_TEMPLATE = 'account/login.html'
ACCOUNT_FORMS = {
    'login': 'core.forms.CustomLoginForm',
}

# Email settings
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')

# Site ID for django-allauth
SITE_ID = 1

# Zoom API settings
ZOOM_API_KEY = os.getenv('ZOOM_API_KEY')
ZOOM_API_SECRET = os.getenv('ZOOM_API_SECRET')

PORT = os.getenv('PORT')

Q_CLUSTER = {
    'name': 'DjangoQ',
    'workers': 4,
    'timeout': 90,
    'retry': 120,
    'queue_limit': 50,
    'bulk': 10,
    'orm': 'default',
    'compress': True,  # Added for better performance
    'label': 'Django Q2',  # Added for better identification
    'redis': {
        'host': os.getenv('REDIS_HOST'),
        'port': int(os.getenv('REDIS_PORT')),
        'db': int(os.getenv('REDIS_DB')),
        'password': os.getenv('REDIS_PASSWORD'),
    }
}


WEASYPRINT_TEMP_DIR = os.path.join(tempfile.gettempdir(), "weasyprint")
os.makedirs(WEASYPRINT_TEMP_DIR, exist_ok=True)


PRIVACY_POLICY = {
    'CURRENT_VERSION': '1.0.0',
    'LAST_UPDATED': '2025-02-08',
    'EXEMPT_PATHS': [
        '/privacy-policy/',
        '/accept-privacy-policy/',
        '/logout/',
        '/admin/',
        '/static/',
        '/media/',
    ],
}


PRIVACY_POLICY_PATH = os.path.join(BASE_DIR, 'legal_docs', 'privacy_policy.md')


MESSAGE_STORAGE = 'django.contrib.messages.storage.session.SessionStorage'

# Message tags
from django.contrib.messages import constants as messages
MESSAGE_TAGS = {
    messages.DEBUG: 'alert-secondary',
    messages.INFO: 'alert-info',
    messages.SUCCESS: 'alert-success',
    messages.WARNING: 'alert-warning',
    messages.ERROR: 'alert-danger',
}


CSRF_HEADER_NAME = 'X-CSRFToken'
CSRF_COOKIE_NAME = 'csrftoken'

# settings.py
MAX_UPLOAD_SIZE = 10485760  # 10MB
CONTENT_TYPES = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']

SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Ensure WebSockets use `wss://` in production
USE_SECURE_WEBSOCKETS = os.getenv("DJANGO_ENV", "development") == "production"


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'django-error.log'),
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'ERROR',
            'propagate': True,
        },
    },
}
