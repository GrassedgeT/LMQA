# backend/memory/config.py

import os
from dotenv import load_dotenv

load_dotenv()

def get_mem0_config(llm_settings=None):
    if llm_settings is None:
        llm_settings = {}

    # 1. Embedder
    if os.getenv("GOOGLE_API_KEY"):
        embedder_config = {"provider": "gemini", "config": {"model": "models/text-embedding-004", "api_key": os.getenv("GOOGLE_API_KEY")}}
    elif os.getenv("OPENAI_API_KEY"):
        embedder_config = {"provider": "openai", "config": {"model": "text-embedding-3-small", "api_key": os.getenv("OPENAI_API_KEY")}}
    else:
        embedder_config = {"provider": "gemini", "config": {"model": "models/text-embedding-004", "api_key": ""}}

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
    
    # 3. Graph Store
    graph_store_config = {
        "provider": "neo4j",
        "config": {
            "url": os.getenv("NEO4J_URI", "neo4j://localhost:7687"),
            "username": os.getenv("NEO4J_USERNAME", "neo4j"),
            "password": os.getenv("NEO4J_PASSWORD"),
        }
    }

    # 4. LLM
    base_url = llm_settings.get("base_url")
    model_name = llm_settings.get("model_name", "gpt-3.5-turbo")
    
    # [同步补全逻辑]
    if not base_url and "deepseek" in str(model_name).lower():
        base_url = "https://api.deepseek.com"

    llm_config = {
        "provider": "openai", 
        "config": {
            "model": model_name,
            "api_key": llm_settings.get("api_key") or os.getenv("OPENAI_API_KEY"),
            "temperature": 0,
            "max_tokens": 2000,
            "openai_base_url": base_url 
        }
    }

    # 5. Reranker
    reranker_config = get_reranker_config(llm_settings)

    config = {
        "version": "v1.1", 
        "embedder": embedder_config,
        "vector_store": vector_store_config,
        "graph_store": graph_store_config,
        "llm": llm_config
    }
    
    if reranker_config:
        config["reranker"] = reranker_config
    
    return config

def get_reranker_config(llm_settings=None):
    # [修复] 补回定义变量
    reranker_provider = os.getenv("RERANKER_PROVIDER", "llm_reranker")
    
    # 默认为 False
    reranker_enabled = os.getenv("RERANKER_ENABLED", "false").lower() == "true"
    if not reranker_enabled:
        return None
    
    if reranker_provider == "llm_reranker":
        if not llm_settings or not llm_settings.get("api_key"):
            return None
        
        base_url = llm_settings.get("base_url")
        if not base_url and "deepseek" in str(llm_settings.get("model_name", "")).lower():
            base_url = "https://api.deepseek.com"

        return {
            "provider": "llm_reranker",
            "config": {
                "provider": "openai",
                "model": llm_settings.get("model_name", "gpt-3.5-turbo"),
                "api_key": llm_settings.get("api_key"),
                "openai_base_url": base_url, 
                "top_k": int(os.getenv("RERANKER_TOP_K", "5")),
                "temperature": 0.1
            }
        }
    
    elif reranker_provider == "cohere":
        cohere_api_key = os.getenv("COHERE_API_KEY")
        if not cohere_api_key: return None
        return {"provider": "cohere", "config": {"model": os.getenv("COHERE_RERANKER_MODEL", "rerank-english-v3.0"), "api_key": cohere_api_key, "top_k": int(os.getenv("RERANKER_TOP_K", "5"))}}
    
    elif reranker_provider == "sentence_transformer":
        return {"provider": "sentence_transformer", "config": {"model": os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"), "device": os.getenv("RERANKER_DEVICE", "cpu"), "top_k": int(os.getenv("RERANKER_TOP_K", "5"))}}
    
    elif reranker_provider == "huggingface":
        return {"provider": "huggingface", "config": {"model": os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-base"), "device": os.getenv("RERANKER_DEVICE", "cpu"), "batch_size": int(os.getenv("RERANKER_BATCH_SIZE", "32")), "top_k": int(os.getenv("RERANKER_TOP_K", "5"))}}
    
    return None