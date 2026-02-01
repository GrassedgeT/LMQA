import logging
import json
import concurrent.futures
from typing import List, Dict, Optional
from flask import current_app

# Adjust imports based on project structure
# Assuming 'backend' is the root context when running
try:
    from memory.manager import MemoryManager
except ImportError:
    # Fallback if running from a different context, though conventions say we should run from root or backend
    import sys
    import os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
    from memory.manager import MemoryManager

from ..core.db import execute_query
from ..core.utils import decrypt_api_key

logger = logging.getLogger(__name__)

class AgentService:
    """智能体服务适配层 - 针对 DeepSeek 优化的 Agentic 模式"""
    
    def __init__(self):
        self.memory_manager = None
        self.agent_service_url = None

    def init_app(self, app):
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
                
                # Handle potential dict response (e.g. {'results': [...]})
                if isinstance(res, dict):
                    res_list = res.get("results", [])
                elif isinstance(res, list):
                    res_list = res
                else:
                    res_list = []

                memories = [m.get("memory", m.get("text", "")) for m in res_list if isinstance(m, dict)]
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
