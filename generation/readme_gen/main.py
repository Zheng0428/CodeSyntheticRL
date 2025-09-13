from utils import register_forward, get_llm_responses_batch, read_yaml
import os
import json
from tqdm import tqdm
import tiktoken  # 用于计算token数量

def parse_your_response(prompt, question_id, repo_info):
    """把仓库信息转为强化学习训练数据格式"""
    return {
        "task_id": f"readme_gen_{question_id}",  # 必填唯一ID
        "question": prompt,                      # 完整的问题描述
        "reward": {                              # 奖励相关信息
            "ground_truth": repo_info['readme_content'],  # 标准答案：真实README
            "style": "rule"  # 评分方式 rule/model/interpreter，这里先用rule
        },
        "data_source": "local_gitrepo",          # 数据来源（可以自定义）
        "repo_name": repo_info['repo_name'],     # 仓库名
        "extra_info": {                          # 额外信息字典
            "repo_path": repo_info['repo_path'],
            "readme_file": repo_info['readme_file'],
            "folder_info": repo_info['folder_info'],
            "type": "readme_generation",
            "description": "Generate comprehensive README documentation based on repository contents"
        }
    }

def save_result(results, output_path):
    """按 JSONL 格式保存"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        for item in results:
            json_line = json.dumps(item, ensure_ascii=False)
            f.write(json_line + '\n')


# 初始化tokenizer
try:
    tokenizer = tiktoken.get_encoding("cl100k_base")
except:
    # 如果tiktoken不可用，使用简单的字符计数作为fallback
    tokenizer = None

def count_tokens(text):
    """计算文本的token数量"""
    if tokenizer:
        return len(tokenizer.encode(text))
    else:
        # fallback: 使用字符数除以4作为近似值
        return len(text) // 4

def load_readme_data(input_path='data/input/gitrepo_5', max_token=None):
    sample = 100
    # Get all repository directories
    repo_dirs = [d for d in os.listdir(input_path) 
                if os.path.isdir(os.path.join(input_path, d)) and not d.startswith('.')]  # 排除隐藏目录
    
    # Limit to sample size if specified
    if sample and len(repo_dirs) > sample:
        repo_dirs = repo_dirs[:sample]
    
    data = []
    repo_id = 0
    for repo_dir in tqdm(repo_dirs):
        repo_path = os.path.join(input_path, repo_dir)
        
        # 查找最外层README文件（不区分大小写）
        readme_file = None
        for file in os.listdir(repo_path):
            # 只检查文件，不检查目录
            if os.path.isfile(os.path.join(repo_path, file)) and \
               (file.lower() == 'readme.md' or file.lower() == 'readme'):
                readme_file = file
                break
        
        if not readme_file:
            continue  # 跳过没有README的仓库
        
        # 读取真实的README内容作为ground truth
        try:
            with open(os.path.join(repo_path, readme_file), 'r', encoding='utf-8') as f:
                readme_content = f.read()
        except Exception as e:
            print(f"读取README失败 {repo_path}: {e}")
            continue
        
        # 获取文件夹信息（排除最外层README，但保留子目录中的README）
        folder_info = folder_to_string(repo_path, exclude_outer_readme=True, max_token=max_token)
        
        # 截断readme_content如果超过max_token
        if max_token and readme_content:
            readme_tokens = count_tokens(readme_content)
            if readme_tokens > max_token:
                # 简单截断（可以根据需要实现更智能的截断）
                if tokenizer:
                    encoded = tokenizer.encode(readme_content)
                    truncated_encoded = encoded[:max_token]
                    readme_content = tokenizer.decode(truncated_encoded)
                else:
                    # fallback: 字符截断
                    readme_content = readme_content[:max_token * 4]
                print(f"警告: README内容被截断，原长度 {readme_tokens} tokens")
        
        data.append({
            'repo_id': repo_id,
            'repo_name': repo_dir,
            'repo_path': repo_path,
            'folder_info': folder_info,
            'readme_content': readme_content,  # 存储真实README内容作为gt
            'readme_file': readme_file  # 记录README文件名，用于后续过滤
        })
        repo_id += 1
    
    return data

def get_file_contents(root_dir, exclude_outer_readme=False, is_outer=True, outer_readme_name=None, max_token=None, current_tokens=0):
    """获取所有文件内容，只在最外层排除README，子目录中的README正常处理，支持token限制"""
    contents = []
    total_tokens = current_tokens
    
    # 扩展名到语言的映射
    ext_to_lang = {
        '.py': 'python',
        '.js': 'javascript',
        '.ts': 'typescript',
        '.java': 'java',
        '.cpp': 'cpp',
        '.c': 'c',
        '.md': 'markdown',
        '.json': 'json',
        '.yml': 'yaml',
        '.yaml': 'yaml',
        '.html': 'html',
        '.css': 'css',
        '.sh': 'bash',
        '.txt': 'text'
    }
    
    entries = os.listdir(root_dir)
    
    # 过滤掉以.开头的文件/目录
    filtered_entries = []
    for entry in entries:
        if entry.startswith('.'):
            continue
        
        # 只在最外层且需要排除README时才过滤
        if is_outer and exclude_outer_readme:
            if entry.lower() in ['readme', 'readme.md']:
                continue
            
        filtered_entries.append(entry)
    
    # 先处理当前目录的文件
    files = [e for e in filtered_entries if os.path.isfile(os.path.join(root_dir, e))]
    for file in files:
        # 检查是否超过token限制
        if max_token and total_tokens >= max_token:
            contents.append(f"\n[警告: 已达到token限制({max_token})，停止读取更多文件]")
            return contents, total_tokens
            
        file_path = os.path.join(root_dir, file)
        relative_path = os.path.relpath(file_path, root_dir)
        
        # 根据扩展名获取语言
        _, ext = os.path.splitext(file)
        lang = ext_to_lang.get(ext.lower(), 'text')
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 计算当前文件的token数量
            file_content_str = f"### {relative_path}\n```{lang}\n{content}\n```\n"
            file_tokens = count_tokens(file_content_str)
            
            # 检查添加后是否超过限制
            if max_token and total_tokens + file_tokens > max_token:
                # 如果超过限制，可以截断内容或跳过
                remaining_tokens = max_token - total_tokens
                if remaining_tokens > 100:  # 至少保留100个token的空间
                    # 截断内容
                    if tokenizer:
                        encoded = tokenizer.encode(content)
                        truncated_encoded = encoded[:remaining_tokens - 50]  # 留一些空间给格式
                        truncated_content = tokenizer.decode(truncated_encoded)
                    else:
                        truncated_content = content[: (remaining_tokens - 50) * 4]
                    
                    file_content_str = f"### {relative_path}\n```{lang}\n{truncated_content}\n[文件内容被截断...]\n```\n"
                    contents.append(file_content_str)
                    total_tokens = max_token
                    contents.append(f"\n[警告: 已达到token限制({max_token})，停止读取更多文件]")
                    return contents, total_tokens
                else:
                    # 跳过这个文件
                    continue
            
            # 添加文件内容
            contents.append(file_content_str)
            total_tokens += file_tokens
            
        except UnicodeDecodeError:
            # 二进制文件，token消耗很少
            bin_content = f"### {relative_path}\n[二进制文件或无法解析的编码，跳过展示]\n"
            bin_tokens = count_tokens(bin_content)
            if max_token and total_tokens + bin_tokens > max_token:
                continue
            contents.append(bin_content)
            total_tokens += bin_tokens
            
        except Exception as e:
            error_content = f"### {relative_path}\n[读取文件时出错: {str(e)}]\n"
            error_tokens = count_tokens(error_content)
            if max_token and total_tokens + error_tokens > max_token:
                continue
            contents.append(error_content)
            total_tokens += error_tokens
    
    # 再处理子目录（如果还有token空间）
    if max_token and total_tokens >= max_token:
        return contents, total_tokens
        
    dirs = [e for e in filtered_entries if os.path.isdir(os.path.join(root_dir, e))]
    for dir in dirs:
        dir_path = os.path.join(root_dir, dir)
        sub_contents, total_tokens = get_file_contents(
            dir_path, exclude_outer_readme, is_outer=False, 
            outer_readme_name=outer_readme_name, max_token=max_token, 
            current_tokens=total_tokens
        )
        contents.extend(sub_contents)
        
        # 检查是否达到限制
        if max_token and total_tokens >= max_token:
            break
    
    return contents, total_tokens

def folder_to_string(root_dir, exclude_outer_readme=False, max_token=None):
    """将文件夹结构和内容转换为字符串，只排除最外层的README，支持token限制"""
    if not os.path.isdir(root_dir):
        return f"错误: {root_dir} 不是一个有效的文件夹路径"
    
    folder_name = os.path.basename(root_dir)
    total_tokens = 0
    
    # 构建结果字符串
    result = [f"# 文件夹内容: {folder_name}\n"]
    total_tokens += count_tokens(result[-1])
    
    # 添加文件夹结构（只在最外层排除README）
    result.append("## 文件夹结构\n")
    total_tokens += count_tokens("## 文件夹结构\n")
    
    structure = get_folder_structure(root_dir, exclude_outer_readme=exclude_outer_readme, is_outer=True)
    structure_str = '\n'.join(structure) + '\n'
    structure_tokens = count_tokens(structure_str)
    
    # 检查结构是否超过限制
    if max_token and total_tokens + structure_tokens > max_token:
        # 截断结构信息
        if tokenizer:
            encoded = tokenizer.encode(structure_str)
            truncated_encoded = encoded[:max_token - total_tokens]
            structure_str = tokenizer.decode(truncated_encoded) + "\n[文件夹结构被截断...]"
        else:
            structure_str = structure_str[: (max_token - total_tokens) * 4] + "\n[文件夹结构被截断...]"
        result.append(structure_str)
        result.append("\n[警告: 已达到token限制，无法显示文件内容]")
        return '\n'.join(result)
    
    result.append(structure_str)
    total_tokens += structure_tokens
    
    result.append("## 文件内容\n")
    total_tokens += count_tokens("## 文件内容\n")
    
    # 添加文件内容（只在最外层排除README）
    file_contents, total_tokens = get_file_contents(
        root_dir, exclude_outer_readme=exclude_outer_readme, 
        is_outer=True, max_token=max_token, current_tokens=total_tokens
    )
    result.extend(file_contents)
    
    # 添加token使用信息（调试用）
    if max_token:
        result.append(f"\n[Token使用情况: {total_tokens}/{max_token}]")
    
    return '\n'.join(result)

def get_folder_structure(root_dir, prefix="", exclude_outer_readme=False, is_outer=True):
    """生成文件夹结构字符串，只在最外层排除README"""
    structure = []
    entries = os.listdir(root_dir)
    
    # 过滤掉以.开头的文件/目录
    filtered_entries = []
    for entry in entries:
        # 排除隐藏文件/目录
        if entry.startswith('.'):
            continue
        
        # 只在最外层且需要排除README时才过滤
        if is_outer and exclude_outer_readme:
            if entry.lower() in ['readme', 'readme.md']:
                continue  # 排除最外层README
            
        filtered_entries.append(entry)
    
    # 区分目录和文件
    dirs = [e for e in filtered_entries if os.path.isdir(os.path.join(root_dir, e))]
    files = [e for e in filtered_entries if os.path.isfile(os.path.join(root_dir, e))]
    
    # 先处理目录，再处理文件
    for i, entry in enumerate(dirs + files):
        path = os.path.join(root_dir, entry)
        is_last = i == len(dirs + files) - 1
        
        if os.path.isdir(path):
            structure.append(f"{prefix}{'└── ' if is_last else '├── '}{entry}/")
            # 递归处理子目录，更新前缀，标记为非外层目录
            new_prefix = prefix + "    " if is_last else prefix + "│   "
            structure.extend(get_folder_structure(path, new_prefix, exclude_outer_readme, is_outer=False))
        else:
            structure.append(f"{prefix}{'└── ' if is_last else '├── '}{entry}")
    
    return structure

@register_forward("readme_gen")
def forward(args):
    """Main function to generate QA pairs with prompt as question and real README as answer"""
    print("readme generation process begins!")
    input_path = args['input_path']
    output_path = args['output_path']
    max_token = args.get('max_token')  # 获取max_token参数
    
    # 1. 加载仓库数据（包含真实README内容）
    data = load_readme_data(
        input_path=input_path,
        max_token=max_token  # 传递max_token参数
    )
    
    if not data:
        print("没有找到包含README的仓库数据")
        return
    
    # 2. 读取prompt模板
    template = read_yaml('readme_gen')
    prompt_template = template.get('prompt_template', 
                                  "Generate a README for a repository with the following structure and contents:\n{folder_info}")
    # 3. 准备prompts（将作为问题）
    prompts = []
    for item in data:
        prompt = prompt_template.format(** item)
        prompts.append(prompt)
    
    # 4. 生成并保存结果 - 不需要调用LLM，直接使用真实README作为答案
    results = []
    for question_id, (prompt, repo_info) in enumerate(zip(prompts, data)):
        # 使用prompt作为问题，真实README作为答案
        parsed_result = parse_your_response(prompt, question_id, repo_info)
        results.append(parsed_result)
    
    save_result(results, output_path)
    print(f"已保存 {len(results)} 个QA对到 {output_path}")