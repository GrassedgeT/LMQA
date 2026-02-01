"""
Benchmark数据加载器
支持 LongBench, LOCOMO, LooGLE 等数据集
"""

import json
import os
from typing import List, Dict, Any, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class BenchmarkSample:
    """单个评测样本"""
    def __init__(self, sample_id: str, context: str, question: str, 
                 answer: str, metadata: Dict[str, Any] = None):
        self.id = sample_id
        self.context = context
        self.question = question
        self.answer = answer
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'context': self.context,
            'question': self.question,
            'answer': self.answer,
            'metadata': self.metadata
        }


class BaseBenchmarkLoader:
    """Benchmark加载器基类"""
    
    def __init__(self, data_dir: str, task: str = None, max_samples: int = None):
        self.data_dir = Path(data_dir)
        self.task = task
        self.max_samples = max_samples
        
        if not self.data_dir.exists():
            logger.warning(f"Data directory not found: {self.data_dir}")
    
    def load(self) -> List[BenchmarkSample]:
        """加载数据，子类需实现此方法"""
        raise NotImplementedError
    
    def _limit_samples(self, samples: List[BenchmarkSample]) -> List[BenchmarkSample]:
        """限制样本数量"""
        if self.max_samples is not None and len(samples) > self.max_samples:
            logger.info(f"Limiting samples from {len(samples)} to {self.max_samples}")
            return samples[:self.max_samples]
        return samples


class LongBenchLoader(BaseBenchmarkLoader):
    """LongBench数据加载器"""
    
    # LongBench任务映射
    TASK_FILES = {
        'narrativeqa': 'narrativeqa.jsonl',
        'qasper': 'qasper.jsonl',
        'multifieldqa_en': 'multifieldqa_en.jsonl',
        'multifieldqa_zh': 'multifieldqa_zh.jsonl',
        'hotpotqa': 'hotpotqa.jsonl',
        '2wikimqa': '2wikimqa.jsonl',
    }
    
    def load(self) -> List[BenchmarkSample]:
        """加载LongBench数据"""
        if not self.task:
            raise ValueError("Task must be specified for LongBench")
        
        if self.task not in self.TASK_FILES:
            raise ValueError(f"Unknown task: {self.task}. Available: {list(self.TASK_FILES.keys())}")
        
        file_path = self.data_dir / self.TASK_FILES[self.task]
        
        if not file_path.exists():
            logger.error(f"Data file not found: {file_path}")
            logger.info(f"Please download LongBench data to: {self.data_dir}")
            logger.info("Download from: https://github.com/THUDM/LongBench")
            return []
        
        samples = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for idx, line in enumerate(f):
                    data = json.loads(line.strip())
                    
                    sample = BenchmarkSample(
                        sample_id=f"{self.task}_{idx}",
                        context=data.get('context', ''),
                        question=data.get('input', ''),
                        answer=data.get('answers', [''])[0] if isinstance(data.get('answers'), list) 
                               else data.get('answers', ''),
                        metadata={
                            'task': self.task,
                            'length': data.get('length', 0),
                            'all_answers': data.get('answers', [])
                        }
                    )
                    samples.append(sample)
            
            logger.info(f"Loaded {len(samples)} samples from {self.task}")
            return self._limit_samples(samples)
        
        except Exception as e:
            logger.error(f"Error loading LongBench data: {e}")
            return []


class LOCOMOLoader(BaseBenchmarkLoader):
    def __init__(self, data_dir: str, hop_count: int = None, max_samples: int = None):
        # 强制 task 为 locomo10 
        super().__init__(data_dir, task="locomo10", max_samples=max_samples)

    def load(self) -> List[BenchmarkSample]:
        # 1. 确定文件路径
        file_path = self.data_dir / "locomo10.json"
        if not file_path.exists():
            # 兼容处理：如果没有 locomo10.json，尝试寻找 2hop.json
            file_path = self.data_dir / "2hop.json"

        if not file_path.exists():
            logger.error(f"LOCOMO data file not found at: {file_path}")
            return []

        # 2. 读取 JSON
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load JSON: {e}")
            return []

        samples = []
        # 3. 解析嵌套结构
        for conversation in data:
            # --- 提取 Context (合并所有 session 的对话) ---
            context_parts = []
            conv_dict = conversation.get('conversation', {})
            
            # 按 session_1, session_2 ... 的顺序提取
            for i in range(1, 100):
                s_key = f"session_{i}"
                if s_key in conv_dict:
                    for turn in conv_dict[s_key]:
                        speaker = turn.get('speaker', 'Unknown')
                        text = turn.get('text', '')
                        context_parts.append(f"{speaker}: {text}")
                else:
                    break
            full_context = "\n".join(context_parts)

            # --- 提取 QA 对 ---
            for qa_idx, qa_item in enumerate(conversation.get('qa', [])):
                sample = BenchmarkSample(
                    sample_id=f"{conversation.get('sample_id', 'conv')}_{qa_idx}",
                    context=full_context,
                    question=qa_item.get('question', ''),
                    answer=str(qa_item.get('answer', '')),
                    metadata={'category': qa_item.get('category')}
                )
                samples.append(sample)
                
                # --- 核心：在这里判断 max_samples 立即返回 ---
                if self.max_samples is not None and len(samples) >= self.max_samples:
                    logger.info(f"Successfully loaded {len(samples)} sample(s) (Limit reached).")
                    return samples
        
        return samples


class LooGLELoader(BaseBenchmarkLoader):
    """LooGLE数据加载器"""
    
    TASK_FILES = {
        'shortdep_qa': 'shortdep_qa.json',
        'longdep_qa': 'longdep_qa.json',
    }
    
    def load(self) -> List[BenchmarkSample]:
        """加载LooGLE数据"""
        if not self.task:
            raise ValueError("Task must be specified for LooGLE")
        
        if self.task not in self.TASK_FILES:
            raise ValueError(f"Unknown task: {self.task}. Available: {list(self.TASK_FILES.keys())}")
        
        file_path = self.data_dir / self.TASK_FILES[self.task]
        
        if not file_path.exists():
            logger.error(f"Data file not found: {file_path}")
            logger.info(f"Please download LooGLE data to: {self.data_dir}")
            return []
        
        samples = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            dataset = data if isinstance(data, list) else data.get('data', [])
            
            for idx, item in enumerate(dataset):
                sample = BenchmarkSample(
                    sample_id=f"loogle_{self.task}_{idx}",
                    context=item.get('context', ''),
                    question=item.get('question', ''),
                    answer=item.get('answer', ''),
                    metadata={'task': self.task}
                )
                samples.append(sample)
            
            logger.info(f"Loaded {len(samples)} samples from LooGLE {self.task}")
            return self._limit_samples(samples)
        
        except Exception as e:
            logger.error(f"Error loading LooGLE data: {e}")
            return []


class BenchmarkRegistry:
    """Benchmark注册表"""
    
    _LOADERS = {
        'longbench': LongBenchLoader,
        'locomo': LOCOMOLoader,
        'loogle': LooGLELoader,
    }
    
    @classmethod
    def register(cls, name: str, loader_class):
        """注册新的benchmark加载器"""
        cls._LOADERS[name] = loader_class
    
    @classmethod
    def get_loader(cls, name: str) -> type:
        """获取加载器类"""
        return cls._LOADERS.get(name)
    
    @classmethod
    def list_benchmarks(cls) -> List[str]:
        """列出所有可用的benchmark"""
        return list(cls._LOADERS.keys())


def load_benchmark(benchmark_name: str, config: Dict[str, Any]) -> List[BenchmarkSample]:
    """
    加载指定benchmark的数据
    
    Args:
        benchmark_name: benchmark名称
        config: 配置字典
    
    Returns:
        样本列表
    """
    loader_class = BenchmarkRegistry.get_loader(benchmark_name)
    
    if not loader_class:
        raise ValueError(f"Unknown benchmark: {benchmark_name}")
    
    benchmark_config = config.get(benchmark_name, {})
    data_dir = benchmark_config.get('data_dir')
    
    if not data_dir:
        raise ValueError(f"data_dir not specified for {benchmark_name}")
    
    all_samples = []
    
    if benchmark_name == 'longbench':
        tasks = benchmark_config.get('tasks', [])
        task_config = benchmark_config.get('task_config', {})
        
        for task in tasks:
            max_samples = task_config.get(task, {}).get('max_samples')
            loader = loader_class(data_dir, task=task, max_samples=max_samples)
            samples = loader.load()
            all_samples.extend(samples)
    
    elif benchmark_name == 'locomo':
        hop_counts = benchmark_config.get('hop_counts', [2, 3, 4])
        max_samples = benchmark_config.get('max_samples')
        loader = loader_class(data_dir, max_samples=max_samples)
        all_samples = loader.load()
        for hop_count in hop_counts:
            loader = loader_class(data_dir, hop_count=hop_count, max_samples=max_samples)
            samples = loader.load()
            all_samples.extend(samples)
    
    elif benchmark_name == 'loogle':
        tasks = benchmark_config.get('tasks', [])
        task_config = benchmark_config.get('task_config', {})
        
        for task in tasks:
            max_samples = task_config.get(task, {}).get('max_samples')
            loader = loader_class(data_dir, task=task, max_samples=max_samples)
            samples = loader.load()
            all_samples.extend(samples)
    
    else:
        # 通用加载
        loader = loader_class(data_dir)
        all_samples = loader.load()
    
    logger.info(f"Total samples loaded from {benchmark_name}: {len(all_samples)}")
    global_max = benchmark_config.get('max_samples')
    if global_max is not None and len(all_samples) > global_max:
        logger.info(f"Checking global limit: cutting samples from {len(all_samples)} to {global_max}")
        all_samples = all_samples[:global_max]
    max_s = benchmark_config.get('max_samples')
    if max_s and len(all_samples) > max_s:
        logger.info(f"Applying emergency truncation: {len(all_samples)} -> {max_s}")
        all_samples = all_samples[:max_s]
    logger.info(f"Total samples loaded from {benchmark_name}: {len(all_samples)}")
    return all_samples


if __name__ == "__main__":
    # 测试数据加载
    logging.basicConfig(level=logging.INFO)
    
    print("Available benchmarks:", BenchmarkRegistry.list_benchmarks())
    
    # 测试LongBench加载
    config = {
        'longbench': {
            'data_dir': 'benchmarks/longbench',
            'tasks': ['narrativeqa'],
            'task_config': {
                'narrativeqa': {'max_samples': 5}
            }
        }
    }
    
    try:
        samples = load_benchmark('longbench', config)
        if samples:
            print(f"\nLoaded {len(samples)} samples")
            print(f"First sample: {samples[0].to_dict()}")
    except Exception as e:
        print(f"Error: {e}")
