"""
{
    "task_id": "xxx",
    "data_source": "xxx",
    "prompt": [{'content': 'You will use the following starter code to write the solution to the problem and enclose your code within delimiters.\npython\nclass Solution:\n    def shortestDistanceAfterQueries(self, n: int, queries: List[List[int]]) -> List[int]:\n        \n', 'role': 'user'}],
    "reward_model": [
        "def check(candidate):\n    assert candidate(n = 7,queries = [[0, 5], [1, 6], [2, 4]]) == [2, 2, 2]\n\ncheck(Solution().shortestDistanceAfterQueries)",
        "def check(candidate):\n    assert candidate(n = 7,queries = [[0, 5], [1, 6], [2, 4]]) == [2, 2, 2]\n\ncheck(Solution().shortestDistanceAfterQueries)",
    ]
}
"""
# python -m unittest tests.test_algo_complexity_pred -v
import json
import unittest
from unittest.mock import patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from reward_score.algo_complexity_pred import compute_score


GT = {
    "task_id": "xxx",
    "data_source": "xxx",
    "prompt": [{"content": "dummy prompt", "role": "user"}],
    "reward_model": [
        "def check(candidate):\n"
        "    assert candidate(n=7, queries=[[0,5],[1,6],[2,4]]) == [2,2,2]\n\n"
        "check(Solution().shortestDistanceAfterQueries)"
    ],
}
GT_STR = json.dumps(GT)


CORRECT_SOLUTION = """
from typing import List

class Solution:
    def shortestDistanceAfterQueries(self, n: int, queries: List[List[int]]) -> List[int]:
        return [2,2,2]
"""

WRONG_SOLUTION = """
from typing import List)

class Solution:
    def shortestDistanceAfterQueries(self, n: int, queries: List[List[int]]) -> List[int]:
        return [1,1,1]
"""


def make_fake_parallel_sandbox(success, stdout, stderr, capture=None):
    """
    Build an async stub for parallel_sandbox so asyncio.run can await it.
    Optionally capture the submitted code for assertions.
    """
    async def _fake(code_list, num_processes=256):
        if capture is not None and code_list:
            capture.append(code_list[0])
        return ([success], [stdout], [stderr])
    return _fake


class TestAlgoComplexityPred(unittest.TestCase):
    def test_empty_solution(self):
        out = compute_score("", GT_STR, {})
        self.assertEqual(out, {"score": 0.0, "extra_info": {"score": 0.0, "valid_code": 0}})

    def test_correct_solution(self):
        with patch(
            "reward_score.algo_complexity_pred.parallel_sandbox",
            new=make_fake_parallel_sandbox(True, "", "")
        ):
            out = compute_score(CORRECT_SOLUTION, GT_STR, {})
            self.assertEqual(out["score"], 1.0)

    def test_wrong_solution(self):
        with patch(
            "reward_score.algo_complexity_pred.parallel_sandbox",
            new=make_fake_parallel_sandbox(False, "", "AssertionError")
        ):
            out = compute_score(WRONG_SOLUTION, GT_STR, {})
            self.assertEqual(out["score"], 0.0)

    def test_stderr_means_zero(self):
        with patch(
            "reward_score.algo_complexity_pred.parallel_sandbox",
            new=make_fake_parallel_sandbox(True, "", "warning")
        ):
            out = compute_score(CORRECT_SOLUTION, GT_STR, {})
            self.assertEqual(out["score"], 0.0)

    def test_code_concatenation_contains_reward_blocks(self):
        captured = []
        with patch(
            "reward_score.algo_complexity_pred.parallel_sandbox",
            new=make_fake_parallel_sandbox(True, "", "", capture=captured)
        ):
            _ = compute_score(CORRECT_SOLUTION, GT_STR, {})
        self.assertTrue(captured and "class Solution" in captured[0])
        self.assertIn("check(Solution().shortestDistanceAfterQueries)", captured[0])


if __name__ == "__main__":
    unittest.main()
