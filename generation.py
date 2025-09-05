# generation.py 主入口
import argparse
import yaml
# 先导入generation模块来注册forward函数
import generation
from utils import _forward_registry


def main():
    parser = argparse.ArgumentParser(description='Code generation tool')
    parser.add_argument('--config_name', default='algo_complexity_pred', help='Config name (e.g., data_generation)')
    
    args = parser.parse_args()
    config_path = f"config/{args.config_name}.yaml"
    
    # 读取配置
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: Config file {config_path} not found")
        return
    
    # 动态调用对应的 forward 函数
    forward_func = _forward_registry[config['forward']]
    forward_func(config)


if __name__ == "__main__":
    main()