# Memory Module (Mem0 Integration)

This module implements a memory layer using [Mem0](https://mem0.ai), integrating Qdrant for vector storage and Neo4j for graph storage (knowledge graph).

## Features

- **User Isolation**: Memories are partitioned by `user_id`.
- **Session Isolation**: Memories can optionally be partitioned by `run_id` (conversation ID).
- **CRUD**: Add, Retrieve, Update, Delete memories.
- **Search**: Vector-based semantic search with graph enhancements (if enabled/supported by the model).
- **Reranker**: Optional reranking of search results for improved relevance.
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
    
    # Reranker 配置
    RERANKER_ENABLED=true
    RERANKER_PROVIDER=llm_reranker
    RERANKER_TOP_K=5
    ```

2.  **Dependencies**:
    Managed via `uv` (pyproject.toml).
    - `mem0ai[graph]`
    - `python-dotenv`

## Reranker 配置

Reranker 用于对搜索结果进行二次排序，提高相关性。支持以下 provider：

### 1. LLM Reranker（推荐）
使用现有的 LLM 进行重排序，无需额外 API：
```bash
RERANKER_PROVIDER=llm_reranker
RERANKER_TOP_K=5
```

### 2. Cohere Reranker
使用 Cohere 的 rerank API：
```bash
RERANKER_PROVIDER=cohere
COHERE_API_KEY=your_cohere_api_key
COHERE_RERANKER_MODEL=rerank-english-v3.0
RERANKER_TOP_K=5
```

### 3. Sentence Transformer（本地模型）
使用本地 cross-encoder 模型，无需 API：
```bash
RERANKER_PROVIDER=sentence_transformer
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
RERANKER_DEVICE=cpu  # 或 cuda
RERANKER_TOP_K=5
```

### 4. HuggingFace Reranker
使用 HuggingFace 模型：
```bash
RERANKER_PROVIDER=huggingface
RERANKER_MODEL=BAAI/bge-reranker-base
RERANKER_DEVICE=cpu
RERANKER_BATCH_SIZE=32
RERANKER_TOP_K=5
```

### 禁用 Reranker
```bash
RERANKER_ENABLED=false
```

## Usage

### 1. Python Interface

You can use the `MemoryManager` singleton class directly in your code:

```python
from backend.memory.manager import MemoryManager

# Initialize
mm = MemoryManager()

# Add Memory
mm.add_memory("I am working on a secret project called Project X.", user_id="user_123")

# Search Memory (with reranking enabled by default)
results = mm.search_memories("What project am I working on?", user_id="user_123")
print(results)

# Search Memory (without reranking)
results = mm.search_memories("What project am I working on?", user_id="user_123", rerank=False)

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
    *   Body: `{"query": "text", "user_id": "uid", "limit": 5, "rerank": true}`
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
