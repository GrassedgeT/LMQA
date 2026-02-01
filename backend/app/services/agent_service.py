# backend/app/services/agent_service.py

import json
import logging
import concurrent.futures
import re
from typing import List, Dict, Optional, Union, Any
from flask import current_app

try:
    from memory.manager import MemoryManager
except ImportError:
    import sys
    import os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
    from memory.manager import MemoryManager

from ..core.utils import decrypt_api_key
from ..core.db import execute_query
from openai import OpenAI

logger = logging.getLogger(__name__)

class AgentService:
    """智能体服务 - Graph RAG (Vector + Graph) + 全域同步一致性删除"""
    
    def __init__(self):
        self.memory_manager = None
        self.agent_service_url = None

    def init_app(self, app):
        self.agent_service_url = app.config.get('AGENT_SERVICE_URL')
        try:
            self.memory_manager = MemoryManager()
            logger.info("MemoryManager initialized successfully via init_app")
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
            client = OpenAI(api_key=model_config['api_key'], base_url=model_config['base_url'])
            return client, model_config['model_name'], model_config
        except Exception as e:
            logger.error(f'创建 LLM Client 失败: {str(e)}')
            return None, None, None

    def warm_up_for_user(self, user_id: int):
        try:
            config = self._get_user_model_config(user_id)
            if self.memory_manager: self.memory_manager.warm_up_client(config)
        except: pass

    # =========================================================================
    # 1. 工具定义
    # =========================================================================
    def _get_tools(self) -> List[Dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "add_local_memory",
                    "description": "【存局部】保存仅与当前对话相关的细节。",
                    "parameters": {
                        "type": "object",
                        "properties": {"content": {"type": "string", "description": "记忆内容"}},
                        "required": ["content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "add_global_memory",
                    "description": "【存全局】保存用户的永久性事实。系统会自动更新知识图谱。",
                    "parameters": {
                        "type": "object",
                        "properties": {"content": {"type": "string", "description": "记忆内容"}},
                        "required": ["content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_local_memories",
                    "description": "【搜局部】同时返回文本记忆和图谱关系。",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string", "description": "搜索关键词"}},
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_global_memories",
                    "description": "【搜全局】同时返回文本记忆和图谱关系。",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string", "description": "搜索关键词"}},
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_memory",
                    "description": "【删除记忆】用户要求'忘记'或'删除'时使用。会同时清理向量和图谱。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string", "description": "要删除的具体事实描述"}
                        },
                        "required": ["content"]
                    }
                }
            }
        ]

    # =========================================================================
    # 2. System Prompt
    # =========================================================================
    def _build_system_prompt(self) -> str:
        return """你是一个拥有双层记忆系统的智能助手。

**记忆架构：**
1. **局部记忆**：当前对话上下文。
2. **全局记忆**：用户长期画像。

**能力说明：**
- 你的搜索结果包含 **文本 (Vector)** 和 **图谱 (Graph)**。请结合两者回答。
- **图谱优先**：如果文本记录被删了，但图谱里还有关系，说明记忆可能未清除干净，请以图谱信息为辅助参考，但如果图谱显示"Unknown"则表示确实不知道。

**操作策略：**
1. **存储 (Add)**：全量存储。
2. **修正 (Correction)**：信息变更时，直接用 `add` 覆盖。
3. **删除 (Delete)**：用户明确要求删除时调用。
4. **搜索 (Search)**：先搜局部，再搜全局。
"""

    # =========================================================================
    # 3. 工具执行 (全域同步修复版)
    # =========================================================================
    def _execute_tool(self, tool_name: str, tool_args: Dict, user_id: int, conversation_id: int, llm_settings: Dict) -> str:
        logger.info(f"🔧 Agent 执行工具: {tool_name} | 参数: {tool_args}")
        if not self.memory_manager: return "错误：记忆模块未初始化。"

        try:
            def parse_search_result(res):
                vectors = []
                relations = []
                raw_list = []
                if isinstance(res, dict): raw_list = res.get("results", []) or []
                elif isinstance(res, list): raw_list = res
                
                for m in raw_list:
                    if isinstance(m, dict):
                        vectors.append({"id": m.get("id"), "content": m.get("memory") or m.get("text") or str(m)})
                    elif isinstance(m, str):
                        vectors.append({"content": m})

                if isinstance(res, dict) and "relations" in res:
                    for rel in res["relations"]:
                        src = rel.get("source")
                        rel_type = rel.get("relationship")
                        dst = rel.get("destination")
                        if src and rel_type and dst:
                            relations.append(f"{src} --[{rel_type}]--> {dst}")
                return vectors, relations

            # --- 删除逻辑 ---
            if tool_name == "delete_memory":
                query_content = tool_args["content"]
                
                # A. 搜索 (包含局部和全局，且不丢弃图谱)
                candidates = []
                # 搜局部
                local_raw = self.memory_manager.search_memories(query=query_content, user_id=str(user_id), run_id=str(conversation_id), scope='local', limit=10, llm_settings=llm_settings)
                vecs_local, rels_local = parse_search_result(local_raw) # [修复1] 之前是 _，现在捕获 relations
                for v in vecs_local: 
                    if 'id' in v: candidates.append({"id": v['id'], "content": v['content'], "scope": "局部"})
                # 把图谱关系也加进去，让 LLM 知道虽然向量没了但图还在
                for r in rels_local:
                    candidates.append({"id": "graph_only", "content": f"[局部图谱残留] {r}", "scope": "局部"})

                # 搜全局
                global_raw = self.memory_manager.search_memories(query=query_content, user_id=str(user_id), run_id=None, scope='global', limit=10, llm_settings=llm_settings)
                vecs_global, rels_global = parse_search_result(global_raw)
                for v in vecs_global: 
                    if 'id' in v: candidates.append({"id": v['id'], "content": v['content'], "scope": "全局"})
                for r in rels_global:
                    candidates.append({"id": "graph_only", "content": f"[全局图谱残留] {r}", "scope": "全局"})

                if not candidates: return f"未找到与 '{query_content}' 相关的记忆。"

                # B. 审查
                reviewer_client = OpenAI(api_key=llm_settings['api_key'], base_url=llm_settings['base_url'])
                review_prompt = f"""
                用户指令：删除 "{query_content}"
                候选记忆：
                {json.dumps(candidates, ensure_ascii=False, indent=2)}
                
                请判断哪些条目必须删除？（仅删除事实匹配的）。
                返回ID列表 JSON，如 ["id1"]。
                注意：如果是 [图谱残留] 条目，不需要返回ID（因为它没法直接删），但这意味着我们需要执行重置操作。
                """
                try:
                    review_res = reviewer_client.chat.completions.create(
                        model=llm_settings['model_name'], messages=[{"role": "user", "content": review_prompt}], temperature=0
                    )
                    review_content = review_res.choices[0].message.content
                    if "```" in review_content: review_content = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', review_content, re.DOTALL).group(1)
                    ids_to_delete = json.loads(review_content)
                except: ids_to_delete = []

                # C. 物理删除 (删除 Vector)
                deleted_contents = []
                for mem_id in ids_to_delete:
                    if mem_id == "graph_only": continue # 跳过虚拟ID
                    target = next((c for c in candidates if c['id'] == mem_id), None)
                    if target:
                        self.memory_manager.delete_memory(mem_id, llm_settings=llm_settings)
                        deleted_contents.append(target['content'])

                # D. 图谱重置 (全域同步修复)
                # 只要删除了东西，或者 LLM 实际上是想删但只能通过重置来解决图谱残留
                if deleted_contents or (candidates and not ids_to_delete):
                    neutralize_prompt = f"""
                    你是一个知识图谱修复专家。用户刚刚删除了关于 "{query_content}" 的信息。
                    
                    为了切断图谱中的旧连接，你需要生成一条“重置声明”。
                    
                    【绝对规则】
                    1. **主语必须是“用户”**：严禁在声明中再次提及被删除的具体名字或实体！
                    2. **仅重置被删属性**：只重置被删除的那一项属性。
                    
                    示例：删除了“我叫张三” -> 输出：“用户的名字未知”
                    示例：删除了“我住在北京” -> 输出：“用户的居住地未知”
                    
                    请生成这句重置声明，不要任何其他废话。
                    """
                    try:
                        neutralize_res = reviewer_client.chat.completions.create(
                            model=llm_settings['model_name'], messages=[{"role": "user", "content": neutralize_prompt}], temperature=0
                        )
                        neutral_statement = neutralize_res.choices[0].message.content.strip()
                        
                        # [关键修复 2] 1. 重置全局 (Global)
                        self.memory_manager.add_memory(
                            content=neutral_statement,
                            user_id=str(user_id),
                            run_id=None,
                            scope='global',
                            metadata={"type": "graph_reset", "source": "delete_tool"},
                            llm_settings=llm_settings
                        )
                        logger.info(f"🔄 图谱重置执行 (Global): {neutral_statement}")

                        # [关键修复 2] 2. 重置局部 (Local) - 这样局部图谱的旧连接也会被 Unknown 覆盖
                        if conversation_id:
                            self.memory_manager.add_memory(
                                content=neutral_statement,
                                user_id=str(user_id),
                                run_id=str(conversation_id),
                                scope='local',
                                metadata={"type": "graph_reset", "source": "delete_tool"},
                                llm_settings=llm_settings
                            )
                            logger.info(f"🔄 图谱重置执行 (Local): {neutral_statement}")

                    except Exception as e:
                        logger.error(f"图谱重置失败: {e}")

                return f"已删除 {len(deleted_contents)} 条记忆，并同步更新了知识图谱状态。"

            # --- 存/取逻辑 ---
            scope = 'local' if 'local' in tool_name else 'global'
            run_id = str(conversation_id) if scope == 'local' else None
            metadata = {"source_conversation_id": str(conversation_id)} if scope == 'global' else None

            if "add" in tool_name:
                self.memory_manager.add_memory(content=tool_args["content"], user_id=str(user_id), run_id=run_id, scope=scope, metadata=metadata, llm_settings=llm_settings)
                return f"{'局部' if scope=='local' else '全局'}记忆已添加。"

            elif "search" in tool_name:
                res = self.memory_manager.search_memories(query=tool_args["query"], user_id=str(user_id), run_id=run_id, scope=scope, limit=5, llm_settings=llm_settings)
                
                logger.info(f"🔎 [RAW Search Result] ({scope}): {res}")
                vectors, relations = parse_search_result(res)
                
                output_data = {
                    "relevant_memories": [v['content'] for v in vectors],
                    "knowledge_graph_connections": relations
                }
                
                final_output = f"{'局部' if scope=='local' else '全局'}搜索结果: {json.dumps(output_data, ensure_ascii=False)}"
                logger.info(f"📤 [To LLM]: {final_output}")
                return final_output
            
            return f"未知工具: {tool_name}"

        except Exception as e:
            logger.error(f"工具执行异常: {e}", exc_info=True)
            return f"工具执行出错: {str(e)}"

    # Agent Loop (保持不变)
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
                response = client.chat.completions.create(model=model_name, messages=messages, tools=tools, tool_choice="auto", temperature=0.7)
                response_message = response.choices[0].message
                if response_message.tool_calls:
                    messages.append(response_message)
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        futures = []
                        for tool_call in response_message.tool_calls:
                            function_name = tool_call.function.name
                            try: arguments = json.loads(tool_call.function.arguments)
                            except: arguments = {}
                            future = executor.submit(self._execute_tool, function_name, arguments, user_id, conversation_id, llm_settings)
                            futures.append((tool_call, future))
                        for tool_call, future in futures:
                            tool_result = future.result()
                            messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": tool_call.function.name, "content": tool_result})
                    current_turn += 1
                else: return response_message.content
            except Exception as e: return f"处理错误: {str(e)}"
        return "思考超时。"
        
    # 兼容方法
    def delete_conversation_memories(self, *args): pass
    def search_memories(self, *args, **kwargs): return []
    def sync_memory(self, *args, **kwargs): return {}
    def update_memory(self, *args, **kwargs): pass
    def delete_memory(self, *args, **kwargs): pass
    def add_interaction(self, *args, **kwargs): pass
    def _process_message_stream_local(self, *args, **kwargs): pass

agent_service = AgentService()