"""
主评测器
实现完整的评测流程：数据加载 -> 推理 -> 评测 -> 报告生成
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from tqdm import tqdm
import requests

from data_loader import load_benchmark, BenchmarkSample
from metrics import MetricsCalculator

logger = logging.getLogger(__name__)


class LMQAClient:
    """LMQA后端API客户端"""
    
    def __init__(self, base_url: str, username: str = None, password: str = None,
                 timeout: int = 600, max_retries: int = 1):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.token = None
        
        # 登录获取token
        if username and password:
            self._login(username, password)
    
    def _login(self, username: str, password: str):
        """登录获取认证token"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/auth/login",
                json={"username": username, "password": password},
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            if data.get('success'):
                self.token = data['data']['access_token']
                self.session.headers.update({
                    'Authorization': f'Bearer {self.token}'
                })
                logger.info(f"Logged in as {username}")
            else:
                logger.error(f"Login failed: {data.get('message')}")
        except Exception as e:
            logger.error(f"Login error: {e}")
    
    def query(self, question: str, context: str = None, conversation_id: int = None) -> Dict[str, Any]:
        """
        查询LMQA系统
        
        Args:
            question: 问题
            context: 上下文（可选，如果系统需要）
            conversation_id: 对话ID
        
        Returns:
            包含answer和metadata的字典
        """
        # 如果没有conversation_id，创建一个新对话
        if not conversation_id:
            conversation_id = self._create_conversation()
        
        # 如果有context，先将其添加为记忆
        if context:
            self.add_memory(conversation_id, context)
        
        # 发送问题
        for attempt in range(self.max_retries):
            try:
                response = self.session.post(
                    f"{self.base_url}/api/conversations/{conversation_id}/messages",
                    json={"content": question},
                    timeout=self.timeout
                )
                response.raise_for_status()
                data = response.json()
                
                if data.get('success'):
                    assistant_message = data['data']['assistant_message']
                    return {
                        'answer': assistant_message['content'],
                        'message_id': assistant_message['id'],
                        'created_at': assistant_message['created_at']
                    }
                else:
                    logger.warning(f"Query failed: {data.get('message')}")
                    return {'answer': '', 'error': data.get('message')}
            
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout on attempt {attempt + 1}/{self.max_retries}")
                if attempt < self.max_retries - 1:
                    time.sleep(2)
                    continue
                return {'answer': '', 'error': 'Timeout'}
            
            except Exception as e:
                logger.error(f"Query error: {e}")
                return {'answer': '', 'error': str(e)}
        
        return {'answer': '', 'error': 'Max retries exceeded'}
    
    def _create_conversation(self) -> int:
        """创建新对话"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/conversations",
                json={"title": "Evaluation"},
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            if data.get('success'):
                return data['data']['id']
        except Exception as e:
            logger.error(f"Failed to create conversation: {e}")
        return None
    
    def add_memory(self, conversation_id: int, content: str):
        """添加记忆（将context作为记忆）"""
        try:
            # 限制context长度，避免过长
            max_length = 20000
            if len(content) > max_length:
                content = content[:max_length] + "... (truncated)"
                logger.info(f"Context truncated to {max_length} characters")
            
            response = self.session.post(
                f"{self.base_url}/api/memories",
                json={
                    "title": "Evaluation Context",
                    "content": content,
                    "conversation_id": conversation_id
                },
                timeout=self.timeout
            )
            
            # 如果400错误，打印详细信息
            if response.status_code == 400:
                logger.error(f"Backend 400 Error Detail: {response.text}")
            
            response.raise_for_status()
            logger.debug(f"Memory added successfully for conversation {conversation_id}")
        except requests.exceptions.HTTPError as e:
            logger.warning(f"Failed to add memory (HTTP {e.response.status_code}): {e.response.text if hasattr(e, 'response') else e}")
        except Exception as e:
            logger.warning(f"Failed to add memory: {e}")


class Evaluator:
    """主评测器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.system_config = config.get('system', {})
        self.eval_config = config.get('evaluation', {})
        self.metrics_config = config.get('metrics', {})
        
        # 初始化组件
        self.client = LMQAClient(
            base_url=self.system_config.get('backend_url'),
            username=self.system_config.get('auth', {}).get('username'),
            password=self.system_config.get('auth', {}).get('password'),
            timeout=self.system_config.get('timeout', 60),
            max_retries=self.system_config.get('max_retries', 3)
        )
        
        self.metrics_calculator = MetricsCalculator(self.metrics_config)
        
        # 创建结果目录
        self.result_dir = Path(self.eval_config.get('output', {}).get('result_dir', 'results'))
        self.result_dir.mkdir(parents=True, exist_ok=True)
    
    def evaluate_sample(self, sample: BenchmarkSample) -> Dict[str, Any]:
        """
        评测单个样本
        
        Args:
            sample: 评测样本
        
        Returns:
            评测结果字典
        """
        start_time = time.time()
        
        # 查询系统
        result = self.client.query(
            question=sample.question,
            context=sample.context
        )
        
        latency = time.time() - start_time
        prediction = result.get('answer', '')
        
        # 计算指标
        if prediction and 'error' not in result:
            scores = self.metrics_calculator.calculate(prediction, sample.answer)
        else:
            scores = {metric: 0.0 for metric in self.metrics_calculator.metrics_list}
        
        return {
            'sample_id': sample.id,
            'question': sample.question,
            'ground_truth': sample.answer,
            'prediction': prediction,
            'scores': scores,
            'latency': latency,
            'error': result.get('error'),
            'metadata': sample.metadata
        }
    
    def evaluate_benchmark(self, benchmark_name: str) -> Dict[str, Any]:
        """
        评测整个benchmark：修改为先全量存入记忆，后统一问答
        """
        logger.info(f"Starting evaluation for {benchmark_name}")
        
        # 1. 核心修复：确保 benchmark 的具体配置被正确读取
        benchmark_config = self.config.get(benchmark_name, {})
        if 'data_dir' not in benchmark_config:
            # 容错：如果配置中没写，尝试默认路径
            benchmark_config['data_dir'] = f"benchmarks/{benchmark_name}"
            self.config[benchmark_name] = benchmark_config 

        # 2. 加载数据
        samples = load_benchmark(benchmark_name, self.config)
        
        if not samples:
            logger.error(f"No samples loaded for {benchmark_name}")
            return {}
        
        logger.info(f"Loaded {len(samples)} samples")

        # ---------------------------------------------------------
        # 第一阶段：全量写入记忆 (Ingestion Phase)
        # ---------------------------------------------------------
        logger.info("=== Phase 1: Ingesting ALL contexts into memory ===")
        # 创建一个该 benchmark 专用的对话 ID
        conv_id = self.client._create_conversation()
        processed_contexts = set() # 去重，防止 LOCOMO 重复存入相同长对话
        
        for sample in tqdm(samples, desc="Ingesting Memory"):
            if sample.context and sample.context not in processed_contexts:
                # 传入完整 context
                self.client.add_memory(conv_id, sample.context)
                processed_contexts.add(sample.context)
                # 给后端留出微弱处理时间
                time.sleep(0.5)

        # 强制等待后端索引和 Fact 提取完成
        wait_time = 20
        logger.info(f"Waiting {wait_time}s for backend background processing...")
        time.sleep(wait_time)

        # ---------------------------------------------------------
        # 第二阶段：正式问答评测 (Evaluation Phase)
        # ---------------------------------------------------------
        logger.info("=== Phase 2: Evaluating questions ===")
        results = []
        errors = []
        
        for sample in tqdm(samples, desc=f"Evaluating {benchmark_name}"):
            try:
                start_time = time.time()
                # 此时直接问问题，不通过 query 重复 add_memory
                # 我们直接调用 client 发送 message
                response = self.client.session.post(
                    f"{self.client.base_url}/api/conversations/{conv_id}/messages",
                    json={"content": sample.question},
                    timeout=self.client.timeout
                )
                response.raise_for_status()
                data = response.json()
                
                prediction = data['data']['assistant_message']['content'] if data.get('success') else ""
                latency = time.time() - start_time
                
                # 计算指标
                scores = self.metrics_calculator.calculate(prediction, sample.answer)
                
                results.append({
                    'sample_id': sample.id,
                    'question': sample.question,
                    'ground_truth': sample.answer,
                    'prediction': prediction,
                    'scores': scores,
                    'latency': latency
                })
            except Exception as e:
                logger.error(f"Error on {sample.id}: {e}")
                errors.append({'sample_id': sample.id, 'error': str(e)})

        # 3. 聚合与保存结果 (保留原 logic)
        all_scores = [r['scores'] for r in results if r.get('scores')]
        aggregated_scores = self.metrics_calculator.aggregate(all_scores)
        
        summary = {
            'benchmark': benchmark_name,
            'total_samples': len(samples),
            'evaluated_samples': len(results),
            'failed_samples': len(errors),
            'aggregated_scores': aggregated_scores,
            'average_latency': sum(r['latency'] for r in results) / len(results) if results else 0,
            'timestamp': datetime.now().isoformat()
        }
        
        if self.eval_config.get('output', {}).get('save_predictions'):
            self._save_results(benchmark_name, results, summary, errors)
        
        return summary
    
    def _save_results(self, benchmark_name: str, results: List[Dict], 
                     summary: Dict, errors: List[Dict]):
        """保存评测结果"""
        timestamp = datetime.now().strftime(self.eval_config.get('output', {}).get('timestamp_format', '%Y%m%d_%H%M%S'))
        
        # 保存详细结果
        result_file = self.result_dir / f"{benchmark_name}_{timestamp}.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump({
                'summary': summary,
                'results': results,
                'errors': errors
            }, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Results saved to {result_file}")
        
        # 保存汇总报告
        report_file = self.result_dir / f"{benchmark_name}_{timestamp}_report.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(self._format_report(summary))
        
        logger.info(f"Report saved to {report_file}")
    
    def _format_report(self, summary: Dict) -> str:
        """格式化评测报告"""
        report = []
        report.append("=" * 60)
        report.append(f"LMQA Evaluation Report")
        report.append("=" * 60)
        report.append(f"Benchmark: {summary['benchmark']}")
        report.append(f"Date: {summary['timestamp']}")
        report.append(f"Total Samples: {summary['total_samples']}")
        report.append(f"Evaluated: {summary['evaluated_samples']}")
        report.append(f"Failed: {summary['failed_samples']}")
        report.append("")
        report.append("-" * 60)
        report.append("Scores:")
        report.append("-" * 60)
        
        for metric, value in sorted(summary['aggregated_scores'].items()):
            if not metric.endswith('_std'):
                std_key = f"{metric}_std"
                std_value = summary['aggregated_scores'].get(std_key, 0)
                report.append(f"{metric:20s}: {value:6.2f} (±{std_value:.2f})")
        
        report.append("")
        report.append(f"Average Latency: {summary['average_latency']:.2f}s")
        report.append("=" * 60)
        
        return "\n".join(report)
    
    def run(self):
        """运行评测"""
        benchmarks = self.eval_config.get('benchmarks', [])
        
        if not benchmarks:
            logger.error("No benchmarks specified in config")
            return
        
        all_summaries = []
        
        for benchmark in benchmarks:
            try:
                summary = self.evaluate_benchmark(benchmark)
                all_summaries.append(summary)
                
                # 打印简报
                print("\n" + self._format_report(summary))
            
            except Exception as e:
                logger.error(f"Error evaluating {benchmark}: {e}")
        
        # 保存总结
        if all_summaries:
            summary_file = self.result_dir / f"evaluation_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(all_summaries, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Evaluation summary saved to {summary_file}")


if __name__ == "__main__":
    import yaml
    
    # 加载配置
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 运行评测
    evaluator = Evaluator(config)
    evaluator.run()
