from pathlib import Path


# ========================

# BASE CONFIGURATION

# ========================


BASE_DIR = Path(__file__).resolve().parent.parent


SECRET_KEY = 'django-insecure-w#+r@gx$^$w^@nngvkpwywgl=4i)c1zw+qnkufvy+s1ujb^-'

DEBUG = True

ALLOWED_HOSTS = ['*']


# ========================

# APPLICATIONS

# ========================


INSTALLED_APPS = [

    # Django default apps

    'django.contrib.admin',

    'django.contrib.auth',

    'django.contrib.contenttypes',

    'django.contrib.sessions',

    'django.contrib.messages',

    'django.contrib.staticfiles',


    # Your custom apps

    'core',

    'accounts',


    # Allauth apps

    'django.contrib.sites',               # Required by allauth

    'allauth',

    'allauth.account',

    'allauth.socialaccount',

    'allauth.socialaccount.providers.google',

    

]


SITE_ID = 1


# ========================

# AUTHENTICATION

# ========================


AUTHENTICATION_BACKENDS = [

    'django.contrib.auth.backends.ModelBackend',               # Django default

    'allauth.account.auth_backends.AuthenticationBackend',     # allauth backend

]


LOGIN_REDIRECT_URL = '/dashboard/'  # Pehle yeh '/' tha

LOGOUT_REDIRECT_URL = '/'


# ========================

# MIDDLEWARE

# ========================


MIDDLEWARE = [

    'django.middleware.security.SecurityMiddleware',

    'django.contrib.sessions.middleware.SessionMiddleware',

    'django.middleware.common.CommonMiddleware',

    'django.middleware.csrf.CsrfViewMiddleware',

    'django.contrib.auth.middleware.AuthenticationMiddleware',

    'django.contrib.messages.middleware.MessageMiddleware',

    'django.middleware.clickjacking.XFrameOptionsMiddleware',


    # ✅ Required by newer django-allauth versions (v65+)

    'allauth.account.middleware.AccountMiddleware',

]


# ========================

# URLS + WSGI

# ========================


ROOT_URLCONF = 'voldio_ai.urls'

WSGI_APPLICATION = 'voldio_ai.wsgi.application'


# ========================

# TEMPLATES

# ========================


TEMPLATES = [

    {

        'BACKEND': 'django.template.backends.django.DjangoTemplates',

        'DIRS': [BASE_DIR / 'templates'],     # global templates folder

        'APP_DIRS': True,

        'OPTIONS': {

            'context_processors': [

                'django.template.context_processors.debug',

                'django.template.context_processors.request',  # required by allauth

                'django.contrib.auth.context_processors.auth',

                'django.contrib.messages.context_processors.messages',

            ],

        },

    },

]


# ========================

# DATABASE

# ========================


DATABASES = {

    'default': {

        'ENGINE': 'django.db.backends.sqlite3',

        'NAME': BASE_DIR / 'db.sqlite3',

    }

}


# ========================

# PASSWORD VALIDATORS

# ========================


AUTH_PASSWORD_VALIDATORS = [

    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},

    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},

    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},

    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},

]


# ========================

# INTERNATIONALIZATION

# ========================


LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# ========================

# STATIC FILES

# ========================

import os 


STATIC_URL = '/static/'


MEDIA_URL = '/media/'


# Local directory jahan aapki files save ho rahi hain

# (Yeh 'uploads' folder ko point karega)

MEDIA_ROOT = os.path.join(BASE_DIR, 'uploads')


# ✅ NAYE API KEYS

# ========================

ELEVENLABS_API_KEY = "sk_08d1c9a5970c639020896b949a7fe6fcf4657da51b285845"

GEMINI_API_KEY = "AIzaSyA-ADXrbtxxYvhNmbJQAY7rCIeM0W8wWSU"


# ========================

# GOOGLE OAUTH SETTINGS

# ========================

SOCIALACCOUNT_PROVIDERS = {

    'google': {

        'APP': {

            'client_id': '135824048393-uv2olnnk9gldamj0bt57itplqote5lkk.apps.googleusercontent.com',

            'secret': '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',

            'key': ''

        },

        'SCOPE': [

            'profile',

            'email',

            'openid',

            'https://www.googleapis.com/auth/calendar.events',

            'https://www.googleapis.com/auth/gmail.compose',

            'https://www.googleapis.com/auth/gmail.send',

        ],

        'AUTH_PARAMS': {

            'access_type': 'offline',

            'prompt': 'consent',   # 👈 This is critical

        }

    }

}



SOCIALACCOUNT_STORE_TOKENS = True


ACCOUNT_LOGIN_TEMPLATE = 'accounts/login.html'

# Allow CSRF from local dev and IDE preview proxy
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://127.0.0.1:59922',
]

# Permit initiating social login via GET (useful in dev and with simple anchor links)
SOCIALACCOUNT_LOGIN_ON_GET = True

# Ensure allauth builds http URLs in dev
ACCOUNT_DEFAULT_HTTP_PROTOCOL = 'http'


# ========================

# DEFAULT PRIMARY KEY TYPE

# ========================


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'