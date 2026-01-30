# 创建 run_eval_example.py
from metrics import MetricsCalculator
import yaml

# 加载配置
with open('config.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# 初始化指标计算器
calculator = MetricsCalculator(config['metrics'])

# 示例评测
prediction = "Paris is the capital of France."
ground_truth = "The capital of France is Paris."

scores = calculator.calculate(prediction, ground_truth)
print(f"Scores: {scores}")
