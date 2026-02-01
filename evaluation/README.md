# LMQA 评测模块

本模块用于在标准长文本QA benchmark上评测LMQA系统的性能。

## 📋 支持的Benchmark

### 1. LongBench
- **来源**: https://github.com/THUDM/LongBench
- **数据集**: 包含多个长文本理解任务
- **评测任务**:
  - NarrativeQA: 叙事问答
  - Qasper: 科学论文问答
  - MultiFieldQA: 多领域问答
  - HotpotQA: 多跳问答
  - 2WikiMultihopQA: 维基多跳问答

### 2. LOCOMO (Long Context Multi-hop Reasoning)
- **来源**: https://github.com/FreedomIntelligence/LOCOMO
- **特点**: 专注于长上下文多跳推理
- **任务类型**: 需要在长文本中进行复杂的多步推理

### 3. LooGLE (Long Context Generic Language Evaluation)
- **来源**: https://github.com/bigai-nlco/LooGLE
- **任务**: 长文档理解和问答

## 🏗️ 评测框架设计

### 评测流程

```
1. 数据加载 → 2. 系统初始化 → 3. 批量推理 → 4. 结果评估 → 5. 报告生成
```

### 目录结构

```
evaluation/
├── README.md                 # 本文件
├── requirements.txt          # 评测依赖
├── config.yaml              # 评测配置
├── benchmarks/              # Benchmark数据集
│   ├── longbench/
│   ├── locomo/
│   └── loogle/
├── evaluator.py             # 主评测器
├── metrics.py               # 评测指标
├── data_loader.py           # 数据加载器
├── results/                 # 评测结果
│   ├── longbench/
│   ├── locomo/
│   └── reports/
└── scripts/                 # 辅助脚本
    ├── download_data.py
    ├── run_eval.py
    └── analyze_results.py
```

## 🚀 快速开始

### 1. 安装依赖

```bash
cd evaluation
pip install -r requirements.txt
```

### 2. 下载数据集

```bash
# 下载 LongBench
python scripts/download_data.py --benchmark longbench

# 下载 LOCOMO
python scripts/download_data.py --benchmark locomo
```

### 3. 配置评测

编辑 `config.yaml` 文件，设置：
- API配置
- 评测数据集
- 采样策略
- 输出路径

### 4. 运行评测

```bash
# 评测 LongBench
python scripts/run_eval.py --benchmark longbench --task narrativeqa

# 评测 LOCOMO
python scripts/run_eval.py --benchmark locomo

# 评测所有任务
python scripts/run_eval.py --all
```

### 5. 查看结果

```bash
# 生成报告
python scripts/analyze_results.py --result results/longbench/narrativeqa_20260121.json

# 查看汇总
cat results/reports/summary.txt
```

## 📊 评测指标

### 问答任务指标

1. **F1 Score**: 答案与参考答案的词汇重叠度
2. **Exact Match (EM)**: 完全匹配率
3. **ROUGE-L**: 最长公共子序列
4. **BLEU**: 机器翻译评估指标
5. **BERTScore**: 基于BERT的语义相似度

### 长文本特定指标

1. **Context Utilization**: 上下文利用率
2. **Multi-hop Accuracy**: 多跳推理准确率
3. **Latency**: 响应延迟
4. **Memory Efficiency**: 内存使用效率

## 🔧 配置说明

### config.yaml 示例

```yaml
# 系统配置
system:
  backend_url: "http://localhost:5000"
  api_key: "your-api-key"
  
# 评测配置
evaluation:
  benchmarks:
    - longbench
    - locomo
  
  # 采样策略
  sampling:
    max_samples: 100  # 每个任务最多评测100个样本
    random_seed: 42
  
  # 输出配置
  output:
    save_predictions: true
    save_metrics: true
    result_dir: "results"

# LongBench配置
longbench:
  tasks:
    - narrativeqa
    - qasper
    - multifieldqa_zh
  data_dir: "benchmarks/longbench"

# LOCOMO配置
locomo:
  data_dir: "benchmarks/locomo"
  hop_count: [2, 3, 4]  # 评测2跳、3跳、4跳任务
```

## 📈 性能基准

### LongBench基准性能（参考）

| Model | NarrativeQA | Qasper | MultiFieldQA |
|-------|------------|--------|--------------|
| GPT-4 | 23.6 | 43.3 | 52.3 |
| Claude-2 | 21.0 | 39.7 | 47.6 |
| **LMQA (目标)** | TBD | TBD | TBD |

### LOCOMO基准性能（参考）

| Model | 2-hop | 3-hop | 4-hop | Avg |
|-------|-------|-------|-------|-----|
| GPT-4 | 85.2 | 72.4 | 58.7 | 72.1 |
| **LMQA (目标)** | TBD | TBD | TBD | TBD |

## 🛠️ 自定义评测

### 添加新的Benchmark

1. 创建数据加载器：
```python
# data_loader.py
class CustomBenchmarkLoader(BaseBenchmarkLoader):
    def load(self):
        # 实现数据加载逻辑
        pass
```

2. 注册Benchmark：
```python
# evaluator.py
BENCHMARK_REGISTRY["custom"] = CustomBenchmarkLoader
```

3. 添加配置：
```yaml
# config.yaml
custom:
  data_dir: "benchmarks/custom"
  # 其他配置...
```

### 添加新的评测指标

```python
# metrics.py
@register_metric("custom_metric")
def custom_metric(predictions, references):
    # 实现评测逻辑
    return score
```

## 🔍 评测最佳实践

1. **数据采样**: 建议先用小样本测试，确认流程正常
2. **批量处理**: 使用批量API减少网络开销
3. **错误处理**: 记录失败案例，便于调试
4. **结果保存**: 保存完整预测结果，便于后续分析
5. **版本控制**: 记录模型版本和配置，确保可复现

## 📝 评测报告示例

```
============================================
LMQA Evaluation Report
============================================
Date: 2026-01-21
Model: LMQA v1.0
Benchmark: LongBench

--------------------------------------------
NarrativeQA Results
--------------------------------------------
Total Samples: 100
F1 Score: 24.5
Exact Match: 15.2
ROUGE-L: 28.3
Average Latency: 2.3s

--------------------------------------------
Error Analysis
--------------------------------------------
Failed Samples: 3
Common Errors:
  - Context retrieval failure: 2
  - API timeout: 1

============================================
```

## 🐛 故障排除

### 问题1: 数据下载失败
```bash
# 手动下载数据集并解压到 benchmarks/ 目录
wget https://github.com/THUDM/LongBench/releases/download/v1.0/data.zip
unzip data.zip -d benchmarks/longbench/
```

### 问题2: API连接超时
- 检查backend服务是否运行
- 增加timeout配置
- 使用重试机制

### 问题3: 内存不足
- 减少batch_size
- 使用流式处理
- 限制max_samples

## 📚 参考资源

- [LongBench Paper](https://arxiv.org/abs/2308.14508)
- [LOCOMO GitHub](https://github.com/FreedomIntelligence/LOCOMO)
- [LooGLE Paper](https://arxiv.org/abs/2311.04939)

## 🤝 贡献指南

欢迎贡献新的benchmark支持或评测指标！请提交PR并确保：
- 代码通过测试
- 添加相关文档
- 更新README

---

如有问题，请查阅文档或提交Issue。
