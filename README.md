# CodeSyntheticRL

一个用于代码合成强化学习的模块化框架，支持代码生成任务和质量评估的端到端流程。

## 🚀 项目概述

CodeSyntheticRL 是一个协作开发的框架，提供了标准化的接口来：

- **生成代码相关的训练数据**：通过 LLM 生成各种代码任务的问答对
- **评估代码质量**：提供多种评分机制，包括规则检查和 LLM 判断
- **支持强化学习训练**：为代码生成模型提供奖励信号

## 🏗️ 核心架构

### 主要组件

```
CodeSyntheticRL/
├── 📁 generation/           # 代码生成任务模块
│   ├── algo_complexity_pred/ # 示例：算法复杂度预测任务
│   └── [your_task]/         # 你的新任务
├── 📁 reward_score/         # 奖励评分模块
│   ├── algo_complexity_pred.py # 示例评分器
│   └── [your_scorer].py    # 你的新评分器
├── 📁 prompt/               # LLM 提示模板
├── 📁 config/               # 任务配置文件
├── 📁 sandbox/              # 代码执行沙箱
├── 📁 data_process/         # 数据处理工具（详见子目录 README）
├── 📄 utils.py              # 核心工具和注册系统
├── 📄 generation.py         # 主入口程序
└── 📄 envs.py               # 环境配置
```

### 核心设计理念

- **插件化架构**：使用装饰器注册系统，新任务即插即用
- **标准化接口**：统一的输入输出格式和函数签名
- **配置驱动**：通过 YAML 配置文件控制任务执行
- **混合评分**：支持规则匹配 + LLM 判断的双重评估

## 🔧 核心机制

### 装饰器注册系统

框架使用两个核心装饰器来实现任务注册：

```python
from utils import register_forward, register_reward_score

# 注册数据生成任务
@register_forward("task_name")
def forward(args):
    # 生成逻辑
    pass

# 注册评分函数
@register_reward_score("scorer_name") 
def compute_score(solution_str, ground_truth, extra_info):
    # 评分逻辑
    return {"score": score, "extra_info": info}
```

### LLM 集成

框架提供了便捷的 LLM 调用接口：

```python
from utils import get_llm_response, get_llm_responses_batch

# 单个请求
response = get_llm_response(prompt, temperature=0.7)

# 批量并发请求（推荐）
responses = get_llm_responses_batch(
    prompts=prompts,
    batch_size=100,
    max_concurrency=15
)
```

## 📊 数据资源

本项目的可用数据集已发布在 Hugging Face Collections：

🔗 **数据集链接**: [Code Synthetic RL Rollout Collection](https://huggingface.co/collections/aaabiao/code-synthetic-rl-rollout-68b9220c78768a27941a3f2c)

该 Collection 包含了各种代码任务的基础数据，你可以：
- 浏览已有的数据集格式作为参考
- 有新需求可以直接 @郑天昱

## 📋 任务文档

详细的任务需求和开发指南请查看：

🔗 **任务文档**: [Code Synthetic RL](https://bytedance.larkoffice.com/docx/C14PdjpiCoA4MPxNjcCcaKGYnqb)


## 📝 快速开始 - 基于示例学习

### 1. 环境配置

```bash
# 安装依赖
pip install requests yaml tqdm aiohttp

# 配置 LLM API
cp envs.py.example envs.py
# 编辑 envs.py 设置你的 API_KEY 和 BASE_URL
```

### 2. 运行示例任务

```bash
# 运行算法复杂度预测任务
python generation.py --config_name algo_complexity_pred

# 测试评分器
python reward_score/algo_complexity_pred.py
```

## 🛠️ 如何添加新任务

### Step 1: 创建生成任务

以 `algo_complexity_pred` 为模板：

**1. 创建任务目录结构**
```bash
mkdir generation/[your_task_name]
touch generation/[your_task_name]/__init__.py
touch generation/[your_task_name]/main.py
```

**2. 实现生成函数** (`generation/[your_task_name]/main.py`)
```python
from utils import register_forward, get_llm_responses_batch, read_yaml

@register_forward("[your_task_name]")
def forward(args):
    """
    参考 algo_complexity_pred/main.py 的实现模式
    """
    input_path = args['input_path']
    output_path = args['output_path']
    
    # 1. 加载数据
    data = load_your_data(input_path)
    
    # 2. 读取 prompt 模板
    template = read_yaml('[your_task_name]')
    
    # 3. 准备 LLM prompts
    prompts = []
    for item in data:
        prompt = template['prompt_template'].format(**item)
        prompts.append(prompt)
    
    # 4. 批量调用 LLM
    responses = get_llm_responses_batch(prompts)
    
    # 5. 解析并保存结果
    results = []
    for response in responses:
        parsed = parse_your_response(response)  # 自定义解析逻辑
        results.append(parsed)
    
    save_results(results, output_path)
```

**3. 创建 prompt 模板** (`prompt/[your_task_name].yaml`)
```yaml
prompt_template: |
  Your task description here...
  
  Input: {input_field}
  
  Generate: specific requirements
  
  Output format:
  [define your expected format]
```

**4. 创建配置文件** (`config/[your_task_name].yaml`)
```yaml
forward: [your_task_name]
input_path: /path/to/your/input/data
output_path: /path/to/your/output/data
limit: 0  # 0 for no limit
llm: true
# 其他自定义参数
```

### Step 2: 创建评分器

参考 `reward_score/algo_complexity_pred.py`：

**1. 创建评分器文件** (`reward_score/[your_task_name].py`)
```python
from utils import register_reward_score

@register_reward_score("[your_task_name]")
def compute_score(solution_str, ground_truth, extra_info):
    """
    参考 algo_complexity_pred.py 的混合评分策略：
    1. 先尝试规则匹配
    2. 失败时使用 LLM 判断
    """
    
    # 规则匹配逻辑
    rule_based_result = your_rule_based_check(solution_str, ground_truth)
    
    if rule_based_result is not None:
        return {
            "score": 1.0 if rule_based_result else 0.0,
            "extra_info": {
                "method": "rule_based",
                "extracted": rule_based_result
            }
        }
    
    # LLM 判断逻辑
    llm_result = your_llm_judgment(solution_str, ground_truth)
    
    return {
        "score": 1.0 if llm_result else 0.0,
        "extra_info": {
            "method": "llm_judgment",
            "details": "..."
        }
    }

def test_[your_task_name]():
    """添加测试用例"""
    test_cases = [
        ("input1", "expected1", 1.0),
        ("input2", "expected2", 0.0),
    ]
    
    for solution, ground_truth, expected in test_cases:
        result = compute_score(solution, ground_truth, None)
        assert abs(result["score"] - expected) < 1e-6

if __name__ == "__main__":
    test_[your_task_name]()
    print("All tests passed!")
```

### Step 3: 运行你的任务

```bash
# 运行数据生成
python generation.py --config_name [your_task_name]

# 测试评分器
python reward_score/[your_task_name].py
```

## 📋 开发规范

### 必须遵循的接口

**Generation 任务：**
- 函数名必须是 `forward`
- 必须接受 `args` 参数（字典格式）
- 必须包含 `input_path` 和 `output_path`
- 使用 `@register_forward("task_name")` 装饰器

**Reward Score 评分器：**
- 函数名必须是 `compute_score`
- 参数：`(solution_str, ground_truth, extra_info)`
- 返回：`{"score": float, "extra_info": dict}`
- 使用 `@register_reward_score("scorer_name")` 装饰器

### 推荐实践

1. **混合评分策略**：优先使用规则匹配，失败时调用 LLM
2. **批量处理**：使用 `get_llm_responses_batch` 提高效率
3. **错误处理**：添加 try-catch 和重试机制
4. **测试用例**：为每个评分器添加测试函数
5. **文档说明**：在代码中添加清晰的注释

## 🧪 测试和验证

每个新任务都应该包含测试：

```python
# 在评分器文件中添加测试
def test_your_scorer():
    # 正确案例
    result = compute_score("correct_answer", "ground_truth", None)
    assert result["score"] == 1.0
    
    # 错误案例
    result = compute_score("wrong_answer", "ground_truth", None)
    assert result["score"] == 0.0

if __name__ == "__main__":
    test_your_scorer()
```

## 📊 项目状态

### 已完成的任务示例
- ✅ **algo_complexity_pred**: 算法复杂度预测 - 完整实现包括混合评分策略

### 等待开发的任务
- 🔄 **你的任务**: 请基于 algo_complexity_pred 的模式来实现

## 🤝 协作指南

1. **Fork 项目**：创建你的分支进行开发
2. **遵循示例**：严格按照 `algo_complexity_pred` 的模式实现
3. **测试充分**：确保你的评分器通过所有测试用例
4. **文档清晰**：为你的任务添加清晰的说明
5. **提交 PR**：完成后提交 Pull Request

## ⚠️ 重要提醒

- 新任务的命名必须唯一，避免冲突
- 严格遵循 `forward` 和 `compute_score` 的函数签名
- LLM 调用需要配置正确的 API 密钥
- 大规模数据处理时注意内存和API限制
- 定期运行测试确保功能正常

## 📚 更多信息

- **数据处理工具**：详见 `./data_process/README.md`
- **沙箱使用**：详见 `./sandbox/README.md`
- **示例代码**：参考 `generation/algo_complexity_pred/` 和 `reward_score/algo_complexity_pred.py`

---

**开始开发你的第一个任务吧！** 🚀