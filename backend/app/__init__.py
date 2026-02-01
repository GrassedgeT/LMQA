from flask import Flask, jsonify
from flask_cors import CORS
import logging
from datetime import datetime

from .core.config import Config
from .core.db import init_db
from .core.utils import error_response
from .services.agent_service import agent_service

from .api.auth import auth_bp
from .api.models import models_bp
from .api.chat import chat_bp
from .api.memories import memories_bp

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Init Config (logging)
    config_class.init_app(app)
    
    # CORS
    CORS(app, origins=app.config['CORS_ORIGINS'], supports_credentials=True)

    # Initialize extensions
    agent_service.init_app(app)

    # Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(models_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(memories_bp)

    # Initialize DB (can be skipped if managed externally, but original main.py did it)
    with app.app_context():
        init_db(app)

    # Global Error Handlers
    @app.errorhandler(404)
    def not_found(error):
        return error_response('资源不存在', 'NOT_FOUND', 404)

    @app.errorhandler(500)
    def internal_error(error):
        logging.error(f'服务器内部错误: {str(error)}')
        return error_response('服务器内部错误', 'INTERNAL_ERROR', 500)

    @app.errorhandler(Exception)
    def handle_exception(e):
        """捕获所有未处理的异常，确保返回JSON格式"""
        logging.error(f'未处理的异常: {str(e)}', exc_info=True)
        return error_response('服务器错误，请稍后重试', 'INTERNAL_ERROR', 500)

    @app.after_request
    def after_request(response):
        """确保所有响应都包含正确的Content-Type"""
        if response.content_type and 'application/json' not in response.content_type:
            # 如果是错误响应且不是JSON，尝试转换为JSON
            if response.status_code >= 400:
                try:
                    data = response.get_data(as_text=True)
                    # 如果响应不是JSON，创建一个JSON错误响应
                    return jsonify({
                        'success': False,
                        'message': data or '请求失败',
                        'error_code': 'ERROR',
                        'timestamp': datetime.utcnow().isoformat() + 'Z'
                    }), response.status_code
                except:
                    pass
        return response

    return app
