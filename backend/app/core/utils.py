import logging
import hashlib
import base64
from datetime import datetime
from typing import Any, Tuple
from flask import jsonify, Response, request, current_app
from cryptography.fernet import Fernet
from .db import execute_query

logger = logging.getLogger(__name__)

# 统一响应格式
def success_response(data: Any = None, message: str = '操作成功') -> Response:
    """成功响应"""
    return jsonify({
        'success': True,
        'message': message,
        'data': data,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    })

def error_response(message: str, error_code: str = 'ERROR', status_code: int = 400) -> Response:
    """错误响应"""
    return jsonify({
        'success': False,
        'message': message,
        'error_code': error_code,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }), status_code

# API Key 加密/解密
def get_encryption_key() -> bytes:
    """获取加密密钥"""
    secret_key = current_app.config['SECRET_KEY']
    # 使用 SHA256 哈希确保密钥长度和安全性
    key_hash = hashlib.sha256(secret_key.encode()).digest()
    return base64.urlsafe_b64encode(key_hash)

def encrypt_api_key(api_key: str) -> str:
    """加密 API Key"""
    try:
        f = Fernet(get_encryption_key())
        encrypted = f.encrypt(api_key.encode())
        return encrypted.decode()
    except Exception as e:
        logger.error(f'加密 API Key 失败: {str(e)}')
        raise

def decrypt_api_key(encrypted_key: str) -> str:
    """解密 API Key"""
    try:
        f = Fernet(get_encryption_key())
        decrypted = f.decrypt(encrypted_key.encode())
        return decrypted.decode()
    except Exception as e:
        logger.error(f'解密 API Key 失败: {str(e)}')
        raise

# 资源验证辅助函数
def verify_resource_ownership(table: str, resource_id: int, user_id: int) -> bool:
    """验证资源是否属于指定用户"""
    # 白名单验证表名，防止SQL注入，使用字典映射避免字符串拼接
    table_queries = {
        'conversations': 'SELECT id FROM conversations WHERE id = ? AND user_id = ?',
        'memories': 'SELECT id FROM memories WHERE id = ? AND user_id = ?',
        'messages': 'SELECT id FROM messages WHERE id = ? AND user_id = ?',
        'user_model_configs': 'SELECT id FROM user_model_configs WHERE id = ? AND user_id = ?'
    }
    if table not in table_queries:
        logger.warning(f'非法的表名: {table}')
        return False
    result = execute_query(table_queries[table], (resource_id, user_id))
    return bool(result)

# 分页参数提取
def get_pagination_params(default_limit: int = 20, max_limit: int = 100) -> Tuple[int, int, int]:
    """提取分页参数"""
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        limit = min(max(1, int(request.args.get('limit', default_limit))), max_limit)
    except (ValueError, TypeError):
        limit = default_limit
    offset = (page - 1) * limit
    return page, limit, offset
