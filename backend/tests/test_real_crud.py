import unittest
import time
import uuid
from unittest.mock import patch
from memory.manager import MemoryManager
from memory.config import get_mem0_config as real_get_config

class TestRealMemoryCRUD(unittest.TestCase):
    """
    Integration tests running against the REAL configured backend services 
    (Qdrant, Neo4j, Gemini, LLM).
    
    WARNING: This will read/write to the databases defined in your .env file.
    It uses a random user_id to attempt isolation, but always be careful.
    """

    @classmethod
    def setUpClass(cls):
        print("\n[Real-CRUD] Initializing MemoryManager with LIVE configuration (Test Collection)...")
        
        # Patch config to use a different collection name
        cls.config_patcher = patch('memory.manager.get_mem0_config')
        cls.mock_get_config = cls.config_patcher.start()
        
        # Get real config but modify collection name
        config = real_get_config()
        if 'vector_store' in config and 'config' in config['vector_store']:
            config['vector_store']['config']['collection_name'] = "mem0_test_crud"
        
        cls.mock_get_config.return_value = config
        
        try:
            cls.manager = MemoryManager()
            # Force re-init if it was already initialized (singleton pattern)
            cls.manager._initialized = False
            cls.manager.__init__()
            
        except Exception as e:
            cls.config_patcher.stop()
            raise unittest.SkipTest(f"Failed to initialize MemoryManager: {e}")

    @classmethod
    def tearDownClass(cls):
        cls.config_patcher.stop()

    def setUp(self):
        # Generate a unique user ID for this test run to ensure isolation
        self.test_user_id = f"test_user_{uuid.uuid4().hex[:8]}"
        self.test_run_id = f"run_{uuid.uuid4().hex[:8]}"
        print(f"\n[Real-CRUD] Starting test with User ID: {self.test_user_id}")

    def tearDown(self):
        # Cleanup after test
        print(f"[Real-CRUD] Cleaning up data for {self.test_user_id}...")
        try:
            self.manager.delete_all_memories(user_id=self.test_user_id)
        except Exception as e:
            print(f"Warning: Cleanup failed: {e}")

    def test_complete_crud_cycle(self):
        # 1. CREATE
        print("1. [CREATE] Adding a new memory...")
        content = "The user is testing the memory system. They like coding in Python."
        result = self.manager.add_memory(content, user_id=self.test_user_id, run_id=self.test_run_id)
        
        # Validate creation
        self.assertTrue(result, "Add memory result should not be empty")
        
        # Extract ID (handling different mem0 response formats)
        if isinstance(result, list) and len(result) > 0:
            memory_id = result[0].get('id')
        elif isinstance(result, dict):
            # Check for 'results' key which some versions have
            if 'results' in result and isinstance(result['results'], list) and len(result['results']) > 0:
                 memory_id = result['results'][0].get('id')
            else:
                memory_id = result.get('id')
        else:
            memory_id = None
            
        self.assertIsNotNone(memory_id, f"Could not retrieve Memory ID from result: {result}")
        print(f"   -> Created Memory ID: {memory_id}")

        # Wait for potential async indexing (Vector DBs/Graph often need a moment)
        time.sleep(2)

        # 2. READ (Get All)
        print("2. [READ] Getting all memories...")
        all_memories_response = self.manager.get_memories(user_id=self.test_user_id)
        
        # mem0.get_all now returns a dict with 'results' and 'relations'
        memories = all_memories_response.get('results', [])
        relations = all_memories_response.get('relations', [])
        
        print(f"   -> Retrieved {len(memories)} memories")
        print(f"   -> Retrieved {len(relations)} relations")
        print(f"   -> Memories content (for debugging): {memories}")
        self.assertGreaterEqual(len(memories), 1, "Should have found at least 1 memory")
        
        # Verify content match
        # mem0 returns 'memory' or 'text' depending on version
        retrieved_texts = [m.get('memory', m.get('text', '')) for m in memories]
        self.assertTrue(any("Python" in t for t in retrieved_texts), "Added content not found in retrieval")

        # 3. READ (Search)
        print("3. [SEARCH] Searching for 'coding'...")
        search_results = self.manager.search_memories("What do they like to code in?", user_id=self.test_user_id)
        print(f"   -> Search returned {len(search_results)} results")
        print(f"   -> Search results content (for debugging): {search_results}") # Debug print
        
        self.assertTrue(len(search_results['results']) > 0, "Search should return results")
        
        first_result_text = search_results['results'][0].get('memory', search_results['results'][0].get('text', ''))
        self.assertIn("Python", first_result_text, "Search result should contain relevant text")

        # 4. UPDATE
        print(f"4. [UPDATE] Updating memory {memory_id}...")
        new_content = "The user is testing the memory system. They like coding in Rust now."
        update_res = self.manager.update_memory(memory_id, new_content)
        
        # Wait for update propagation
        time.sleep(2)
        
        # Verify Update
        updated_memories_response = self.manager.get_memories(user_id=self.test_user_id)
        updated_memories_list = updated_memories_response.get('results', [])
        # Find the specific memory by ID
        updated_memory = next((m for m in updated_memories_list if m['id'] == memory_id), None)
        self.assertIsNotNone(updated_memory, "Memory disappeared after update")
        
        updated_text = updated_memory.get('memory', updated_memory.get('text', ''))
        print(f"   -> Updated content: {updated_text}")
        self.assertIn("Rust", updated_text, "Memory content was not updated to include 'Rust'")
        self.assertNotIn("Python", updated_text, "Old content 'Python' still present (assuming full replacement)")

        # 5. DELETE
        print(f"5. [DELETE] Deleting memory {memory_id}...")
        self.manager.delete_memory(memory_id)
        
        time.sleep(1)
        
        # Verify Deletion
        final_memories_response = self.manager.get_memories(user_id=self.test_user_id)
        final_memories_list = final_memories_response.get('results', [])
        # Should be empty or at least not contain that ID
        deleted_exists = any(m['id'] == memory_id for m in final_memories_list)
        self.assertFalse(deleted_exists, "Memory still exists after deletion")
        print("   -> Memory successfully deleted")

if __name__ == '__main__':
    unittest.main()
