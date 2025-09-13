import difflib
from utils import register_reward_score, get_llm_response

def compute_similarity(a: str, b: str) -> float:
    """计算两个字符串的相似度（0-1之间）"""
    return difflib.SequenceMatcher(None, a, b).ratio()

def rule_based_check(solution_str, ground_truth, high_thresh=0.9, low_thresh=0.15):
    """
    使用文本相似度的规则匹配：
    - 如果相似度>=high_thresh → 返回1.0
    - 如果相似度<=low_thresh → 返回0.0
    - 否则返回相似度（小数）
    """
    if not solution_str.strip() or not ground_truth.strip():
        return 0.0  # 空字符串直接返回0分
    
    similarity = compute_similarity(solution_str, ground_truth)
    
    if similarity >= high_thresh:
        return 1.0  # 完全匹配，返回1.0 
    if similarity <= low_thresh:
        return 0.0  # 完全不匹配，返回0.0s
    # 如果在阈值之间，返回计算的相似度
    return similarity

def llm_judgment(solution_str, ground_truth):
    """
    用LLM判断README是否和ground_truth足够匹配。
    LLM会根据prompt中的标准返回评分。
    """
    LLM_JUDGMENT_PROMPT = f"""
    You are evaluating whether an auto-generated README matches the reference README.

    Generated README:
    \"\"\"{solution_str}\"\"\"

    Reference README:
    \"\"\"{ground_truth}\"\"\"

    Please rate the similarity between the generated README and the reference README based on the following scale:

    - 1.0: The generated README fully matches the reference README, covering all the content and intent.
    - 0.8-1.0: The generated README is very similar, covering most of the important points with minor differences.
    - 0.5-0.8: The generated README covers some important points, but there are major missing details or unclear explanations.
    - 0.3-0.5: The generated README has some similarity but misses many critical details, or there are significant misunderstandings.
    - 0.0-0.3: The generated README is not similar to the reference README, with little to no overlap in content.

    Please return a score between 0 and 1, inclusive, based on this scale.
    """
    try:
        llm_response = get_llm_response(LLM_JUDGMENT_PROMPT, temperature=0.0)
        if llm_response:
            return float(llm_response.strip())  # 返回 LLM 给出的评分
    except Exception:
        pass
    return 0.0  # 如果LLM出错，返回0.0

@register_reward_score("readme_gen")
def compute_score(solution_str, ground_truth, extra_info):
    """
    README 生成任务评分：
    1. 先用相似度做规则匹配
    2. 不确定时使用 LLM 判断并给出评分
    """
    # 使用规则匹配评分
    rule_based_result = rule_based_check(solution_str, ground_truth)
    

    return {
        "score": rule_based_result,
        "extra_info": {
            "method": "rule_based",
            "similarity": compute_similarity(solution_str, ground_truth),
            "decision": rule_based_result >= 0.8
        }
    }

    # # 先不考虑用llm判断
    # llm_score = llm_judgment(solution_str, ground_truth)
    
    # return {
    #     "score": llm_score,
    #     "extra_info": {
    #         "method": "llm_judgment",
    #         "similarity": compute_similarity(solution_str, ground_truth),
    #         "decision": llm_score >= 0.8
    #     }
    # }
