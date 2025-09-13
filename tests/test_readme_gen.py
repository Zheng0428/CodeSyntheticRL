import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from reward_score.readme_gen_pred import compute_score  # 根据实际路径导入

def test_readme_gen():
    """测试 readme_gen 任务评分逻辑"""
    
    test_cases = [
        # (solution_str, ground_truth, expected_similarity, description)
        ("This project explains how to install and run the code.", 
         "This project explains how to install and run the code!", 
         1.0, "High similarity, should score 1.0"),
        
        ("Completely unrelated text", 
         "This README describes how to install the package", 
         0.0, "Low similarity, should score 0.0"),
        
        ("", 
         "Some README content", 
         0.0, "Empty solution, should score 0.0"),
        
        ("Some content", 
         "", 
         0.0, "Empty ground truth, should score 0.0")
        
    ]
    
    total_tests = len(test_cases)
    passed_tests = 0
    
    for i, (solution_str, ground_truth, expected_similarity, description) in enumerate(test_cases, 1):
        result = compute_score(solution_str, ground_truth, None)
        actual_score = result["score"]
        
        # Check if the actual score matches the expected score within a small epsilon
        if abs(actual_score - expected_similarity) < 1e-6:
            print(f"Test {i}: ✓ PASS - {description}")
            passed_tests += 1
        else:
            print(f"Test {i}: ✗ FAIL - {description}")
            print(f"  Expected: {expected_similarity}, Got: {actual_score}")
    
    print(f"Results: {passed_tests}/{total_tests} passed")
    return passed_tests == total_tests

if __name__ == "__main__":
    test_readme_gen()
