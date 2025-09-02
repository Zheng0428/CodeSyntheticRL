# 数据处理脚本说明

本目录包含四个用于网页数据处理的Python脚本，分别负责统计、分类、采样和HTML转换功能。

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

### 4. html2markdown.py - HTML转Markdown批处理工具
**功能**: 批量将JSON文件中的HTML内容转换为Markdown格式

**主要特性**:
- 支持两种运行模式：清理模式和保留模式
- **清理模式**: 删除所有历史处理文件并重新处理所有目录
- **保留模式**: 跳过已处理的目录，只处理未处理的文件夹
- 多进程并行处理，提升转换效率
- 使用trafilatura和自定义算法进行HTML到Markdown转换
- 支持按目录合并转换结果
- 自动标记内容格式（markdown/raw/error）

**输入**: 包含HTML内容的JSON文件目录
**输出**: 转换后的Markdown格式JSON文件

**使用示例**:
```bash
# 清理模式：删除历史文件并重新处理所有目录
python html2markdown.py --cleanup-mode --input-dir domain_samples --output-suffix _markdown --workers 8

# 保留模式（默认）：跳过已处理目录，只处理新目录
python html2markdown.py --input-dir domain_samples --output-suffix _markdown --workers 8

# 测试模式
python html2markdown.py --test --verbose --max-files-per-dir 5
```

**运行模式说明**:
- `--cleanup-mode`: 启用清理模式，删除所有以`--output-suffix`结尾的文件并重新处理
- 默认保留模式: 保留已存在的处理文件，跳过已有输出文件的目录

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
    ↓
4. html2markdown.py (转换)
    ↓
   Markdown格式数据集
```

## 系统要求

- Python 3.6+
- 依赖包: pandas, tqdm, psutil, trafilatura (html2markdown.py需要)
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

### html2markdown.py
- `--cleanup-mode`: 启用清理模式，删除历史文件并重新处理
- `--output-suffix`: 输出文件后缀 (默认_markdown)
- `--max-files-per-dir`: 每个目录最多处理的JSON文件数量 (默认0，无限制)
- `--verbose`: 显示详细输出
- `--test`: 测试模式，只处理前3个目录

## 注意事项

1. **内存管理**: 处理大规模数据时建议使用多进程模式，单个进程内存不足时会自动分块处理
2. **存储空间**: 确保有足够的磁盘空间存储中间结果和最终输出
3. **数据质量**: 脚本会自动过滤无效URL和空数据
4. **进程优化**: 根据机器配置调整workers参数，过多进程可能导致内存不足
5. **HTML转换**: html2markdown.py需要安装trafilatura依赖: `pip install trafilatura`
6. **模式选择**: 使用html2markdown.py时，根据需求选择清理模式或保留模式

## 输出文件说明

- `url_stats.json`: URL统计报告，包含域名分布、协议统计等
- `collection_summary.json`: 分类收集摘要
- `sampling_summary.json`: 采样统计报告
- `*_markdown.json`: HTML转Markdown后的文件
- 各域名目录下的JSON文件: 实际的网页内容数据

## 快速开始

### 完整流程示例

```bash
# 1. 统计分析
python url_classifier_fast.py --data-dir /path/to/data --output url_stats.json

# 2. 分类收集  
python web_content_collector.py --stats-file url_stats.json --data-dir /path/to/data --output-dir domain_collections

# 3. 数据采样
python extract_samples.py --input-dir domain_collections --output-dir domain_samples --sample-size 100

# 4. HTML转换 (清理模式)
python html2markdown.py --cleanup-mode --input-dir domain_samples --output-suffix _markdown

# 4. HTML转换 (保留模式，增量处理)
python html2markdown.py --input-dir domain_samples --output-suffix _markdown
```

### 测试模式

所有脚本都支持测试模式，用于快速验证功能：

```bash
python url_classifier_fast.py --test
python web_content_collector.py --test
python extract_samples.py --test
python html2markdown.py --test --verbose
```