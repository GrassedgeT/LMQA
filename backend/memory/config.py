
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def get_mem0_config(llm_settings=None):
    """
    Constructs the configuration dictionary for Mem0.
    Args:
        llm_settings (dict, optional): Contains 'provider', 'model', 'api_key', 'base_url'.
    """
    
    # 1. Embedding 和 数据库配置 (保持不变)
    embedder_config = {
        "provider": "gemini",
        "config": {
            "model": "models/text-embedding-004",
            "api_key": os.getenv("GOOGLE_API_KEY") # 确保环境变量里有这个
        }
    }

    vector_store_config = {
        "provider": "qdrant",
        "config": {
            "collection_name": "mem0",
            "host": os.getenv("QDRANT_HOST", "localhost"),
            "port": int(os.getenv("QDRANT_PORT", 6333)),
            "embedding_model_dims": 768,
        }
    }
    
    graph_store_config = {
        "provider": "neo4j",
        "config": {
            "url": os.getenv("NEO4J_URI", "neo4j://localhost:7687"),
            "username": os.getenv("NEO4J_USERNAME", "neo4j"),
            "password": os.getenv("NEO4J_PASSWORD"),
        }
    }

    # 2. 动态构建 LLM 配置
    # 默认配置（如果没有传入 llm_settings，作为兜底）
    default_llm_config = {
        "provider": "openai", 
        "config": {
            "model": "deepseek-chat",
            "api_key": os.getenv("DEEPSEEK_API_KEY"), 
            "base_url": "https://api.deepseek.com/v1",
            "temperature": 0.2,
            "max_tokens": 2000,
        }
    }

    if llm_settings:
        # 我们统一使用 'openai' provider 模式，因为 DeepSeek/Qwen/Kimi 都兼容 OpenAI 协议
        # 这样兼容性最好，不需要 Mem0 内部去适配各种非标准 provider
        llm_config = {
            "provider": "openai", 
            "config": {
                "model": llm_settings.get("model_name"),
                "api_key": llm_settings.get("api_key"),
                "base_url": llm_settings.get("base_url"),
                "temperature": 0.2,
                "max_tokens": 2000,
            }
        }
    else:
        llm_config = default_llm_config

    config = {
        "embedder": embedder_config,
        "vector_store": vector_store_config,
        "graph_store": graph_store_config,
        "llm": llm_config,
        "custom_update_memory_prompt": UPDATE_MEMORY_PROMPT
    }

    return config

UPDATE_MEMORY_PROMPT = """You are a smart memory manager which controls the memory of a system.
You can perform four operations: (1) add into the memory, (2) update the memory, (3) delete from the memory, and (4) no change.

Based on the above four operations, the memory will change.

Compare newly retrieved facts with the existing memory. For each new fact, decide whether to:
- ADD: Add it to the memory as a new element
- UPDATE: Update an existing memory element
- DELETE: Delete an existing memory element
- NONE: Make no change (if the fact is already present or irrelevant)

There are specific guidelines to select which operation to perform:

1. **Add**: If the retrieved facts contain new information not present in the memory, then you have to add it by generating a new ID in the id field.
- **Example**:
    - Old Memory:
        [
            {
                "id" : "0",
                "text" : "User is a software engineer"
            }
        ]
    - Retrieved facts: ["Name is John"]
    - New Memory:
        {
            "memory" : [
                {
                    "id" : "0",
                    "text" : "User is a software engineer",
                    "event" : "NONE"
                },
                {
                    "id" : "1",
                    "text" : "Name is John",
                    "event" : "ADD"
                }
            ]

        }

2. **Update**: If the retrieved facts contain information that is already present in the memory but the information is totally different, then you have to update it. 
If the retrieved fact contains information that conveys the same thing as the elements present in the memory, then you have to keep the fact which has the most information. 
Example (a) -- if the memory contains "User likes to play cricket" and the retrieved fact is "Loves to play cricket with friends", then update the memory with the retrieved facts.
Example (b) -- if the memory contains "Likes cheese pizza" and the retrieved fact is "Loves cheese pizza", then you do not need to update it because they convey the same information.
If the direction is to update the memory, then you have to update it.
Please keep in mind while updating you have to keep the same ID.
Please note to return the IDs in the output from the input IDs only and do not generate any new ID.
- **Example**:
    - Old Memory:
        [
            {
                "id" : "0",
                "text" : "I really like cheese pizza"
            },
            {
                "id" : "1",
                "text" : "User is a software engineer"
            },
            {
                "id" : "2",
                "text" : "User likes to play cricket"
            }
        ]
    - Retrieved facts: ["Loves chicken pizza", "Loves to play cricket with friends"]
    - New Memory:
        {
        "memory" : [
                {
                    "id" : "0",
                    "text" : "Loves cheese and chicken pizza",
                    "event" : "UPDATE",
                    "old_memory" : "I really like cheese pizza"
                },
                {
                    "id" : "1",
                    "text" : "User is a software engineer",
                    "event" : "NONE"
                },
                {
                    "id" : "2",
                    "text" : "Loves to play cricket with friends",
                    "event" : "UPDATE",
                    "old_memory" : "User likes to play cricket"
                }
            ]
        }


3. **Delete**: If the retrieved facts contain information that contradicts the information present in the memory, then you have to delete it. Or if the direction is to delete the memory, then you have to delete it.
Please note to return the IDs in the output from the input IDs only and do not generate any new ID.
- **Example**:
    - Old Memory:
        [
            {
                "id" : "0",
                "text" : "Name is John"
            },
            {
                "id" : "1",
                "text" : "Loves cheese pizza"
            }
        ]
    - Retrieved facts: ["Dislikes cheese pizza"]
    - New Memory:
        {
        "memory" : [
                {
                    "id" : "0",
                    "text" : "Name is John",
                    "event" : "NONE"
                },
                {
                    "id" : "1",
                    "text" : "Loves cheese pizza",
                    "event" : "DELETE"
                }
        ]
        }

4. **No Change**: If the retrieved facts contain information that is already present in the memory, then you do not need to make any changes.
- **Example**:
    - Old Memory:
        [
            {
                "id" : "0",
                "text" : "Name is John"
            },
            {
                "id" : "1",
                "text" : "Loves cheese pizza"
            }
        ]
    - Retrieved facts: ["Name is John"]
    - New Memory:
        {
        "memory" : [
                {
                    "id" : "0",
                    "text" : "Name is John",
                    "event" : "NONE"
                },
                {
                    "id" : "1",
                    "text" : "Loves cheese pizza",
                    "event" : "NONE"
                }
            ]
        }
"""