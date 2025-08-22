import asyncio
import json
import os

import numpy as np

if os.getenv("SANDBOX_ENDPOINT", None) is not None:
    from aiic_verl.utils.sandbox.local_sandbox import parallel_sandbox
else:
    from aiic_verl.utils.sandbox.internal_sandbox import parallel_sandbox

MAX_CHAR_DISPLAY = 2048


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

    ground_truth = json.loads(ground_truth)
    code_to_execute = solution_str + "\n" + ground_truth["functional"]
    sandbox_success, sandbox_stdout, sandbox_stderr = asyncio.run(
        parallel_sandbox([code_to_execute], num_processes=256)
    )
    success = sandbox_success[0]
    stdout = str(sandbox_stdout[0])
    stderr = str(sandbox_stderr[0])

    if not success or len(stderr) > 0:
        return {
            "score": 0.0,
            "extra_info": {
                "score": 0.0,
                "valid_code": 1 if has_code_piece else 0,
            },
        }

    return {
        "score": 1.0,
        "extra_info": {
            "score": 1.0,
            "valid_code": 1 if has_code_piece else 0,
        },
    }
