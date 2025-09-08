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


def test_algo_complexity_pred():
    """
    Test function for the algo_complexity_pred reward scorer.
    """
    print("Testing algo_complexity_pred reward scorer...")
    print("=" * 60)
    
    # Test cases: (solution_str, ground_truth, expected_score, description)
    test_cases = [
        # Perfect matches
        ("O(n)", "O(n)", 1.0, "Perfect match - simple"),
        ("The time complexity is O(log n)", "O(log n)", 1.0, "Perfect match - with text"),
        ("Answer: O(n^2)", "O(n^2)", 1.0, "Perfect match - quadratic"),
        
        # Normalized matches
        ("O(n*log(n))", "O(n log n)", 1.0, "Normalized match - spacing"),
        ("O(N)", "O(n)", 1.0, "Normalized match - case"),
        ("o(1)", "O(1)", 1.0, "Normalized match - lowercase"),
        
        # Correct answers with explanations
        ("The algorithm has O(n) time complexity because it iterates through the array once.", "O(n)", 1.0, "Correct with explanation"),
        ("Time complexity: O(log n) due to binary search", "O(log n)", 1.0, "Correct with reasoning"),
        
        # Incorrect answers
        ("O(n)", "O(log n)", 0.0, "Wrong complexity"),
        ("O(n^2)", "O(n)", 0.0, "Wrong complexity - higher order"),
        
        # No clear notation
        ("The algorithm is very fast", "O(1)", 0.0, "No complexity notation"),
        ("Linear time complexity", "O(n)", 1.0, "Description that LLM can understand"),
        
        # Empty/invalid responses
        ("", "O(n)", 0.0, "Empty response"),
        ("   ", "O(n)", 0.0, "Whitespace only"),
        
        # Multiple complexities (should extract first/main one)
        ("Time: O(n), Space: O(1)", "O(n)", 1.0, "Multiple complexities - correct first"),
        ("Space: O(n), Time: O(log n)", "O(log n)", 0.0, "Multiple complexities - wrong order"),
        
        # Edge cases
        ("The complexity is O(2^n) exponential", "O(2^n)", 1.0, "Exponential complexity"),
        ("O(n!) factorial time", "O(n!)", 1.0, "Factorial complexity"),
        ("Θ(n log n)", "O(n log n)", 1.0, "Theta notation"),
        
        # Common variations
        ("O(n²)", "O(n^2)", 1.0, "Unicode superscript"),
        ("O(n**2)", "O(n^2)", 1.0, "Python exponentiation"),
        ("O(logn)", "O(log n)", 1.0, "No space in log"),
        
        # Cases that test LLM assistance (natural language understanding)
        ("The time complexity is quadratic", "O(n^2)", 1.0, "Natural language - LLM should understand quadratic"),
        ("This runs in linear time", "O(n)", 1.0, "Natural language - LLM should understand linear"),
        ("Constant time operation", "O(1)", 1.0, "Natural language - LLM should understand constant"),
        ("The algorithm's complexity is O(n) where n is the input size", "O(n)", 1.0, "Clear notation with explanation"),
    ]
    
    total_tests = len(test_cases)
    passed_tests = 0
    
    for i, (solution_str, ground_truth, expected_score, description) in enumerate(test_cases, 1):
        try:
            result = compute_score(solution_str, ground_truth, None)
            actual_score = result["score"]
            extra_info = result["extra_info"]
            
            # Check if score matches expected
            score_correct = abs(actual_score - expected_score) < 1e-6
            
            if score_correct:
                status = "✓ PASS"
                passed_tests += 1
            else:
                status = "✗ FAIL"
            
            print(f"Test {i:2d}: {status}")
            print(f"  Description: {description}")
            print(f"  Input: '{solution_str}'")
            print(f"  Ground Truth: '{ground_truth}'")
            print(f"  Expected Score: {expected_score}")
            print(f"  Actual Score: {actual_score}")
            print(f"  Extracted: '{extra_info.get('extracted_complexity', 'None')}'")
            print(f"  Method Used: {extra_info.get('method_used', 'Unknown')}")
            print(f"  Has Clear Notation: {extra_info.get('has_clear_notation', False)}")
            
            if not score_correct:
                print(f"  ❌ Expected {expected_score}, got {actual_score}")
            
            print()
            
        except Exception as e:
            print(f"Test {i:2d}: ✗ ERROR")
            print(f"  Description: {description}")
            print(f"  Error: {e}")
            print()
    
    print("=" * 60)
    print(f"Test Results: {passed_tests}/{total_tests} passed ({passed_tests/total_tests*100:.1f}%)")
    
    if passed_tests == total_tests:
        print("🎉 All tests passed!")
    else:
        print(f"⚠️  {total_tests - passed_tests} tests failed")
    
    return passed_tests == total_tests


if __name__ == "__main__":
    # Run tests when script is executed directly
    test_algo_complexity_pred()