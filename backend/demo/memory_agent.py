#!/usr/bin/env python3
"""
记忆代理系统 - 基于mem0官方SDK的实现
参考: https://docs.mem0.ai/cookbooks/integrations/agents-sdk-tool
支持自托管模式和工具调用机制
"""

import json
import logging
from typing import Optional, Dict, List, Any
from dataclasses import dataclass

from config import MEM0_CONFIG
from mem0 import Memory
from openai import OpenAI

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class MemoryOperation:
    """记忆操作结果"""
    success: bool
    message: str
    data: Any = None


class MemoryToolManager:
    """
    记忆工具管理器 - 管理所有记忆相关的工具函数
    这些工具可以被LLM调用来实现自动化的记忆管理
    """

    def __init__(self, llm_config: Dict = None):
        """
        初始化记忆工具管理器

        Args:
            llm_config: LLM配置，如果为None则使用MEM0_CONFIG中的配置
        """
        self.llm_config = llm_config or MEM0_CONFIG
        self.memory = Memory.from_config(self.llm_config)
        self._operation_history: List[MemoryOperation] = []

        # 定义所有可用的工具
        self.tools = self._define_tools()

    def _define_tools(self) -> List[Dict]:
        """
        定义所有可供LLM调用的工具函数

        Returns:
            工具定义列表（符合OpenAI Function Calling格式）
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "add_memory",
                    "description": "向记忆系统添加新的记忆。当用户提供关于自己的信息时，应该调用此工具来存储这些信息。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "要存储的记忆内容。应该是关于用户的事实信息，例如：'用户叫张三，来自北京，是一名工程师'"
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
                    "description": "在记忆系统中搜索相关记忆。当需要查找关于用户的信息时调用此工具。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "搜索查询，例如：'用户的工作是什么？' 或 '用户的兴趣爱好'"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "返回结果的最大数量，默认为5",
                                "default": 5
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_memory",
                    "description": "从记忆系统中删除特定的记忆。需要先通过search_memories或get_all_memories获取记忆ID，然后才能删除。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "memory_id": {
                                "type": "string",
                                "description": "要删除的记忆的UUID（唯一标识符），通常是一个UUID字符串，例如：'0ec3af98-1b41-47c6-9704-9163f333153e'。必须从search_memories或get_all_memories的结果中获取。"
                            }
                        },
                        "required": ["memory_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_all_memories",
                    "description": "获取存储的所有记忆。用于查看完整的记忆列表。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "返回的最大记忆数量，默认为20",
                                "default": 20
                            }
                        },
                        "required": []
                    }
                }
            },
        ]

    def add_memory(self, content: str, user_id: str = "default_user") -> MemoryOperation:
        """
        添加记忆

        Args:
            content: 记忆内容
            user_id: 用户ID

        Returns:
            MemoryOperation 对象
        """
        try:
            logger.info(f"添加记忆: {content[:50]}...")
            result = self.memory.add(
                messages=[{"role": "user", "content": content}],
                user_id=user_id
            )
            
            operation = MemoryOperation(
                success=True,
                data=result,
                message=f"成功添加记忆，提取了 {len(result.get('results', []))} 条信息"
            )
            self._operation_history.append(operation)
            return operation
        except Exception as e:
            logger.error(f"添加记忆失败: {str(e)}")
            operation = MemoryOperation(
                success=False,
                data=None,
                message=f"添加记忆失败: {str(e)}"
            )
            self._operation_history.append(operation)
            return operation

    def search_memories(
        self, query: str, limit: int = 5, user_id: str = "default_user"
    ) -> MemoryOperation:
        """
        搜索记忆

        Args:
            query: 搜索查询
            limit: 返回结果数量限制
            user_id: 用户ID

        Returns:
            MemoryOperation 对象
        """
        try:
            logger.info(f"搜索记忆: {query}")
            result = self.memory.search(
                query=query,
                user_id=user_id,
                limit=limit
            )
            
            # 处理结果格式
            memories = result.get("results", []) if isinstance(result, dict) else result
            
            operation = MemoryOperation(
                success=True,
                data=memories,
                message=f"找到 {len(memories)} 条相关记忆"
            )
            self._operation_history.append(operation)
            return operation
        except Exception as e:
            logger.error(f"搜索记忆失败: {str(e)}")
            operation = MemoryOperation(
                success=False,
                data=None,
                message=f"搜索记忆失败: {str(e)}"
            )
            self._operation_history.append(operation)
            return operation

    def delete_memory(self, memory_id: str, user_id: str = "default_user") -> MemoryOperation:
        """
        删除记忆

        Args:
            memory_id: 记忆ID
            user_id: 用户ID（仅用于参数一致性，mem0.delete()不需要此参数）

        Returns:
            MemoryOperation 对象
        """
        try:
            logger.info(f"删除记忆: {memory_id}")
            # mem0的delete方法只接受memory_id
            result = self.memory.delete(memory_id=memory_id)
            
            operation = MemoryOperation(
                success=True,
                data=result,
                message="记忆删除成功"
            )
            self._operation_history.append(operation)
            return operation
        except Exception as e:
            logger.error(f"删除记忆失败: {str(e)}")
            operation = MemoryOperation(
                success=False,
                data=None,
                message=f"删除记忆失败: {str(e)}"
            )
            self._operation_history.append(operation)
            return operation

    def get_all_memories(self, limit: int = 20, user_id: str = "default_user") -> MemoryOperation:
        """
        获取所有记忆

        Args:
            limit: 返回的最大数量
            user_id: 用户ID

        Returns:
            MemoryOperation 对象
        """
        try:
            logger.info(f"获取所有记忆 (limit={limit})")
            result = self.memory.get_all(user_id=user_id, limit=limit)
            
            # 处理结果格式
            memories = result.get("results", []) if isinstance(result, dict) else result
            
            operation = MemoryOperation(
                success=True,
                data=memories,
                message=f"共获取 {len(memories)} 条记忆"
            )
            self._operation_history.append(operation)
            return operation
        except Exception as e:
            logger.error(f"获取记忆失败: {str(e)}")
            operation = MemoryOperation(
                success=False,
                data=None,
                message=f"获取记忆失败: {str(e)}"
            )
            self._operation_history.append(operation)
            return operation

    def update_memory(
        self, old_content: str, new_content: str, user_id: str = "default_user"
    ) -> MemoryOperation:
        """
        更新记忆（通过删除旧的和添加新的）

        Args:
            old_content: 原始内容
            new_content: 新内容
            user_id: 用户ID

        Returns:
            MemoryOperation 对象
        """
        try:
            logger.info(f"更新记忆: {old_content[:30]}... -> {new_content[:30]}...")
            
            # 首先搜索要更新的记忆
            search_result = self.memory.search(
                query=old_content,
                user_id=user_id,
                limit=1
            )
            
            memories = search_result.get("results", []) if isinstance(search_result, dict) else search_result
            
            if not memories:
                operation = MemoryOperation(
                    success=False,
                    data=None,
                    message="未找到要更新的记忆"
                )
                self._operation_history.append(operation)
                return operation
            
            # 删除旧记忆并添加新记忆
            memory_id = memories[0].get("id")
            if memory_id:
                self.delete_memory(memory_id, user_id)
            
            result = self.add_memory(new_content, user_id)
            
            operation = MemoryOperation(
                success=True,
                data=result.data,
                message="记忆更新成功"
            )
            self._operation_history.append(operation)
            return operation
        except Exception as e:
            logger.error(f"更新记忆失败: {str(e)}")
            operation = MemoryOperation(
                success=False,
                data=None,
                message=f"更新记忆失败: {str(e)}"
            )
            self._operation_history.append(operation)
            return operation

    def process_tool_call(
        self, tool_name: str, tool_input: Dict, user_id: str = "default_user"
    ) -> str:
        """
        处理LLM调用的工具

        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数
            user_id: 用户ID

        Returns:
            工具执行结果的字符串表示
        """
        try:
            if tool_name == "add_memory":
                result = self.add_memory(tool_input["content"], user_id)
            elif tool_name == "search_memories":
                result = self.search_memories(
                    tool_input["query"],
                    tool_input.get("limit", 5),
                    user_id
                )
            elif tool_name == "delete_memory":
                result = self.delete_memory(tool_input["memory_id"], user_id)
            elif tool_name == "get_all_memories":
                result = self.get_all_memories(tool_input.get("limit", 20), user_id)
            elif tool_name == "update_memory":
                result = self.update_memory(
                    tool_input["old_content"],
                    tool_input["new_content"],
                    user_id
                )
            else:
                return f"未知的工具: {tool_name}"
            
            # 格式化结果
            if result.success:
                # 处理两种可能的数据格式：dict with "results" key 或 直接是list
                items = []
                if isinstance(result.data, dict) and "results" in result.data:
                    items = result.data["results"]
                elif isinstance(result.data, list):
                    items = result.data
                
                # 如果有结果项，格式化显示
                if items and isinstance(items, list) and len(items) > 0:
                    formatted_items = []
                    for item in items[:3]:  # 只显示前3项
                        if isinstance(item, dict):
                            memory_id = item.get("id", "unknown")
                            content = item.get("memory", item.get("content", str(item)))
                            # 将memory_id包含在格式化输出中，以便LLM可以看到
                            formatted_items.append(f"- [ID: {memory_id}] {content[:80]}")
                        else:
                            formatted_items.append(f"- {str(item)[:100]}")
                    return f"{result.message}\n" + "\n".join(formatted_items)
                return result.message
            else:
                return f"操作失败: {result.message}"
        except Exception as e:
            logger.error(f"处理工具调用失败: {str(e)}")
            return f"处理工具调用失败: {str(e)}"


class ConversationalMemoryAgent:
    """
    对话式记忆代理 - 使用LLM和工具来进行自然的对话和记忆管理
    """

    def __init__(self, llm_api_key: str = None, llm_base_url: str = None, model: str = None):
        """
        初始化对话式记忆代理

        Args:
            llm_api_key: LLM API密钥
            llm_base_url: LLM API基础URL
            model: LLM模型名称
        """
        # 初始化LLM客户端
        self.llm_api_key = llm_api_key or MEM0_CONFIG["llm"]["config"]["api_key"]
        self.llm_base_url = llm_base_url or MEM0_CONFIG["llm"]["config"]["openai_base_url"]
        self.model = model or MEM0_CONFIG["llm"]["config"]["model"]
        
        self.client = OpenAI(
            api_key=self.llm_api_key,
            base_url=self.llm_base_url
        )
        
        # 初始化记忆工具管理器
        self.tool_manager = MemoryToolManager()
        
        # 对话历史
        self.conversation_history: List[Dict] = []
        self.user_id = "default_user"

    def _build_system_prompt(self) -> str:
        """构建系统提示"""
        return """你是一个有帮助的AI助手，具有记忆管理能力。

你可以使用以下工具来管理用户的记忆：
1. add_memory - 添加新的记忆
2. search_memories - 搜索相关记忆
3. delete_memory - 删除记忆（需要使用从search_memories或get_all_memories返回的ID）
4. get_all_memories - 获取所有记忆
5. update_memory - 更新记忆

**关键指导原则：**
- 当用户提供关于自己的信息（如姓名、职业、兴趣、经历等）时，主动使用 add_memory 工具来存储这些信息
- 当用户询问关于他们自己的问题时，先使用 search_memories 工具来查找相关记忆
- 不要对用户说"我没有你的信息"，而是使用 search_memories 工具来查找
- **删除记忆时的正确流程**：
  1. 先调用 search_memories 或 get_all_memories 查找要删除的记忆
  2. 从返回结果中获取记忆的ID（格式为 UUID）
  3. 使用 delete_memory 工具并传入正确的 memory_id（不是记忆内容，而是ID！）
- 保持对话自然流畅，在必要时才明确提及使用了记忆工具
- 大多数情况下，用户更新信息时，直接使用 add_memory 会自动处理更新，无需显式删除
- 定期总结用户的信息以保持准确性

**重要提示：delete_memory 的 memory_id 参数必须是从搜索结果中获取的 UUID，不能是记忆的文本内容！**

记住：用户希望通过对话来管理记忆，而不是手动操作。因此要主动、智能地使用这些工具。"""

    def chat(self, user_message: str) -> str:
        """
        进行对话并自动处理记忆管理

        Args:
            user_message: 用户消息

        Returns:
            助手回复
        """
        # 添加用户消息到历史
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        max_iterations = 5
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            logger.info(f"对话迭代 {iteration}/{max_iterations}")

            # 构建消息列表（包括系统提示，直接添加到消息中）
            messages = [
                {"role": "system", "content": self._build_system_prompt()}
            ] + self.conversation_history

            try:
                # 调用LLM
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=self.tool_manager.tools,
                    tool_choice="auto",
                    temperature=0.7,
                    max_tokens=1500
                )

                # 检查响应
                choice = response.choices[0]
                
                # 如果LLM要求调用工具
                if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                    tool_calls = choice.message.tool_calls
                    
                    # 添加LLM的回复到历史（包含工具调用）
                    assistant_message = {
                        "role": "assistant",
                        "content": choice.message.content or ""
                    }
                    
                    # 正确的方式：将tool_calls添加到assistant消息
                    if tool_calls:
                        assistant_message["tool_calls"] = [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments
                                }
                            }
                            for tc in tool_calls
                        ]
                    
                    self.conversation_history.append(assistant_message)
                    
                    # 处理工具调用并收集结果
                    for tool_call in tool_calls:
                        tool_name = tool_call.function.name
                        tool_input = json.loads(tool_call.function.arguments)

                        logger.info(f"调用工具: {tool_name}, 参数: {tool_input}")

                        # 执行工具
                        tool_result = self.tool_manager.process_tool_call(
                            tool_name, tool_input, self.user_id
                        )
                        
                        # 添加工具结果到历史
                        self.conversation_history.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": tool_result
                        })
                    
                    # 继续循环，让LLM基于工具结果生成最终回复
                    continue

                else:
                    # LLM返回最终消息
                    final_message = choice.message.content
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": final_message
                    })
                    return final_message

            except Exception as e:
                logger.error(f"对话处理失败: {str(e)}", exc_info=True)
                error_message = f"处理请求时出错: {str(e)}"
                self.conversation_history.append({
                    "role": "assistant",
                    "content": error_message
                })
                return error_message

        # 超过最大迭代次数
        error_message = "对话过程中达到最大迭代次数"
        self.conversation_history.append({
            "role": "assistant",
            "content": error_message
        })
        return error_message

    def get_conversation_history(self) -> List[Dict]:
        """获取对话历史"""
        return self.conversation_history

    def clear_history(self):
        """清除对话历史"""
        self.conversation_history = []
        logger.info("对话历史已清除")

    def set_user_id(self, user_id: str):
        """设置用户ID"""
        self.user_id = user_id
        self.tool_manager.memory = Memory.from_config(MEM0_CONFIG)
        logger.info(f"用户ID已设置为: {user_id}")
