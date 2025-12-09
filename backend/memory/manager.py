
from mem0 import Memory
from .config import get_mem0_config
from typing import List, Dict, Any, Optional

class MemoryManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MemoryManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        config = get_mem0_config()
        self.memory = Memory.from_config(config)
        self._initialized = True

    def add_memory(self, content: str | List[Dict[str, str]], user_id: str, run_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Adds a memory or a list of messages to the memory store.
        
        Args:
            content: The text content or list of messages (chat history) to add.
            user_id: The unique identifier for the user.
            run_id: Optional unique identifier for the conversation/session (provides session isolation).
            metadata: Optional dictionary of metadata to attach.
            
        Returns:
            The result from mem0.add()
        """
        params = {"user_id": user_id}
        if run_id:
            params["run_id"] = run_id
        if metadata:
            params["metadata"] = metadata

        return self.memory.add(content, **params)

    def get_memories(self, user_id: str, run_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Retrieves all memories for a specific user (and optionally a specific run).
        
        Args:
            user_id: The unique identifier for the user.
            run_id: Optional unique identifier for the conversation/session.
            limit: Maximum number of memories to return.
            
        Returns:
            List of memory objects.
        """
        params = {"user_id": user_id}
        if run_id:
            params["run_id"] = run_id
        # Note: mem0's get_all might have different signatures depending on version, 
        # but generally supports filtering by user_id/run_id.
        # Current mem0 docs suggest using get_all(user_id=..., run_id=...)
        
        return self.memory.get_all(limit=limit, **params)

    def search_memories(self, query: str, user_id: str, run_id: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Searches for memories relevant to the query.
        
        Args:
            query: The search query string.
            user_id: The unique identifier for the user.
            run_id: Optional unique identifier for the conversation/session.
            limit: Maximum number of results to return.
            
        Returns:
            List of relevant memory objects with scores.
        """
        params = {"user_id": user_id, "limit": limit}
        if run_id:
            params["run_id"] = run_id
            
        return self.memory.search(query, **params)

    def update_memory(self, memory_id: str, new_data: str) -> Dict[str, Any]:
        """
        Updates a specific memory.
        
        Args:
            memory_id: The ID of the memory to update.
            new_data: The new text content for the memory.
            
        Returns:
            The result of the update operation.
        """
        return self.memory.update(memory_id, new_data)

    def delete_memory(self, memory_id: str) -> Dict[str, Any]:
        """
        Deletes a specific memory.
        
        Args:
            memory_id: The ID of the memory to delete.
            
        Returns:
            The result of the delete operation.
        """
        return self.memory.delete(memory_id)

    def delete_all_memories(self, user_id: str, run_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Deletes all memories for a user (and optionally a specific run).
        
        Args:
            user_id: The unique identifier for the user.
            run_id: Optional unique identifier for the conversation/session.
            
        Returns:
            The result of the delete operation.
        """
        params = {"user_id": user_id}
        if run_id:
            params["run_id"] = run_id
            
        return self.memory.delete_all(**params)

    def get_graph(self, user_id: str, run_id: Optional[str] = None):
        """
        Returns the graph structure if graph store is enabled.
        This depends on Mem0's specific graph retrieval implementation which might be evolving.
        Typically we rely on search to traverse the graph, but if specific graph export is needed,
        we might need to query the Neo4j driver directly if Mem0 doesn't expose a 'dump_graph' method yet.
        
        For now, we'll assume basic interaction via search is the primary graph usage.
        """
        pass
