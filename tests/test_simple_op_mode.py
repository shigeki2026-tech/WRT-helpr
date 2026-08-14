import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_simple_op_entrypoint_uses_shared_app_and_single_read_only_tab():
    assert (ROOT / "app_simple.py").exists()
    assert (ROOT / "start_simple.bat").exists()

    env = os.environ.copy()
    env["WRT_SIMPLE_OP_MODE"] = "1"
    code = (
        "import json, app; "
        "print(json.dumps({'simple': app.SIMPLE_OP_MODE, 'tabs': app.MAIN_TAB_ORDER}, ensure_ascii=False))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout.strip().splitlines()[-1])

    assert result == {"simple": True, "tabs": ["during_call"]}
