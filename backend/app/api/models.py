from flask import Blueprint, request, current_app
import logging
import sqlite3
from ..core.db import execute_query, execute_update
from ..core.auth_utils import require_auth
from ..core.utils import success_response, error_response, encrypt_api_key, decrypt_api_key, verify_resource_ownership
from ..services.agent_service import agent_service

logger = logging.getLogger(__name__)

models_bp = Blueprint('models', __name__, url_prefix='/api/user/model-configs')

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

@models_bp.route('/providers', methods=['GET'])
@require_auth
def get_model_providers():
    """获取支持的模型提供商列表"""
    return success_response({
        'providers': MODEL_PROVIDERS
    })

@models_bp.route('', methods=['GET'])
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

@models_bp.route('/default', methods=['GET'])
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

@models_bp.route('', methods=['POST'])
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
    if len(model_name) > current_app.config['MAX_MODEL_NAME_LENGTH']:
        return error_response(f'模型名称长度不能超过{current_app.config["MAX_MODEL_NAME_LENGTH"]}个字符', 'VALIDATION_ERROR', 400)
    if not api_key:
        return error_response('API Key 不能为空', 'VALIDATION_ERROR', 400)
    if len(api_key) > current_app.config['MAX_API_KEY_LENGTH']:
        return error_response(f'API Key 长度不能超过{current_app.config["MAX_API_KEY_LENGTH"]}个字符', 'VALIDATION_ERROR', 400)
    if base_url and len(base_url) > current_app.config['MAX_BASE_URL_LENGTH']:
        return error_response(f'Base URL 长度不能超过{current_app.config["MAX_BASE_URL_LENGTH"]}个字符', 'VALIDATION_ERROR', 400)
    
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
        # 保存配置...
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

@models_bp.route('/<int:config_id>', methods=['PUT'])
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
    if model_name and len(model_name) > current_app.config['MAX_MODEL_NAME_LENGTH']:
        return error_response(f'模型名称长度不能超过{current_app.config["MAX_MODEL_NAME_LENGTH"]}个字符', 'VALIDATION_ERROR', 400)
    available_models = MODEL_PROVIDERS[provider].get('models', [])
    if available_models and model_name not in available_models:
        return error_response('不支持的模型名称', 'VALIDATION_ERROR', 400)
    if api_key and len(api_key) > current_app.config['MAX_API_KEY_LENGTH']:
        return error_response(f'API Key 长度不能超过{current_app.config["MAX_API_KEY_LENGTH"]}个字符', 'VALIDATION_ERROR', 400)
    if base_url and len(base_url) > current_app.config['MAX_BASE_URL_LENGTH']:
        return error_response(f'Base URL 长度不能超过{current_app.config["MAX_BASE_URL_LENGTH"]}个字符', 'VALIDATION_ERROR', 400)
    
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

@models_bp.route('/<int:config_id>', methods=['DELETE'])
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

@models_bp.route('/<int:config_id>/set-default', methods=['PUT'])
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

@models_bp.route('/<int:config_id>/test', methods=['POST'])
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
