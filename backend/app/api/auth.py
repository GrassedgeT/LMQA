from flask import Blueprint, request, current_app
import logging
from ..core.db import execute_query, execute_update
from ..core.auth_utils import hash_password, check_password, generate_token, require_auth
from ..core.utils import success_response, error_response
from ..services.agent_service import agent_service

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

@auth_bp.route('/register', methods=['POST'])
def register():
    """用户注册"""
    try:
        data = request.get_json()
        
        if not data or not data.get('username') or not data.get('email') or not data.get('password'):
            return error_response('缺少必需字段：username, email, password', 'VALIDATION_ERROR', 400)
        
        username = data['username'].strip()
        email = data['email'].strip().lower()
        password = data['password']
        
        # 验证
        if len(username) < 3 or len(username) > current_app.config['MAX_USERNAME_LENGTH']:
            return error_response(f'用户名长度必须在3-{current_app.config["MAX_USERNAME_LENGTH"]}个字符之间', 'VALIDATION_ERROR', 400)
        
        if len(email) > current_app.config['MAX_EMAIL_LENGTH']:
            return error_response(f'邮箱长度不能超过{current_app.config["MAX_EMAIL_LENGTH"]}个字符', 'VALIDATION_ERROR', 400)
        
        if len(password) < 8:
            return error_response('密码长度至少8个字符', 'VALIDATION_ERROR', 400)
        
        # 检查用户名和邮箱是否已存在
        existing_user = execute_query('SELECT id FROM users WHERE username = ? OR email = ?', (username, email))
        if existing_user:
            logger.warning(f'注册失败：用户名或邮箱已存在 - {username}/{email}')
            return error_response('用户名或邮箱已存在', 'USERNAME_EXISTS', 409)
        
        # 创建用户
        password_hash = hash_password(password)
        user_id = execute_update(
            'INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
            (username, email, password_hash)
        )
        
        logger.info(f'用户注册成功: user_id={user_id}, username={username}')
        return success_response({
            'user_id': user_id,
            'username': username,
            'email': email
        }, '注册成功')
    except Exception as e:
        logger.error(f'用户注册时发生错误: {str(e)}', exc_info=True)
        return error_response('注册失败，请稍后重试', 'INTERNAL_ERROR', 500)

@auth_bp.route('/login', methods=['POST'])
def login():
    """用户登录 (增加预热)"""
    try:
        data = request.get_json()
        if not data or not data.get('username') or not data.get('password'):
            return error_response('缺少必需字段：username, password', 'VALIDATION_ERROR', 400)
        
        username = data['username'].strip()
        password = data['password']
        
        user = execute_query('SELECT * FROM users WHERE username = ? OR email = ?', (username, username))
        if not user:
            return error_response('用户名或密码错误', 'INVALID_CREDENTIALS', 401)
        
        user = dict(user[0])
        if not check_password(password, user['password_hash']):
            return error_response('用户名或密码错误', 'INVALID_CREDENTIALS', 401)
        
        token = generate_token(user['id'])
        
        # === [新增] 登录成功后预热 ===
        try:
            agent_service.warm_up_for_user(user['id'])
        except: pass
        # ===========================

        return success_response({
            'access_token': token,
            'token_type': 'Bearer',
            'expires_in': int(current_app.config['JWT_EXPIRATION_DELTA'].total_seconds()),
            'user': {'id': user['id'], 'username': user['username'], 'email': user['email']}
        }, '登录成功')
    except Exception as e:
        logger.error(f'登录失败: {str(e)}', exc_info=True)
        return error_response('登录失败', 'INTERNAL_ERROR', 500)

@auth_bp.route('/me', methods=['GET'])
@require_auth
def get_current_user():
    """获取当前用户信息"""
    user = execute_query('SELECT id, username, email, created_at FROM users WHERE id = ?', (request.current_user_id,))
    if not user:
        return error_response('用户不存在', 'NOT_FOUND', 404)
    
    user = dict(user[0])
    return success_response(user)

@auth_bp.route('/me', methods=['PUT'])
@require_auth
def update_current_user():
    """更新当前用户信息"""
    data = request.get_json()
    if not data:
        return error_response('缺少请求数据', 'VALIDATION_ERROR', 400)
    
    update_fields = []
    params = []
    
    # 允许更新的字段
    if 'username' in data:
        username = data['username'].strip()
        if len(username) < 3 or len(username) > current_app.config['MAX_USERNAME_LENGTH']:
            return error_response(f'用户名长度必须在3-{current_app.config["MAX_USERNAME_LENGTH"]}个字符之间', 'VALIDATION_ERROR', 400)
        # 检查用户名是否已被其他用户使用
        existing = execute_query('SELECT id FROM users WHERE username = ? AND id != ?', (username, request.current_user_id))
        if existing:
            return error_response('用户名已存在', 'USERNAME_EXISTS', 409)
        update_fields.append('username = ?')
        params.append(username)
    
    if 'email' in data:
        email = data['email'].strip().lower()
        if len(email) > current_app.config['MAX_EMAIL_LENGTH']:
            return error_response(f'邮箱长度不能超过{current_app.config["MAX_EMAIL_LENGTH"]}个字符', 'VALIDATION_ERROR', 400)
        # 检查邮箱是否已被其他用户使用
        existing = execute_query('SELECT id FROM users WHERE email = ? AND id != ?', (email, request.current_user_id))
        if existing:
            return error_response('邮箱已被注册', 'EMAIL_EXISTS', 409)
        update_fields.append('email = ?')
        params.append(email)
    
    if not update_fields:
        return error_response('没有要更新的字段', 'VALIDATION_ERROR', 400)
    
    update_fields.append('updated_at = CURRENT_TIMESTAMP')
    params.append(request.current_user_id)
    
    execute_update(
        f'UPDATE users SET {", ".join(update_fields)} WHERE id = ?',
        tuple(params)
    )
    
    user = dict(execute_query('SELECT id, username, email, created_at FROM users WHERE id = ?', (request.current_user_id,))[0])
    logger.info(f'用户信息更新成功: user_id={request.current_user_id}')
    return success_response(user, '用户信息更新成功')

@auth_bp.route('/password', methods=['PUT'])
@require_auth
def update_password():
    """修改密码"""
    data = request.get_json()
    if not data or not data.get('old_password') or not data.get('new_password'):
        return error_response('缺少必需字段：old_password, new_password', 'VALIDATION_ERROR', 400)
    
    old_password = data['old_password']
    new_password = data['new_password']
    
    if len(new_password) < 8:
        return error_response('新密码长度至少8个字符', 'VALIDATION_ERROR', 400)
    
    # 获取当前用户密码哈希
    user = execute_query('SELECT password_hash FROM users WHERE id = ?', (request.current_user_id,))
    if not user:
        return error_response('用户不存在', 'NOT_FOUND', 404)
    
    # 验证旧密码
    if not check_password(old_password, user[0]['password_hash']):
        logger.warning(f'修改密码失败：原密码错误 - user_id={request.current_user_id}')
        return error_response('原密码错误', 'INVALID_PASSWORD', 401)
    
    # 更新密码
    new_password_hash = hash_password(new_password)
    execute_update(
        'UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
        (new_password_hash, request.current_user_id)
    )
    
    logger.info(f'密码修改成功: user_id={request.current_user_id}')
    return success_response(None, '密码修改成功')

@auth_bp.route('/refresh', methods=['POST'])
@require_auth
def refresh_token():
    """刷新Token"""
    # 生成新的token
    new_token = generate_token(request.current_user_id)
    
    logger.info(f'Token刷新成功: user_id={request.current_user_id}')
    return success_response({
        'access_token': new_token,
        'token_type': 'Bearer',
        'expires_in': int(current_app.config['JWT_EXPIRATION_DELTA'].total_seconds())
    }, 'Token刷新成功')
