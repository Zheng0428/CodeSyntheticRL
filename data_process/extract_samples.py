#!/usr/bin/env python3
"""
从每个根URL目录中提取100条数据样本
"""

import json
import os
import random
import argparse
from pathlib import Path
import glob
from tqdm import tqdm
import multiprocessing as mp
from functools import partial
import psutil

def extract_samples_from_domain(domain_dir_args):
    """
    从单个域名目录中随机提取样本（多进程版本）
    """
    domain_dir, output_dir, sample_size, seed, max_files = domain_dir_args
    
    # 在每个进程中设置随机种子
    random.seed(seed + hash(domain_dir) % 10000)
    
    return _extract_samples_from_domain(domain_dir, output_dir, sample_size, max_files)

def _extract_samples_from_domain(domain_dir, output_dir, sample_size=100, max_files=10):
    """
    从单个域名目录中随机提取样本（优化版本：先随机选择文件再采样）
    """
    domain_name = os.path.basename(domain_dir)
    
    # 查找所有JSON文件
    json_files = glob.glob(os.path.join(domain_dir, "*.json"))
    if not json_files:
        print(f"  警告: {domain_name} 目录中没有找到JSON文件")
        return None
    
    # 随机选择最多max_files个文件进行读取
    selected_files = random.sample(json_files, min(max_files, len(json_files)))
    
    print(f"  {domain_name}: 从 {len(json_files)} 个文件中随机选择 {len(selected_files)} 个文件")
    
    # 收集选中文件的数据
    all_data = []
    total_read_data = 0
    
    for json_file in selected_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    all_data.extend(data)
                    total_read_data += len(data)
                else:
                    print(f"  警告: {json_file} 中的数据格式不是列表")
        except Exception as e:
            print(f"  错误: 无法读取 {json_file}: {e}")
            continue
    
    if not all_data:
        print(f"  警告: {domain_name} 中没有有效数据")
        return None
    
    # 随机采样
    actual_sample_size = min(sample_size, len(all_data))
    if len(all_data) < sample_size:
        print(f"  注意: {domain_name} 从 {total_read_data} 条数据中只采样到 {len(all_data)} 条，少于请求的 {sample_size} 条")
    
    sampled_data = random.sample(all_data, actual_sample_size)
    
    print(f"  {domain_name}: 最终采样 {actual_sample_size} 条数据")
    
    # 创建输出目录
    output_domain_dir = os.path.join(output_dir, domain_name)
    os.makedirs(output_domain_dir, exist_ok=True)
    
    # 保存样本数据
    output_file = os.path.join(output_domain_dir, f"{domain_name}_samples.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(sampled_data, f, ensure_ascii=False, indent=2)
    
    return {
        'domain': domain_name,
        'total_files': len(json_files),
        'selected_files': len(selected_files),
        'total_data_in_selected_files': total_read_data,
        'valid_data': len(all_data),
        'sampled': actual_sample_size,
        'output_file': output_file
    }

def main():
    parser = argparse.ArgumentParser(description='从每个根URL目录中提取样本数据')
    parser.add_argument('--input-dir', 
                       default='/mnt/hdfs/tiktok_aiic_new/user/tianyu/opencoder/dataset/domain_collections',
                       help='输入目录路径（包含各个域名文件夹）')
    parser.add_argument('--output-dir', 
                       default='/mnt/hdfs/tiktok_aiic_new/user/tianyu/opencoder/dataset/domain_samples',
                       help='输出目录路径')
    parser.add_argument('--sample-size', type=int, default=100,
                       help='每个域名采样数量（默认100）')
    parser.add_argument('--seed', type=int, default=42,
                       help='随机种子（默认42）')
    parser.add_argument('--workers', type=int, default=None,
                       help='并行进程数（默认自动）')
    parser.add_argument('--single-process', action='store_true',
                       help='强制使用单进程模式')
    parser.add_argument('--max-files', type=int, default=10,
                       help='每个域名最多读取的文件数（默认10）')
    
    args = parser.parse_args()
    
    # 设置随机种子
    random.seed(args.seed)
    
    print("=== 域名数据采样器 ===")
    print(f"输入目录: {args.input_dir}")
    print(f"输出目录: {args.output_dir}")
    print(f"采样数量: {args.sample_size}")
    print(f"随机种子: {args.seed}")
    
    # 创建输出目录
    os.makedirs(args.output_dir, exist_ok=True)
    
    # 查找所有域名目录
    domain_dirs = [
        d for d in os.listdir(args.input_dir) 
        if os.path.isdir(os.path.join(args.input_dir, d)) and not d.startswith('.')
    ]
    
    if not domain_dirs:
        print(f"错误: 在 {args.input_dir} 中没有找到域名目录")
        return
    
    print(f"找到 {len(domain_dirs)} 个域名目录")
    
    # 设置并行进程数
    max_workers = args.workers or min(mp.cpu_count(), len(domain_dirs), 16)
    use_multiprocessing = not args.single_process and len(domain_dirs) > 1
    
    if use_multiprocessing:
        print(f"并行进程数: {max_workers}")
    else:
        print("使用单进程模式")

    # 准备域名目录路径
    domain_dir_paths = [
        os.path.join(args.input_dir, domain_dir_name) 
        for domain_dir_name in domain_dirs
    ]
    
    # 处理每个域名目录
    results = []
    successful_samples = 0
    
    if use_multiprocessing:
        # 多进程模式
        print("开始多进程采样...")
        
        # 准备参数
        args_list = [
            (domain_dir_path, args.output_dir, args.sample_size, args.seed, args.max_files)
            for domain_dir_path in domain_dir_paths
        ]
        
        with mp.Pool(max_workers) as pool:
            all_results = list(tqdm(
                pool.imap(extract_samples_from_domain, args_list),
                total=len(args_list),
                desc="多进程采样"
            ))
        
        # 处理结果
        for i, result in enumerate(all_results):
            if result:
                results.append(result)
                successful_samples += 1
                print(f"  ✓ {result['domain']}: {result['sampled']} 条样本 (从 {result['selected_files']}/{result['total_files']} 文件中采样)")
            else:
                print(f"  ✗ {domain_dirs[i]}: 采样失败")
    else:
        # 单进程模式
        for domain_dir_name in tqdm(domain_dirs, desc="处理域名目录"):
            domain_dir_path = os.path.join(args.input_dir, domain_dir_name)
            result = _extract_samples_from_domain(domain_dir_path, args.output_dir, args.sample_size, args.max_files)
            
            if result:
                results.append(result)
                successful_samples += 1
                print(f"  ✓ {result['domain']}: {result['sampled']} 条样本 (从 {result['selected_files']}/{result['total_files']} 文件中采样)")
            else:
                print(f"  ✗ {domain_dir_name}: 采样失败")
    
    # 生成摘要报告
    summary = {
        'total_domains': len(domain_dirs),
        'successful_samples': successful_samples,
        'failed_samples': len(domain_dirs) - successful_samples,
        'sample_size_requested': args.sample_size,
        'random_seed': args.seed,
        'multiprocessing_used': use_multiprocessing,
        'workers': max_workers if use_multiprocessing else 1,
        'results': results
    }
    
    # 保存摘要报告
    summary_file = os.path.join(args.output_dir, 'sampling_summary.json')
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print(f"\n=== 采样摘要 ===")
    print(f"总域名数: {summary['total_domains']}")
    print(f"成功采样: {summary['successful_samples']}")
    print(f"失败采样: {summary['failed_samples']}")
    print(f"总采样数据: {sum(r['sampled'] for r in results)}")
    print(f"摘要报告: {summary_file}")
    print("采样完成！")

if __name__ == "__main__":
    main()