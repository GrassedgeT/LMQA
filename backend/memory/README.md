# Memory Module (Mem0 Integration)

This module implements a memory layer using [Mem0](https://mem0.ai), integrating Qdrant for vector storage and Neo4j for graph storage (knowledge graph).

## Features

- **User Isolation**: Memories are partitioned by `user_id`.
- **Session Isolation**: Memories can optionally be partitioned by `run_id` (conversation ID).
- **CRUD**: Add, Retrieve, Update, Delete memories.
- **Search**: Vector-based semantic search with graph enhancements (if enabled/supported by the model).
- **Graph Storage**: Integration with Neo4j for relationship mapping.

## Setup

1.  **Environment Variables**:
    Ensure the following are set in your `backend/.env` file:

    ```bash
    GOOGLE_API_KEY=your_gemini_api_key
    QDRANT_HOST=localhost
    QDRANT_PORT=6333
    NEO4J_URI=neo4j://localhost:7687
    NEO4J_USERNAME=neo4j
    NEO4J_PASSWORD=your_password
    ```

2.  **Dependencies**:
    Managed via `uv` (pyproject.toml).
    - `mem0ai[graph]`
    - `python-dotenv`

## Usage

### 1. Python Interface

You can use the `MemoryManager` singleton class directly in your code:

```python
from backend.memory.manager import MemoryManager

# Initialize
mm = MemoryManager()

# Add Memory
mm.add_memory("I am working on a secret project called Project X.", user_id="user_123")

# Search Memory
results = mm.search_memories("What project am I working on?", user_id="user_123")
print(results)

# Get All Memories
all_mems = mm.get_memories(user_id="user_123")
```

### 2. API Endpoints

A Flask Blueprint is provided in `routes.py`. You can register it in your main application:

```python
# In main.py
from backend.memory.routes import memory_bp
app.register_blueprint(memory_bp)
```

**Endpoints:**

*   `POST /api/memory/add`
    *   Body: `{"content": "text", "user_id": "uid", "run_id": "optional_rid"}`
*   `POST /api/memory/search`
    *   Body: `{"query": "text", "user_id": "uid", "limit": 5}`
*   `GET /api/memory/all?user_id=uid`
*   `PUT /api/memory/update/<memory_id>`
    *   Body: `{"text": "new text"}`
*   `DELETE /api/memory/delete/<memory_id>`
*   `DELETE /api/memory/delete-all?user_id=uid`

## Testing

Run the included unit tests:

```bash
python -m unittest backend/tests/test_memory.py
```
