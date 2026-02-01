"""
评测指标实现
支持多种QA评测指标：F1, EM, ROUGE, BLEU等
"""

import re
import string
import numpy as np
from collections import Counter
from typing import List, Dict, Any
import logging

try:
    from rouge_score import rouge_scorer
    ROUGE_AVAILABLE = True
except ImportError:
    ROUGE_AVAILABLE = False
    logging.warning("rouge_score not installed. ROUGE metrics will be unavailable.")

try:
    import nltk
    NLTK_AVAILABLE = True
except ImportError:
    NLTK_AVAILABLE = False
    logging.warning("nltk not installed. Some metrics may be unavailable.")

logger = logging.getLogger(__name__)


def normalize_answer(s: str) -> str:
    """规范化答案文本"""
    def remove_articles(text):
        return re.sub(r'\b(a|an|the)\b', ' ', text)
    
    def white_space_fix(text):
        return ' '.join(text.split())
    
    def remove_punc(text):
        exclude = set(string.punctuation)
        return ''.join(ch for ch in text if ch not in exclude)
    
    def lower(text):
        return text.lower()
    
    return white_space_fix(remove_articles(remove_punc(lower(s))))


def f1_score(prediction: str, ground_truth: str) -> float:
    """
    计算F1分数
    Args:
        prediction: 预测答案
        ground_truth: 标准答案
    Returns:
        F1分数 (0-100)
    """
    prediction_tokens = normalize_answer(prediction).split()
    ground_truth_tokens = normalize_answer(ground_truth).split()
    
    common = Counter(prediction_tokens) & Counter(ground_truth_tokens)
    num_same = sum(common.values())
    
    if num_same == 0:
        return 0.0
    
    precision = 1.0 * num_same / len(prediction_tokens)
    recall = 1.0 * num_same / len(ground_truth_tokens)
    f1 = (2 * precision * recall) / (precision + recall)
    
    return f1 * 100


def exact_match_score(prediction: str, ground_truth: str) -> float:
    """
    计算精确匹配分数
    Args:
        prediction: 预测答案
        ground_truth: 标准答案
    Returns:
        EM分数 (0 or 100)
    """
    return 100.0 if normalize_answer(prediction) == normalize_answer(ground_truth) else 0.0


def rouge_score_func(prediction: str, ground_truth: str, rouge_types: List[str] = None) -> Dict[str, float]:
    """
    计算ROUGE分数
    Args:
        prediction: 预测答案
        ground_truth: 标准答案
        rouge_types: ROUGE类型列表，如 ['rouge1', 'rouge2', 'rougeL']
    Returns:
        ROUGE分数字典
    """
    if not ROUGE_AVAILABLE:
        logger.warning("rouge_score not available, returning zeros")
        return {rt: 0.0 for rt in (rouge_types or ['rougeL'])}
    
    if rouge_types is None:
        rouge_types = ['rougeL']
    
    scorer = rouge_scorer.RougeScorer(rouge_types, use_stemmer=True)
    scores = scorer.score(ground_truth, prediction)
    
    return {
        rouge_type: scores[rouge_type].fmeasure * 100
        for rouge_type in rouge_types
    }


def bleu_score(prediction: str, ground_truth: str, max_order: int = 4) -> float:
    """
    计算BLEU分数
    Args:
        prediction: 预测答案
        ground_truth: 标准答案
        max_order: 最大n-gram阶数
    Returns:
        BLEU分数 (0-100)
    """
    if not NLTK_AVAILABLE:
        logger.warning("nltk not available, returning 0")
        return 0.0
    
    try:
        from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
        
        reference = [ground_truth.split()]
        hypothesis = prediction.split()
        
        smoothie = SmoothingFunction().method4
        score = sentence_bleu(reference, hypothesis, 
                             weights=[1.0/max_order]*max_order,
                             smoothing_function=smoothie)
        return score * 100
    except Exception as e:
        logger.error(f"BLEU calculation error: {e}")
        return 0.0


def calculate_metrics(prediction: str, ground_truth: str, 
                     metrics_list: List[str] = None) -> Dict[str, float]:
    """
    计算多个评测指标
    Args:
        prediction: 预测答案
        ground_truth: 标准答案
        metrics_list: 要计算的指标列表
    Returns:
        指标字典
    """
    if metrics_list is None:
        metrics_list = ['f1', 'em']
    
    results = {}
    
    for metric in metrics_list:
        metric_lower = metric.lower()
        
        if metric_lower == 'f1':
            results['f1'] = f1_score(prediction, ground_truth)
        
        elif metric_lower == 'em':
            results['em'] = exact_match_score(prediction, ground_truth)
        
        elif metric_lower.startswith('rouge'):
            if metric_lower == 'rougel':
              metric_lower = 'rougeL'
            rouge_scores = rouge_score_func(prediction, ground_truth, [metric_lower])
            results.update(rouge_scores)
        
        elif metric_lower == 'bleu':
            results['bleu'] = bleu_score(prediction, ground_truth)
        
        else:
            logger.warning(f"Unknown metric: {metric}")
    
    return results


def aggregate_metrics(all_scores: List[Dict[str, float]]) -> Dict[str, float]:
    """
    聚合多个样本的评测结果
    Args:
        all_scores: 所有样本的分数列表
    Returns:
        聚合后的平均分数
    """
    if not all_scores:
        return {}
    
    # 获取所有指标名称
    metrics = set()
    for scores in all_scores:
        metrics.update(scores.keys())
    
    # 计算每个指标的平均值
    aggregated = {}
    for metric in metrics:
        values = [scores.get(metric, 0.0) for scores in all_scores]
        aggregated[metric] = np.mean(values)
        aggregated[f'{metric}_std'] = np.std(values)
    
    return aggregated


class MetricsCalculator:
    """评测指标计算器"""
    
    def __init__(self, metrics_config: Dict[str, Any] = None):
        """
        初始化
        Args:
            metrics_config: 指标配置字典
        """
        self.config = metrics_config or {}
        self.metrics_list = []
        
        # 根据配置启用指标
        if self.config.get('f1', {}).get('enabled', True):
            self.metrics_list.append('f1')
        
        if self.config.get('em', {}).get('enabled', True):
            self.metrics_list.append('em')
        
        if self.config.get('rouge', {}).get('enabled', True):
            rouge_types = self.config.get('rouge', {}).get('rouge_types', ['rougeL'])
            self.metrics_list.extend(rouge_types)
        
        if self.config.get('bleu', {}).get('enabled', False):
            self.metrics_list.append('bleu')
        
        logger.info(f"Metrics calculator initialized with: {self.metrics_list}")
    
    def calculate(self, prediction: str, ground_truth: str) -> Dict[str, float]:
        """
        计算指标
        Args:
            prediction: 预测答案
            ground_truth: 标准答案
        Returns:
            指标字典
        """
        return calculate_metrics(prediction, ground_truth, self.metrics_list)
    
    def calculate_batch(self, predictions: List[str], 
                       ground_truths: List[str]) -> List[Dict[str, float]]:
        """
        批量计算指标
        Args:
            predictions: 预测答案列表
            ground_truths: 标准答案列表
        Returns:
            指标列表
        """
        assert len(predictions) == len(ground_truths), \
            "Predictions and ground truths must have the same length"
        
        results = []
        for pred, gt in zip(predictions, ground_truths):
            results.append(self.calculate(pred, gt))
        
        return results
    
    def aggregate(self, all_scores: List[Dict[str, float]]) -> Dict[str, float]:
        """
        聚合评测结果
        Args:
            all_scores: 所有样本的分数列表
        Returns:
            聚合后的分数
        """
        return aggregate_metrics(all_scores)


# 注册自定义指标的装饰器
_CUSTOM_METRICS = {}

def register_metric(name: str):
    """注册自定义指标"""
    def decorator(func):
        _CUSTOM_METRICS[name] = func
        return func
    return decorator


def get_custom_metric(name: str):
    """获取自定义指标函数"""
    return _CUSTOM_METRICS.get(name)


# 示例：注册一个自定义指标
@register_metric("custom_accuracy")
def custom_accuracy(prediction: str, ground_truth: str) -> float:
    """自定义准确率指标示例"""
    # 实现自定义逻辑
    return 100.0 if prediction.strip() == ground_truth.strip() else 0.0


if __name__ == "__main__":
    # 测试
    pred = "The capital of France is Paris."
    gt = "Paris is the capital of France."
    
    print("Testing metrics:")
    print(f"F1 Score: {f1_score(pred, gt):.2f}")
    print(f"EM Score: {exact_match_score(pred, gt):.2f}")
    print(f"ROUGE Scores: {rouge_score_func(pred, gt, ['rougeL'])}")
    
    # 测试计算器
    calculator = MetricsCalculator()
    scores = calculator.calculate(pred, gt)
    print(f"All scores: {scores}")
