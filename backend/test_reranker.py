# test_reranker.py
# 测试 reranker 是否正常工作

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from memory.config import get_mem0_config, get_reranker_config

def test_reranker_config():
    """测试 reranker 配置是否正确生成"""
    print("=" * 50)
    print("测试 1: Reranker 配置")
    print("=" * 50)
    
    # 模拟 llm_settings
    llm_settings = {
        "api_key": "test_key",
        "base_url": "https://example.com",
        "model_name": "gpt-3.5-turbo"
    }
    
    reranker_config = get_reranker_config(llm_settings)
    
    if reranker_config:
        print(f"✅ Reranker 已启用")
        print(f"   Provider: {reranker_config.get('provider')}")
        print(f"   Config: {reranker_config.get('config')}")
    else:
        print("❌ Reranker 未启用")
    
    print()

def test_mem0_config():
    """测试完整的 mem0 配置"""
    print("=" * 50)
    print("测试 2: Mem0 完整配置")
    print("=" * 50)
    
    llm_settings = {
        "api_key": "test_key",
        "base_url": "https://example.com",
        "model_name": "gpt-3.5-turbo"
    }
    
    config = get_mem0_config(llm_settings)
    
    print(f"✅ 配置生成成功")
    print(f"   Version: {config.get('version')}")
    print(f"   Embedder: {config.get('embedder', {}).get('provider')}")
    print(f"   Vector Store: {config.get('vector_store', {}).get('provider')}")
    print(f"   Graph Store: {config.get('graph_store', {}).get('provider')}")
    print(f"   LLM: {config.get('llm', {}).get('provider')}")
    
    if 'reranker' in config:
        print(f"   Reranker: {config.get('reranker', {}).get('provider')} ✅")
    else:
        print(f"   Reranker: 未配置")
    
    print()

def test_sentence_transformer_import():
    """测试 sentence-transformers 是否可用"""
    print("=" * 50)
    print("测试 3: Sentence Transformers 依赖")
    print("=" * 50)
    
    try:
        from sentence_transformers import CrossEncoder
        print("✅ sentence-transformers 已安装")
        
        # 尝试加载模型（首次会下载）
        model_name = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
        print(f"   尝试加载模型: {model_name}")
        print("   (首次运行会自动下载模型，请稍候...)")
        
        model = CrossEncoder(model_name)
        print(f"✅ 模型加载成功!")
        
        # 测试重排序
        query = "What is the capital of France?"
        documents = [
            "Paris is the capital of France.",
            "Berlin is the capital of Germany.",
            "The Eiffel Tower is in Paris.",
            "London is a big city."
        ]
        
        pairs = [[query, doc] for doc in documents]
        scores = model.predict(pairs)
        
        print("\n   重排序测试:")
        print(f"   Query: {query}")
        print("   结果 (按相关性排序):")
        
        doc_scores = list(zip(documents, scores))
        doc_scores.sort(key=lambda x: x[1], reverse=True)
        
        for i, (doc, score) in enumerate(doc_scores):
            print(f"   {i+1}. [score={score:.4f}] {doc}")
        
        print("\n✅ Reranker 工作正常!")
        
    except ImportError as e:
        print(f"❌ sentence-transformers 未安装: {e}")
        print("   请运行: uv add sentence-transformers")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
    
    print()

def test_env_variables():
    """测试环境变量"""
    print("=" * 50)
    print("测试 4: 环境变量配置")
    print("=" * 50)
    
    env_vars = [
        ("RERANKER_ENABLED", "true"),
        ("RERANKER_PROVIDER", "sentence_transformer"),
        ("RERANKER_TOP_K", "5"),
        ("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"),
        ("RERANKER_DEVICE", "cpu"),
    ]
    
    for var, default in env_vars:
        value = os.getenv(var, f"(未设置, 默认: {default})")
        print(f"   {var}: {value}")
    
    print()

if __name__ == "__main__":
    print("\n🔍 Reranker 功能测试\n")
    
    test_env_variables()
    test_reranker_config()
    test_mem0_config()
    test_sentence_transformer_import()
    
    print("=" * 50)
    print("测试完成!")
    print("=" * 50)
