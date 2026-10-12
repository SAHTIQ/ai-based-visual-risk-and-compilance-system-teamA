"""
Digital Twin AI — Application Configuration

Loads configuration from environment variables.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration class."""

    # Flask
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('FLASK_DEBUG', 'false').lower() in ('true', '1', 'yes')

    # Firebase Admin SDK
    FIREBASE_CREDENTIALS_PATH = os.getenv('FIREBASE_CREDENTIALS_PATH', 'serviceAccountKey.json')
    FIREBASE_PROJECT_ID = os.getenv('FIREBASE_PROJECT_ID', '')

    # Firebase Client Config (passed to frontend templates)
    FIREBASE_API_KEY = os.getenv('FIREBASE_API_KEY', '')
    FIREBASE_AUTH_DOMAIN = os.getenv('FIREBASE_AUTH_DOMAIN', '')
    FIREBASE_STORAGE_BUCKET = os.getenv('FIREBASE_STORAGE_BUCKET', '')
    FIREBASE_MESSAGING_SENDER_ID = os.getenv('FIREBASE_MESSAGING_SENDER_ID', '')
    FIREBASE_APP_ID = os.getenv('FIREBASE_APP_ID', '')

    # ── Quanta AI Gateway (OpenAI-compatible /chat/completions) ──────────────
    # Provider-agnostic: works with Gemini, Hugging Face Router, OpenAI, or a
    # local Ollama server. Only LLM_API_KEY (a provider key) is required.
    LLM_ENABLED       = os.getenv('LLM_ENABLED', 'true').lower() not in ('false', '0', 'no')
    LLM_BASE_URL      = os.getenv('LLM_BASE_URL', '')
    LLM_API_KEY       = os.getenv('LLM_API_KEY', '')
    LLM_MODEL         = os.getenv('LLM_MODEL', '')          # writer / composer model
    LLM_PLANNER_MODEL = os.getenv('LLM_PLANNER_MODEL', '')  # fast router model

    # Legacy / alternate provider keys (still honoured by the gateway)
    HF_API_KEY = os.getenv('HF_API_KEY', '')
    HF_TOKEN   = os.getenv('HF_TOKEN', '')
    HF_MODEL   = os.getenv('HF_MODEL', 'Qwen/Qwen2.5-72B-Instruct')


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False


# Configuration map
config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}
