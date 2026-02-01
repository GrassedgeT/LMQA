#!/usr/bin/env python3
"""
自动下载和准备benchmark数据集
"""

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path
import urllib.request
import zipfile
import shutil

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def download_longbench(data_dir: str = "benchmarks/longbench"):
    """下载LongBench数据集"""
    logger.info("Downloading LongBench dataset...")
    
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)
    
    # LongBench GitHub仓库
    repo_url = "https://github.com/THUDM/LongBench.git"
    
    try:
        # 尝试使用git克隆
        logger.info(f"Cloning from {repo_url}...")
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, "temp_longbench"],
            check=True
        )
        
        # 移动数据文件
        temp_data = Path("temp_longbench/data")
        if temp_data.exists():
            for file in temp_data.glob("*.jsonl"):
                shutil.copy(file, data_path / file.name)
                logger.info(f"Copied {file.name}")
        
        # 清理临时目录
        shutil.rmtree("temp_longbench")
        
        logger.info(f"✓ LongBench data downloaded to {data_path}")
        
        # 列出下载的文件
        files = list(data_path.glob("*.jsonl"))
        logger.info(f"Downloaded {len(files)} files:")
        for f in files:
            logger.info(f"  - {f.name}")
        
        return True
    
    except subprocess.CalledProcessError:
        logger.error("Git clone failed. Please install git or download manually.")
        logger.info(f"Manual download: {repo_url}")
        logger.info(f"Copy data/*.jsonl files to {data_path}/")
        return False
    except Exception as e:
        logger.error(f"Error downloading LongBench: {e}")
        return False


def download_locomo(data_dir: str = "benchmarks/locomo"):
    """下载LOCOMO数据集"""
    logger.info("Downloading LOCOMO dataset...")
    
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)
    
    # LOCOMO GitHub仓库
    repo_url = "https://github.com/FreedomIntelligence/LOCOMO.git"
    
    try:
        logger.info(f"Cloning from {repo_url}...")
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, "temp_locomo"],
            check=True
        )
        
        # LOCOMO的数据可能在不同的目录
        temp_repo = Path("temp_locomo")
        
        # 查找数据文件
        data_found = False
        for pattern in ["data/*.json", "dataset/*.json", "*.json"]:
            for file in temp_repo.glob(pattern):
                if file.is_file():
                    shutil.copy(file, data_path / file.name)
                    logger.info(f"Copied {file.name}")
                    data_found = True
        
        # 清理临时目录
        shutil.rmtree("temp_locomo")
        
        if data_found:
            logger.info(f"✓ LOCOMO data downloaded to {data_path}")
            
            # 列出下载的文件
            files = list(data_path.glob("*.json"))
            logger.info(f"Downloaded {len(files)} files:")
            for f in files:
                logger.info(f"  - {f.name}")
            
            return True
        else:
            logger.warning("No data files found in LOCOMO repository")
            logger.info("Please check the repository structure and download manually")
            return False
    
    except subprocess.CalledProcessError:
        logger.error("Git clone failed. Please install git or download manually.")
        logger.info(f"Manual download: {repo_url}")
        logger.info(f"Copy data files to {data_path}/")
        return False
    except Exception as e:
        logger.error(f"Error downloading LOCOMO: {e}")
        return False


def create_sample_data(benchmark: str, data_dir: str):
    """创建示例数据用于测试"""
    import json
    
    logger.info(f"Creating sample data for {benchmark}...")
    
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)
    
    if benchmark == "longbench":
        # 创建示例NarrativeQA数据 - 使用有实际意义的问题
        samples = [
            {
                "context": "Paris is the capital and most populous city of France. With an official estimated population of 2,102,650 residents as of 1 January 2023 in an area of more than 105 square kilometres, Paris is the fourth-most populated city in the European Union and the 30th most densely populated city in the world in 2022.",
                "input": "What is the capital of France?",
                "answers": ["Paris"],
                "length": 250
            },
            {
                "context": "The Eiffel Tower is a wrought-iron lattice tower on the Champ de Mars in Paris, France. It is named after the engineer Gustave Eiffel, whose company designed and built the tower from 1887 to 1889. Locally nicknamed 'La dame de fer' (French for 'Iron Lady'), it was constructed as the centerpiece of the 1889 World's Fair.",
                "input": "Who is the Eiffel Tower named after?",
                "answers": ["Gustave Eiffel"],
                "length": 300
            },
            {
                "context": "The Pacific Ocean is the largest and deepest of Earth's five oceanic divisions. It extends from the Arctic Ocean in the north to the Southern Ocean in the south, and is bounded by the continents of Asia and Australia in the west and the Americas in the east. At 165,250,000 square kilometers in area, this largest division of the World Ocean covers about 46% of Earth's water surface.",
                "input": "Which is the largest ocean on Earth?",
                "answers": ["Pacific Ocean", "The Pacific Ocean", "Pacific"],
                "length": 350
            },
            {
                "context": "William Shakespeare was an English playwright, poet and actor. He is widely regarded as the greatest writer in the English language and the world's pre-eminent dramatist. He is often called England's national poet and the 'Bard of Avon'. His extant works, including collaborations, consist of some 39 plays, 154 sonnets, three long narrative poems and a few other verses.",
                "input": "How many plays did Shakespeare write?",
                "answers": ["39", "39 plays", "about 39"],
                "length": 320
            },
            {
                "context": "The Great Wall of China is a series of fortifications that were built across the historical northern borders of ancient Chinese states and Imperial China as protection against various nomadic groups. The total length of all sections of the Great Wall is estimated to be 21,196 kilometers. The wall was built from the 7th century BC to the 16th century AD.",
                "input": "When was the Great Wall of China built?",
                "answers": ["from the 7th century BC to the 16th century AD", "7th century BC to 16th century AD"],
                "length": 380
            }
        ]
        
        file_path = data_path / "narrativeqa.jsonl"
        with open(file_path, 'w', encoding='utf-8') as f:
            for sample in samples:
                f.write(json.dumps(sample, ensure_ascii=False) + '\n')
        
        logger.info(f"✓ Created sample data: {file_path}")
        
    elif benchmark == "locomo":
        # 创建示例LOCOMO数据
        sample_data = [
            {
                "context": "Sample context for multi-hop reasoning.",
                "question": "Sample question?",
                "answer": "Sample answer"
            }
        ]
        
        for hop in [2, 3, 4]:
            file_path = data_path / f"{hop}hop.json"
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(sample_data * 5, f, indent=2)
            logger.info(f"✓ Created sample data: {file_path}")


def check_data(benchmark: str, data_dir: str):
    """检查数据是否存在"""
    data_path = Path(data_dir)
    
    if not data_path.exists():
        logger.warning(f"Data directory not found: {data_path}")
        return False
    
    if benchmark == "longbench":
        files = list(data_path.glob("*.jsonl"))
    elif benchmark == "locomo":
        files = list(data_path.glob("*.json"))
    else:
        files = list(data_path.glob("*"))
    
    if files:
        logger.info(f"✓ Found {len(files)} data files in {data_path}:")
        for f in files:
            size = f.stat().st_size / 1024  # KB
            logger.info(f"  - {f.name} ({size:.1f} KB)")
        return True
    else:
        logger.warning(f"No data files found in {data_path}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Download benchmark datasets')
    parser.add_argument('--benchmark', type=str, 
                       choices=['longbench', 'locomo', 'all'],
                       default='all',
                       help='Which benchmark to download')
    parser.add_argument('--data-dir', type=str,
                       help='Override data directory')
    parser.add_argument('--sample', action='store_true',
                       help='Create sample data for testing (not real data)')
    parser.add_argument('--check', action='store_true',
                       help='Only check if data exists')
    
    args = parser.parse_args()
    
    # 默认数据目录
    benchmarks_config = {
        'longbench': 'benchmarks/longbench',
        'locomo': 'benchmarks/locomo'
    }
    
    if args.data_dir:
        benchmarks_config = {k: args.data_dir for k in benchmarks_config}
    
    success = True
    
    if args.benchmark in ['longbench', 'all']:
        data_dir = benchmarks_config['longbench']
        
        if args.check:
            check_data('longbench', data_dir)
        elif args.sample:
            create_sample_data('longbench', data_dir)
        else:
            if not download_longbench(data_dir):
                success = False
    
    if args.benchmark in ['locomo', 'all']:
        data_dir = benchmarks_config['locomo']
        
        if args.check:
            check_data('locomo', data_dir)
        elif args.sample:
            create_sample_data('locomo', data_dir)
        else:
            if not download_locomo(data_dir):
                success = False
    
    if not success:
        logger.warning("\n⚠️  Some downloads failed.")
        logger.info("You can:")
        logger.info("1. Install git and retry")
        logger.info("2. Download manually from GitHub")
        logger.info("3. Use --sample to create test data")
        return 1
    
    logger.info("\n✓ All downloads completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
