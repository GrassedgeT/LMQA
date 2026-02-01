from flask import Blueprint, request, current_app
import logging
import json
from datetime import datetime
from ..core.db import execute_query, execute_update
from ..core.auth_utils import require_auth
from ..core.utils import success_response, error_response, verify_resource_ownership
from ..services.agent_service import agent_service

logger = logging.getLogger(__name__)

memories_bp = Blueprint('memories', __name__, url_prefix='/api/memories')

@memories_bp.route('', methods=['GET'])
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

@memories_bp.route('', methods=['POST'])
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

    if len(title) > current_app.config['MAX_MEMORY_TITLE_LENGTH']:
        return error_response(f'记忆标题长度不能超过{current_app.config["MAX_MEMORY_TITLE_LENGTH"]}个字符', 'VALIDATION_ERROR', 400)

    if len(content) > current_app.config['MAX_MEMORY_CONTENT_LENGTH']:
        return error_response(f'记忆内容长度不能超过{current_app.config["MAX_MEMORY_CONTENT_LENGTH"]}个字符', 'VALIDATION_ERROR', 400)

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

@memories_bp.route('/<int:memory_id>', methods=['PUT'])
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
        'title': current_app.config['MAX_MEMORY_TITLE_LENGTH'],
        'content': current_app.config['MAX_MEMORY_CONTENT_LENGTH'],
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

@memories_bp.route('/<int:memory_id>', methods=['DELETE'])
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

@memories_bp.route('/search', methods=['POST'])
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
