# generation.py 主入口
import yaml
from utils import _forward_registry

# 读取配置
with open("config/data_generation.yaml", "r") as f:
    config = yaml.safe_load(f)

# 动态调用对应的 forward 函数
forward_func = _forward_registry[config['forward']]
forward_func(config['input_path'], config['output_path'])