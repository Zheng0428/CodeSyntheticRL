import pandas as pd
import json
import os
import sys
from collections import defaultdict, Counter
import glob
from tqdm import tqdm
import argparse
import multiprocessing as mp
from functools import partial
import psutil
import gc
import warnings
warnings.filterwarnings('ignore')

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import extract_root_domain, get_memory_usage, force_gc, safe_parquet_read_batches


def process_file_chunk(file_path, chunk_size=10000):
    """处理单个文件块并返回统计结果，使用公共的分批读取函数"""
    try:
        local_stats = {
            'domain_stats': {},  # 使用普通dict代替defaultdict
            'protocol_stats': {},
            'total_records': 0,
            'valid_urls': 0,
            'invalid_urls': 0,
            'file_name': os.path.basename(file_path)
        }
        
        # 使用公共的安全分批读取函数
        for chunk_df in safe_parquet_read_batches(file_path, chunk_size):
            local_stats['total_records'] += len(chunk_df)
            
            # 过滤掉空的URL
            if 'url' in chunk_df.columns:
                valid_mask = chunk_df['url'].notna() & (chunk_df['url'] != '')
                valid_urls = chunk_df.loc[valid_mask, 'url']
                
                invalid_count = len(chunk_df) - len(valid_urls)
                local_stats['invalid_urls'] += invalid_count
                
                # 处理有效URLs
                for url in valid_urls:
                    protocol, root_domain = extract_root_domain(url)
                    
                    if not root_domain:
                        local_stats['invalid_urls'] += 1
                        continue
                    
                    local_stats['valid_urls'] += 1
                    
                    # 使用get方法避免defaultdict
                    local_stats['protocol_stats'][protocol] = local_stats['protocol_stats'].get(protocol, 0) + 1
                    local_stats['domain_stats'][root_domain] = local_stats['domain_stats'].get(root_domain, 0) + 1
            
            # 立即清理chunk数据
            del chunk_df
            if 'valid_urls' in locals():
                del valid_urls
            force_gc()
        
        return local_stats
        
    except Exception as e:
        print(f"处理文件 {file_path} 时出错: {e}")
        return {
            'domain_stats': {},
            'protocol_stats': {},
            'total_records': 0,
            'valid_urls': 0,
            'invalid_urls': 0,
            'file_name': os.path.basename(file_path)
        }

class FastURLClassifier:
    def __init__(self, data_dir, min_frequency=2, chunk_size=10000, max_workers=None):
        self.data_dir = data_dir
        self.min_frequency = min_frequency  # 最小频次阈值
        self.chunk_size = chunk_size  # 分块大小
        self.max_workers = max_workers or min(mp.cpu_count(), 8)  # 默认进程数
        
    def filter_low_frequency_domains(self, merged_stats):
        """过滤低频域名以减少内存使用"""
        # 如果域名数量过多，先过滤一次低频域名
        if len(merged_stats['domain_stats']) > 1000000:  # 超过100万个域名时过滤
            print(f"域名数量过多({len(merged_stats['domain_stats']):,})，过滤低频域名...")
            filtered_domains = {
                domain: count for domain, count in merged_stats['domain_stats'].items()
                if count >= max(2, self.min_frequency)
            }
            removed_count = len(merged_stats['domain_stats']) - len(filtered_domains)
            print(f"移除了 {removed_count:,} 个低频域名")
            
            merged_stats['domain_stats'] = filtered_domains
            gc.collect()
            print(f"过滤后内存使用: {get_memory_usage():.1f} MB")
        
        return merged_stats
    
    # get_memory_usage 函数已从 utils 导入，直接使用
    
    def merge_results(self, all_stats):
        """合并多个进程的统计结果"""
        merged = {
            'domain_stats': {},
            'protocol_stats': {},
            'total_records': 0,
            'valid_urls': 0,
            'invalid_urls': 0
        }
        
        for stats in all_stats:
            merged['total_records'] += stats['total_records']
            merged['valid_urls'] += stats['valid_urls']
            merged['invalid_urls'] += stats['invalid_urls']
            
            # 合并域名统计
            for domain, count in stats['domain_stats'].items():
                merged['domain_stats'][domain] = merged['domain_stats'].get(domain, 0) + count
            
            # 合并协议统计
            for protocol, count in stats['protocol_stats'].items():
                merged['protocol_stats'][protocol] = merged['protocol_stats'].get(protocol, 0) + count
            
            # 清理已处理的stats释放内存
            stats.clear()
        
        # 强制垃圾回收
        gc.collect()
        return merged
    
    def process_all_files(self, test_mode=False, use_multiprocessing=True):
        """处理所有parquet文件，支持多进程加速"""
        pattern = os.path.join(self.data_dir, "part-*")
        files = glob.glob(pattern)
        
        if test_mode:
            files = files[:2]  # 测试模式处理2个文件测试多进程
            print(f"测试模式：处理 {len(files)} 个文件")
        else:
            print(f"找到 {len(files)} 个文件")
        
        print(f"当前内存使用: {get_memory_usage():.1f} MB")
        
        if not use_multiprocessing or len(files) == 1:
            # 单进程模式
            print(f"使用单进程处理")
            all_stats = []
            for file_path in tqdm(files, desc="处理文件"):
                stats = process_file_chunk(file_path, self.chunk_size)
                all_stats.append(stats)
                print(f"处理完成: {stats['file_name']} - 总记录: {stats['total_records']}, 有效: {stats['valid_urls']}")
                gc.collect()
                print(f"内存使用: {get_memory_usage():.1f} MB")
        else:
            # 多进程模式
            print(f"使用 {self.max_workers} 个进程并行处理")
            
            # 创建进程函数
            process_func = partial(process_file_chunk, chunk_size=self.chunk_size)
            
            with mp.Pool(self.max_workers) as pool:
                # 使用imap而不是map以获得进度显示
                all_stats = list(tqdm(
                    pool.imap(process_func, files),
                    total=len(files),
                    desc="多进程处理文件"
                ))
                
                # 显示处理结果
                for stats in all_stats:
                    print(f"处理完成: {stats['file_name']} - 总记录: {stats['total_records']}, 有效: {stats['valid_urls']}")
        
        print(f"所有文件处理完成，合并结果...")
        merged_stats = self.merge_results(all_stats)
        
        print(f"合并完成，最终内存使用: {get_memory_usage():.1f} MB")
        return merged_stats
    
    def generate_statistics(self, merged_stats):
        """生成统计信息，优化内存使用"""
        # 过滤掉频次小于阈值的域名
        filtered_domains = {
            domain: count for domain, count in merged_stats['domain_stats'].items() 
            if count >= self.min_frequency
        }
        
        # 使用生成器来减少内存使用
        top_domains = dict(sorted(filtered_domains.items(), key=lambda x: x[1], reverse=True)[:100])
        
        stats = {
            'summary': {
                'total_records': merged_stats['total_records'],
                'valid_urls': merged_stats['valid_urls'],
                'invalid_urls': merged_stats['invalid_urls'],
                'unique_domains_total': len(merged_stats['domain_stats']),
                'unique_domains_filtered': len(filtered_domains),
                'min_frequency_threshold': self.min_frequency
            },
            'protocol_distribution': merged_stats['protocol_stats'].copy(),
            'domain_distribution': top_domains,  # 前100个域名
            'filtered_domains': filtered_domains  # 过滤后的所有域名
        }
        
        # 清理原始数据释放内存
        merged_stats.clear()
        gc.collect()
        
        return stats
    
    def save_statistics(self, output_file, test_mode=False, use_multiprocessing=True):
        """保存统计结果到JSON文件"""
        merged_stats = self.process_all_files(test_mode, use_multiprocessing)
        
        # 在生成最终统计前过滤低频域名
        merged_stats = self.filter_low_frequency_domains(merged_stats)
        
        stats = self.generate_statistics(merged_stats)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        
        print(f"统计结果已保存到: {output_file}")
        return stats

def main():
    parser = argparse.ArgumentParser(description='URL分类统计工具（多进程加速，内存优化）')
    parser.add_argument('--test', action='store_true', help='测试模式，只处理少量文件')
    parser.add_argument('--data-dir', default="/mnt/hdfs/tiktok_aiic_new/user/liuqian/opencoder_web_reprocessed/", 
                       help='数据目录路径')
    parser.add_argument('--output', default="/mnt/bn/tiktok-mm-5/aiic/users/tianyu/CodeSyntheticRL/data_process/url_stats.json",
                       help='输出文件路径')
    parser.add_argument('--min-freq', type=int, default=2, help='域名最小频次阈值（默认2）')
    parser.add_argument('--chunk-size', type=int, default=10000, help='分块大小（默认10000行）')
    parser.add_argument('--workers', type=int, default=None, help='并行进程数（默认自动）')
    parser.add_argument('--single-process', action='store_true', help='强制使用单进程模式')
    
    args = parser.parse_args()
    
    if args.test:
        print("=== 测试模式 ===")
        output_file = args.output.replace('.json', '_test.json')
    else:
        print("=== 完整处理模式 ===")
        output_file = args.output
    
    # 显示初始内存使用情况
    process = psutil.Process(os.getpid())
    print(f"初始内存使用: {process.memory_info().rss / 1024 / 1024:.1f} MB")
    print(f"系统可用内存: {psutil.virtual_memory().available / 1024 / 1024 / 1024:.1f} GB")
    print(f"CPU核心数: {mp.cpu_count()}")
    
    # 确定进程数
    max_workers = args.workers or min(mp.cpu_count(), 8)
    use_multiprocessing = not args.single_process
    
    print(f"多进程模式: {'启用' if use_multiprocessing else '禁用'}")
    if use_multiprocessing:
        print(f"进程数: {max_workers}")
    
    classifier = FastURLClassifier(
        args.data_dir, 
        min_frequency=args.min_freq, 
        chunk_size=args.chunk_size,
        max_workers=max_workers
    )
    stats = classifier.save_statistics(output_file, test_mode=args.test, use_multiprocessing=use_multiprocessing)
    
    # 打印摘要
    print("\n=== 处理摘要 ===")
    print(f"总记录数: {stats['summary']['total_records']:,}")
    print(f"有效URL: {stats['summary']['valid_urls']:,}")
    print(f"无效URL: {stats['summary']['invalid_urls']:,}")
    print(f"唯一域名总数: {stats['summary']['unique_domains_total']:,}")
    print(f"过滤后域名数: {stats['summary']['unique_domains_filtered']:,} (频次>={args.min_freq})")
    print(f"最终内存使用: {process.memory_info().rss / 1024 / 1024:.1f} MB")
    
    print("\n=== 协议分布 ===")
    for protocol, count in sorted(stats['protocol_distribution'].items(), 
                                key=lambda x: x[1], reverse=True):
        percentage = (count / stats['summary']['valid_urls']) * 100 if stats['summary']['valid_urls'] > 0 else 0
        print(f"{protocol}: {count:,} ({percentage:.2f}%)")
    
    print("\n=== Top 20 域名 ===")
    for i, (domain, count) in enumerate(stats['domain_distribution'].items()):
        if i >= 20:
            break
        percentage = (count / stats['summary']['valid_urls']) * 100 if stats['summary']['valid_urls'] > 0 else 0
        print(f"{domain}: {count:,} ({percentage:.2f}%)")

if __name__ == "__main__":
    main()