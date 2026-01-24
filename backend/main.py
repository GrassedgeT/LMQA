from flask import Flask, jsonify, request, Response, stream_with_context
from flask_cors import CORS
import sqlite3
import json
import os
import jwt
import logging
import requests
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Optional, Dict, List, Any
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet
import base64
import hashlib
from memory.manager import MemoryManager
import concurrent.futures

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
MAX_API_KEY_LENGTH = 500  # API Key 最大长度
MAX_BASE_URL_LENGTH = 500  # Base URL 最大长度
MAX_MODEL_NAME_LENGTH = 100  # 模型名称最大长度

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
            conversation_id INTEGER,
            mem0_memory_id TEXT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            memory_type TEXT,
            category TEXT,
            tags TEXT,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
    ''')
    
    # 用户模型配置表
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_model_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            model_name TEXT NOT NULL,
            api_key TEXT NOT NULL,
            base_url TEXT,
            is_default INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id, provider, model_name)
        )
    ''')
    
    # 数据库迁移：为memories表添加conversation_id字段
    try:
        # 检查memories表是否已有conversation_id字段
        c.execute("PRAGMA table_info(memories)")
        columns = c.fetchall()
        column_names = [col[1] for col in columns]

        if 'conversation_id' not in column_names:
            logger.info('为memories表添加conversation_id字段')
            c.execute('ALTER TABLE memories ADD COLUMN conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE')
    except Exception as e:
        logger.error(f'数据库迁移失败: {str(e)}')
        # 不抛出异常，继续运行

    conn.commit()
    conn.close()

# 数据库操作辅助函数
def convert_timestamp_to_iso(timestamp_str: str) -> str:
    """将 SQLite 时间戳转换为 ISO 8601 格式（UTC）"""
    if not timestamp_str:
        return timestamp_str
    try:
        # SQLite 的 CURRENT_TIMESTAMP 返回格式: 'YYYY-MM-DD HH:MM:SS' (UTC)
        # 转换为 ISO 8601 格式并添加 UTC 时区标识
        dt = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        # 假设数据库存储的是 UTC 时间，转换为 UTC 时区对象
        dt_utc = dt.replace(tzinfo=timezone.utc)
        # 返回 ISO 8601 格式字符串，带 'Z' 后缀表示 UTC
        return dt_utc.isoformat().replace('+00:00', 'Z')
    except (ValueError, AttributeError, TypeError):
        # 如果解析失败，返回原值
        return timestamp_str

def execute_query(query: str, params: tuple = ()) -> List[sqlite3.Row]:
    """执行查询"""
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    try:
        c = conn.cursor()
        c.execute(query, params)
        results = c.fetchall()
        # 转换所有时间戳字段为 ISO 8601 格式
        converted_results = []
        for row in results:
            row_dict = dict(row)
            # 转换所有可能的时间戳字段
            timestamp_fields = ['created_at', 'updated_at', 'last_message_at', 'edited_at']
            for field in timestamp_fields:
                if field in row_dict and row_dict[field]:
                    row_dict[field] = convert_timestamp_to_iso(row_dict[field])
            # 创建一个类似 Row 的对象，保持原有接口
            class RowLike:
                def __init__(self, data):
                    self._data = data
                    for key, value in data.items():
                        setattr(self, key, value)
                def __getitem__(self, key):
                    return self._data[key]
                def __contains__(self, key):
                    return key in self._data
                def keys(self):
                    return self._data.keys()
                def get(self, key, default=None):
                    return self._data.get(key, default)
            converted_results.append(RowLike(row_dict))
        return converted_results if converted_results else results
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

# API Key 加密/解密
def get_encryption_key() -> bytes:
    """获取加密密钥"""
    secret_key = app.config['SECRET_KEY']
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
def get_pagination_params(default_limit: int = 20, max_limit: int = 100) -> tuple:
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

# 智能体服务接口适配层
class AgentService:
    """智能体服务适配层 - 针对 DeepSeek 优化的 Agentic 模式"""
    
    def __init__(self):
        self.agent_service_url = app.config.get('AGENT_SERVICE_URL')
        try:
            self.memory_manager = MemoryManager()
            logger.info("MemoryManager initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MemoryManager: {e}")
            self.memory_manager = None

    def _get_user_model_config(self, user_id: int) -> Optional[Dict]:
        try:
            config = execute_query('SELECT provider, model_name, api_key, base_url FROM user_model_configs WHERE user_id = ? AND is_default = 1 LIMIT 1', (user_id,))
            if config:
                config_dict = dict(config[0])
                config_dict['api_key'] = decrypt_api_key(config_dict['api_key'])
                return config_dict
            return None
        except Exception as e:
            logger.error(f'获取用户模型配置失败: {str(e)}')
            return None

    def _get_llm_client(self, user_id: int):
        model_config = self._get_user_model_config(user_id)
        if not model_config: return None, None, None
        try:
            from openai import OpenAI
            client = OpenAI(api_key=model_config['api_key'], base_url=model_config['base_url'])
            return client, model_config['model_name'], model_config
        except Exception as e:
            logger.error(f'创建 LLM 客户端失败: {str(e)}')
            return None, None, None

    def warm_up_for_user(self, user_id: int):
        try:
            config = self._get_user_model_config(user_id)
            if self.memory_manager: self.memory_manager.warm_up_client(config)
        except: pass

    # =========================================================================
    # 1. 工具定义 (加强版：防止漏记姓名)
    # =========================================================================
    def _get_tools(self) -> List[Dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "add_memory",
                    "description": "保存用户的重要信息。⚠️重要：如果用户同时提供了【姓名/身份】和【其他事实】，必须将它们合并保存，绝对不能遗漏姓名！",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "要存储的完整事实。必须包含主语。例如用户说'我是小王，有个同事叫小张'，你必须填入：'用户叫小王，用户有一个同事叫小张' (必须包含两点)。"
                            }
                        },
                        "required": ["content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_memories",
                    "description": "搜索历史记忆。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "搜索关键词"
                            },
                            "limit": {
                                "type": "integer",
                                "default": 5
                            }
                        },
                        "required": ["query"]
                    }
                }
            }
        ]

    # =========================================================================
    # 2. System Prompt (加强版：全量存储原则)
    # =========================================================================
    def _build_system_prompt(self) -> str:
        return """你是一个智能助手，负责管理用户记忆。

**记忆管理最高准则：**
1. **全量存储（关键）**：当用户一句话包含多个信息点（尤其是包含“我叫XXX”这种身份信息）时，**必须**将所有信息合并在一次 `add_memory` 调用中。
   - ❌ 错误行为：用户说“我叫小王，同事是小张”，你只存“用户有个同事叫小张”。（漏掉了名字！）
   - ✅ 正确行为：你调用 `add_memory(content="用户叫小王，用户有一个同事叫小张")`。

2. **主语明确**：DeepSeek/LLM 请注意，Mem0 需要明确的主语。
   - 不要说 "是个程序员"。
   - 要说 "用户是程序员"。

3. **先搜后答**：回答问题前先搜索。
"""

    # =========================================================================
    # 3. 工具执行 (保持不变)
    # =========================================================================
    def _execute_tool(self, tool_name: str, tool_args: Dict, user_id: int, conversation_id: int, llm_settings: Dict) -> str:
        logger.info(f"🔧 Agent 执行工具: {tool_name} | 参数: {tool_args}")
        if not self.memory_manager: return "错误：记忆模块未初始化。"

        try:
            if tool_name == "add_memory":
                res = self.memory_manager.add_memory(
                    content=tool_args["content"],
                    user_id=str(user_id),
                    run_id=None, # 保持全局
                    metadata={"source_conversation_id": str(conversation_id)},
                    llm_settings=llm_settings
                )
                return "记忆已添加。"

            elif tool_name == "search_memories":
                res = self.memory_manager.search_memories(
                    query=tool_args["query"],
                    user_id=str(user_id),
                    limit=tool_args.get("limit", 5),
                    llm_settings=llm_settings
                )
                memories = [m.get("memory", m.get("text", "")) for m in res]
                return f"搜索结果: {json.dumps(memories, ensure_ascii=False)}"
            
            return f"未知工具: {tool_name}"
        except Exception as e:
            logger.error(f"工具执行异常: {e}")
            return f"工具执行出错: {str(e)}"

    # =========================================================================
    # 4. Agent Loop (保持不变)
    # =========================================================================
    def chat_agent(self, user_id: int, conversation_id: int, user_message: str, history_messages: List[Dict]) -> str:
        client, model_name, llm_settings = self._get_llm_client(user_id)
        if not client: return "请先配置模型 API Key。"

        messages = [{"role": "system", "content": self._build_system_prompt()}]
        messages.extend(history_messages)
        messages.append({"role": "user", "content": user_message})

        tools = self._get_tools()
        max_turns = 5
        current_turn = 0
        
        while current_turn < max_turns:
            try:
                response = client.chat.completions.create(
                    model=model_name, messages=messages, tools=tools, tool_choice="auto", temperature=0.7
                )
                response_message = response.choices[0].message
                
                if response_message.tool_calls:
                    messages.append(response_message)
                    
                    # 并行执行
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        futures = []
                        for tool_call in response_message.tool_calls:
                            function_name = tool_call.function.name
                            try:
                                arguments = json.loads(tool_call.function.arguments)
                            except: arguments = {}
                            
                            future = executor.submit(
                                self._execute_tool,
                                function_name, arguments, user_id, conversation_id, llm_settings
                            )
                            futures.append((tool_call, future))
                        
                        for tool_call, future in futures:
                            tool_result = future.result()
                            messages.append({
                                "tool_call_id": tool_call.id, "role": "tool", 
                                "name": tool_call.function.name, "content": tool_result
                            })
                    
                    current_turn += 1
                else:
                    return response_message.content
            except Exception as e:
                logger.error(f"Agent Loop Error: {e}")
                return f"处理错误: {str(e)}"
        
        return "思考超时。"

    # --- 兼容方法 ---
    def delete_conversation_memories(self, *args): pass
    def search_memories(self, *args, **kwargs): return []
    def sync_memory(self, *args, **kwargs): return {}
    def update_memory(self, *args, **kwargs): pass
    def delete_memory(self, *args, **kwargs): pass
    def add_interaction(self, *args, **kwargs): pass
    def _process_message_stream_local(self, *args, **kwargs): pass

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
            'expires_in': int(app.config['JWT_EXPIRATION_DELTA'].total_seconds()),
            'user': {'id': user['id'], 'username': user['username'], 'email': user['email']}
        }, '登录成功')
    except Exception as e:
        logger.error(f'登录失败: {str(e)}', exc_info=True)
        return error_response('登录失败', 'INTERNAL_ERROR', 500)

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

# ==================== 模型配置相关接口 ====================

# 模型提供商配置
MODEL_PROVIDERS = {
    'deepseek': {
        'name': 'DeepSeek',
        'base_url': 'https://api.deepseek.com/v1',
        'models': ['deepseek-chat', 'deepseek-coder']
    },
    'qwen': {
        'name': '通义千问 (Qwen)',
        'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        'models': ['qwen-turbo', 'qwen-plus', 'qwen-max']
    },
    'kimi': {
        'name': 'Kimi (Moonshot)',
        'base_url': 'https://api.moonshot.cn/v1',
        'models': ['moonshot-v1-8k', 'moonshot-v1-32k', 'moonshot-v1-128k']
    },
    # 新增项
    'openai': {
        'name': 'OpenAI 兼容 (自定义)',
        'base_url': 'https://api.openai.com/v1', # 默认值，用户可修改
        'models': [] # 空列表表示不限制模型名称
    }
}

@app.route('/api/user/model-configs/providers', methods=['GET'])
@require_auth
def get_model_providers():
    """获取支持的模型提供商列表"""
    return success_response({
        'providers': MODEL_PROVIDERS
    })

@app.route('/api/user/model-configs', methods=['GET'])
@require_auth
def get_model_configs():
    """获取用户的所有模型配置"""
    configs = execute_query(
        'SELECT id, user_id, provider, model_name, base_url, is_default, created_at, updated_at FROM user_model_configs WHERE user_id = ? ORDER BY is_default DESC, created_at DESC',
        (request.current_user_id,)
    )
    return success_response({
        'configs': [dict(c) for c in configs]
    })

@app.route('/api/user/model-configs/default', methods=['GET'])
@require_auth
def get_default_model_config():
    """获取用户的默认模型配置"""
    config = execute_query(
        'SELECT id, user_id, provider, model_name, base_url, is_default, created_at, updated_at FROM user_model_configs WHERE user_id = ? AND is_default = 1 LIMIT 1',
        (request.current_user_id,)
    )
    if config:
        return success_response(dict(config[0]))
    return error_response('未设置默认模型配置', 'NOT_FOUND', 404)

@app.route('/api/user/model-configs', methods=['POST'])
@require_auth
def create_model_config():
    """创建新的模型配置"""
    data = request.get_json()
    if not data:
        return error_response('缺少请求数据', 'VALIDATION_ERROR', 400)
    
    provider = data.get('provider', '').strip().lower()
    model_name = data.get('model_name', '').strip()
    api_key = data.get('api_key', '').strip()
    base_url = data.get('base_url', '').strip()
    is_default = data.get('is_default', False)
    
    # 验证
    available_models = MODEL_PROVIDERS[provider].get('models', [])
    if provider in MODEL_PROVIDERS and available_models and model_name not in available_models:
        return error_response(f'不支持的模型名称，支持的模型: {", ".join(available_models)}', 'VALIDATION_ERROR', 400)
    if not model_name:
        return error_response('模型名称不能为空', 'VALIDATION_ERROR', 400)
    if len(model_name) > MAX_MODEL_NAME_LENGTH:
        return error_response(f'模型名称长度不能超过{MAX_MODEL_NAME_LENGTH}个字符', 'VALIDATION_ERROR', 400)
    if not api_key:
        return error_response('API Key 不能为空', 'VALIDATION_ERROR', 400)
    if len(api_key) > MAX_API_KEY_LENGTH:
        return error_response(f'API Key 长度不能超过{MAX_API_KEY_LENGTH}个字符', 'VALIDATION_ERROR', 400)
    if base_url and len(base_url) > MAX_BASE_URL_LENGTH:
        return error_response(f'Base URL 长度不能超过{MAX_BASE_URL_LENGTH}个字符', 'VALIDATION_ERROR', 400)
    
    # 使用默认 base_url 如果未提供
    if not base_url:
        base_url = MODEL_PROVIDERS[provider]['base_url']
    
    # 加密 API Key
    try:
        encrypted_api_key = encrypt_api_key(api_key)
    except Exception as e:
        logger.error(f'加密 API Key 失败: {str(e)}')
        return error_response('API Key 加密失败', 'INTERNAL_ERROR', 500)
    
    # 如果设置为默认，先取消其他默认配置
    if is_default:
        execute_update(
            'UPDATE user_model_configs SET is_default = 0 WHERE user_id = ?',
            (request.current_user_id,)
        )
    
    try:
        # 保存配置... (你的原有逻辑)
        config_id = execute_update(
            'INSERT INTO user_model_configs (user_id, provider, model_name, api_key, base_url, is_default) VALUES (?, ?, ?, ?, ?, ?)',
            (request.current_user_id, provider, model_name, encrypted_api_key, base_url, 1 if is_default else 0)
        )
        
        # === [新增] 配置变更后预热 ===
        try:
            agent_service.warm_up_for_user(request.current_user_id)
        except: pass
        # ===========================
        return success_response({'id': config_id}, '模型配置创建成功')
    except sqlite3.IntegrityError:
        return error_response('该模型配置已存在', 'DUPLICATE_ERROR', 409)
    except Exception as e:
        logger.error(f'创建模型配置失败: {str(e)}')
        return error_response('创建模型配置失败', 'INTERNAL_ERROR', 500)

@app.route('/api/user/model-configs/<int:config_id>', methods=['PUT'])
@require_auth
def update_model_config(config_id):
    """更新模型配置"""
    if not verify_resource_ownership('user_model_configs', config_id, request.current_user_id):
        return error_response('模型配置不存在或无权限', 'NOT_FOUND', 404)
    
    data = request.get_json()
    if not data:
        return error_response('缺少请求数据', 'VALIDATION_ERROR', 400)
    
    provider = data.get('provider', '').strip().lower() if data.get('provider') else None
    model_name = data.get('model_name', '').strip() if data.get('model_name') else None
    api_key = data.get('api_key', '').strip() if data.get('api_key') else None
    base_url = data.get('base_url', '').strip() if data.get('base_url') else None
    is_default = data.get('is_default')
    
    # 获取现有配置
    existing = execute_query(
        'SELECT provider, model_name, base_url FROM user_model_configs WHERE id = ?',
        (config_id,)
    )
    if not existing:
        return error_response('模型配置不存在', 'NOT_FOUND', 404)
    
    existing = dict(existing[0])
    provider = provider or existing['provider']
    model_name = model_name or existing['model_name']
    base_url = base_url or existing['base_url'] or MODEL_PROVIDERS[provider]['base_url']
    
    # 验证
    if provider not in MODEL_PROVIDERS:
        return error_response('不支持的模型提供商', 'VALIDATION_ERROR', 400)
    if model_name and len(model_name) > MAX_MODEL_NAME_LENGTH:
        return error_response(f'模型名称长度不能超过{MAX_MODEL_NAME_LENGTH}个字符', 'VALIDATION_ERROR', 400)
    available_models = MODEL_PROVIDERS[provider].get('models', [])
    if available_models and model_name not in available_models:
        return error_response('不支持的模型名称', 'VALIDATION_ERROR', 400)
    if api_key and len(api_key) > MAX_API_KEY_LENGTH:
        return error_response(f'API Key 长度不能超过{MAX_API_KEY_LENGTH}个字符', 'VALIDATION_ERROR', 400)
    if base_url and len(base_url) > MAX_BASE_URL_LENGTH:
        return error_response(f'Base URL 长度不能超过{MAX_BASE_URL_LENGTH}个字符', 'VALIDATION_ERROR', 400)
    
    # 如果设置了新的 API Key，加密它
    encrypted_api_key = None
    if api_key:
        try:
            encrypted_api_key = encrypt_api_key(api_key)
        except Exception as e:
            logger.error(f'加密 API Key 失败: {str(e)}')
            return error_response('API Key 加密失败', 'INTERNAL_ERROR', 500)
    
    # 如果设置为默认，先取消其他默认配置
    if is_default:
        execute_update(
            'UPDATE user_model_configs SET is_default = 0 WHERE user_id = ? AND id != ?',
            (request.current_user_id, config_id)
        )
    update_fields = []
    update_params = []
    if encrypted_api_key:
        update_fields.append('api_key = ?')
        update_params.append(encrypted_api_key)
    if provider and provider in MODEL_PROVIDERS:
        update_fields.append('provider = ?')
        update_params.append(provider)
    if model_name and model_name in MODEL_PROVIDERS[provider]['models']:
        update_fields.append('model_name = ?')
        update_params.append(model_name)
    if base_url:
        update_fields.append('base_url = ?')
        update_params.append(base_url)
    if is_default is not None:
        update_fields.append('is_default = ?')
        update_params.append(1 if is_default else 0)
    
    if not update_fields:
        return error_response('没有需要更新的字段', 'VALIDATION_ERROR', 400)
    
    update_fields.append('updated_at = CURRENT_TIMESTAMP')
    update_params.append(config_id)
    
    try:
        execute_update(
            f'UPDATE user_model_configs SET {", ".join(update_fields)} WHERE id = ?',
            tuple(update_params)
        )
        # === [新增] 配置变更后预热 ===
        try:
            agent_service.warm_up_for_user(request.current_user_id)
        except: pass
        # ===========================
        logger.info(f'更新模型配置成功: config_id={config_id}')
        return success_response(None, '模型配置更新成功')
    except Exception as e:
        logger.error(f'更新模型配置失败: {str(e)}')
        return error_response('更新模型配置失败', 'INTERNAL_ERROR', 500)

@app.route('/api/user/model-configs/<int:config_id>', methods=['DELETE'])
@require_auth
def delete_model_config(config_id):
    """删除模型配置"""
    if not verify_resource_ownership('user_model_configs', config_id, request.current_user_id):
        return error_response('模型配置不存在或无权限', 'NOT_FOUND', 404)
    
    try:
        execute_update('DELETE FROM user_model_configs WHERE id = ?', (config_id,))
        logger.info(f'删除模型配置成功: config_id={config_id}')
        return success_response(None, '模型配置删除成功')
    except Exception as e:
        logger.error(f'删除模型配置失败: {str(e)}')
        return error_response('删除模型配置失败', 'INTERNAL_ERROR', 500)

@app.route('/api/user/model-configs/<int:config_id>/set-default', methods=['PUT'])
@require_auth
def set_default_model_config(config_id):
    """设置默认模型配置"""
    if not verify_resource_ownership('user_model_configs', config_id, request.current_user_id):
        return error_response('模型配置不存在或无权限', 'NOT_FOUND', 404)
    
    try:
        # 先取消所有默认配置
        execute_update(
            'UPDATE user_model_configs SET is_default = 0 WHERE user_id = ?',
            (request.current_user_id,)
        )
        # 设置新的默认配置
        execute_update(
            'UPDATE user_model_configs SET is_default = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (config_id,)
        )
        logger.info(f'设置默认模型配置成功: config_id={config_id}')
        return success_response(None, '默认模型配置设置成功')
    except Exception as e:
        logger.error(f'设置默认模型配置失败: {str(e)}')
        return error_response('设置默认模型配置失败', 'INTERNAL_ERROR', 500)

@app.route('/api/user/model-configs/<int:config_id>/test', methods=['POST'])
@require_auth
def test_model_config(config_id):
    """测试模型配置的 API Key 是否有效"""
    if not verify_resource_ownership('user_model_configs', config_id, request.current_user_id):
        return error_response('模型配置不存在或无权限', 'NOT_FOUND', 404)
    
    config = execute_query(
        'SELECT provider, model_name, api_key, base_url FROM user_model_configs WHERE id = ?',
        (config_id,)
    )
    if not config:
        return error_response('模型配置不存在', 'NOT_FOUND', 404)
    
    config = dict(config[0])
    try:
        api_key = decrypt_api_key(config['api_key'])
    except Exception as e:
        logger.error(f'解密 API Key 失败: user_id={request.current_user_id}, config_id={config_id}')
        return error_response('解密 API Key 失败', 'INTERNAL_ERROR', 500)
    
    # 测试 API Key
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url=config['base_url']
        )
        # 发送一个简单的测试请求
        response = client.chat.completions.create(
            model=config['model_name'],
            messages=[{'role': 'user', 'content': 'Hello'}],
            max_tokens=10
        )
        return success_response({'valid': True, 'message': 'API Key 有效'}, 'API Key 测试成功')
    except Exception as e:
        # 避免泄露详细的 API Key 错误信息
        error_msg = str(e)
        logger.error(f'测试 API Key 失败: user_id={request.current_user_id}, config_id={config_id}, error_type={type(e).__name__}')
        if 'api' in error_msg.lower() and ('key' in error_msg.lower() or 'auth' in error_msg.lower() or '401' in error_msg or '403' in error_msg):
            return error_response('API Key 无效或已过期', 'TEST_FAILED', 400)
        elif 'network' in error_msg.lower() or 'connection' in error_msg.lower() or 'timeout' in error_msg.lower():
            return error_response('网络连接失败，请检查网络设置', 'TEST_FAILED', 400)
        else:
            return error_response('API Key 测试失败，请检查配置', 'TEST_FAILED', 400)

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
    
    # 删除对话相关记忆
    agent_service.delete_conversation_memories(request.current_user_id, conversation_id)
    
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
    
    # 限制批量删除数量，防止资源耗尽
    if len(conversation_ids) > 100:
        return error_response('批量删除数量不能超过100', 'VALIDATION_ERROR', 400)
    
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
    """发送消息 - Agentic 模式 (逻辑已替换)"""
    data = request.get_json()
    content = data.get('content', '').strip()
    if not content: return error_response('内容不能为空', 'VALIDATION_ERROR', 400)
    
    if not verify_resource_ownership('conversations', conversation_id, request.current_user_id):
        return error_response('无权限', 'NOT_FOUND', 404)
    
    # 1. 保存用户消息
    user_message_id = execute_update(
        'INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)',
        (conversation_id, 'user', content)
    )
    
    # 2. 准备历史 (去重)
    history_messages = execute_query(
        'SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at ASC LIMIT 20',
        (conversation_id,)
    )
    history = [{'role': m['role'], 'content': m['content']} for m in history_messages[:-1]]
    
    # 3. Agent 思考与执行 (这就是你要的逻辑)
    assistant_content = agent_service.chat_agent(
        user_id=request.current_user_id,
        conversation_id=conversation_id,
        user_message=content,
        history_messages=history
    )
    
    # 4. 保存 AI 回答
    assistant_message_id = execute_update(
        'INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)',
        (conversation_id, 'assistant', assistant_content)
    )
    
    # 5. 更新元数据
    execute_update(
        'UPDATE conversations SET message_count = message_count + 2, last_message_at = CURRENT_TIMESTAMP WHERE id = ?',
        (conversation_id,)
    )
    
    # 自动标题
    conversation_data = dict(execute_query('SELECT title FROM conversations WHERE id = ?', (conversation_id,))[0])
    if not conversation_data.get('title') or conversation_data['title'] == '新对话':
        execute_update('UPDATE conversations SET title = ? WHERE id = ?', (content[:30], conversation_id))
    
    return success_response({
        'user_message': dict(execute_query('SELECT * FROM messages WHERE id = ?', (user_message_id,))[0]),
        'assistant_message': dict(execute_query('SELECT * FROM messages WHERE id = ?', (assistant_message_id,))[0])
    })

@app.route('/api/conversations/<int:conversation_id>/messages/stream', methods=['POST'])
@require_auth
def send_message_stream(conversation_id):
    """流式发送消息 - Agent 适配版"""
    # 注意：为了支持 Tool Call 循环，这里我们采用"伪流式"。
    # 即：服务器先执行完完整的 Agent 思考过程（可能包含多次搜索/存储），
    # 拿到最终文本后，再以流的形式吐给前端。这样前端代码不用改。
    
    data = request.get_json()
    if not data or not data.get('content'):
        return error_response('缺少必需字段：content', 'VALIDATION_ERROR', 400)
    
    content = data['content'].strip()
    if not verify_resource_ownership('conversations', conversation_id, request.current_user_id):
        return error_response('对话不存在或无权限', 'NOT_FOUND', 404)
    
    def generate():
        try:
            # 1. 保存用户消息
            user_message_id = execute_update(
                'INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)',
                (conversation_id, 'user', content)
            )
            # 发送用户消息事件
            yield f"event: user_message\ndata: {json.dumps({'type': 'user_message', 'message_id': user_message_id, 'content': content})}\n\n"
            
            # 2. 准备历史
            history_messages = execute_query(
                'SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at ASC LIMIT 20',
                (conversation_id,)
            )
            history = [{'role': m['role'], 'content': m['content']} for m in history_messages[:-1]]
            
            # 3. 【核心】执行 Agent 思考 (这步会阻塞，直到思考完成)
            # 在这里，Agent 可能会调用 add_memory 存入数据库
            final_content = agent_service.chat_agent(
                user_id=request.current_user_id,
                conversation_id=conversation_id,
                user_message=content,
                history_messages=history
            )
            
            # 4. 模拟流式输出最终结果 (为了兼容前端动画)
            # 将结果切片发送
            chunk_size = 10
            for i in range(0, len(final_content), chunk_size):
                chunk = final_content[i:i+chunk_size]
                yield f"event: token\ndata: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
            
            # 5. 保存 AI 完整回答
            assistant_message_id = execute_update(
                'INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)',
                (conversation_id, 'assistant', final_content)
            )
            execute_update(
                'UPDATE conversations SET message_count = message_count + 2, last_message_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                (conversation_id,)
            )
            
            yield f"event: done\ndata: {json.dumps({'type': 'done', 'message_id': assistant_message_id})}\n\n"
            
        except Exception as e:
            logger.error(f'Agent 流式处理失败: {str(e)}', exc_info=True)
            yield f"event: error\ndata: {json.dumps({'type': 'error', 'message': '智能体处理失败', 'error_code': 'INTERNAL_ERROR'})}\n\n"

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
    limit = int(request.args.get('limit', 100))
    conversation_id = request.args.get('conversation_id')
    user_id = str(request.current_user_id)
    
    run_id = None
    if conversation_id and conversation_id != '0':
        run_id = str(conversation_id)

    try:
        if not agent_service.memory_manager:
            return success_response({'memories': [], 'relations': [], 'pagination': {}})

        # 调用 manager
        raw_result = agent_service.memory_manager.get_memories(
            user_id=user_id, 
            run_id=run_id, 
            limit=limit,
            llm_settings=agent_service._get_user_model_config(request.current_user_id)
        )
        
        if raw_result is None: raw_result = {}
            
        results = raw_result.get('results', [])
        relations = raw_result.get('relations', []) # <--- 获取图数据

        # 格式化列表
        memories_list = []
        for m in results:
            if not isinstance(m, dict): continue
            content = m.get('memory', m.get('text', ''))
            metadata = m.get('metadata') or {}
            
            memories_list.append({
                'id': m.get('id'),
                'title': metadata.get('title', content[:50] + '...'),
                'content': content,
                'category': metadata.get('category', '自动生成'),
                'tags': metadata.get('tags'),
                'conversation_id': int(metadata.get('source_conversation_id', 0)) if metadata.get('source_conversation_id', '').isdigit() else None,
                'created_at': m.get('created_at', datetime.utcnow().isoformat() + 'Z'),
                'updated_at': m.get('updated_at', datetime.utcnow().isoformat() + 'Z')
            })
        
        # 返回结果 (带上 relations)
        return success_response({
            'memories': memories_list,
            'relations': relations, # <--- 关键：传给前端
            'pagination': {
                'page': 1,
                'limit': limit,
                'total': len(memories_list),
                'total_pages': 1
            }
        })

    except Exception as e:
        logger.error(f"获取记忆路由失败: {e}", exc_info=True)
        return success_response({'memories': [], 'relations': [], 'pagination': {}})

@app.route('/api/memories', methods=['POST'])
@require_auth
def create_memory():
    """创建记忆（conversation_id 可选，若未提供则为用户级记忆）"""
    data = request.get_json()
    if not data or not data.get('title') or not data.get('content'):
        return error_response('缺少必需字段：title, content', 'VALIDATION_ERROR', 400)

    conversation_id = data.get('conversation_id')
    conversation_id_int = None
    if conversation_id:
        try:
            conversation_id_int = int(conversation_id)
            if not verify_resource_ownership('conversations', conversation_id_int, request.current_user_id):
                return error_response('对话不存在或无权限', 'NOT_FOUND', 404)
        except (ValueError, TypeError):
            return error_response('conversation_id 必须是有效的整数', 'VALIDATION_ERROR', 400)

    # 输入长度验证和格式化
    title = data['title'].strip()
    content = data['content'].strip()

    if not title:
        return error_response('记忆标题不能为空', 'VALIDATION_ERROR', 400)
    
    if not content:
        return error_response('记忆内容不能为空', 'VALIDATION_ERROR', 400)

    if len(title) > MAX_MEMORY_TITLE_LENGTH:
        return error_response(f'记忆标题长度不能超过{MAX_MEMORY_TITLE_LENGTH}个字符', 'VALIDATION_ERROR', 400)

    if len(content) > MAX_MEMORY_CONTENT_LENGTH:
        return error_response(f'记忆内容长度不能超过{MAX_MEMORY_CONTENT_LENGTH}个字符', 'VALIDATION_ERROR', 400)

    # 规范化内容：统一换行符
    content = content.replace('\r\n', '\n').replace('\r', '\n')

    memory_id = execute_update(
        '''INSERT INTO memories (user_id, conversation_id, title, content, memory_type, category, tags, metadata)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (
            request.current_user_id,
            conversation_id_int,
            title,
            content,
            data.get('memory_type'),
            data.get('category'),
            json.dumps(data.get('tags', [])) if data.get('tags') else None,
            json.dumps(data.get('metadata', {})) if data.get('metadata') else None
        )
    )

    # 同步到智能体系统
    sync_result = agent_service.sync_memory(request.current_user_id, {
        'id': memory_id,
        'conversation_id': conversation_id_int,
        'title': title,
        'content': content,
        'category': data.get('category'),
        'tags': data.get('tags', [])
    })

    # Update mem0_memory_id if available
    if isinstance(sync_result, dict):
        mem0_id = sync_result.get('id')
        if not mem0_id and 'results' in sync_result and isinstance(sync_result['results'], list) and len(sync_result['results']) > 0:
             mem0_id = sync_result['results'][0].get('id')
        
        if mem0_id:
             execute_update('UPDATE memories SET mem0_memory_id = ? WHERE id = ?', (mem0_id, memory_id))

    memory = dict(execute_query('SELECT * FROM memories WHERE id = ?', (memory_id,))[0])
    return success_response(memory, '记忆创建成功')

@app.route('/api/memories/<int:memory_id>', methods=['PUT'])
@require_auth
def update_memory(memory_id):
    """更新记忆"""
    data = request.get_json()
    if not verify_resource_ownership('memories', memory_id, request.current_user_id):
        return error_response('记忆不存在或无权限', 'NOT_FOUND', 404)

    # 验证对话ID（如果要更改对话）
    conversation_id = data.get('conversation_id')
    if conversation_id:
        if not verify_resource_ownership('conversations', int(conversation_id), request.current_user_id):
            return error_response('对话不存在或无权限', 'NOT_FOUND', 404)

    update_fields = []
    params = []

    # 允许更新的字段列表（防止SQL注入）
    allowed_fields = {
        'title': MAX_MEMORY_TITLE_LENGTH,
        'content': MAX_MEMORY_CONTENT_LENGTH,
        'category': 50,
        'tags': None,  # JSON格式，长度由内容决定
        'memory_type': 50,
        'conversation_id': None  # 允许更改所属对话
    }

    for field, max_length in allowed_fields.items():
        if field in data:
            value = data[field]
            if field == 'title':
                value = value.strip()
                if not value:
                    return error_response('记忆标题不能为空', 'VALIDATION_ERROR', 400)
                if max_length and len(value) > max_length:
                    return error_response(f'记忆标题长度不能超过{max_length}个字符', 'VALIDATION_ERROR', 400)
            elif field == 'content':
                value = value.strip()
                if not value:
                    return error_response('记忆内容不能为空', 'VALIDATION_ERROR', 400)
                if max_length and len(value) > max_length:
                    return error_response(f'记忆内容长度不能超过{max_length}个字符', 'VALIDATION_ERROR', 400)
                # 规范化内容：统一换行符
                value = value.replace('\r\n', '\n').replace('\r', '\n')
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

    # 同步更新到 MemoryManager
    memory = dict(execute_query('SELECT * FROM memories WHERE id = ?', (memory_id,))[0])
    if memory.get('mem0_memory_id'):
        # Mem0 update (primarily updates content)
        # Note: If title changed, we might want to update it in metadata if mem0 supports it, 
        # but mem0.update mainly takes 'text'.
        # We'll use the new content (or existing content if not changed).
        current_content = memory['content']
        agent_service.update_memory(memory['mem0_memory_id'], current_content)

    return success_response(memory, '记忆更新成功')

@app.route('/api/memories/<int:memory_id>', methods=['DELETE'])
@require_auth
def delete_memory(memory_id):
    """删除记忆"""
    if not verify_resource_ownership('memories', memory_id, request.current_user_id):
        return error_response('记忆不存在或无权限', 'NOT_FOUND', 404)
    
    # Get mem0_memory_id before deletion
    memory = execute_query('SELECT mem0_memory_id FROM memories WHERE id = ?', (memory_id,))
    mem0_id = memory[0]['mem0_memory_id'] if memory else None

    execute_update('DELETE FROM memories WHERE id = ? AND user_id = ?', (memory_id, request.current_user_id))
    
    if mem0_id:
        agent_service.delete_memory(mem0_id)

    return success_response(None, '记忆删除成功')

@app.route('/api/memories/search', methods=['POST'])
@require_auth
def search_memories():
    """语义搜索记忆（必须指定对话ID）"""
    data = request.get_json()
    if not data or not data.get('query'):
        return error_response('缺少必需字段：query', 'VALIDATION_ERROR', 400)
    
    conversation_id = data.get('conversation_id')
    if not conversation_id:
        return error_response('缺少必需字段：conversation_id', 'VALIDATION_ERROR', 400)
    
    # 验证用户有权限访问该对话
    try:
        conversation_id_int = int(conversation_id)
    except (ValueError, TypeError):
        return error_response('conversation_id 必须是有效的整数', 'VALIDATION_ERROR', 400)
    
    if not verify_resource_ownership('conversations', conversation_id_int, request.current_user_id):
        return error_response('对话不存在或无权限', 'NOT_FOUND', 404)
    
    query = data['query']
    limit = data.get('limit', 10)
    
    # 调用智能体服务进行语义搜索（仅搜索指定对话的记忆）
    results = agent_service.search_memories(request.current_user_id, query, limit, conversation_id_int)
    
    return success_response({'memories': results})

# 初始化数据库
# 全局错误处理 - 确保所有错误都返回JSON格式
@app.errorhandler(404)
def not_found(error):
    return error_response('资源不存在', 'NOT_FOUND', 404)

@app.errorhandler(500)
def internal_error(error):
    logger.error(f'服务器内部错误: {str(error)}')
    return error_response('服务器内部错误', 'INTERNAL_ERROR', 500)

@app.errorhandler(Exception)
def handle_exception(e):
    """捕获所有未处理的异常，确保返回JSON格式"""
    logger.error(f'未处理的异常: {str(e)}', exc_info=True)
    return error_response('服务器错误，请稍后重试', 'INTERNAL_ERROR', 500)

# 确保所有响应都是JSON格式
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

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
