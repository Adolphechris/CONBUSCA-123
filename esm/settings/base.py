from pathlib import Path
import os
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEBUG = True

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # LOCAL
    'approvisionnements.apps.ApprovisionnementsConfig',
    'caisse.apps.CaisseConfig',
    'clients.apps.ClientsConfig',
    'commandes.apps.CommandesConfig',
    'creanciers.apps.CreanciersConfig',
    'factures.apps.FacturesConfig',
    'fournisseurs.apps.FournisseursConfig',
    'produits.apps.ProduitsConfig',
    'ecommerce.apps.EcommerceConfig',
    'paie.apps.PaieConfig',
    'parametres.apps.ParametresConfig',
    'patrimoine.apps.PatrimoineConfig',
    'rapports.apps.RapportsConfig',
    'users.apps.UsersConfig',
    'users_management.apps.UsersManagementConfig',
    'activity_logs.apps.ActivityLogsConfig',
    'notifications.apps.NotificationsConfig',
    'direction.apps.DirectionConfig',
    # Contrib
    'django.forms',
    'django_filters',
    'django_htmx',
    # API REST
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'drf_spectacular',
    'api',
    'django_select2',
    'simple_history',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'users.middleware.ForcePasswordChangeMiddleware',
    'simple_history.middleware.HistoryRequestMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
    'activity_logs.middleware.CurrentUserMiddleware',
]

ROOT_URLCONF = 'esm.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
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

WSGI_APPLICATION = 'esm.wsgi.application'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
USE_L10N = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
]

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'users.CustomUser'
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = 'index'
LOGOUT_REDIRECT_URL = '/login/'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

FORM_RENDERER = 'django.forms.renderers.TemplatesSetting'

# ── Firebase Configuration ─────────────────────────────────────────
# Ces paramètres sont requis pour la synchronisation avec Firestore
# et Firebase Storage (boutique en ligne)

FIREBASE_CREDENTIALS = os.getenv('FIREBASE_CREDENTIALS', '')
FIREBASE_STORAGE_BUCKET = os.getenv('FIREBASE_STORAGE_BUCKET', '')
FIREBASE_PROJECT_ID = os.getenv('FIREBASE_PROJECT_ID', '')

# Validation: au moins les credentials doivent être définis en production
if not DEBUG and not FIREBASE_CREDENTIALS:
    import warnings
    warnings.warn(
        "FIREBASE_CREDENTIALS n'est pas configuré. "
        "La synchronisation Firestore ne fonctionnera pas."
    )

# ── CORS Configuration ─────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://10.158.25.167:3000",
]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_ORIGINS = DEBUG

# ── REST Framework Configuration ────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
    },
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_VERSIONING_CLASS': 'rest_framework.versioning.NamespaceVersioning',
    'TEST_REQUEST_DEFAULT_FORMAT': 'json',
}

# ── SimpleJWT Configuration ─────────────────────────────────────────
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
}

# ── drf-spectacular (Swagger) Configuration ─────────────────────────
SPECTACULAR_SETTINGS = {
    'TITLE': 'ESM - API REST',
    'DESCRIPTION': 'API REST pour la boutique ESM (Espace de Services et de Management)',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,
    },
}
