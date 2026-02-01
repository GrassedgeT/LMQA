from flask import Blueprint, request, Response, stream_with_context, current_app
import logging
import json
from ..core.db import execute_query, execute_update
from ..core.auth_utils import require_auth
from ..core.utils import success_response, error_response, verify_resource_ownership, get_pagination_params
from ..services.agent_service import agent_service

logger = logging.getLogger(__name__)

chat_bp = Blueprint('chat', __name__, url_prefix='/api/conversations')

@chat_bp.route('', methods=['GET'])
@require_auth
def get_conversations():
    """获取对话列表"""
    page, limit, offset = get_pagination_params(20, 100)
    conversations = execute_query(
        '''SELECT * FROM conversations WHERE user_id = ? ORDER BY updated_at DESC LIMIT ? OFFSET ?''',
        (request.current_user_id, limit, offset)
    )
    total_result = execute_query('SELECT COUNT(*) as count FROM conversations WHERE user_id = ?', (request.current_user_id,))
    total = total_result[0]['count'] if total_result else 0
    
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

@chat_bp.route('', methods=['POST'])
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

@chat_bp.route('/<int:conversation_id>', methods=['PUT'])
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

@chat_bp.route('/<int:conversation_id>', methods=['DELETE'])
@require_auth
def delete_conversation(conversation_id):
    """删除对话"""
    if not verify_resource_ownership('conversations', conversation_id, request.current_user_id):
        return error_response('对话不存在或无权限', 'NOT_FOUND', 404)
    
    # 删除对话相关记忆
    agent_service.delete_conversation_memories(request.current_user_id, conversation_id)
    
    execute_update('DELETE FROM conversations WHERE id = ?', (conversation_id,))
    return success_response(None, '对话删除成功')

@chat_bp.route('/batch', methods=['DELETE'])
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

@chat_bp.route('/<int:conversation_id>/messages', methods=['GET'])
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
    total_result = execute_query('SELECT COUNT(*) as count FROM messages WHERE conversation_id = ?', (conversation_id,))
    total = total_result[0]['count'] if total_result else 0
    return success_response({
        'messages': [dict(m) for m in messages],
        'pagination': {
            'page': page,
            'limit': limit,
            'total': total,
            'total_pages': (total + limit - 1) // limit
        }
    })

@chat_bp.route('/<int:conversation_id>/messages', methods=['POST'])
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

@chat_bp.route('/<int:conversation_id>/messages/stream', methods=['POST'])
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

@chat_bp.route('/<int:conversation_id>/messages/<int:message_id>', methods=['PUT'])
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
    if len(content) > current_app.config['MAX_MESSAGE_LENGTH']:
        return error_response(f'消息内容长度不能超过{current_app.config["MAX_MESSAGE_LENGTH"]}个字符', 'VALIDATION_ERROR', 400)
    
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

@chat_bp.route('/<int:conversation_id>/messages/<int:message_id>', methods=['DELETE'])
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