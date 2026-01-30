#!/usr/bin/env python3
"""
交互式对话终端 - 允许用户与记忆代理进行自然对话
模拟前端对话流程，用于测试记忆管理功能
"""

import sys
import time
from typing import Optional
from dotenv import load_dotenv
from memory_agent import ConversationalMemoryAgent, MemoryToolManager
from mem0 import Memory
from config import MEM0_CONFIG

# 加载环境变量
load_dotenv()

class InteractiveChatUI:
    """交互式聊天界面"""

    def __init__(self):
        """初始化聊天界面"""
        self.agent: Optional[ConversationalMemoryAgent] = None
        self.tool_manager: Optional[MemoryToolManager] = None
        self.current_user = "default_user"
        self.session_messages = []

    def print_header(self):
        """打印欢迎标题"""
        print("\n" + "=" * 70)
        print("  🧠 记忆代理系统 - 交互式对话终端")
        print("=" * 70)
        print("\n欢迎使用记忆代理系统！")
        print("这是一个具有长期记忆能力的对话系统。")
        print("\n✨ 您可以：")
        print("   • 告诉我关于您的信息（姓名、职业、兴趣等）")
        print("   • 询问我关于您的任何事情")
        print("   • 让我更新或删除某些记忆")
        print("\n💡 系统会自动管理您的记忆，无需手动操作。")
        print("\n📝 命令列表：")
        print("   /quit 或 /exit     - 退出程序")
        print("   /clear             - 清除对话历史（但保留记忆）")
        print("   /user <name>       - 切换用户")
        print("   /memories          - 查看所有已保存的记忆")
        print("   /help              - 显示帮助信息")
        print("\n" + "=" * 70 + "\n")

    def print_separator(self):
        """打印分隔符"""
        print("-" * 70)

    def format_response(self, role: str, content: str, max_width: int = 68):
        """格式化输出"""
        if role == "user":
            prefix = "👤 您: "
            color_code = "\033[94m"  # 蓝色
        else:
            prefix = "🤖 助手: "
            color_code = "\033[92m"  # 绿色
        
        reset_code = "\033[0m"
        
        # 按行分割内容
        lines = content.split('\n')
        formatted_lines = []
        
        for line in lines:
            if len(line) <= max_width:
                formatted_lines.append(line)
            else:
                # 长行进行折行
                while len(line) > max_width:
                    formatted_lines.append(line[:max_width])
                    line = line[max_width:]
                if line:
                    formatted_lines.append(line)
        
        # 打印第一行（带前缀）
        if formatted_lines:
            print(f"{color_code}{prefix}{formatted_lines[0]}{reset_code}")
            # 打印后续行（不带前缀，缩进对齐）
            indent = " " * len(prefix)
            for line in formatted_lines[1:]:
                print(f"{color_code}{indent}{line}{reset_code}")
        
        self.print_separator()

    def show_memories(self):
        """显示所有记忆"""
        if not self.tool_manager:
            print("❌ 记忆系统未初始化")
            return

        print("\n📚 获取所有已保存的记忆...")
        result = self.tool_manager.get_all_memories(limit=20, user_id=self.current_user)
        
        if result.success:
            memories = result.data
            if memories:
                print(f"\n✅ 找到 {len(memories)} 条记忆：\n")
                for i, memory in enumerate(memories, 1):
                    memory_content = memory.get("memory", str(memory))
                    print(f"  {i}. {memory_content[:80]}")
                    if len(memory_content) > 80:
                        print(f"     {memory_content[80:160]}")
            else:
                print("\n📭 暂无保存的记忆")
        else:
            print(f"\n❌ 获取记忆失败: {result.message}")
        
        print()

    def show_help(self):
        """显示帮助信息"""
        help_text = """
📖 帮助信息：

【基本用法】
直接输入您的消息，系统会自动理解并管理您的记忆。

【关于记忆】
系统会在以下情况自动保存您的信息：
- 您告诉我您的名字、职业、兴趣等个人信息
- 您分享您的经历或故事
- 您提到您的偏好或习惯

【关于查询】
您可以询问任何关于您自己的事情，系统会：
- 在记忆库中搜索相关信息
- 根据保存的记忆生成准确的回答
- 保持对话的连贯性和上下文

【命令参考】
/quit 或 /exit      退出程序
/clear              清除当前对话历史
/user <name>        切换用户
/memories           查看所有保存的记忆
/help               显示此帮助信息

【示例对话】
用户: 我叫李明，今年25岁，我是一个Python开发工程师
→ 系统会自动保存这个信息

用户: 我现在住在深圳
→ 系统会添加或更新您的位置信息

用户: 我之前告诉你我是什么工作？
→ 系统会在记忆中查找并回答您

【提示】
💡 系统会根据对话内容自动判断何时保存、更新或删除记忆
💡 您的记忆会被持久化保存，即使关闭程序也会保留
💡 每个用户有独立的记忆空间
"""
        print(help_text)

    def switch_user(self, user_name: str):
        """切换用户"""
        if not user_name:
            print("❌ 请提供用户名")
            return
        
        self.current_user = user_name
        self.agent.set_user_id(user_name)
        self.session_messages = []
        print(f"✅ 已切换到用户: {user_name}")
        print(f"💡 该用户有独立的记忆空间\n")

    def initialize(self) -> bool:
        """初始化系统"""
        print("\n🔄 正在初始化记忆系统...")
        
        try:
            # 初始化对话代理
            self.agent = ConversationalMemoryAgent()
            # 使用agent内部的tool_manager，确保同步
            self.tool_manager = self.agent.tool_manager
            
            print("✅ 记忆系统初始化成功！")
            print(f"   使用模型: {self.agent.model}")
            print(f"   API地址: {self.agent.llm_base_url}")
            print(f"   当前用户: {self.current_user}\n")
            
            return True
        except Exception as e:
            print(f"❌ 初始化失败: {str(e)}")
            print("\n可能的原因：")
            print("1. LLM服务未运行（检查配置的API地址）")
            print("2. Qdrant向量数据库未运行")
            print("3. API密钥或配置不正确")
            print("\n请检查 backend/.env 文件中的配置")
            return False

    def process_command(self, user_input: str) -> bool:
        """处理特殊命令，返回是否继续"""
        user_input = user_input.strip()
        
        if not user_input.startswith('/'):
            return True
        
        command = user_input.lower().split()[0]
        args = user_input.split()[1:] if len(user_input.split()) > 1 else []
        
        if command in ['/quit', '/exit']:
            print("\n👋 谢谢使用记忆代理系统！再见！\n")
            return False
        
        elif command == '/clear':
            if self.agent:
                self.agent.clear_history()
                self.session_messages = []
            print("✅ 对话历史已清除")
            return True
        
        elif command == '/user':
            user_name = ' '.join(args) if args else None
            self.switch_user(user_name)
            return True
        
        elif command == '/memories':
            self.show_memories()
            return True
        
        elif command == '/help':
            self.show_help()
            return True
        
        else:
            print(f"❌ 未知命令: {command}")
            print("💡 输入 /help 查看所有命令")
            return True

    def run(self):
        """主对话循环"""
        self.print_header()
        
        # 初始化系统
        if not self.initialize():
            return

        print("📝 开始对话（输入 /help 查看命令列表）:\n")
        
        try:
            while True:
                try:
                    # 获取用户输入
                    user_input = input("👤 您: ").strip()
                    
                    if not user_input:
                        continue
                    
                    # 处理命令
                    if not self.process_command(user_input):
                        break
                    
                    # 如果是普通消息，调用代理
                    if not user_input.startswith('/'):
                        print("\n🤔 正在处理您的消息...\n")
                        
                        start_time = time.time()
                        response = self.agent.chat(user_input)
                        elapsed_time = time.time() - start_time
                        
                        # 格式化和显示响应
                        self.format_response("assistant", response)
                        
                        # 显示统计信息
                        print(f"⏱️  响应时间: {elapsed_time:.2f}秒")
                        print(f"💬 对话轮数: {len(self.agent.conversation_history) // 2}\n")
                
                except KeyboardInterrupt:
                    print("\n\n⚠️  对话被中断")
                    cont = input("是否继续？(y/n): ").strip().lower()
                    if cont != 'y':
                        print("\n👋 再见！\n")
                        break
                    print()
        
        except Exception as e:
            print(f"\n❌ 发生错误: {str(e)}")
            print("💡 请检查日志获取更多信息")
            import traceback
            traceback.print_exc()


def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("  🧠 记忆代理系统 - 交互式对话终端")
    print("=" * 70 + "\n")
    
    chat_ui = InteractiveChatUI()
    chat_ui.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 程序异常: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
