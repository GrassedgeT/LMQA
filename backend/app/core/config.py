import os
import logging
from datetime import timedelta

class Config:
    # Basic Config
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        if os.environ.get('FLASK_ENV') == 'production':
            raise ValueError('生产环境必须设置SECRET_KEY环境变量')
        SECRET_KEY = 'dev-secret-key-change-in-production'
    
    JWT_ALGORITHM = 'HS256'
    JWT_EXPIRATION_DELTA = timedelta(hours=24)
    DATABASE = os.environ.get('DATABASE', 'app.db')
    AGENT_SERVICE_URL = os.environ.get('AGENT_SERVICE_URL', '')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

    # CORS
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*').split(',')

    # Input Constraints
    MAX_MESSAGE_LENGTH = 10000
    MAX_MEMORY_CONTENT_LENGTH = 50000
    MAX_MEMORY_TITLE_LENGTH = 200
    MAX_USERNAME_LENGTH = 50
    MAX_EMAIL_LENGTH = 100
    MAX_API_KEY_LENGTH = 500
    MAX_BASE_URL_LENGTH = 500
    MAX_MODEL_NAME_LENGTH = 100

    @staticmethod
    def init_app(app):
        # Configure Logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
