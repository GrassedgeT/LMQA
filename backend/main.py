from flask import Flask, jsonify, request, Response, stream_with_context
from flask_cors import CORS
import sqlite3
import json
import os
import jwt
import logging
import requests
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional, Dict, List, Any
from werkzeug.security import generate_password_hash, check_password_hash

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# CORS配置 - 生产环境应该限制具体域名
cors_origins = os.environ.get('CORS_ORIGINS', '*').split(',')
CORS(app, origins=cors_origins, supports_credentials=True)

# 配置
secret_key = os.environ.get('SECRET_KEY')
if not secret_key:
    if os.environ.get('FLASK_ENV') == 'production':
        raise ValueError('生产环境必须设置SECRET_KEY环境变量')
    secret_key = 'dev-secret-key-change-in-production'
    logger.warning('使用默认SECRET_KEY，生产环境请设置SECRET_KEY环境变量')

app.config['SECRET_KEY'] = secret_key
app.config['JWT_ALGORITHM'] = 'HS256'
app.config['JWT_EXPIRATION_DELTA'] = timedelta(hours=24)
app.config['DATABASE'] = os.environ.get('DATABASE', 'app.db')
app.config['AGENT_SERVICE_URL'] = os.environ.get('AGENT_SERVICE_URL', '')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 限制请求大小为16MB

# 输入长度限制配置
MAX_MESSAGE_LENGTH = 10000
MAX_MEMORY_CONTENT_LENGTH = 50000
MAX_MEMORY_TITLE_LENGTH = 200
MAX_USERNAME_LENGTH = 50
MAX_EMAIL_LENGTH = 100

# 数据库初始化
def init_db():
    """初始化数据库表"""
    conn = sqlite3.connect(app.config['DATABASE'])
    c = conn.cursor()
    
    # 用户表
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 对话表
    c.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT,
            message_count INTEGER DEFAULT 0,
            last_message_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    # 消息表
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
    ''')
    
    # 记忆表
    c.execute('''
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            mem0_memory_id TEXT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            memory_type TEXT,
            category TEXT,
            tags TEXT,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()

# 数据库操作辅助函数
def execute_query(query: str, params: tuple = ()) -> List[sqlite3.Row]:
    """执行查询"""
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    try:
        c = conn.cursor()
        c.execute(query, params)
        return c.fetchall()
    except Exception as e:
        logger.error(f'数据库查询错误: {str(e)}, SQL: {query}, Params: {params}')
        raise
    finally:
        conn.close()

def execute_update(query: str, params: tuple = ()) -> int:
    """执行更新，返回最后插入的ID"""
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    try:
        c = conn.cursor()
        c.execute(query, params)
        conn.commit()
        return c.lastrowid
    except Exception as e:
        conn.rollback()
        logger.error(f'数据库更新错误: {str(e)}, SQL: {query}, Params: {params}')
        raise
    finally:
        conn.close()

# 认证辅助函数
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
        'exp': datetime.utcnow() + app.config['JWT_EXPIRATION_DELTA'],
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm=app.config['JWT_ALGORITHM'])

def verify_token(token: str) -> Optional[Dict]:
    """验证JWT token"""
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=[app.config['JWT_ALGORITHM']])
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

# 资源验证辅助函数
def verify_resource_ownership(table: str, resource_id: int, user_id: int) -> bool:
    """验证资源是否属于指定用户"""
    # 白名单验证表名，防止SQL注入
    allowed_tables = {'conversations', 'memories', 'messages'}
    if table not in allowed_tables:
        logger.warning(f'非法的表名: {table}')
        return False
    result = execute_query(f'SELECT id FROM {table} WHERE id = ? AND user_id = ?', (resource_id, user_id))
    return bool(result)

# 分页参数提取
def get_pagination_params(default_limit: int = 20, max_limit: int = 100) -> tuple:
    """提取分页参数"""
    page = int(request.args.get('page', 1))
    limit = min(int(request.args.get('limit', default_limit)), max_limit)
    offset = (page - 1) * limit
    return page, limit, offset

# 智能体服务接口适配层
class AgentService:
    """智能体服务适配层"""
    
    def __init__(self):
        self.agent_service_url = app.config.get('AGENT_SERVICE_URL')
    
    def _make_request(self, endpoint: str, data: Dict, timeout: int = 30) -> Optional[Dict]:
        """统一的HTTP请求方法"""
        try:
            response = requests.post(f"{self.agent_service_url}{endpoint}", json=data, timeout=timeout)
            if response.status_code == 200:
                return response.json()
            logger.warning(f'请求失败，状态码: {response.status_code}')
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f'请求失败: {str(e)}')
            return None
    
    def process_message(self, user_id: int, conversation_id: int, message: str, context: Dict) -> str:
        """处理消息，调用智能体生成回答"""
        if self.agent_service_url:
            result = self._make_request('/process', {
                'user_id': user_id,
                'conversation_id': conversation_id,
                'message': message,
                'context': context
            }, timeout=60)
            return result.get('assistant_message', '抱歉，智能体服务返回了空响应') if result else '调用智能体服务失败'
        return self._process_message_local(user_id, conversation_id, message, context)
    
    def _process_message_local(self, user_id: int, conversation_id: int, message: str, context: Dict) -> str:
        """本地LLM处理（简化实现）"""
        # 这里是一个简化的实现，实际应该调用OpenAI或DeepSeek API
        # 为了演示，返回一个简单的响应
        history = context.get('history', [])
        memories = context.get('memories', [])
        
        # 如果有记忆，添加到上下文中
        memory_context = ''
        if memories:
            memory_context = '\n相关记忆：\n' + '\n'.join([m.get('content', '') for m in memories[:3]])
        
        # 简化的响应生成（实际应该调用LLM API）
        response_text = f"我收到了您的消息：{message}\n"
        if memory_context:
            response_text += memory_context
        response_text += "\n\n（这是简化版的响应，实际应该调用LLM API生成）"
        
        return response_text
    
    def sync_memory(self, user_id: int, memory_data: Dict) -> bool:
        """同步记忆到智能体系统"""
        if not self.agent_service_url:
            return True
        result = self._make_request('/memories/sync', {'user_id': user_id, 'memory': memory_data})
        return result is not None
    
    def search_memories(self, user_id: int, query: str, limit: int = 10) -> List[Dict]:
        """语义搜索记忆"""
        if self.agent_service_url:
            result = self._make_request('/memories/search', {'user_id': user_id, 'query': query, 'limit': limit})
            if result:
                return result.get('memories', [])
        # 本地模式：简单的关键词搜索
        try:
            results = execute_query(
                '''SELECT * FROM memories WHERE user_id = ? AND (content LIKE ? OR title LIKE ?) LIMIT ?''',
                (user_id, f'%{query}%', f'%{query}%', limit)
            )
            return [dict(row) for row in results]
        except Exception as e:
            logger.error(f'本地记忆搜索失败: {str(e)}')
            return []

# 初始化智能体服务
agent_service = AgentService()

# ==================== 认证相关接口 ====================

@app.route('/api/auth/register', methods=['POST'])
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
        if len(username) < 3 or len(username) > MAX_USERNAME_LENGTH:
            return error_response(f'用户名长度必须在3-{MAX_USERNAME_LENGTH}个字符之间', 'VALIDATION_ERROR', 400)
        
        if len(email) > MAX_EMAIL_LENGTH:
            return error_response(f'邮箱长度不能超过{MAX_EMAIL_LENGTH}个字符', 'VALIDATION_ERROR', 400)
        
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

@app.route('/api/auth/login', methods=['POST'])
def login():
    """用户登录"""
    try:
        data = request.get_json()
        
        if not data or not data.get('username') or not data.get('password'):
            return error_response('缺少必需字段：username, password', 'VALIDATION_ERROR', 400)
        
        username = data['username'].strip()
        password = data['password']
        
        # 查询用户（支持用户名或邮箱登录）
        user = execute_query('SELECT * FROM users WHERE username = ? OR email = ?', (username, username))
        if not user:
            logger.warning(f'登录失败：用户不存在 - {username}')
            return error_response('用户名或密码错误', 'INVALID_CREDENTIALS', 401)
        
        user = dict(user[0])
        
        # 验证密码
        if not check_password(password, user['password_hash']):
            logger.warning(f'登录失败：密码错误 - user_id={user["id"]}')
            return error_response('用户名或密码错误', 'INVALID_CREDENTIALS', 401)
        
        # 生成token
        token = generate_token(user['id'])
        
        logger.info(f'用户登录成功: user_id={user["id"]}, username={user["username"]}')
        return success_response({
            'access_token': token,
            'token_type': 'Bearer',
            'expires_in': int(app.config['JWT_EXPIRATION_DELTA'].total_seconds()),
            'user': {
                'id': user['id'],
                'username': user['username'],
                'email': user['email']
            }
        }, '登录成功')
    except Exception as e:
        logger.error(f'用户登录时发生错误: {str(e)}', exc_info=True)
        return error_response('登录失败，请稍后重试', 'INTERNAL_ERROR', 500)

@app.route('/api/auth/me', methods=['GET'])
@require_auth
def get_current_user():
    """获取当前用户信息"""
    user = execute_query('SELECT id, username, email, created_at FROM users WHERE id = ?', (request.current_user_id,))
    if not user:
        return error_response('用户不存在', 'NOT_FOUND', 404)
    
    user = dict(user[0])
    return success_response(user)

@app.route('/api/auth/me', methods=['PUT'])
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
        if len(username) < 3 or len(username) > MAX_USERNAME_LENGTH:
            return error_response(f'用户名长度必须在3-{MAX_USERNAME_LENGTH}个字符之间', 'VALIDATION_ERROR', 400)
        # 检查用户名是否已被其他用户使用
        existing = execute_query('SELECT id FROM users WHERE username = ? AND id != ?', (username, request.current_user_id))
        if existing:
            return error_response('用户名已存在', 'USERNAME_EXISTS', 409)
        update_fields.append('username = ?')
        params.append(username)
    
    if 'email' in data:
        email = data['email'].strip().lower()
        if len(email) > MAX_EMAIL_LENGTH:
            return error_response(f'邮箱长度不能超过{MAX_EMAIL_LENGTH}个字符', 'VALIDATION_ERROR', 400)
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

@app.route('/api/auth/password', methods=['PUT'])
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

@app.route('/api/auth/refresh', methods=['POST'])
@require_auth
def refresh_token():
    """刷新Token"""
    # 生成新的token
    new_token = generate_token(request.current_user_id)
    
    logger.info(f'Token刷新成功: user_id={request.current_user_id}')
    return success_response({
        'access_token': new_token,
        'token_type': 'Bearer',
        'expires_in': int(app.config['JWT_EXPIRATION_DELTA'].total_seconds())
    }, 'Token刷新成功')

# ==================== 对话相关接口 ====================

@app.route('/api/conversations', methods=['GET'])
@require_auth
def get_conversations():
    """获取对话列表"""
    page, limit, offset = get_pagination_params(20, 100)
    conversations = execute_query(
        '''SELECT * FROM conversations WHERE user_id = ? ORDER BY updated_at DESC LIMIT ? OFFSET ?''',
        (request.current_user_id, limit, offset)
    )
    total = execute_query('SELECT COUNT(*) as count FROM conversations WHERE user_id = ?', (request.current_user_id,))[0]['count']
    return success_response({
        'conversations': [dict(c) for c in conversations],
        'pagination': {
            'page': page,
            'limit': limit,
            'total': total,
            'total_pages': (total + limit - 1) // limit,
            'has_next': offset + limit < total,
            'has_prev': page > 1
        }
    })

@app.route('/api/conversations', methods=['POST'])
@require_auth
def create_conversation():
    """创建对话"""
    data = request.get_json() or {}
    title = data.get('title', '新对话')
    
    conversation_id = execute_update(
        'INSERT INTO conversations (user_id, title) VALUES (?, ?)',
        (request.current_user_id, title)
    )
    
    conversation = dict(execute_query('SELECT * FROM conversations WHERE id = ?', (conversation_id,))[0])
    return success_response(conversation, '对话创建成功')

@app.route('/api/conversations/<int:conversation_id>', methods=['PUT'])
@require_auth
def update_conversation(conversation_id):
    """更新对话"""
    if not verify_resource_ownership('conversations', conversation_id, request.current_user_id):
        return error_response('对话不存在或无权限', 'NOT_FOUND', 404)
    
    data = request.get_json()
    if not data:
        return error_response('缺少请求数据', 'VALIDATION_ERROR', 400)
    
    update_fields = []
    params = []
    
    if 'title' in data:
        title = data['title'].strip()
        if len(title) > 200:
            return error_response('对话标题长度不能超过200个字符', 'VALIDATION_ERROR', 400)
        update_fields.append('title = ?')
        params.append(title)
    
    if not update_fields:
        return error_response('没有要更新的字段', 'VALIDATION_ERROR', 400)
    
    update_fields.append('updated_at = CURRENT_TIMESTAMP')
    params.append(conversation_id)
    
    execute_update(
        f'UPDATE conversations SET {", ".join(update_fields)} WHERE id = ?',
        tuple(params)
    )
    
    conversation = dict(execute_query('SELECT * FROM conversations WHERE id = ?', (conversation_id,))[0])
    return success_response(conversation, '对话更新成功')

@app.route('/api/conversations/<int:conversation_id>', methods=['DELETE'])
@require_auth
def delete_conversation(conversation_id):
    """删除对话"""
    if not verify_resource_ownership('conversations', conversation_id, request.current_user_id):
        return error_response('对话不存在或无权限', 'NOT_FOUND', 404)
    execute_update('DELETE FROM conversations WHERE id = ?', (conversation_id,))
    return success_response(None, '对话删除成功')

@app.route('/api/conversations/batch', methods=['DELETE'])
@require_auth
def batch_delete_conversations():
    """批量删除对话"""
    data = request.get_json()
    if not data or not data.get('conversation_ids'):
        return error_response('缺少必需字段：conversation_ids', 'VALIDATION_ERROR', 400)
    
    conversation_ids = data['conversation_ids']
    if not isinstance(conversation_ids, list) or len(conversation_ids) == 0:
        return error_response('conversation_ids必须是非空数组', 'VALIDATION_ERROR', 400)
    
    # 验证所有对话都属于当前用户
    placeholders = ','.join(['?'] * len(conversation_ids))
    conversations = execute_query(
        f'SELECT id FROM conversations WHERE id IN ({placeholders}) AND user_id = ?',
        tuple(conversation_ids + [request.current_user_id])
    )
    
    if len(conversations) != len(conversation_ids):
        return error_response('部分对话不存在或无权限', 'FORBIDDEN', 403)
    
    # 批量删除
    execute_update(
        f'DELETE FROM conversations WHERE id IN ({placeholders})',
        tuple(conversation_ids)
    )
    
    logger.info(f'批量删除对话成功: user_id={request.current_user_id}, count={len(conversation_ids)}')
    return success_response({'deleted_count': len(conversation_ids)}, '批量删除成功')

@app.route('/api/conversations/<int:conversation_id>/messages', methods=['GET'])
@require_auth
def get_messages(conversation_id):
    """获取对话消息历史"""
    if not verify_resource_ownership('conversations', conversation_id, request.current_user_id):
        return error_response('对话不存在或无权限', 'NOT_FOUND', 404)
    page, limit, offset = get_pagination_params(50, 100)
    messages = execute_query(
        '''SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC LIMIT ? OFFSET ?''',
        (conversation_id, limit, offset)
    )
    total = execute_query('SELECT COUNT(*) as count FROM messages WHERE conversation_id = ?', (conversation_id,))[0]['count']
    return success_response({
        'messages': [dict(m) for m in messages],
        'pagination': {
            'page': page,
            'limit': limit,
            'total': total,
            'total_pages': (total + limit - 1) // limit
        }
    })

@app.route('/api/conversations/<int:conversation_id>/messages', methods=['POST'])
@require_auth
def send_message(conversation_id):
    """发送消息"""
    data = request.get_json()
    if not data or not data.get('content'):
        return error_response('缺少必需字段：content', 'VALIDATION_ERROR', 400)
    
    content = data['content'].strip()
    if not content:
        return error_response('消息内容不能为空', 'VALIDATION_ERROR', 400)
    if len(content) > MAX_MESSAGE_LENGTH:
        return error_response(f'消息内容长度不能超过{MAX_MESSAGE_LENGTH}个字符', 'VALIDATION_ERROR', 400)
    if not verify_resource_ownership('conversations', conversation_id, request.current_user_id):
        return error_response('对话不存在或无权限', 'NOT_FOUND', 404)
    
    # 保存用户消息
    user_message_id = execute_update(
        'INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)',
        (conversation_id, 'user', content)
    )
    
    # 获取对话历史
    history_messages = execute_query(
        'SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at ASC LIMIT 20',
        (conversation_id,)
    )
    history = [{'role': m['role'], 'content': m['content']} for m in history_messages]
    
    # 获取相关记忆
    memories = agent_service.search_memories(request.current_user_id, content, limit=5)
    
    # 调用智能体生成回答
    context = {
        'history': history,
        'memories': memories
    }
    assistant_content = agent_service.process_message(
        request.current_user_id,
        conversation_id,
        content,
        context
    )
    
    # 保存AI回答
    assistant_message_id = execute_update(
        'INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)',
        (conversation_id, 'assistant', assistant_content)
    )
    
    # 更新对话的message_count和last_message_at
    execute_update(
        'UPDATE conversations SET message_count = message_count + 2, last_message_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
        (conversation_id,)
    )
    
    # 如果对话没有标题，从第一条消息生成标题
    conversation_data = dict(execute_query('SELECT title FROM conversations WHERE id = ?', (conversation_id,))[0])
    if not conversation_data.get('title') or conversation_data['title'] == '新对话':
        # 使用消息的前30个字符作为标题
        title = content[:30] + ('...' if len(content) > 30 else '')
        execute_update('UPDATE conversations SET title = ? WHERE id = ?', (title, conversation_id))
    
    user_message = dict(execute_query('SELECT * FROM messages WHERE id = ?', (user_message_id,))[0])
    assistant_message = dict(execute_query('SELECT * FROM messages WHERE id = ?', (assistant_message_id,))[0])
    
    return success_response({
        'user_message': user_message,
        'assistant_message': assistant_message
    }, '消息发送成功')

@app.route('/api/conversations/<int:conversation_id>/messages/stream', methods=['POST'])
@require_auth
def send_message_stream(conversation_id):
    """流式发送消息（Server-Sent Events）"""
    data = request.get_json()
    if not data or not data.get('content'):
        return error_response('缺少必需字段：content', 'VALIDATION_ERROR', 400)
    
    content = data['content'].strip()
    if not content:
        return error_response('消息内容不能为空', 'VALIDATION_ERROR', 400)
    if len(content) > MAX_MESSAGE_LENGTH:
        return error_response(f'消息内容长度不能超过{MAX_MESSAGE_LENGTH}个字符', 'VALIDATION_ERROR', 400)
    if not verify_resource_ownership('conversations', conversation_id, request.current_user_id):
        return error_response('对话不存在或无权限', 'NOT_FOUND', 404)
    
    def generate():
        try:
            # 保存用户消息
            user_message_id = execute_update(
                'INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)',
                (conversation_id, 'user', content)
            )
            
            # 发送用户消息事件
            yield f"event: user_message\ndata: {json.dumps({'type': 'user_message', 'message_id': user_message_id, 'content': content})}\n\n"
            
            # 获取对话历史和记忆
            history_messages = execute_query(
                'SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at ASC LIMIT 20',
                (conversation_id,)
            )
            history = [{'role': m['role'], 'content': m['content']} for m in history_messages]
            memories = agent_service.search_memories(request.current_user_id, content, limit=5)
            
            context = {'history': history, 'memories': memories}
            
            # 调用智能体服务（流式）
            if agent_service.agent_service_url:
                # 外部服务流式调用
                try:
                    response = requests.post(
                        f"{agent_service.agent_service_url}/process/stream",
                        json={
                            'user_id': request.current_user_id,
                            'conversation_id': conversation_id,
                            'message': content,
                            'context': context
                        },
                        stream=True,
                        timeout=120
                    )
                    
                    if response.status_code == 200:
                        assistant_content = ''
                        for line in response.iter_lines():
                            if line:
                                line_str = line.decode('utf-8')
                                if line_str.startswith('data: '):
                                    try:
                                        data = json.loads(line_str[6:])
                                        if data.get('type') == 'token':
                                            token = data.get('content', '')
                                            assistant_content += token
                                            yield f"event: token\ndata: {json.dumps({'type': 'token', 'content': token})}\n\n"
                                        elif data.get('type') == 'done':
                                            break
                                    except json.JSONDecodeError:
                                        continue
                        
                        # 保存完整回答
                        assistant_message_id = execute_update(
                            'INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)',
                            (conversation_id, 'assistant', assistant_content)
                        )
                        execute_update(
                            'UPDATE conversations SET message_count = message_count + 2, last_message_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                            (conversation_id,)
                        )
                        yield f"event: done\ndata: {json.dumps({'type': 'done', 'message_id': assistant_message_id})}\n\n"
                    else:
                        yield f"event: error\ndata: {json.dumps({'type': 'error', 'message': '智能体服务错误', 'error_code': 'AGENT_ERROR'})}\n\n"
                except Exception as e:
                    logger.error(f'流式调用智能体服务失败: {str(e)}')
                    yield f"event: error\ndata: {json.dumps({'type': 'error', 'message': f'调用智能体服务失败: {str(e)}', 'error_code': 'AGENT_ERROR'})}\n\n"
            else:
                # 本地模式：简化实现（非真正流式，但返回流式格式）
                assistant_content = agent_service.process_message(
                    request.current_user_id,
                    conversation_id,
                    content,
                    context
                )
                
                # 模拟流式输出（逐字符发送）
                for char in assistant_content:
                    yield f"event: token\ndata: {json.dumps({'type': 'token', 'content': char})}\n\n"
                
                # 保存完整回答
                assistant_message_id = execute_update(
                    'INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)',
                    (conversation_id, 'assistant', assistant_content)
                )
                execute_update(
                    'UPDATE conversations SET message_count = message_count + 2, last_message_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                    (conversation_id,)
                )
                yield f"event: done\ndata: {json.dumps({'type': 'done', 'message_id': assistant_message_id})}\n\n"
                
        except Exception as e:
            logger.error(f'流式发送消息失败: {str(e)}', exc_info=True)
            yield f"event: error\ndata: {json.dumps({'type': 'error', 'message': '发送消息失败', 'error_code': 'INTERNAL_ERROR'})}\n\n"
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no'
    })

@app.route('/api/conversations/<int:conversation_id>/messages/<int:message_id>', methods=['PUT'])
@require_auth
def update_message(conversation_id, message_id):
    """更新消息"""
    if not verify_resource_ownership('conversations', conversation_id, request.current_user_id):
        return error_response('对话不存在或无权限', 'NOT_FOUND', 404)
    
    data = request.get_json()
    if not data or not data.get('content'):
        return error_response('缺少必需字段：content', 'VALIDATION_ERROR', 400)
    
    content = data['content'].strip()
    if not content:
        return error_response('消息内容不能为空', 'VALIDATION_ERROR', 400)
    if len(content) > MAX_MESSAGE_LENGTH:
        return error_response(f'消息内容长度不能超过{MAX_MESSAGE_LENGTH}个字符', 'VALIDATION_ERROR', 400)
    
    # 验证消息属于该对话
    message = execute_query(
        'SELECT * FROM messages WHERE id = ? AND conversation_id = ?',
        (message_id, conversation_id)
    )
    if not message:
        return error_response('消息不存在', 'NOT_FOUND', 404)
    
    # 只允许更新用户消息
    if message[0]['role'] != 'user':
        return error_response('只能编辑用户消息', 'FORBIDDEN', 403)
    
    execute_update(
        'UPDATE messages SET content = ? WHERE id = ?',
        (content, message_id)
    )
    
    updated_message = dict(execute_query('SELECT * FROM messages WHERE id = ?', (message_id,))[0])
    return success_response(updated_message, '消息更新成功')

@app.route('/api/conversations/<int:conversation_id>/messages/<int:message_id>', methods=['DELETE'])
@require_auth
def delete_message(conversation_id, message_id):
    """删除消息"""
    if not verify_resource_ownership('conversations', conversation_id, request.current_user_id):
        return error_response('对话不存在或无权限', 'NOT_FOUND', 404)
    
    # 验证消息属于该对话
    message = execute_query(
        'SELECT * FROM messages WHERE id = ? AND conversation_id = ?',
        (message_id, conversation_id)
    )
    if not message:
        return error_response('消息不存在', 'NOT_FOUND', 404)
    
    execute_update('DELETE FROM messages WHERE id = ?', (message_id,))
    
    # 更新对话的消息计数
    execute_update(
        'UPDATE conversations SET message_count = message_count - 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
        (conversation_id,)
    )
    
    return success_response(None, '消息删除成功')

# ==================== 记忆相关接口 ====================

@app.route('/api/memories', methods=['GET'])
@require_auth
def get_memories():
    """获取记忆列表"""
    page, limit, offset = get_pagination_params(20, 100)
    category = request.args.get('category')
    search = request.args.get('search')
    
    conditions = ['user_id = ?']
    params = [request.current_user_id]
    if category:
        conditions.append('category = ?')
        params.append(category)
    if search:
        conditions.append('(content LIKE ? OR title LIKE ?)')
        params.extend([f'%{search}%', f'%{search}%'])
    
    where_clause = ' AND '.join(conditions)
    memories = execute_query(
        f'SELECT * FROM memories WHERE {where_clause} ORDER BY updated_at DESC LIMIT ? OFFSET ?',
        tuple(params + [limit, offset])
    )
    total = execute_query(f'SELECT COUNT(*) as count FROM memories WHERE {where_clause}', tuple(params))[0]['count']
    
    return success_response({
        'memories': [dict(m) for m in memories],
        'pagination': {
            'page': page,
            'limit': limit,
            'total': total,
            'total_pages': (total + limit - 1) // limit
        }
    })

@app.route('/api/memories', methods=['POST'])
@require_auth
def create_memory():
    """创建记忆"""
    data = request.get_json()
    if not data or not data.get('title') or not data.get('content'):
        return error_response('缺少必需字段：title, content', 'VALIDATION_ERROR', 400)
    
    # 输入长度验证
    title = data['title'].strip()
    content = data['content'].strip()
    
    if len(title) > MAX_MEMORY_TITLE_LENGTH:
        return error_response(f'记忆标题长度不能超过{MAX_MEMORY_TITLE_LENGTH}个字符', 'VALIDATION_ERROR', 400)
    
    if len(content) > MAX_MEMORY_CONTENT_LENGTH:
        return error_response(f'记忆内容长度不能超过{MAX_MEMORY_CONTENT_LENGTH}个字符', 'VALIDATION_ERROR', 400)
    
    memory_id = execute_update(
        '''INSERT INTO memories (user_id, title, content, memory_type, category, tags, metadata)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (
            request.current_user_id,
            title,
            content,
            data.get('memory_type'),
            data.get('category'),
            json.dumps(data.get('tags', [])) if data.get('tags') else None,
            json.dumps(data.get('metadata', {})) if data.get('metadata') else None
        )
    )
    
    # 同步到智能体系统
    agent_service.sync_memory(request.current_user_id, {
        'id': memory_id,
        'title': title,
        'content': content,
        'category': data.get('category'),
        'tags': data.get('tags', [])
    })
    
    memory = dict(execute_query('SELECT * FROM memories WHERE id = ?', (memory_id,))[0])
    return success_response(memory, '记忆创建成功')

@app.route('/api/memories/<int:memory_id>', methods=['PUT'])
@require_auth
def update_memory(memory_id):
    """更新记忆"""
    data = request.get_json()
    if not verify_resource_ownership('memories', memory_id, request.current_user_id):
        return error_response('记忆不存在或无权限', 'NOT_FOUND', 404)
    
    update_fields = []
    params = []
    
    # 允许更新的字段列表（防止SQL注入）
    allowed_fields = {
        'title': MAX_MEMORY_TITLE_LENGTH,
        'content': MAX_MEMORY_CONTENT_LENGTH,
        'category': 50,
        'tags': None,  # JSON格式，长度由内容决定
        'memory_type': 50
    }
    
    for field, max_length in allowed_fields.items():
        if field in data:
            value = data[field]
            if field == 'title' or field == 'content':
                value = value.strip()
                if max_length and len(value) > max_length:
                    return error_response(f'{field}长度不能超过{max_length}个字符', 'VALIDATION_ERROR', 400)
            elif field == 'tags':
                value = json.dumps(value) if isinstance(value, list) else value
            update_fields.append(f'{field} = ?')
            params.append(value)
    
    if not update_fields:
        return error_response('没有要更新的字段', 'VALIDATION_ERROR', 400)
    
    update_fields.append('updated_at = CURRENT_TIMESTAMP')
    params.append(memory_id)
    params.append(request.current_user_id)
    
    # 使用安全的字段名列表构建SQL
    execute_update(
        f'UPDATE memories SET {", ".join(update_fields)} WHERE id = ? AND user_id = ?',
        tuple(params)
    )
    
    memory = dict(execute_query('SELECT * FROM memories WHERE id = ?', (memory_id,))[0])
    return success_response(memory, '记忆更新成功')

@app.route('/api/memories/<int:memory_id>', methods=['DELETE'])
@require_auth
def delete_memory(memory_id):
    """删除记忆"""
    if not verify_resource_ownership('memories', memory_id, request.current_user_id):
        return error_response('记忆不存在或无权限', 'NOT_FOUND', 404)
    execute_update('DELETE FROM memories WHERE id = ? AND user_id = ?', (memory_id, request.current_user_id))
    return success_response(None, '记忆删除成功')

@app.route('/api/memories/search', methods=['POST'])
@require_auth
def search_memories():
    """语义搜索记忆"""
    data = request.get_json()
    if not data or not data.get('query'):
        return error_response('缺少必需字段：query', 'VALIDATION_ERROR', 400)
    
    query = data['query']
    limit = data.get('limit', 10)
    
    # 调用智能体服务进行语义搜索
    results = agent_service.search_memories(request.current_user_id, query, limit)
    
    return success_response({'memories': results})

# 初始化数据库
if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
