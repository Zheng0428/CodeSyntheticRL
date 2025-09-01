#!/usr/bin/env python3
"""
批量将HTML内容转换为Markdown格式
从domain_samples目录读取JSON文件，处理其中的HTML内容并保存新文件
"""

import sys
import os
import json
import glob
import argparse
from pathlib import Path
from tqdm import tqdm
import multiprocessing as mp
from functools import partial

# 添加code-html-to-markdown目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'code-html-to-markdown'))

# 导入函数
from main import code_html_to_markdown

def process_single_file(file_args):
    """
    处理单个JSON文件（多进程版本）
    """
    json_file, output_suffix, verbose = file_args
    return _process_single_file(json_file, output_suffix, verbose)

def _process_single_file(json_file, output_suffix="_markdown", verbose=True):
    """
    处理单个JSON文件，将content字段的HTML转换为Markdown
    """
    try:
        # 读取JSON文件
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not isinstance(data, list):
            if verbose:
                print(f"  警告: {os.path.basename(json_file)} 不是列表格式，跳过")
            return None
        
        processed_count = 0
        error_count = 0
        
        # 处理每条数据
        for item in data:
            if isinstance(item, dict) and 'content' in item:
                try:
                    html_content = item['content']
                    if html_content and isinstance(html_content, str):
                        # 转换HTML为Markdown
                        markdown_content = code_html_to_markdown(html_content)
                        item['content'] = markdown_content
                        item['content_format'] = 'markdown'  # 添加格式标记
                        processed_count += 1
                    else:
                        # 空内容或非字符串内容，标记为原始格式
                        item['content_format'] = 'raw'
                except Exception as e:
                    if verbose:
                        print(f"    转换错误: {str(e)[:100]}...")
                    error_count += 1
                    # 保留原始内容，标记为错误
                    item['content_format'] = 'error'
        
        # 生成输出文件名
        file_path = Path(json_file)
        output_file = file_path.parent / f"{file_path.stem}{output_suffix}.json"
        
        # 保存处理后的数据
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return {
            'input_file': json_file,
            'output_file': str(output_file),
            'total_items': len(data),
            'processed_items': processed_count,
            'error_items': error_count,
            'success': True
        }
        
    except Exception as e:
        return {
            'input_file': json_file,
            'output_file': None,
            'total_items': 0,
            'processed_items': 0,
            'error_items': 0,
            'success': False,
            'error': str(e)
        }

def find_json_files(input_dir, exclude_suffix="_markdown"):
    """
    查找输入目录下所有的JSON文件（排除输出文件）
    """
    json_files = []
    
    # 遍历所有子目录
    for domain_dir in os.listdir(input_dir):
        domain_path = os.path.join(input_dir, domain_dir)
        if os.path.isdir(domain_path):
            # 查找该域名目录下的JSON文件
            pattern = os.path.join(domain_path, "*.json")
            files = glob.glob(pattern)
            
            # 过滤掉以exclude_suffix结尾的文件
            filtered_files = [
                f for f in files 
                if not os.path.basename(f).endswith(f"{exclude_suffix}.json")
            ]
            json_files.extend(filtered_files)
    
    return json_files

def cleanup_existing_output_files(input_dir, output_suffix):
    """
    清理目录下所有以指定后缀结尾的文件
    """
    deleted_count = 0
    
    # 遍历所有子目录
    for domain_dir in os.listdir(input_dir):
        domain_path = os.path.join(input_dir, domain_dir)
        if os.path.isdir(domain_path):
            # 查找以output_suffix结尾的JSON文件
            pattern = os.path.join(domain_path, f"*{output_suffix}.json")
            files_to_delete = glob.glob(pattern)
            
            for file_path in files_to_delete:
                try:
                    os.remove(file_path)
                    deleted_count += 1
                except Exception as e:
                    print(f"  警告: 无法删除文件 {file_path}: {e}")
    
    return deleted_count

def group_files_by_directory(json_files):
    """
    将文件按所在目录分组
    """
    grouped_files = {}
    
    for file_path in json_files:
        directory = os.path.dirname(file_path)
        if directory not in grouped_files:
            grouped_files[directory] = []
        grouped_files[directory].append(file_path)
    
    return grouped_files

def process_directory_files(dir_args):
    """
    处理单个目录下的所有JSON文件并合并（多进程版本）
    """
    directory_path, files_in_dir, output_suffix, verbose = dir_args
    return _process_directory_files(directory_path, files_in_dir, output_suffix, verbose)

def _process_directory_files(directory_path, files_in_dir, output_suffix="_markdown", verbose=True):
    """
    处理单个目录下的所有JSON文件并合并为一个文件
    """
    try:
        all_processed_data = []
        total_items = 0
        processed_count = 0
        error_count = 0
        
        directory_name = os.path.basename(directory_path)
        
        if verbose:
            print(f"  处理目录: {directory_name} ({len(files_in_dir)} 个文件)")
        
        # 处理目录下的每个JSON文件
        for json_file in files_in_dir:
            try:
                # 读取JSON文件
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                if not isinstance(data, list):
                    if verbose:
                        print(f"    警告: {os.path.basename(json_file)} 不是列表格式，跳过")
                    continue
                
                # 处理每条数据
                for item in data:
                    total_items += 1
                    if isinstance(item, dict) and 'content' in item:
                        try:
                            html_content = item['content']
                            if html_content and isinstance(html_content, str):
                                # 转换HTML为Markdown
                                markdown_content = code_html_to_markdown(html_content)
                                item['content'] = markdown_content
                                item['content_format'] = 'markdown'
                                item['source_file'] = os.path.basename(json_file)  # 记录源文件
                                processed_count += 1
                            else:
                                item['content_format'] = 'raw'
                                item['source_file'] = os.path.basename(json_file)
                        except Exception as e:
                            if verbose:
                                print(f"      转换错误: {str(e)[:100]}...")
                            error_count += 1
                            item['content_format'] = 'error'
                            item['source_file'] = os.path.basename(json_file)
                    
                    all_processed_data.append(item)
                        
            except Exception as e:
                if verbose:
                    print(f"    文件读取错误 {json_file}: {e}")
                continue
        
        if not all_processed_data:
            return {
                'directory': directory_path,
                'output_file': None,
                'total_items': 0,
                'processed_items': 0,
                'error_items': 0,
                'success': False,
                'error': '没有有效数据'
            }
        
        # 生成合并后的输出文件名
        output_file = os.path.join(directory_path, f"{directory_name}{output_suffix}.json")
        
        # 保存合并后的数据
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_processed_data, f, ensure_ascii=False, indent=2)
        
        if verbose:
            print(f"    ✓ 合并完成: {len(all_processed_data)} 条数据 -> {os.path.basename(output_file)}")
        
        return {
            'directory': directory_path,
            'output_file': output_file,
            'source_files': len(files_in_dir),
            'total_items': total_items,
            'processed_items': processed_count,
            'error_items': error_count,
            'success': True
        }
        
    except Exception as e:
        return {
            'directory': directory_path,
            'output_file': None,
            'source_files': len(files_in_dir),
            'total_items': 0,
            'processed_items': 0,
            'error_items': 0,
            'success': False,
            'error': str(e)
        }

def main():
    parser = argparse.ArgumentParser(description='批量将HTML内容转换为Markdown格式')
    parser.add_argument('--input-dir', 
                       default='/mnt/hdfs/tiktok_aiic_new/user/tianyu/opencoder/dataset/domain_samples',
                       help='输入目录路径（包含各个域名文件夹）')
    parser.add_argument('--output-suffix', default='_markdown',
                       help='输出文件后缀（默认_markdown）')
    parser.add_argument('--workers', type=int, default=None,
                       help='并行进程数（默认自动）')
    parser.add_argument('--single-process', action='store_true',
                       help='强制使用单进程模式')
    parser.add_argument('--test', action='store_true',
                       help='测试模式，只处理前5个文件')
    parser.add_argument('--verbose', action='store_true',
                       help='显示详细输出')
    
    args = parser.parse_args()
    
    print("=== HTML转Markdown批处理工具 ===")
    print(f"输入目录: {args.input_dir}")
    print(f"输出后缀: {args.output_suffix}")
    
    # 检查依赖
    try:
        import trafilatura
        print("✓ trafilatura 依赖检查通过")
    except ImportError:
        print("✗ 缺少 trafilatura 依赖，请安装: pip install trafilatura")
        return
    
    # 检查输入目录
    if not os.path.exists(args.input_dir):
        print(f"✗ 输入目录不存在: {args.input_dir}")
        return
    
    # 清理已存在的输出文件
    print(f"\n清理已存在的{args.output_suffix}文件...")
    deleted_count = cleanup_existing_output_files(args.input_dir, args.output_suffix)
    if deleted_count > 0:
        print(f"✓ 已删除 {deleted_count} 个旧的输出文件")
    else:
        print("✓ 没有找到需要清理的文件")
    
    # 查找所有JSON文件（排除输出文件）
    print("\n查找JSON文件...")
    json_files = find_json_files(args.input_dir, args.output_suffix)
    
    if not json_files:
        print("✗ 没有找到任何JSON文件")
        return
    
    # 按目录分组文件
    grouped_files = group_files_by_directory(json_files)
    
    if args.test:
        # 测试模式：只处理前几个目录
        test_dirs = list(grouped_files.keys())[:3]
        grouped_files = {k: v for k, v in grouped_files.items() if k in test_dirs}
        print(f"测试模式：处理 {len(grouped_files)} 个目录")
    else:
        print(f"找到 {len(json_files)} 个JSON文件，分布在 {len(grouped_files)} 个目录中")
    
    # 显示分组信息
    if args.verbose:
        print("\n目录分组信息:")
        for directory, files in grouped_files.items():
            dir_name = os.path.basename(directory)
            print(f"  {dir_name}: {len(files)} 个文件")
    
    # 设置并行参数
    max_workers = args.workers or min(mp.cpu_count(), len(grouped_files), 8)
    use_multiprocessing = not args.single_process and len(grouped_files) > 1
    
    if use_multiprocessing:
        print(f"\n使用 {max_workers} 个进程并行处理 {len(grouped_files)} 个目录")
    else:
        print(f"\n使用单进程模式处理 {len(grouped_files)} 个目录")
    
    # 处理文件（按目录合并）
    results = []
    
    if use_multiprocessing:
        # 多进程模式
        args_list = [
            (directory_path, files_in_dir, args.output_suffix, args.verbose)
            for directory_path, files_in_dir in grouped_files.items()
        ]
        
        with mp.Pool(max_workers) as pool:
            all_results = list(tqdm(
                pool.imap(process_directory_files, args_list),
                total=len(args_list),
                desc="多进程处理目录"
            ))
        
        results = all_results
    else:
        # 单进程模式
        for directory_path, files_in_dir in tqdm(grouped_files.items(), desc="处理目录"):
            result = _process_directory_files(directory_path, files_in_dir, args.output_suffix, args.verbose)
            results.append(result)
    
    # 统计结果
    successful = [r for r in results if r and r['success']]
    failed = [r for r in results if r and not r['success']]
    
    total_dirs = len(grouped_files)
    total_source_files = sum(r['source_files'] for r in successful)
    total_items = sum(r['total_items'] for r in successful)
    total_processed = sum(r['processed_items'] for r in successful)
    total_errors = sum(r['error_items'] for r in successful)
    
    print(f"\n=== 处理摘要 ===")
    print(f"处理目录数: {total_dirs}")
    print(f"源文件总数: {total_source_files}")
    print(f"成功处理目录: {len(successful)}")
    print(f"处理失败目录: {len(failed)}")
    print(f"数据项总数: {total_items}")
    print(f"成功转换: {total_processed}")
    print(f"转换错误: {total_errors}")
    print(f"转换率: {(total_processed/total_items*100):.2f}%" if total_items > 0 else "0%")
    print(f"生成合并文件: {len(successful)} 个")
    
    # 显示失败的目录
    if failed:
        print(f"\n处理失败的目录:")
        for result in failed:
            dir_name = os.path.basename(result['directory'])
            print(f"  ✗ {dir_name}: {result.get('error', '未知错误')}")
    
    # 显示成功的目录示例
    if successful and args.verbose:
        print(f"\n成功处理的目录示例:")
        for result in successful[:5]:
            dir_name = os.path.basename(result['directory'])
            output_name = os.path.basename(result['output_file'])
            print(f"  ✓ {dir_name}: {result['source_files']} 文件 -> {output_name} "
                  f"({result['processed_items']}/{result['total_items']} 项)")
    
    # 显示所有生成的文件
    if successful:
        print(f"\n生成的合并文件:")
        for result in successful:
            output_name = os.path.basename(result['output_file'])
            print(f"  📄 {output_name}")
    
    print("\n处理完成！")

if __name__ == "__main__":
    main()