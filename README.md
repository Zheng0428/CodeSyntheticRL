# CodeSyntheticRL

## 🏗️ 架构设计

### 1. Generation 模块 (`generation/`)
负责代码生成任务，每个子任务都是一个独立的子目录。

### 2. Reward Score 模块 (`reward_score/`)
负责代码质量评估和奖励计算，每个评分器都是一个独立的 Python 文件。

## 📁 模块组织结构

```
CodeSyntheticRL/
├── generation/                    # 代码生成模块
│   ├── __init__.py              # 自动导入所有子模块
│   ├── algo_complexity_pred/    # 算法复杂度预测生成器
│   │   ├── __init__.py          # 导入 main 模块
│   │   ├── main.py              # 包含 forward 函数
│   │   └── data_generate.py     # 辅助工具函数
│   └── [new_task]/              # 新任务目录（可扩展）
│       ├── __init__.py          # 导入 main 模块
│       └── main.py              # 包含 forward 函数
├── reward_score/                  # 奖励评分模块
│   ├── __init__.py              # 自动导入所有评分器
│   ├── algo_complexity_pred.py  # 算法复杂度预测评分器
│   └── [new_scorer].py          # 新评分器（可扩展）
└── utils.py                      # 核心注册器和工具函数
```

## 🔧 核心机制

### 装饰器注册系统

项目使用两个核心装饰器来注册功能：

1. **`@register_forward`**: 注册代码生成任务
2. **`@register_reward_score`**: 注册评分函数

这些装饰器将函数注册到全局注册表中，实现动态调用。

## 📝 如何添加新的 Generation 任务

### 步骤 1: 创建任务目录结构

```bash
mkdir generation/new_task_name
touch generation/new_task_name/__init__.py
touch generation/new_task_name/main.py
```

### 步骤 2: 实现 main.py

```python
# generation/new_task_name/main.py
from utils import register_forward

@register_forward("new_task_name")
def forward(input_path, output_path, **kwargs):
    """
    新任务的 forward 函数
    
    Args:
        input_path: 输入数据路径
        output_path: 输出数据路径
        **kwargs: 其他参数
    """
    # 实现您的生成逻辑
    print(f"正在处理 {input_path} -> {output_path}")
    
    # 您的代码生成逻辑...    
```

### 步骤 3: 创建 __init__.py

```python
# generation/new_task_name/__init__.py
from . import main
```

### 步骤 4: 创建配置文件（可选）

```yaml
# config/new_task_name.yaml
param1: "value1"
param2: "value2"
```

## 📊 如何添加新的 Reward Score 评分器

### 步骤 1: 创建评分器文件

```bash
touch reward_score/new_scorer.py
```

### 步骤 2: 实现评分函数

```python
# reward_score/new_scorer.py
from utils import register_reward_score

@register_reward_score("new_scorer")
def compute_score(solution_str, ground_truth, extra_info):
    """
    新的评分函数
    
    Args:
        solution_str: 待评分的代码字符串
        ground_truth: 标准答案
        extra_info: 额外信息
    
    Returns:
        dict: 包含分数和额外信息的字典
    """
    # 实现您的评分逻辑
    score = 0.0
    
    # 示例：检查代码长度
    if len(solution_str.strip()) > 0:
        score += 0.5
    
    # 示例：检查是否包含特定函数
    if "def " in solution_str:
        score += 0.5
    
    return {
        "score": score,
        "extra_info": {
            "code_length": len(solution_str),
            "has_function": "def " in solution_str
        }
    }
```

## 🔄 自动导入机制

### Generation 模块自动导入

`generation/__init__.py` 会自动：

1. 导入根目录下的所有 `.py` 文件
2. 递归导入所有子目录
3. 如果子目录有 `__init__.py`，导入整个子目录
4. 如果没有 `__init__.py`，尝试导入 `main.py`

### Reward Score 模块自动导入

`reward_score/__init__.py` 会自动导入所有 `.py` 文件（排除 `__init__.py`）。

## 🚀 实际使用示例

### 运行现有的生成任务

```python
# 导入整个模块（会自动注册所有功能）
import generation
import reward_score

# 使用注册的生成器
from utils import _forward_registry
forward_func = _forward_registry["algo_complexity_pred"]
result = forward_func("input.jsonl", "output.json")

# 使用注册的评分器
from utils import _reward_score_registry
scorer_func = _reward_score_registry["algo_complexity_pred"]
score = scorer_func("code_string", "ground_truth", {})
```

### 通过配置文件运行

```python
# generation.py 主入口
import yaml
from utils import _forward_registry

# 读取配置
with open("config/data_generation.yaml", "r") as f:
    config = yaml.safe_load(f)

# 动态调用对应的 forward 函数
forward_func = _forward_registry[config['forward']]
forward_func(config['input_path'], config['output_path'])
```

## ⚠️ 注意事项

1. **命名规范**: 任务名称和评分器名称必须唯一
2. **函数签名**: `forward` 函数必须接受 `input_path` 和 `output_path` 参数
3. **返回值**: `compute_score` 函数必须返回包含 `score` 键的字典
4. **导入顺序**: 确保在使用前先导入相应的模块
