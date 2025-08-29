# 数据处理脚本说明

本目录包含三个用于网页数据处理的Python脚本，分别负责统计、分类和采样功能。

## 脚本概览

### 1. url_classifier_fast.py - URL统计分析器
**功能**: 对大规模parquet数据进行URL统计分析，提取域名分布信息

**主要特性**:
- 多进程并行处理，支持大规模数据
- 内存优化，分块处理避免内存溢出
- 域名频次统计和协议分析
- 自动过滤低频域名减少内存使用

**输入**: parquet格式的网页数据文件
**输出**: JSON格式的统计报告，包含域名分布和协议统计

**使用示例**:
```bash
python url_classifier_fast.py --data-dir /path/to/data --output url_stats.json --min-freq 100
```

### 2. web_content_collector.py - 网页内容分类收集器
**功能**: 根据URL统计结果，按高频域名分类收集存储网页内容

**主要特性**:
- 基于域名频次阈值筛选目标域名
- 按域名组织数据，分别存储
- 支持多进程并行处理
- 自动合并同域名的多个文件

**输入**: 
- parquet格式的网页数据文件
- URL统计JSON文件（来自url_classifier_fast.py）

**输出**: 按域名组织的JSON文件，每个域名一个目录

**使用示例**:
```bash
python web_content_collector.py --stats-file url_stats.json --data-dir /path/to/data --output-dir domain_collections --min-frequency 100
```

### 3. extract_samples.py - 数据采样器
**功能**: 从每个根URL目录中随机提取指定数量的数据样本

**主要特性**:
- **优化采样策略**: 先随机选择少量文件再采样，大幅提升处理速度
- 多进程并行处理，支持大规模域名目录
- 支持自定义采样数量和文件选择数量
- 随机采样保证数据代表性
- 可设置随机种子确保结果可重现
- 生成详细的采样统计报告

**性能优化**:
- 当单个域名有上千个文件时，避免读取所有文件
- 默认只随机选择10个文件进行数据采样
- 大幅减少I/O操作和内存使用

**输入**: 分类后的域名目录（来自web_content_collector.py）
**输出**: 每个域名的样本数据和采样统计报告

**使用示例**:
```bash
python extract_samples.py --input-dir domain_collections --output-dir domain_samples --sample-size 100 --max-files 10 --workers 8
```

## 工作流程

完整的数据处理流程为：

```
原始parquet数据 
    ↓
1. url_classifier_fast.py (统计)
    ↓
   URL统计文件
    ↓  
2. web_content_collector.py (分类)
    ↓
   按域名分类的数据目录
    ↓
3. extract_samples.py (采样)
    ↓
   样本数据集
```

## 系统要求

- Python 3.6+
- 依赖包: pandas, tqdm, psutil
- 建议内存: 500GB+ (处理大规模数据时)
- 多核CPU (支持并行处理)

## 配置参数

### 通用参数
- `--workers`: 并行进程数
- `--test`: 测试模式，处理少量文件
- `--single-process`: 强制单进程模式

### url_classifier_fast.py
- `--min-freq`: 域名最小频次阈值 (默认2)
- `--chunk-size`: 分块大小 (默认10000行)

### web_content_collector.py  
- `--min-frequency`: 域名最小频次阈值 (默认100)

### extract_samples.py
- `--sample-size`: 每个域名采样数量 (默认100)
- `--seed`: 随机种子 (默认42)
- `--max-files`: 每个域名最多读取的文件数 (默认10)

## 注意事项

1. **内存管理**: 处理大规模数据时建议使用多进程模式，单个进程内存不足时会自动分块处理
2. **存储空间**: 确保有足够的磁盘空间存储中间结果和最终输出
3. **数据质量**: 脚本会自动过滤无效URL和空数据
4. **进程优化**: 根据机器配置调整workers参数，过多进程可能导致内存不足

## 输出文件说明

- `url_stats.json`: URL统计报告，包含域名分布、协议统计等
- `collection_summary.json`: 分类收集摘要
- `sampling_summary.json`: 采样统计报告
- 各域名目录下的JSON文件: 实际的网页内容数据