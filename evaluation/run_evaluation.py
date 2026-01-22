#!/usr/bin/env python3
"""
自动化评测运行脚本
支持命令行参数配置
"""

import argparse
import logging
import yaml
from pathlib import Path

from evaluator import Evaluator


def setup_logging(level: str = "INFO"):
    """配置日志"""
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO
    
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/evaluation.log'),
            logging.StreamHandler()
        ]
    )


def main():
    parser = argparse.ArgumentParser(description='Run LMQA benchmark evaluation')
    
    # 基本参数
    parser.add_argument('--config', type=str, default='config.yaml',
                       help='Path to config file (default: config.yaml)')
    parser.add_argument('--benchmark', type=str, choices=['longbench', 'locomo', 'loogle', 'all'],
                       default='all', help='Which benchmark to evaluate')
    parser.add_argument('--task', type=str, help='Specific task to evaluate (for LongBench)')
    
    # 系统配置覆盖
    parser.add_argument('--backend-url', type=str, help='Override backend URL')
    parser.add_argument('--username', type=str, help='Override username')
    parser.add_argument('--password', type=str, help='Override password')
    
    # 采样配置
    parser.add_argument('--max-samples', type=int, help='Maximum number of samples to evaluate')
    parser.add_argument('--random-seed', type=int, help='Random seed for sampling')
    
    # 输出配置
    parser.add_argument('--result-dir', type=str, help='Override result directory')
    parser.add_argument('--no-save', action='store_true', help='Do not save results')
    
    # 日志配置
    parser.add_argument('--log-level', type=str, default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Logging level')
    
    args = parser.parse_args()
    
    # 设置日志
    Path('logs').mkdir(exist_ok=True)
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)
    
    # 加载配置
    logger.info(f"Loading config from {args.config}")
    try:
        with open(args.config, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error(f"Config file not found: {args.config}")
        return 1
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return 1
    
    # 应用命令行参数覆盖
    if args.backend_url:
        config['system']['backend_url'] = args.backend_url
        logger.info(f"Using backend URL: {args.backend_url}")
    
    if args.username:
        config['system']['auth']['username'] = args.username
    
    if args.password:
        config['system']['auth']['password'] = args.password
    
    if args.max_samples:
        config['evaluation']['sampling']['max_samples'] = args.max_samples
        logger.info(f"Limiting to {args.max_samples} samples")
    
    if args.random_seed:
        config['evaluation']['sampling']['random_seed'] = args.random_seed
    
    if args.result_dir:
        config['evaluation']['output']['result_dir'] = args.result_dir
    
    if args.no_save:
        config['evaluation']['output']['save_predictions'] = False
        config['evaluation']['output']['save_metrics'] = False
    
    # 设置要评测的benchmark
    if args.benchmark != 'all':
        config['evaluation']['benchmarks'] = [args.benchmark]
        logger.info(f"Evaluating benchmark: {args.benchmark}")
    
    # 如果指定了task（仅用于LongBench）
    if args.task and args.benchmark == 'longbench':
        config['longbench']['tasks'] = [args.task]
        logger.info(f"Evaluating task: {args.task}")
    
    # 创建评测器并运行
    logger.info("Initializing evaluator...")
    try:
        if args.max_samples:
            config['evaluation']['sampling']['max_samples'] = args.max_samples
            if args.benchmark != 'all':
                if args.benchmark not in config:
                    config[args.benchmark] = {}
                config[args.benchmark]['max_samples'] = args.max_samples
        if args.task and args.benchmark == 'longbench':
            config['longbench']['tasks'] = [args.task]

        evaluator = Evaluator(config)
        logger.info("Starting evaluation...")
        evaluator.run()
        logger.info("Evaluation completed successfully!")
        return 0
    except KeyboardInterrupt:
        logger.warning("Evaluation interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Evaluation failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit(main())
