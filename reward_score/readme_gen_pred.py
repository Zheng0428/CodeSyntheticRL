import difflib
from utils import register_reward_score, get_llm_response

def compute_similarity(a: str, b: str) -> float:
    """计算两个字符串的相似度（0-1之间）"""
    return difflib.SequenceMatcher(None, a, b).ratio()

def rule_based_check(solution_str, ground_truth, high_thresh=0.8, low_thresh=0.3):
    """
    使用文本相似度的规则匹配：
    - 如果相似度>=high_thresh → True
    - 如果相似度<=low_thresh → False
    - 否则 → None (交给LLM)
    """
    if not solution_str.strip() or not ground_truth.strip():
        return False  # 空直接判定为错误
    
    similarity = compute_similarity(solution_str, ground_truth)
    
    if similarity >= high_thresh:
        return True
    elif similarity <= low_thresh:
        return False
    else:
        return None  # 交给 LLM 处理

def llm_judgment(solution_str, ground_truth):
    """
    用LLM判断README是否和ground_truth足够匹配。
    LLM 只需回答YES/NO
    """
    prompt = f"""You are evaluating if an auto-generated README matches the reference README.

Generated README:
\"\"\"{solution_str}\"\"\"

Reference README:
\"\"\"{ground_truth}\"\"\"

Does the generated README adequately cover the same content and intent as the reference README?

Answer only "YES" or "NO"."""
    try:
        llm_response = get_llm_response(prompt, temperature=0.0)
        if llm_response:
            return llm_response.strip().upper() == "YES"
    except Exception:
        pass
    return False

@register_reward_score("readme_gen")
def compute_score(solution_str, ground_truth, extra_info):
    """
    README 生成任务评分：
    1. 用相似度做规则匹配
    2. 不确定时用LLM判断
    """
    # 规则匹配
    rule_based_result = rule_based_check(solution_str, ground_truth)
    
    if rule_based_result is not None:  # True or False
        return {
            "score": 1.0 if rule_based_result else 0.0,
            "extra_info": {
                "method": "rule_based",
                "similarity": compute_similarity(solution_str, ground_truth),
                "decision": rule_based_result
            }
        }
    
    # LLM 判断
    llm_result = llm_judgment(solution_str, ground_truth)
    
    return {
        "score": 1.0 if llm_result else 0.0,
        "extra_info": {
            "method": "llm_judgment",
            "similarity": compute_similarity(solution_str, ground_truth),
            "decision": llm_result
        }
    }
