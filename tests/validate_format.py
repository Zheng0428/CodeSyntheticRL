#!/usr/bin/env python3
"""
数据格式验证脚本 - CodeSyntheticRL

该脚本用于验证JSONL文件是否符合项目的标准化输出格式要求。

用法:
    python tests/validate_format.py /path/to/data.jsonl
"""

import json
import sys
import os
from typing import Dict, Any, List, Tuple


def validate_required_fields(data: Dict[str, Any], line_num: int) -> List[str]:
    """
    验证必需字段是否存在且类型正确
    
    Args:
        data: 单行JSON数据
        line_num: 行号
    
    Returns:
        错误信息列表
    """
    errors = []
    
    # 定义必需字段及其类型
    required_fields = {
        'task_id': str,
        'question': str,
        'reward': dict,
        'data_source': str,
        'repo_name': str,
        'extra_info': dict
    }
    
    # 检查必需字段
    for field, expected_type in required_fields.items():
        if field not in data:
            errors.append(f"行 {line_num}: 缺少必需字段 '{field}'")
        elif not isinstance(data[field], expected_type):
            errors.append(f"行 {line_num}: 字段 '{field}' 类型错误，期望 {expected_type.__name__}，实际 {type(data[field]).__name__}")
    
    return errors


def validate_reward_structure(data: Dict[str, Any], line_num: int) -> List[str]:
    """
    验证reward字段的结构
    
    Args:
        data: 单行JSON数据
        line_num: 行号
    
    Returns:
        错误信息列表
    """
    errors = []
    
    if 'reward' not in data:
        return errors  # 这个错误已在validate_required_fields中捕获
    
    reward = data['reward']
    if not isinstance(reward, dict):
        return errors  # 类型错误已在validate_required_fields中捕获
    
    # 检查reward子字段
    required_reward_fields = {
        'ground_truth': str,
        'style': str
    }
    
    for field, expected_type in required_reward_fields.items():
        if field not in reward:
            errors.append(f"行 {line_num}: reward字段缺少子字段 '{field}'")
        elif not isinstance(reward[field], expected_type):
            errors.append(f"行 {line_num}: reward.{field} 类型错误，期望 {expected_type.__name__}，实际 {type(reward[field]).__name__}")
    
    # 检查style字段值的有效性
    if 'style' in reward and isinstance(reward['style'], str):
        valid_styles = {'rule', 'model', 'interpreter'}
        if reward['style'] not in valid_styles:
            errors.append(f"行 {line_num}: reward.style 值无效 '{reward['style']}'，仅支持: {', '.join(valid_styles)}")
    
    return errors


def validate_string_fields(data: Dict[str, Any], line_num: int) -> List[str]:
    """
    验证字符串字段是否为空
    
    Args:
        data: 单行JSON数据
        line_num: 行号
    
    Returns:
        错误信息列表
    """
    errors = []
    
    string_fields = ['task_id', 'question', 'data_source', 'repo_name']
    
    for field in string_fields:
        if field in data and isinstance(data[field], str):
            if not data[field].strip():
                errors.append(f"行 {line_num}: 字段 '{field}' 不能为空字符串")
    
    # 检查reward.ground_truth
    if 'reward' in data and isinstance(data['reward'], dict):
        if 'ground_truth' in data['reward'] and isinstance(data['reward']['ground_truth'], str):
            if not data['reward']['ground_truth'].strip():
                errors.append(f"行 {line_num}: reward.ground_truth 不能为空字符串")
    
    return errors


def validate_extra_fields(data: Dict[str, Any], line_num: int) -> List[str]:
    """
    检查是否有未定义的额外字段
    
    Args:
        data: 单行JSON数据
        line_num: 行号
    
    Returns:
        警告信息列表
    """
    warnings = []
    
    expected_fields = {'task_id', 'question', 'reward', 'data_source', 'repo_name', 'extra_info'}
    actual_fields = set(data.keys())
    
    extra_fields = actual_fields - expected_fields
    if extra_fields:
        warnings.append(f"行 {line_num}: 发现额外字段: {', '.join(extra_fields)}")
    
    return warnings


def validate_line(line: str, line_num: int) -> Tuple[List[str], List[str]]:
    """
    验证单行数据
    
    Args:
        line: JSON行数据
        line_num: 行号
    
    Returns:
        (错误列表, 警告列表)
    """
    errors = []
    warnings = []
    
    # 尝试解析JSON
    try:
        data = json.loads(line.strip())
    except json.JSONDecodeError as e:
        errors.append(f"行 {line_num}: JSON格式错误 - {str(e)}")
        return errors, warnings
    
    # 检查是否为字典
    if not isinstance(data, dict):
        errors.append(f"行 {line_num}: 数据必须是JSON对象，实际类型: {type(data).__name__}")
        return errors, warnings
    
    # 验证必需字段
    errors.extend(validate_required_fields(data, line_num))
    
    # 验证reward结构
    errors.extend(validate_reward_structure(data, line_num))
    
    # 验证字符串字段
    errors.extend(validate_string_fields(data, line_num))
    
    # 检查额外字段
    warnings.extend(validate_extra_fields(data, line_num))
    
    return errors, warnings


def validate_jsonl_file(file_path: str) -> bool:
    """
    验证JSONL文件格式
    
    Args:
        file_path: JSONL文件路径
    
    Returns:
        是否验证通过
    """
    if not os.path.exists(file_path):
        print(f"❌ 错误: 文件不存在 - {file_path}")
        return False
    
    if not file_path.endswith('.jsonl'):
        print(f"⚠️  警告: 文件扩展名不是.jsonl - {file_path}")
    
    print(f"🔍 验证文件: {file_path}")
    print("=" * 60)
    
    total_lines = 0
    valid_lines = 0
    total_errors = 0
    total_warnings = 0
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:  # 跳过空行
                    continue
                
                total_lines += 1
                errors, warnings = validate_line(line, line_num)
                
                if errors:
                    for error in errors:
                        print(f"❌ {error}")
                    total_errors += len(errors)
                else:
                    valid_lines += 1
                
                if warnings:
                    for warning in warnings:
                        print(f"⚠️  {warning}")
                    total_warnings += len(warnings)
    
    except UnicodeDecodeError:
        print(f"❌ 错误: 文件编码不是UTF-8")
        return False
    except Exception as e:
        print(f"❌ 错误: 读取文件时发生异常 - {str(e)}")
        return False
    
    # 输出统计信息
    print("=" * 60)
    print(f"📊 验证统计:")
    print(f"   总行数: {total_lines}")
    print(f"   有效行数: {valid_lines}")
    print(f"   错误行数: {total_lines - valid_lines}")
    print(f"   总错误数: {total_errors}")
    print(f"   总警告数: {total_warnings}")
    
    success_rate = (valid_lines / total_lines * 100) if total_lines > 0 else 0
    print(f"   成功率: {success_rate:.1f}%")
    
    if total_errors == 0:
        print(f"✅ 验证通过! 所有数据都符合标准格式。")
        return True
    else:
        print(f"❌ 验证失败! 发现 {total_errors} 个错误。")
        return False


def main():
    """主函数"""
    if len(sys.argv) != 2:
        print("用法: python tests/validate_format.py <jsonl_file_path>")
        print("示例: python tests/validate_format.py /path/to/data.jsonl")
        sys.exit(1)
    
    file_path = sys.argv[1]
    
    print("🚀 CodeSyntheticRL 数据格式验证器")
    print("=" * 60)
    
    success = validate_jsonl_file(file_path)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()