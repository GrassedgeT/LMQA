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
    # 确保 llm_settings 不为 None
    if llm_settings is None:
        llm_settings = {}
    
    llm_config = {
        "provider": "openai", 
        "config": {
            "model": llm_settings.get("model_name", "gpt-3.5-turbo"),
            "api_key": llm_settings.get("api_key") or os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY"),
            "openai_base_url": llm_settings.get("base_url"), 
            "temperature": 0,
            "max_tokens": 2000,
        }
    }

    # 5. Reranker 配置
    # 支持多种 provider: llm_reranker, cohere, sentence_transformer, huggingface
    reranker_config = get_reranker_config(llm_settings)

    # 返回配置
    # [关键修改]: 显式加入 version 字段，某些 Mem0 版本依赖它来激活 Graph Pipeline
    config = {
        "version": "v1.1", 
        "embedder": embedder_config,
        "vector_store": vector_store_config,
        "graph_store": graph_store_config,
        "llm": llm_config
    }
    
    # 只有配置了 reranker 才加入
    if reranker_config:
        config["reranker"] = reranker_config
    
    return config


def get_reranker_config(llm_settings=None):
    """
    获取 Reranker 配置
    
    支持的 provider:
    - llm_reranker: 使用 LLM 进行重排序（推荐，复用现有 LLM）
    - cohere: Cohere API（需要 COHERE_API_KEY）
    - sentence_transformer: 本地 cross-encoder 模型
    - huggingface: HuggingFace 模型
    
    通过环境变量 RERANKER_PROVIDER 控制，默认使用 llm_reranker
    """
    reranker_provider = os.getenv("RERANKER_PROVIDER", "llm_reranker")
    reranker_enabled = os.getenv("RERANKER_ENABLED", "true").lower() == "true"
    
    if not reranker_enabled:
        return None
    
    if reranker_provider == "llm_reranker":
        # 使用 LLM 进行重排序，复用用户配置的 LLM
        # 必须要有有效的 llm_settings 和 api_key
        if not llm_settings or not llm_settings.get("api_key"):
            # 如果没有 llm_settings，则禁用 llm_reranker
            return None
        
        return {
            "provider": "llm_reranker",
            "config": {
                "llm": {
                    "provider": "openai",
                    "config": {
                        "model": llm_settings.get("model_name", "gpt-3.5-turbo"),
                        "api_key": llm_settings.get("api_key"),
                        "openai_base_url": llm_settings.get("base_url"),
                    }
                },
                "top_k": int(os.getenv("RERANKER_TOP_K", "5")),
                "temperature": 0.0
            }
        }
    
    elif reranker_provider == "cohere":
        # Cohere API 重排序
        cohere_api_key = os.getenv("COHERE_API_KEY")
        if not cohere_api_key:
            return None
        return {
            "provider": "cohere",
            "config": {
                "model": os.getenv("COHERE_RERANKER_MODEL", "rerank-english-v3.0"),
                "api_key": cohere_api_key,
                "top_k": int(os.getenv("RERANKER_TOP_K", "5"))
            }
        }
    
    elif reranker_provider == "sentence_transformer":
        # 本地 cross-encoder 模型（无需 API，但需要安装 sentence-transformers）
        return {
            "provider": "sentence_transformer",
            "config": {
                "model": os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"),
                "device": os.getenv("RERANKER_DEVICE", "cpu"),
                "top_k": int(os.getenv("RERANKER_TOP_K", "5"))
            }
        }
    
    elif reranker_provider == "huggingface":
        # HuggingFace 模型
        return {
            "provider": "huggingface",
            "config": {
                "model": os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-base"),
                "device": os.getenv("RERANKER_DEVICE", "cpu"),
                "batch_size": int(os.getenv("RERANKER_BATCH_SIZE", "32")),
                "top_k": int(os.getenv("RERANKER_TOP_K", "5"))
            }
        }
    
    return None