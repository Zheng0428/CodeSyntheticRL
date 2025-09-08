"""
A testcase should have `import_code` and `test_code`.
See test_ground_truth_full_spec() in tests/test_code_reward.py for example testcase.
"""
import ast
import asyncio
import os
import numpy as np

if os.getenv("SANDBOX_ENDPOINT", None) is not None:
    from sandbox.local_sandbox import parallel_sandbox
else:
    from sandbox.internal_sandbox import parallel_sandbox
from utils import register_reward_score
MAX_CHAR_DISPLAY = 2048


def strip_main_guard(src: str) -> str:
    """
    Remove top-level `if __name__ == "__main__": ...` blocks from `src` via AST,
    while preserving the `else:` branch (since under not-main it would run).
    We match both `__name__ == "__main__"` and `"__main__" == __name__`.
    Returns the transformed source code as a string.
    """

    def _is_main_guard(test: ast.AST) -> bool:
        # Match: (__name__ == "__main__") OR ("__main__" == __name__)
        if not isinstance(test, ast.Compare) or len(test.ops) != 1 or len(test.comparators) != 1:
            return False
        if not isinstance(test.ops[0], ast.Eq):
            return False
        left, right = test.left, test.comparators[0]
        def _is_name(n): return isinstance(n, ast.Name) and n.id == "__name__"
        def _is_main(n): return isinstance(n, ast.Constant) and n.value == "__main__"
        return (_is_name(left) and _is_main(right)) or (_is_main(left) and _is_name(right))

    class Strip(ast.NodeTransformer):
        """Delete main-guard `if` blocks, keep their `else` suite."""
        def _flatten(self, stmts):
            out = []
            for s in stmts:
                res = self.visit(s)
                if res is None:
                    continue
                if isinstance(res, list):
                    out.extend(res)
                else:
                    out.append(res)
            return out

        def visit_If(self, node: ast.If):
            # First, transform children
            node = self.generic_visit(node)
            # If this `if` is the main guard, drop its body and keep `else`
            if _is_main_guard(node.test):
                return self._flatten(node.orelse)
            return node

    tree = ast.parse(src)
    tree = Strip().visit(tree)
    ast.fix_missing_locations(tree)

    try:
        return ast.unparse(tree)
    except Exception:
        import astor
        return astor.to_source(tree)


def instrument_asserts_and_count(src: str):
    """
    Instrument every `assert` with `__ASSERTS_RAN__ += 1` and *statically* compute
    how many times all asserts will execute, accounting for `for`-loops (including
    nesting). We only count loops whose iteration count can be determined at parse time.

    Supported iterables (statically countable):
      - range(k) / range(a, b[, step])   with integer literal args (including unary +/-)
      - literal containers: list/tuple/set/dict (length = number of elements/keys)
      - enumerate(<any of the above>)    (length = length of the underlying iterable)

    Unsupported (raise ValueError):
      - loops whose iteration count cannot be statically determined (e.g., names,
        attribute calls, comprehensions, function calls with unknown return lengths)
      - while-loops (by design)

    Returns:
      (instrumented_source: str, total_expected_asserts: int)
    """
    tree = ast.parse(src)

    # ---------- Helpers to evaluate constant integers and range lengths ----------

    def _const_int(node):
        """Return an int if `node` is an integer literal (supports unary +/-), else None."""
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return node.value
        if (
            isinstance(node, ast.UnaryOp)
            and isinstance(node.op, (ast.UAdd, ast.USub))
            and isinstance(node.operand, ast.Constant)
            and isinstance(node.operand.value, int)
        ):
            return +node.operand.value if isinstance(node.op, ast.UAdd) else -node.operand.value
        return None

    def _range_len(args):
        """
        Compute the length of range(...) given AST args already verified to be constant ints.
        Returns an int, or None if invalid (e.g., step == 0 or malformed).
        """
        if len(args) == 1:
            start, stop, step = 0, _const_int(args[0]), 1
        elif len(args) == 2:
            start, stop, step = _const_int(args[0]), _const_int(args[1]), 1
        elif len(args) == 3:
            start, stop, step = _const_int(args[0]), _const_int(args[1]), _const_int(args[2])
        else:
            return None

        if None in (start, stop, step) or step == 0:
            return None

        if step > 0:
            n = (stop - start + step - 1) // step
        else:
            # For negative steps, mirror the positive-step ceiling division logic.
            n = (start - stop - step - 1) // (-step)

        return max(0, n)

    def _static_iter_len(node):
        """
        Return the static iteration count for a `for` iterable expression, or None if unknown.

        Supports:
          - range(...)
          - enumerate(<supported iterable>)
          - literal list/tuple/set/dict
        """
        # range(...)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "range":
            # All args must be constant ints (allow unary +/-)
            ints_ok = True
            for a in node.args:
                if _const_int(a) is None:
                    ints_ok = False
                    break
            return _range_len(node.args) if ints_ok else None

        # enumerate(x)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "enumerate":
            if len(node.args) >= 1:
                return _static_iter_len(node.args[0])
            return None

        # Literal containers
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return len(node.elts)
        if isinstance(node, ast.Dict):
            return len(node.keys)

        # Unknown / dynamic
        return None

    # ---------- Node transformer with a loop-multiplier stack ----------

    class LoopAwareRewriter(ast.NodeTransformer):
        """
        Inserts `__ASSERTS_RAN__ += 1` immediately before each `assert` statement
        and counts *dynamic* executions by maintaining a multiplier for enclosing loops.
        """

        def __init__(self):
            super().__init__()
            self.count = 0
            self.multiplier_stack = [1]  # product of statically-known loop lengths

        def _flatten_block(self, stmts):
            """Visit a list of statements and flatten results (since visits may return lists)."""
            out = []
            for s in stmts:
                res = self.visit(s)
                if res is None:
                    continue
                if isinstance(res, list):
                    out.extend(res)
                else:
                    out.append(res)
            return out

        def visit_Assert(self, node: ast.Assert):
            self.count += self.multiplier_stack[-1]
            # call a helper instead of doing `+= 1` directly
            inc = ast.parse("__INC_ASSERTS__()").body[0]
            return [inc, node]

        def visit_For(self, node: ast.For):
            # Visit target and iter normally (they're expressions; will not produce statement lists).
            node.target = self.visit(node.target) or node.target
            node.iter = self.visit(node.iter) or node.iter

            # Determine static iteration count.
            iter_len = _static_iter_len(node.iter)
            if iter_len is None:
                raise ValueError("Cannot statically determine iteration count for this 'for' loop.")

            # Enter loop body with multiplied count.
            self.multiplier_stack.append(self.multiplier_stack[-1] * iter_len)
            node.body = self._flatten_block(node.body)
            self.multiplier_stack.pop()

            # `for ... else:` executes the else-block exactly once if the loop wasn't broken.
            # We conservatively count it once (no multiplier), as static break analysis is out of scope.
            node.orelse = self._flatten_block(node.orelse)
            return node

        # If you want to be explicit about unsupported async-for:
        def visit_AsyncFor(self, node: ast.AsyncFor):
            raise ValueError("Async for-loops are not supported for static assert counting.")

        # Fallback to default behavior for all other nodes.
        def generic_visit(self, node):
            return super().generic_visit(node)

    # Transform and unparse
    rw = LoopAwareRewriter()
    new_tree = rw.visit(tree)
    ast.fix_missing_locations(new_tree)

    try:
        new_src = ast.unparse(new_tree)  # Python 3.9+
    except Exception:
        import astor

        new_src = astor.to_source(new_tree)

    return new_src, rw.count


def build_hardened_code(
    solution_str: str,
    import_code: str,
    test_code: str,
):
    """
    Build a single Python program that:
      1) blocks premature exits (sys.exit, os._exit, quit/exit, self-kill)
      2) runs instrumented tests and prints a signed success token only if ALL asserts ran and passed
    """
    # Preprocess the user solution OUTSIDE the generated program
    solution_no_main = strip_main_guard(solution_str)

    # Instrument ONLY the test side (test_code + entry_point)
    tests_instr, expected = instrument_asserts_and_count(test_code)

    SAFE_PREFIX = f"""
import builtins, sys, os

def _blocked(*a, **k):
    raise RuntimeError("blocked: premature exit is not allowed")

# Block various exit paths
builtins.exit = _blocked
builtins.quit = _blocked
sys.exit = _blocked
try:
    import posix
    posix._exit = _blocked
except Exception:
    pass
os._exit = _blocked

# Block self-kill
if hasattr(os, "kill"):
    _orig_kill = os.kill
    def _no_kill(pid, sig):
        if pid == os.getpid():
            raise RuntimeError("blocked: kill self")
        return _orig_kill(pid, sig)
    os.kill = _no_kill
"""

    RUN_USER = f"{import_code}\n\n{solution_no_main}"

    RUN_TESTS = f"""
# ==== RUN INSTRUMENTED TESTS ====
__ASSERTS_RAN__ = 0

def __INC_ASSERTS__():
    # Called before each assert in the instrumented tests
    global __ASSERTS_RAN__
    __ASSERTS_RAN__ += 1

# ---- tests begin ----
{tests_instr}
# ---- tests end ----

# Expect exact number of asserts executed
if __ASSERTS_RAN__ != {expected}:
    raise AssertionError(f"only ran {{__ASSERTS_RAN__}}/{expected} asserts")
"""

    return SAFE_PREFIX + RUN_USER + RUN_TESTS


@register_reward_score("sandbox")
def compute_score(solution_str, ground_truth, extra_info):
    if isinstance(extra_info, np.ndarray):
        extra_info = extra_info.item()

    has_code_piece = len(solution_str) != 0
    if not has_code_piece:
        return {
            "score": 0.0,
            "extra_info": {
                "score": 0.0,
                "valid_code": 1 if has_code_piece else 0,
            },
        }

    if isinstance(ground_truth, dict):  # LeetCode
        code_to_execute = build_hardened_code(
            solution_str=solution_str,
            import_code=ground_truth["import_code"],
            test_code=ground_truth["test_code"],
        )
        sandbox_success, sandbox_stdout, sandbox_stderr = asyncio.run(
            parallel_sandbox([code_to_execute], num_processes=256)
        )
        success = sandbox_success[0]
        stdout = "" if sandbox_stdout[0] is None else str(sandbox_stdout[0])
        stderr = "" if sandbox_stderr[0] is None else str(sandbox_stderr[0])

        if success and len(stderr) == 0:
            return {"score": 1.0, "extra_info": {"score": 1.0, "valid_code": 1 if has_code_piece else 0}}
        else:
            return {"score": 0.0, "extra_info": {"score": 0.0, "valid_code": 1 if has_code_piece else 0}}
    else:
        raise ValueError(f"Ground truth should be a dict, but got {type(ground_truth)}")
