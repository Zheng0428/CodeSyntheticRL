"""
Self-contained tests for compute_score for README generation.

Covers:
- Rule-based similarity scoring (high/low threshold)
- Fallback to LLM judgment
- Edge cases (empty solution, empty ground truth)
"""

import unittest
import textwrap

from reward_score.readme_gen_pred import compute_score

class TestReadmeGenScore(unittest.TestCase):

    def test_rule_based_high_similarity(self):
        """High similarity should trigger rule-based True (score=1.0)."""
        # Very similar strings
        solution = "This project explains how to install and run the code."
        ground_truth = "This project explains how to install and run the code!"
        result = compute_score(solution, ground_truth, extra_info=0)
        self.assertEqual(result["score"], 1.0)
        self.assertEqual(result["extra_info"]["method"], "rule_based")

    def test_rule_based_low_similarity(self):
        """Low similarity should trigger rule-based False (score=0.0)."""
        solution = "Completely unrelated text"
        ground_truth = "This README describes how to install the package"
        result = compute_score(solution, ground_truth, extra_info=0)
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["extra_info"]["method"], "rule_based")

    def test_empty_solution(self):
        """Empty solution should return score=0.0."""
        solution = ""
        ground_truth = "Some README content"
        result = compute_score(solution, ground_truth, extra_info=0)
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["extra_info"]["method"], "rule_based")

    def test_empty_ground_truth(self):
        """Empty ground truth should return score=0.0."""
        solution = "Some content"
        ground_truth = ""
        result = compute_score(solution, ground_truth, extra_info=0)
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["extra_info"]["method"], "rule_based")

    def test_fallback_llm_judgment(self):
        """
        Similarity in between thresholds should call llm_judgment.
        We monkeypatch llm_judgment to return True for test.
        """
        import reward_score.readme_gen_pred as rg
        original_llm = rg.llm_judgment
        rg.llm_judgment = lambda s, g: True  # Always YES

        solution = "This README covers installation and usage instructions."
        ground_truth = "Installation and usage of this tool are explained here."
        result = rg.compute_score(solution, ground_truth, extra_info=0)
        self.assertEqual(result["score"], 1.0)
        self.assertEqual(result["extra_info"]["method"], "llm_judgment")

        rg.llm_judgment = original_llm  # restore

    def test_fallback_llm_judgment_false(self):
        """
        Similarity in between thresholds should call llm_judgment.
        We monkeypatch llm_judgment to return False for test.
        """
        import reward_score.readme_gen_pred as rg
        original_llm = rg.llm_judgment
        rg.llm_judgment = lambda s, g: False  # Always NO

        solution = "Partial overlap with ground truth content"
        ground_truth = "Ground truth content partially overlaps"
        result = rg.compute_score(solution, ground_truth, extra_info=0)
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["extra_info"]["method"], "llm_judgment")

        rg.llm_judgment = original_llm  # restore

if __name__ == "__main__":
    unittest.main()
