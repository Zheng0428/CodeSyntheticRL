import asyncio
import json
import os
import numpy as np

if os.getenv("SANDBOX_ENDPOINT", None) is not None:
    from sandbox.local_sandbox import parallel_sandbox
else:
    from sandbox.internal_sandbox import parallel_sandbox

MAX_CHAR_DISPLAY = 2048


def compute_score(solution_str, ground_truth, extra_info):
    """
    ground_truth format:
    {
        "task_id": "...",
        "data_source": "...",
        "prompt": [...],
        "reward_model": [
            "def check(candidate): ...\ncheck(Solution().method)",
            ...
        ]
    }

    Logic:
    - Concatenate solution_str with reward_model code
    - Run in sandbox
    - If success and no stderr -> score = 1.0
    - Otherwise -> score = 0.0
    """

    # Handle numpy scalar for extra_info
    if isinstance(extra_info, np.ndarray):
        try:
            extra_info = extra_info.item()
        except Exception:
            extra_info = None

    has_code_piece = bool(solution_str.strip())
    if not has_code_piece:
        return {"score": 0.0, "extra_info": {"score": 0.0, "valid_code": 0}}

    # Parse ground_truth JSON
    try:
        gt = json.loads(ground_truth)
    except Exception:
        return {"score": 0.0, "extra_info": {"score": 0.0, "valid_code": 1}}

    reward_model = gt.get("reward_model")
    if isinstance(reward_model, list):
        rm_code = "\n".join(reward_model)
    elif isinstance(reward_model, str):
        rm_code = reward_model
    else:
        return {"score": 0.0, "extra_info": {"score": 0.0, "valid_code": 1}}

    code_to_execute = solution_str + "\n" + rm_code

    sandbox_success, sandbox_stdout, sandbox_stderr = asyncio.run(
        parallel_sandbox([code_to_execute], num_processes=256)
    )
    success = bool(sandbox_success and sandbox_success[0])
    stderr = str(sandbox_stderr[0]) if sandbox_stderr else ""

    if not success or len(stderr) > 0:
        return {"score": 0.0, "extra_info": {"score": 0.0, "valid_code": 1}}

    return {"score": 1.0, "extra_info": {"score": 1.0, "valid_code": 1}}
