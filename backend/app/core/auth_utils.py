from functools import wraps
from datetime import datetime
from typing import Optional, Dict
import jwt
from flask import request, jsonify, current_app
from werkzeug.security import generate_password_hash, check_password_hash

def hash_password(password: str) -> str:
    """使用werkzeug生成密码哈希"""
    return generate_password_hash(password)

def check_password(password: str, password_hash: str) -> bool:
    """验证密码"""
    return check_password_hash(password_hash, password)

def generate_token(user_id: int) -> str:
    """生成JWT token"""
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + current_app.config['JWT_EXPIRATION_DELTA'],
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm=current_app.config['JWT_ALGORITHM'])

def verify_token(token: str) -> Optional[Dict]:
    """验证JWT token"""
    try:
        payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=[current_app.config['JWT_ALGORITHM']])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def require_auth(f):
    """认证装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(' ')[1]  # Bearer <token>
            except IndexError:
                pass
        
        if not token:
            return jsonify({
                'success': False,
                'message': '未提供认证token',
                'error_code': 'UNAUTHORIZED'
            }), 401
        
        payload = verify_token(token)
        if not payload:
            return jsonify({
                'success': False,
                'message': 'Token无效或已过期',
                'error_code': 'TOKEN_INVALID'
            }), 401
        
        request.current_user_id = payload['user_id']
        return f(*args, **kwargs)
    
    return decorated
