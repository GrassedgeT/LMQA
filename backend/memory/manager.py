# backend/memory/manager.py

import json
import hashlib
import time
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
        # 确保字典排序后 hash 一致
        return hashlib.md5(json.dumps(llm_settings, sort_keys=True).encode()).hexdigest()

    def _get_client(self, llm_settings: Optional[Dict] = None):
        config_hash = self._get_config_hash(llm_settings)
        if config_hash in self._clients:
            return self._clients[config_hash]

        logger.info(f"⚡ 初始化 Mem0 客户端 (Hash: {config_hash})")
        config = get_mem0_config(llm_settings)
        
        # 记录 reranker 配置状态
        if 'reranker' in config:
            reranker_provider = config['reranker'].get('provider', 'unknown')
            logger.info(f"✅ Reranker 已配置: provider={reranker_provider}")
        else:
            logger.info(f"ℹ️ Reranker 未配置")
        
        client = Memory.from_config(config)
        self._clients[config_hash] = client
        return client

    def warm_up_client(self, llm_settings: Dict):
        try:
            self._get_client(llm_settings)
            logger.info("✅ Mem0 客户端预热完成")
        except Exception as e:
            logger.error(f"❌ 预热失败: {e}")

    def add_memory(self, content: str, user_id: str, run_id: Optional[str] = None, metadata: Optional[Dict] = None, llm_settings: Optional[Dict] = None) -> Dict:
        """
        添加记忆：
        1. 强制 run_id=None (存为全局，保证图谱 Entity 唯一性)
        2. 将 conversation_id 存入 metadata
        3. 遇到 Qdrant 404 自动重试
        """
        client = self._get_client(llm_settings)
        
        params = {"user_id": user_id}
        
        # 将 run_id 转移到 metadata
        final_metadata = metadata or {}
        if run_id:
            final_metadata["source_conversation_id"] = str(run_id)
        if final_metadata:
            params["metadata"] = final_metadata

        # 包装消息，确保 Mem0 正确提取图谱
        messages = [{"role": "user", "content": content}]

        try:
            # 关键：这里不传 run_id 参数给 Mem0
            return client.add(messages, **params)
        except Exception as e:
            # 404 自动修复逻辑 (针对 Qdrant Collection 不存在的情况)
            error_str = str(e)
            if "404" in error_str or "Not found" in error_str:
                logger.warning(f"⚠️ 集合丢失，尝试重建客户端并重试: {e}")
                # 清除缓存
                config_hash = self._get_config_hash(llm_settings)
                if config_hash in self._clients:
                    del self._clients[config_hash]
                # 重新获取 client 并重试
                client = self._get_client(llm_settings)
                return client.add(messages, **params)
            raise e

    def search_memories(self, query: str, user_id: str, run_id: Optional[str] = None, limit: int = 5, llm_settings: Optional[Dict] = None, rerank: bool = True) -> List[Dict]:
        """
        搜索记忆
        
        Args:
            query: 搜索查询
            user_id: 用户 ID
            run_id: 对话 ID（可选）
            limit: 返回数量限制
            llm_settings: LLM 配置
            rerank: 是否启用 reranker 重排序（默认 True）
        
        Returns:
            搜索结果列表，如果启用 reranker，结果会按相关性重新排序
        """
        params = {"user_id": user_id, "limit": limit, "rerank": rerank}
        logger.info(f"🔍 搜索记忆: query='{query}', user_id={user_id}, rerank={rerank}")
        
        results = self._get_client(llm_settings).search(query, **params)
        
        # 检查 reranker 是否生效（结果中是否有 rerank_score）
        # if results and isinstance(results, list) and len(results) > 0:
        #     first_result = results[0]
        #     if isinstance(first_result, dict) and 'rerank_score' in first_result:
        #         logger.info(f"✅ Reranker 生效! 返回 {len(results)} 条结果，首条 rerank_score={first_result.get('rerank_score'):.4f}")
        #     else:
        #         logger.info(f"📋 搜索完成，返回 {len(results)} 条结果 (无 rerank_score，可能 reranker 未配置或未启用)")
        # else:
        #     logger.info(f"📋 搜索完成，返回 0 条结果")
        
        return results

    def get_memories(self, user_id: str, run_id: Optional[str] = None, limit: int = 100, llm_settings: Optional[Dict] = None) -> Dict[str, Any]:
        """
        [关键修复] 获取记忆列表
        1. 获取 run_id=None 的全局记忆
        2. 过滤 results (Python 过滤)
        3. 透传 relations (图数据) <--- 本次新增
        """
        client = self._get_client(llm_settings)
        
        try:
            # 1. 拉取所有数据
            all_memories = client.get_all(user_id=user_id, limit=limit)
        except Exception as e:
            logger.error(f"Mem0 get_all 异常: {e}")
            return {"results": [], "relations": []}

        if all_memories is None:
            return {"results": [], "relations": []}

        # 2. 解析结构
        # Mem0 v1.x 典型结构: {'results': [...], 'relations': [...]}
        if isinstance(all_memories, dict):
            results = all_memories.get("results", []) or []
            relations = all_memories.get("relations", []) or []
        elif isinstance(all_memories, list):
            results = all_memories
            relations = []
        else:
            results = []
            relations = []

        # 3. 过滤 Results (向量记忆)
        target_run_id = str(run_id) if run_id is not None else None
        
        # 如果查看全部，直接返回
        if not target_run_id or target_run_id == "0":
            return {"results": results, "relations": relations}

        # 如果查看特定对话，过滤 results
        filtered_results = []
        for mem in results:
            if not isinstance(mem, dict): continue
            meta = mem.get("metadata", {}) or {}
            source_id = str(meta.get("source_conversation_id", ""))
            
            if source_id == target_run_id:
                filtered_results.append(mem)
        
        # 注意：对于 relations (图数据)，Mem0 通常返回的是全局关系。
        # 即使是查看特定对话，展示相关的图谱关系也是有益的，所以我们不对 relations 进行强过滤
        # (除非我们在 metadata 里也存了 source_id 给 relations，但 Mem0 v1.x 可能不支持给边加 metadata)
        
        return {"results": filtered_results, "relations": relations}

    def update_memory(self, memory_id: str, new_data: str, llm_settings: Optional[Dict] = None) -> Dict:
        return self._get_client(llm_settings).update(memory_id, new_data)

    def delete_memory(self, memory_id: str, llm_settings: Optional[Dict] = None) -> Dict:
        return self._get_client(llm_settings).delete(memory_id)

    def delete_all_memories(self, user_id: str, run_id: Optional[str] = None, llm_settings: Optional[Dict] = None) -> Dict:
        client = self._get_client(llm_settings)
        
        # 如果是删全库
        if not run_id:
            return client.delete_all(user_id=user_id)
        
        # 如果是删特定对话的记忆，先查 ID 再删
        # 复用我们修好的 get_memories 来找 ID
        memories_resp = self.get_memories(user_id, run_id, limit=1000, llm_settings=llm_settings)
        memories = memories_resp.get("results", [])
        
        count = 0
        for mem in memories:
            if "id" in mem:
                client.delete(mem["id"])
                count += 1
        
        return {"message": f"Deleted {count} memories for run_id {run_id}"}