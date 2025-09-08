"""
Tests for algo_complexity_pred reward scorer.

Run with: python tests/test_algo_complexity_pred.py
Or: python -m unittest tests.test_algo_complexity_pred -v
"""
import sys
import os

# Add the project root to the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the scorer function
from reward_score.algo_complexity_pred import compute_score


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