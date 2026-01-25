# backend/memory/config.py

import os
from dotenv import load_dotenv

load_dotenv()

def get_mem0_config(llm_settings=None):
    # 1. Embedder
    if os.getenv("GOOGLE_API_KEY"):
        embedder_config = {
            "provider": "gemini",
            "config": {
                "model": "models/text-embedding-004",
                "api_key": os.getenv("GOOGLE_API_KEY")
            }
        }
    elif os.getenv("OPENAI_API_KEY"):
        embedder_config = {
            "provider": "openai",
            "config": {
                "model": "text-embedding-3-small",
                "api_key": os.getenv("OPENAI_API_KEY")
            }
        }
    else:
        embedder_config = {
            "provider": "gemini",
            "config": {
                "model": "models/text-embedding-004",
                "api_key": "" 
            }
        }

    # 2. Vector Store
    vector_store_config = {
        "provider": "qdrant",
        "config": {
            "collection_name": "mem0",
            "host": os.getenv("QDRANT_HOST", "localhost"),
            "port": int(os.getenv("QDRANT_PORT", 6333)),
            "embedding_model_dims": 768, 
        }
    }
    
    # 3. Graph Store (关键检查点)
    graph_store_config = {
        "provider": "neo4j",
        "config": {
            "url": os.getenv("NEO4J_URI", "neo4j://localhost:7687"),
            "username": os.getenv("NEO4J_USERNAME", "neo4j"),
            "password": os.getenv("NEO4J_PASSWORD"),
        }
    }

    # 4. LLM
    llm_config = {
        "provider": "openai", 
        "config": {
            "model": llm_settings.get("model_name", "gpt-3.5-turbo"),
            "api_key": llm_settings.get("api_key", os.getenv("OPENAI_API_KEY")),
            "openai_base_url": llm_settings.get("base_url"), 
            "temperature": 0,
            "max_tokens": 2000,
        }
    }

    # 返回配置
    # [关键修改]: 显式加入 version 字段，某些 Mem0 版本依赖它来激活 Graph Pipeline
    return {
        "version": "v1.1", 
        "embedder": embedder_config,
        "vector_store": vector_store_config,
        "graph_store": graph_store_config,
        "llm": llm_config
    }