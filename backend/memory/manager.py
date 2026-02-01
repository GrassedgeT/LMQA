# backend/memory/manager.py

import json
import hashlib
import time
import os  # [必须导入]
from mem0 import Memory
from .config import get_mem0_config
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class MemoryManager:
    _instance = None
    _clients = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MemoryManager, cls).__new__(cls)
        return cls._instance

    def _get_config_hash(self, llm_settings: Dict) -> str:
        if not llm_settings: return "default"
        return hashlib.md5(json.dumps(llm_settings, sort_keys=True).encode()).hexdigest()

    def _get_client(self, llm_settings: Optional[Dict] = None):
        config_hash = self._get_config_hash(llm_settings)
        if config_hash in self._clients:
            return self._clients[config_hash]

        logger.info(f"⚡ 初始化 Mem0 客户端 (Hash: {config_hash})")
        
        # =========================================================
        # [核心修复] 强制设置环境变量 (Monkey Patch)
        # 解决 Mem0 Graph/Reranker 组件忽略配置回退到 OpenAI 官方接口的问题
        # =========================================================
        if llm_settings:
            base_url = llm_settings.get("base_url")
            api_key = llm_settings.get("api_key")
            model_name = str(llm_settings.get("model_name", "")).lower()
            
            # 1. 智能补全 DeepSeek URL (防止前端没传)
            if not base_url and "deepseek" in model_name:
                base_url = "https://api.deepseek.com"
                # 同时回写到 settings，保证 config.py 也能拿到
                llm_settings["base_url"] = base_url
            
            # 2. 强制注入环境变量 (核弹级修复)
            if base_url:
                os.environ["OPENAI_BASE_URL"] = base_url
                logger.info(f"🔧 [Environment] 强制设置 OPENAI_BASE_URL={base_url}")
            
            if api_key:
                os.environ["OPENAI_API_KEY"] = api_key
        # =========================================================

        config = get_mem0_config(llm_settings)
        
        # 记录配置状态
        if 'reranker' in config:
            logger.info(f"✅ Reranker: {config['reranker'].get('provider')}")
        else:
            logger.info(f"ℹ️ Reranker: Disabled")
        
        client = Memory.from_config(config)
        self._clients[config_hash] = client
        return client

    def warm_up_client(self, llm_settings: Dict):
        try:
            self._get_client(llm_settings)
            logger.info("✅ Mem0 客户端预热完成")
        except Exception as e:
            logger.error(f"❌ 预热失败: {e}")

    # --- 隔离逻辑 (保持不变) ---
    def _resolve_ids(self, user_id: str, run_id: Optional[str], scope: str) -> tuple:
        if scope == 'local':
            if not run_id:
                raise ValueError("Local memory requires a valid run_id")
            return f"{user_id}_conv_{run_id}", None
        return user_id, None

    # --- 核心操作 (保持不变，确保引用了最新的 _get_client) ---
    def add_memory(self, content: str, user_id: str, run_id: Optional[str] = None, scope: str = 'global', metadata: Optional[Dict] = None, llm_settings: Optional[Dict] = None) -> Dict:
        client = self._get_client(llm_settings)
        target_user_id, target_run_id = self._resolve_ids(user_id, run_id, scope)
        params = {"user_id": target_user_id}
        if target_run_id: params["run_id"] = target_run_id

        final_metadata = metadata or {}
        final_metadata["real_user_id"] = user_id
        if run_id: final_metadata["source_conversation_id"] = str(run_id)
        final_metadata["scope"] = scope
        params["metadata"] = final_metadata

        messages = [{"role": "user", "content": content}]
        try:
            return client.add(messages, **params)
        except Exception as e:
            if "404" in str(e) or "Not found" in str(e):
                logger.warning(f"⚠️ 集合丢失重试: {e}")
                config_hash = self._get_config_hash(llm_settings)
                if config_hash in self._clients: del self._clients[config_hash]
                client = self._get_client(llm_settings)
                return client.add(messages, **params)
            raise e

    def search_memories(self, query: str, user_id: str, run_id: Optional[str] = None, scope: str = 'global', limit: int = 5, llm_settings: Optional[Dict] = None) -> List[Dict]:
        client = self._get_client(llm_settings)
        target_user_id, target_run_id = self._resolve_ids(user_id, run_id, scope)
        params = {"user_id": target_user_id, "limit": limit}
        if target_run_id: params["run_id"] = target_run_id
        
        try:
            return client.search(query, **params)
        except Exception as e:
            logger.error(f"Mem0 Search Error: {e}")
            return []

    def get_memories(self, user_id: str, run_id: Optional[str] = None, limit: int = 100, llm_settings: Optional[Dict] = None) -> Dict[str, Any]:
        client = self._get_client(llm_settings)
        if run_id and str(run_id) != "0":
            target_user_id = f"{user_id}_conv_{run_id}"
        else:
            target_user_id = user_id
            
        try:
            all_memories = client.get_all(user_id=target_user_id, limit=limit)
        except Exception as e:
            logger.error(f"Mem0 get_all 异常: {e}")
            return {"results": [], "relations": []}

        if all_memories is None: return {"results": [], "relations": []}

        if isinstance(all_memories, dict):
            results = all_memories.get("results", []) or []
            relations = all_memories.get("relations", []) or []
        elif isinstance(all_memories, list):
            results = all_memories
            relations = []
        else:
            results, relations = [], []
        
        return {"results": results, "relations": relations}

    # ... update/delete ...
    def update_memory(self, memory_id: str, new_data: str, llm_settings: Optional[Dict] = None) -> Dict:
        return self._get_client(llm_settings).update(memory_id, new_data)

    def delete_memory(self, memory_id: str, llm_settings: Optional[Dict] = None) -> Dict:
        return self._get_client(llm_settings).delete(memory_id)

    def delete_all_memories(self, user_id: str, run_id: Optional[str] = None, llm_settings: Optional[Dict] = None) -> Dict:
        client = self._get_client(llm_settings)
        if run_id:
            target_user_id = f"{user_id}_conv_{run_id}"
            return client.delete_all(user_id=target_user_id)
        else:
            return client.delete_all(user_id=user_id)