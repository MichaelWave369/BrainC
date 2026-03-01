"""BrainC v0.4 — Safe local Python code execution sandbox.

Runs user-provided Python snippets in an isolated temp directory with a
strict timeout. Dangerous imports, system calls, and file writes are
rejected via AST analysis before any code is executed.
"""

import ast
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

TIMEOUT = 10  # seconds

# Top-level module names that are never allowed to be imported
_BLOCKED_IMPORTS = {
    "os", "subprocess", "shutil", "socket", "ctypes", "importlib",
    "pty", "sys", "platform", "signal", "resource", "threading",
    "multiprocessing", "concurrent", "asyncio", "selectors",
}

# Built-in function names that are always rejected
_BLOCKED_BUILTINS = {"eval", "exec", "__import__", "compile", "memoryview"}

# open() modes that write or truncate files
_WRITE_MODES = {"w", "a", "x", "wb", "ab", "xb", "w+", "a+", "x+", "r+"}


def _check_safety(code: str) -> Optional[str]:
    """Return an error string if the code fails safety checks, else None."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"Syntax error: {exc}"

    for node in ast.walk(tree):
        # Block dangerous imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in _BLOCKED_IMPORTS:
                    return f"Rejected: import '{alias.name}' is not permitted in the sandbox."

        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top in _BLOCKED_IMPORTS:
                return f"Rejected: 'from {node.module} import ...' is not permitted in the sandbox."

        elif isinstance(node, ast.Call):
            # Block eval(), exec(), __import__(), compile()
            if isinstance(node.func, ast.Name) and node.func.id in _BLOCKED_BUILTINS:
                return f"Rejected: '{node.func.id}()' is not permitted in the sandbox."

            # Block open() in write modes
            if isinstance(node.func, ast.Name) and node.func.id == "open":
                mode = _extract_open_mode(node)
                if mode and mode.strip("b+") in ("w", "a", "x"):
                    return "Rejected: open() in write mode is not permitted in the sandbox."

            # Block attribute calls like os.system(), subprocess.Popen(), shutil.rmtree()
            if isinstance(node.func, ast.Attribute):
                obj = node.func.value
                if isinstance(obj, ast.Name) and obj.id in _BLOCKED_IMPORTS:
                    return (
                        f"Rejected: '{obj.id}.{node.func.attr}()' is not permitted "
                        "in the sandbox."
                    )

    return None


def _extract_open_mode(call_node: ast.Call) -> Optional[str]:
    """Return the mode string from an open() call node, or None if not determinable."""
    # open(path, mode) — positional
    if len(call_node.args) >= 2:
        arg = call_node.args[1]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    # open(path, mode=...) — keyword
    for kw in call_node.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            return kw.value.value
    return None


def execute_code(code: str) -> dict:
    """Execute Python code safely and return {output, error, success, execution_time}."""
    error = _check_safety(code)
    if error:
        return {"output": "", "error": error, "success": False, "execution_time": 0.0}

    with tempfile.TemporaryDirectory() as tmpdir:
        script = Path(tmpdir) / "script.py"
        script.write_text(code, encoding="utf-8")

        t0 = time.monotonic()
        try:
            result = subprocess.run(
                ["python3", str(script)],
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
                cwd=tmpdir,
            )
            elapsed = round(time.monotonic() - t0, 3)
            return {
                "output": result.stdout[:5000],
                "error": result.stderr[:2000],
                "success": result.returncode == 0,
                "execution_time": elapsed,
            }
        except subprocess.TimeoutExpired:
            elapsed = round(time.monotonic() - t0, 3)
            return {
                "output": "",
                "error": f"Execution timed out after {TIMEOUT}s.",
                "success": False,
                "execution_time": elapsed,
            }
        except Exception as exc:
            return {
                "output": "",
                "error": str(exc),
                "success": False,
                "execution_time": 0.0,
            }
