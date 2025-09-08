"""
Self-contained tests for compute_score using a hardened evaluator.

What this file contains:
- Unit tests covering many edge cases to ensure robustness

Run:
    python -m unittest -v aiic_verl/tests/test_code_reward.py
"""

import textwrap
import unittest

from reward_score.sandbox import compute_score


# ----------------------------
# Helpers to build ground_truth
# ----------------------------

def wrap_gt_asserts(assert_src: str) -> str:
    """
    Assert-only tests: put asserts directly into test_code.
    """
    return {
        "import_code": "",
        "test_code": assert_src,
    }


def wrap_gt_check(check_body_src: str, entry_point_expr: str) -> str:
    """
    check/candidate-style tests: define check(...) in test_code and
    append an explicit call check(<entry_point_expr>) at the end.
    """
    test_code = f"{check_body_src.rstrip()}\ncheck({entry_point_expr})\n"
    return {
        "import_code": "",
        "test_code": test_code,
    }


class TestComputeScore(unittest.TestCase):

    def test_success_simple(self):
        """All asserts pass; should return score=1.0"""
        solution = textwrap.dedent(
            """
            def add(a, b):
                return a + b
            """
        )
        tests = textwrap.dedent(
            """
            assert add(1, 2) == 3
            assert add(-1, 1) == 0
            assert add(0, 0) == 0
            # Ensure we really executed all asserts
            for i in range(5):
                assert add(i, i) == 2*i
            """
        )
        gt = wrap_gt_asserts(tests)
        result = compute_score(solution, gt, extra_info=0)
        self.assertEqual(result["score"], 1.0)

    def test_fail_assert(self):
        """An assert fails; should return score=0.0"""
        solution = "def add(a,b): return a+b"
        tests = "assert add(1,1) == 3"
        gt = wrap_gt_asserts(tests)
        result = compute_score(solution, gt, extra_info=0)
        self.assertEqual(result["score"], 0.0)

    def test_empty_solution(self):
        """Empty solution string; should return score=0.0 and valid_code=0"""
        solution = ""
        tests = "assert True"
        gt = wrap_gt_asserts(tests)
        result = compute_score(solution, gt, extra_info=0)
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["extra_info"]["valid_code"], 0)

    def test_premature_sys_exit(self):
        """User calls sys.exit(); hardened prefix should block -> failure"""
        solution = textwrap.dedent(
            """
            import sys
            def foo(): return 42
            sys.exit(0)
            """
        )
        tests = "assert foo() == 42"
        gt = wrap_gt_asserts(tests)
        result = compute_score(solution, gt, extra_info=0)
        self.assertEqual(result["score"], 0.0)

    def test_raise_system_exit(self):
        """User raises exit(); should surface as failure (stderr non-empty or blocked call)"""
        solution = textwrap.dedent(
            """
            import sys
            def foo(): return 1
            sys.exit(0)
            """
        )
        tests = "assert foo() == 1"
        gt = wrap_gt_asserts(tests)
        result = compute_score(solution, gt, extra_info=0)
        self.assertEqual(result["score"], 0.0)

    def test_fake_token_does_not_pass(self):
        """User prints a fake token; evaluator must not accept it."""
        solution = textwrap.dedent(
            """
            def ok(): return True
            print("__EVAL_OK__:deadbeef:9999")
            """
        )
        tests_ok = "assert ok()"
        gt_ok = wrap_gt_asserts(tests_ok)
        result_ok = compute_score(solution, gt_ok, extra_info=0)
        # Now make the asserts fail to ensure fake token does nothing:
        tests_fail = "assert not ok()"
        gt_fail = wrap_gt_asserts(tests_fail)
        result_fail = compute_score(solution, gt_fail, extra_info=0)
        self.assertEqual(result_fail["score"], 0.0)

    def test_all_asserts_must_run(self):
        """Multiple asserts; evaluator must ensure all of them ran (count matches)."""
        solution = "def inc(x): return x+1"
        tests = textwrap.dedent(
            """
            # 5 asserts total
            assert inc(0) == 1
            assert inc(1) == 2
            assert inc(2) == 3
            assert inc(-1) == 0
            assert inc(10) == 11
            """
        )
        gt = wrap_gt_asserts(tests)
        result = compute_score(solution, gt, extra_info=0)
        self.assertEqual(result["score"], 1.0)
        # Now make one assert wrong -> should fail and not print success token
        tests_bad = tests + "\nassert inc(100) == 999\n"
        gt_bad = wrap_gt_asserts(tests_bad)
        result_bad = compute_score(solution, gt_bad, extra_info=0)
        self.assertEqual(result_bad["score"], 0.0)

    def test_solution_with_main_guard(self):
        """Solution includes a __main__ block; the evaluator must not execute it."""
        solution = textwrap.dedent(
            """
            def mul(a, b):
                return a * b

            if __name__ == "__main__":
                assert False
            """
        )
        tests = "assert mul(3, 4) == 12"
        gt = wrap_gt_asserts(tests)
        result = compute_score(solution, gt, extra_info=0)
        self.assertEqual(result["score"], 1.0)

    def test_user_ground_truth_style_check(self):
        """Integrate solution_str with functional tests using explicit check(...) call; should return score=1.0."""
        solution = textwrap.dedent(
            """
            from typing import List

            class Solution:
                def countSubarrays(self, nums: List[int]) -> int:
                    count = 0
                    n = len(nums)
                    for i in range(n - 2):
                        a = nums[i]
                        b = nums[i + 1]
                        c = nums[i + 2]
                        if 2 * (a + c) == b:
                            count += 1
                    return count
            """
        )

        check_body = textwrap.dedent(
            """
            def check(candidate):
                assert candidate(nums = [5, 10, 5, 15, 5]) == 0
                assert candidate(nums = [1, 1, 1]) == 0
                assert candidate(nums = [1, -1, 1, -1, 1]) == 0
            """
        )
        gt = wrap_gt_check(check_body, "Solution().countSubarrays")
        result = compute_score(solution, gt, extra_info=0)
        self.assertEqual(result["score"], 1.0)

    def test_ground_truth_full_spec(self):
        """
        Use the provided ground_truth sample as a test case.
        """
        solution = textwrap.dedent(
            """
            # A stub solution tailored to the concrete queries in the sample ground_truth.
            class Solution:
                def shortestDistanceAfterQueries(self, n, queries):
                    if n == 7 and queries == [[0, 5], [1, 6], [2, 4]]:
                        return [2, 2, 2]
                    if n == 8 and queries == [[1, 5], [2, 6], [3, 7], [0, 4], [0, 6], [0, 7]]:
                        return [4, 4, 4, 4, 2, 1]
                    if n == 6 and queries == [[1, 3], [2, 5], [0, 3]]:
                        return [4, 3, 3]
                    raise NotImplementedError("stub solution for evaluator tests")
            """
        )

        import_code = textwrap.dedent(
            """
            import random
            import functools
            import collections
            import string
            import math
            import datetime

            from typing import *
            from functools import *
            from collections import *
            from itertools import *
            from heapq import *
            from bisect import *
            from string import *
            from operator import *
            from math import *

            inf = float('inf')

            class ListNode:
                def __init__(self, val=0, next=None):
                    self.val = val
                    self.next = next

            def list_node(values: list):
                if not values:
                    return None
                head = ListNode(values[0])
                p = head
                for val in values[1:]:
                    node = ListNode(val)
                    p.next = node
                    p = node
                return head

            def is_same_list(p1, p2):
                if p1 is None and p2 is None:
                    return True
                if not p1 or not p2:
                    return False
                return p1.val == p2.val and is_same_list(p1.next, p2.next)

            class TreeNode:
                def __init__(self, val=0, left=None, right=None):
                    self.val = val
                    self.left = left
                    self.right = right

            def tree_node(values: list):
                if not values:
                    return None
                root = TreeNode(values[0])
                i = 1
                queue = deque()
                queue.append(root)
                while queue:
                    node = queue.popleft()
                    if i < len(values) and values[i] is not None:
                        node.left = TreeNode(values[i])
                        queue.append(node.left)
                    i += 1
                    if i < len(values) and values[i] is not None:
                        node.right = TreeNode(values[i])
                        queue.append(node.right)
                    i += 1
                return root

            def is_same_tree(p, q):
                if not p and not q:
                    return True
                elif not p or not q:
                    return False
                elif p.val != q.val:
                    return False
                else:
                    return is_same_tree(p.left, q.left) and is_same_tree(p.right, q.right)
            """
        )

        test_code = textwrap.dedent(
            """
            def check(candidate):
                assert candidate(n = 7,queries = [[0, 5], [1, 6], [2, 4]]) == [2, 2, 2]
                assert candidate(n = 8,queries = [[1, 5], [2, 6], [3, 7], [0, 4], [0, 6], [0, 7]]) == [4, 4, 4, 4, 2, 1]
                assert candidate(n = 6,queries = [[1, 3], [2, 5], [0, 3]]) == [4, 3, 3]
            
            check(Solution().shortestDistanceAfterQueries)
            """
        )

        ground_truth = {
            "import_code": import_code,
            "test_code": test_code,
        }

        result = compute_score(solution, ground_truth, extra_info=0)
        self.assertEqual(result["score"], 1.0)


if __name__ == "__main__":
    unittest.main()
