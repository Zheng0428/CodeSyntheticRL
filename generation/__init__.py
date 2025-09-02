import os
import importlib
import glob

# 获取 generation 目录下所有 .py 文件（排除 __init__.py）
generation_files = glob.glob(os.path.join(os.path.dirname(__file__), "*.py"))
generation_files = [f for f in generation_files if not f.endswith("__init__.py")]

# 动态导入每个生成文件
for generation_file in generation_files:
    module_name = os.path.splitext(os.path.basename(generation_file))[0]
    importlib.import_module(f"generation.{module_name}")

# 递归导入子目录中的模块
subdirs = [d for d in os.listdir(os.path.dirname(__file__)) 
           if os.path.isdir(os.path.join(os.path.dirname(__file__), d))]

for subdir in subdirs:
    subdir_path = os.path.join(os.path.dirname(__file__), subdir)
    subdir_init = os.path.join(subdir_path, "__init__.py")
    
    # 如果子目录有 __init__.py 文件，导入它
    if os.path.exists(subdir_init):
        importlib.import_module(f"generation.{subdir}")
    else:
        # 如果没有 __init__.py，尝试导入子目录中的 main.py
        main_file = os.path.join(subdir_path, "main.py")
        if os.path.exists(main_file):
            importlib.import_module(f"generation.{subdir}.main")
