#!/usr/bin/env python3
"""
网页内容收集分类器
根据URL统计结果，按高频域名分类收集存储网页内容
"""

import json
import os
import sys
import argparse
import pandas as pd
import glob
from tqdm import tqdm
import warnings
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import multiprocessing as mp
from functools import partial
import psutil
import gc
warnings.filterwarnings('ignore')

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import extract_root_domain, get_memory_usage, force_gc, safe_parquet_read_batches

def extract_domain(url):
    """提取URL的域名（包装函数）"""
    protocol, root_domain = extract_root_domain(url)
    return root_domain

def process_file_by_domain(file_path, target_domains, chunk_size=50000, output_dir="/tmp/domain_collections"):
    """
    流式处理单个文件，按域名分类存储URL和内容
    """
    try:
        # 为每个目标域名创建数据收集器
        domain_data = {domain: [] for domain in target_domains}
        
        file_stats = {
            'file_name': os.path.basename(file_path),
            'total_processed': 0,
            'domain_counts': defaultdict(int),
            'errors': 0
        }
        
        # 使用公共的安全分批读取函数
        for chunk_df in safe_parquet_read_batches(file_path, chunk_size):
            file_stats['total_processed'] += len(chunk_df)
            
            if 'url' not in chunk_df.columns:
                continue
            
            # 处理每个URL
            for idx, row in chunk_df.iterrows():
                url = row.get('url')
                if not url or pd.isna(url) or url == '':
                    continue
                
                try:
                    domain = extract_domain(url)
                    if domain and domain in target_domains:
                        # 收集URL数据
                        url_data = {
                            'url': url,
                            'domain': domain,
                            'file_source': os.path.basename(file_path)
                        }
                        
                        # 如果有其他列，也添加进去
                        for col in chunk_df.columns:
                            if col != 'url':
                                url_data[col] = row.get(col)
                        
                        domain_data[domain].append(url_data)
                        file_stats['domain_counts'][domain] += 1
                        
                except Exception as e:
                    file_stats['errors'] += 1
                    continue
            
            # 使用公共的垃圾回收函数
            force_gc()
        
        # 将收集的数据保存到临时文件
        saved_files = {}
        for domain, urls in domain_data.items():
            if urls:  # 只保存有数据的域名
                # 创建域名目录
                domain_dir = os.path.join(output_dir, domain.replace('.', '_'))
                os.makedirs(domain_dir, exist_ok=True)
                
                # 保存到JSON文件
                output_file = os.path.join(domain_dir, f"{file_stats['file_name']}.json")
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(urls, f, ensure_ascii=False, indent=2)
                
                saved_files[domain] = output_file
        
        file_stats['saved_files'] = saved_files
        return file_stats
        
    except Exception as e:
        return {
            'file_name': os.path.basename(file_path),
            'total_processed': 0,
            'domain_counts': defaultdict(int),
            'errors': 1,
            'error_message': str(e)
        }

class DomainBasedCollector:
    def __init__(self, data_dir, stats_file, output_dir, min_frequency=100):
        self.data_dir = data_dir
        self.stats_file = stats_file
        self.output_dir = output_dir
        self.min_frequency = min_frequency
        self.target_domains = set()
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
    
    def load_high_frequency_domains(self):
        """从统计文件中加载高频域名（频率 > min_frequency）"""
        print(f"从 {self.stats_file} 加载域名统计...")
        
        with open(self.stats_file, 'r', encoding='utf-8') as f:
            stats = json.load(f)
        
        domain_dist = stats.get('domain_distribution', {})
        
        # 筛选高频域名
        high_freq_domains = {
            domain: count for domain, count in domain_dist.items() 
            if count >= self.min_frequency
        }
        
        self.target_domains = set(high_freq_domains.keys())
        
        print(f"找到 {len(self.target_domains)} 个高频域名（频率 >= {self.min_frequency}）:")
        
        # 显示前20个域名
        sorted_domains = sorted(high_freq_domains.items(), key=lambda x: x[1], reverse=True)
        for i, (domain, count) in enumerate(sorted_domains[:20]):
            print(f"  {i+1:2d}. {domain:<30} ({count:,} URLs)")
        
        if len(sorted_domains) > 20:
            print(f"  ... 以及其他 {len(sorted_domains)-20} 个域名")
        
        # 保存域名列表到输出目录
        domains_file = os.path.join(self.output_dir, 'target_domains.json')
        with open(domains_file, 'w', encoding='utf-8') as f:
            json.dump({
                'total_domains': len(high_freq_domains),
                'min_frequency': self.min_frequency,
                'domains': high_freq_domains
            }, f, indent=2, ensure_ascii=False)
        
        print(f"域名列表已保存到: {domains_file}")
        return stats
    
    # get_memory_usage 函数已从 utils 导入，直接使用
    
    def collect_and_classify(self, test_mode=False, use_multiprocessing=True, max_workers=16):
        """收集并按域名分类存储数据"""
        pattern = os.path.join(self.data_dir, "part-*")
        files = glob.glob(pattern)
        
        if test_mode:
            files = files[:25]  # 测试模式处理3个文件
            print(f"测试模式：处理 {len(files)} 个文件")
        else:
            print(f"找到 {len(files)} 个文件")
        
        print(f"当前内存使用: {get_memory_usage():.1f} MB")
        print(f"输出目录: {self.output_dir}")
        
        if not use_multiprocessing or len(files) == 1:
            # 单进程模式
            print("使用单进程处理")
            all_stats = []
            for file_path in tqdm(files, desc="处理文件"):
                stats = process_file_by_domain(
                    file_path, self.target_domains, output_dir=self.output_dir
                )
                all_stats.append(stats)
                print(f"处理完成: {stats['file_name']} - "
                      f"总数: {stats['total_processed']:,}, "
                      f"收集: {sum(stats['domain_counts'].values()):,}, "
                      f"错误: {stats['errors']}")
                gc.collect()
        else:
            # 多进程模式
            print(f"使用 {max_workers} 个进程并行处理")
            
            process_func = partial(
                process_file_by_domain,
                target_domains=self.target_domains,
                output_dir=self.output_dir
            )
            
            with mp.Pool(max_workers) as pool:
                all_stats = list(tqdm(
                    pool.imap(process_func, files),
                    total=len(files),
                    desc="多进程处理文件"
                ))
        
        return self.generate_summary(all_stats)
    
    def generate_summary(self, all_stats):
        """生成处理摘要"""
        summary = {
            'collection_time': datetime.now().isoformat(),
            'total_files_processed': len(all_stats),
            'total_urls_processed': 0,
            'total_urls_collected': 0,
            'total_errors': 0,
            'domain_collection_stats': defaultdict(int),
            'file_stats': []
        }
        
        for stats in all_stats:
            summary['total_urls_processed'] += stats['total_processed']
            summary['total_errors'] += stats['errors']
            
            collected_count = sum(stats['domain_counts'].values())
            summary['total_urls_collected'] += collected_count
            
            # 合并域名统计
            for domain, count in stats['domain_counts'].items():
                summary['domain_collection_stats'][domain] += count
            
            summary['file_stats'].append({
                'file_name': stats['file_name'],
                'processed': stats['total_processed'],
                'collected': collected_count,
                'errors': stats['errors'],
                'saved_files': len(stats.get('saved_files', {}))
            })
        
        # 转换为普通字典
        summary['domain_collection_stats'] = dict(summary['domain_collection_stats'])
        
        return summary
    
    def consolidate_domain_files(self):
        """合并每个域名的所有文件为单个大文件"""
        print("\\n开始合并域名文件...")
        
        consolidated_stats = {}
        
        for domain in self.target_domains:
            domain_dir = os.path.join(self.output_dir, domain.replace('.', '_'))
            if not os.path.exists(domain_dir):
                continue
            
            # 收集该域名的所有JSON文件
            json_files = glob.glob(os.path.join(domain_dir, "*.json"))
            if not json_files:
                continue
            
            print(f"合并域名 {domain}: {len(json_files)} 个文件")
            
            all_urls = []
            for json_file in json_files:
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        urls = json.load(f)
                        all_urls.extend(urls)
                except Exception as e:
                    print(f"  警告: 无法读取 {json_file}: {e}")
            
            # 保存合并后的文件
            if all_urls:
                consolidated_file = os.path.join(domain_dir, f"{domain}_all_urls.json")
                with open(consolidated_file, 'w', encoding='utf-8') as f:
                    json.dump(all_urls, f, ensure_ascii=False, indent=2)
                
                consolidated_stats[domain] = {
                    'total_urls': len(all_urls),
                    'source_files': len(json_files),
                    'consolidated_file': consolidated_file
                }
                
                print(f"  -> {len(all_urls):,} URLs 保存到 {consolidated_file}")
        
        # 保存合并统计
        consolidation_summary = os.path.join(self.output_dir, 'consolidation_summary.json')
        with open(consolidation_summary, 'w', encoding='utf-8') as f:
            json.dump({
                'consolidation_time': datetime.now().isoformat(),
                'domains_consolidated': len(consolidated_stats),
                'domain_stats': consolidated_stats
            }, f, indent=2, ensure_ascii=False)
        
        print(f"合并摘要保存到: {consolidation_summary}")
        return consolidated_stats
    
    def save_summary(self, summary, output_file):
        """保存处理摘要"""
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"处理摘要已保存到: {output_file}")

def main():
    parser = argparse.ArgumentParser(description='按域名分类收集网页内容')
    parser.add_argument('--stats-file', 
                       default='/mnt/bn/tiktok-mm-5/aiic/users/tianyu/CodeSyntheticRL/data_process/url_stats.json',
                       help='URL统计文件路径')
    parser.add_argument('--data-dir', 
                       default='/mnt/hdfs/tiktok_aiic_new/user/liuqian/opencoder_web_reprocessed/',
                       help='parquet数据目录')
    parser.add_argument('--output-dir', 
                       default='/mnt/hdfs/tiktok_aiic_new/user/tianyu/opencoder/dataset/domain_collections',
                       help='输出目录')
    parser.add_argument('--min-frequency', type=int, default=100, 
                       help='域名最小频率阈值（默认100）')
    parser.add_argument('--workers', type=int, default=16, help='并行进程数（默认4）')
    parser.add_argument('--test', action='store_true', help='测试模式，只处理少量文件')
    parser.add_argument('--single-process', action='store_true', help='强制使用单进程模式')
    
    args = parser.parse_args()
    
    print("=== 按域名分类的网页内容收集器 ===")
    print(f"统计文件: {args.stats_file}")
    print(f"数据目录: {args.data_dir}")
    print(f"输出目录: {args.output_dir}")
    print(f"最小频率: {args.min_frequency}")
    print(f"进程数: {args.workers}")
    
    # 显示系统信息
    process = psutil.Process(os.getpid())
    print(f"初始内存使用: {process.memory_info().rss / 1024 / 1024:.1f} MB")
    print(f"系统可用内存: {psutil.virtual_memory().available / 1024 / 1024 / 1024:.1f} GB")
    
    # 创建收集器
    collector = DomainBasedCollector(
        data_dir=args.data_dir,
        stats_file=args.stats_file,
        output_dir=args.output_dir,
        min_frequency=args.min_frequency
    )
    
    # 加载高频域名
    stats = collector.load_high_frequency_domains()
    
    # 执行数据收集
    print("\\n开始数据收集...")
    use_multiprocessing = not args.single_process
    summary = collector.collect_and_classify(
        test_mode=args.test,
        use_multiprocessing=use_multiprocessing,
        max_workers=args.workers
    )
    
    # 保存处理摘要
    summary_file = os.path.join(args.output_dir, 'collection_summary.json')
    collector.save_summary(summary, summary_file)
    
    # 打印摘要
    print("\\n=== 收集摘要 ===")
    print(f"处理文件数: {summary['total_files_processed']}")
    print(f"总处理URL数: {summary['total_urls_processed']:,}")
    print(f"总收集URL数: {summary['total_urls_collected']:,}")
    print(f"收集率: {(summary['total_urls_collected']/summary['total_urls_processed']*100):.2f}%")
    print(f"总错误数: {summary['total_errors']:,}")
    
    print("\\n=== 域名收集分布（前20） ===")
    sorted_domains = sorted(summary['domain_collection_stats'].items(), 
                           key=lambda x: x[1], reverse=True)
    for i, (domain, count) in enumerate(sorted_domains[:20]):
        print(f"{i+1:2d}. {domain:<30} {count:,} URLs")
    
    # 执行文件合并
    print("\\n执行文件合并...")
    # consolidated_stats = collector.consolidate_domain_files()
        
    print(f"\\n最终内存使用: {get_memory_usage():.1f} MB")
    print("处理完成！")

if __name__ == "__main__":
    main()