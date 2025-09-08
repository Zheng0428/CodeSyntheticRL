import json
import re
import os
import sys
import numpy as np
from typing import Dict, Any, Optional

# Add parent directory to path to import utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from utils import register_reward_score, get_llm_response
except ImportError:
    print("Could not import functions from utils.py. Make sure it exists in the parent directory.")
    sys.exit(1)

MAX_CHAR_DISPLAY = 2048

# LLM prompt template for model-based judgment
LLM_JUDGMENT_PROMPT = """You are evaluating whether a response correctly answers a question about algorithm complexity.

Response: "{response}"
Expected Answer: "{ground_truth}"

Task: Determine if the response correctly identifies the complexity as "{ground_truth}".

The response is CORRECT if:
1. It contains the exact complexity notation "{ground_truth}"
2. It describes the complexity using equivalent terms (e.g., "linear" for O(n), "quadratic" for O(n^2), "constant" for O(1))
3. It uses equivalent notation (e.g., O(n^2) = O(n²) = O(n**2))

Answer ONLY with "YES" if the response is correct, or "NO" if it is incorrect.

Answer:"""

def normalize_complexity(complexity_str: str) -> str:
    """
    Normalize complexity notation for comparison.
    
    Args:
        complexity_str (str): The complexity string to normalize
        
    Returns:
        str: Normalized complexity string
    """
    if not complexity_str:
        return ""
    
    # Remove whitespace and convert to lowercase
    normalized = complexity_str.strip().lower()
    
    # Convert all notation types to O()
    normalized = re.sub(r'[θΘ]\(([^)]+)\)', r'O(\1)', normalized)
    normalized = re.sub(r'[ωΩ]\(([^)]+)\)', r'O(\1)', normalized)
    normalized = re.sub(r'o\(([^)]+)\)', r'O(\1)', normalized)
    
    # Handle parentheses mismatch (fix missing closing parenthesis)
    if normalized.startswith('o(') and not normalized.endswith(')'):
        normalized += ')'
    
    # Remove extra spaces around operators
    normalized = re.sub(r'\s*\*\s*', '*', normalized)
    normalized = re.sub(r'\s*\+\s*', '+', normalized)
    normalized = re.sub(r'\s*\^\s*', '^', normalized)
    
    # Normalize log expressions
    # n*log(n) -> n*log n
    normalized = re.sub(r'log\s*\(\s*n\s*\)', 'log n', normalized)
    normalized = re.sub(r'logn\b', 'log n', normalized)
    
    # Normalize spacing in compound expressions
    # n*log n -> n log n
    normalized = re.sub(r'n\s*\*\s*log\s+n', 'n log n', normalized)
    
    # n^2 vs n²
    normalized = normalized.replace('²', '^2')
    normalized = normalized.replace('³', '^3')
    
    # Handle 2^n vs 2**n
    normalized = normalized.replace('**', '^')
    
    # Final cleanup - ensure proper O() format
    if not normalized.startswith('o('):
        normalized = re.sub(r'^([^o].*)', r'O(\1)', normalized)
        if not normalized.endswith(')'):
            normalized += ')'
    
    return normalized

def extract_complexity_from_response(response: str) -> Optional[str]:
    """
    Extract complexity notation from LLM response.
    
    Args:
        response (str): The LLM response
        
    Returns:
        Optional[str]: Extracted complexity or None
    """
    if not response:
        return None
    
    # Handle nested parentheses by finding balanced expressions
    import re
    
    # Find starting positions of complexity notations
    starts = []
    for match in re.finditer(r'[OoΘθΩω]\(', response, re.IGNORECASE):
        starts.append(match.start())
    
    for start in starts:
        # Find the matching closing parenthesis
        paren_count = 0
        for i, char in enumerate(response[start:]):
            if char == '(':
                paren_count += 1
            elif char == ')':
                paren_count -= 1
                if paren_count == 0:
                    # Found the matching closing parenthesis
                    complexity = response[start:start + i + 1]
                    return complexity
    
    return None


def judge_with_llm(response: str, ground_truth: str) -> bool:
    """
    Use LLM to judge if response correctly answers the complexity question.
    
    Args:
        response (str): The response to evaluate
        ground_truth (str): The expected complexity answer
        
    Returns:
        bool: True if correct, False otherwise
    """
    if not response.strip() or not ground_truth.strip():
        return False
    
    try:
        prompt = LLM_JUDGMENT_PROMPT.format(
            response=response,
            ground_truth=ground_truth
        )
        llm_response = get_llm_response(prompt, temperature=0.0)
        
        if llm_response:
            answer = llm_response.strip().upper()
            return answer == "YES"
    except Exception as e:
        # If LLM fails, return False
        pass
    
    return False


def extract_and_compare_hybrid(response: str, ground_truth: str) -> tuple[Optional[str], bool, str]:
    """
    Hybrid approach: rule-based first, then model-based judgment.
    
    Args:
        response (str): The response to extract complexity from
        ground_truth (str): The ground truth complexity
        
    Returns:
        tuple: (extracted_complexity, is_correct, method_used)
    """
    # Step 1: Try rule-based extraction
    extracted_complexity = extract_complexity_from_response(response)
    
    if extracted_complexity:
        # Step 2: Try rule-based comparison
        is_correct = compare_complexities(extracted_complexity, ground_truth)
        
        if is_correct:
            return extracted_complexity, True, "rule_based"
        else:
            # Rule-based comparison failed, try LLM judgment
            is_correct_llm = judge_with_llm(response, ground_truth)
            method = "hybrid_rule_extract_llm_judge"
            return extracted_complexity, is_correct_llm, method
    
    # Step 3: Rule-based extraction failed, use LLM judgment directly
    is_correct_llm = judge_with_llm(response, ground_truth)
    
    if is_correct_llm:
        return "LLM_DETERMINED", True, "llm_judgment"
    else:
        return None, False, "extraction_failed"

def compare_complexities(predicted: str, ground_truth: str) -> bool:
    """
    Compare two complexity notations for equivalence.
    
    Args:
        predicted (str): Predicted complexity
        ground_truth (str): Ground truth complexity
        
    Returns:
        bool: True if they match, False otherwise
    """
    if not predicted or not ground_truth:
        return False
    
    norm_predicted = normalize_complexity(predicted)
    norm_ground_truth = normalize_complexity(ground_truth)
    
    return norm_predicted == norm_ground_truth

@register_reward_score("algo_complexity_pred")
def compute_score(solution_str: str, ground_truth: str, extra_info: Any) -> Dict[str, Any]:
    """
    Compute reward score for algorithm complexity prediction.
    
    Args:
        solution_str (str): The model's response to the complexity query
        ground_truth (str): The expected complexity answer (e.g., "O(n)", "O(log n)")
        extra_info (Any): Additional information
        
    Returns:
        Dict[str, Any]: Score and additional information
        
    Logic:
    - Extract complexity from solution_str
    - Compare directly with ground_truth
    - Score = 1.0 if match, 0.0 otherwise
    - Focus on extractability of model output
    """
    
    # Handle numpy scalar for extra_info
    if isinstance(extra_info, np.ndarray):
        try:
            extra_info = extra_info.item()
        except Exception:
            extra_info = None
    
    # Check if solution exists
    has_solution = bool(solution_str.strip())
    if not has_solution:
        return {"score": 0.0, "extra_info": {"score": 0.0, "valid_response": 0, "extracted_complexity": None}}
    
    # Ground truth is now directly the complexity string
    gt_complexity = ground_truth.strip()
    if not gt_complexity:
        return {"score": 0.0, "extra_info": {"score": 0.0, "valid_response": 1, "error": "Empty ground truth"}}
    
    # Use hybrid extraction and comparison approach
    extracted_complexity, is_correct, method_used = extract_and_compare_hybrid(solution_str, gt_complexity)
    
    score = 1.0 if is_correct else 0.0
    
    # Determine if response is well-formatted (easy to extract)
    has_clear_notation = bool(re.search(r'[OoΘθΩω]\([^)]+\)', solution_str, re.IGNORECASE))
    
    extra_info_result = {
        "score": score,
        "valid_response": 1,
        "extracted_complexity": extracted_complexity,
        "ground_truth_complexity": gt_complexity,
        "is_correct": is_correct,
        "method_used": method_used,
        "has_clear_notation": has_clear_notation,
        "response_length": len(solution_str),
        "response": solution_str[:MAX_CHAR_DISPLAY] if len(solution_str) > MAX_CHAR_DISPLAY else solution_str
    }
    
    return {"score": score, "extra_info": extra_info_result}


