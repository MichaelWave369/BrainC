#!/usr/bin/env python3
"""BrainC v0.3 — GGUF Export & Ollama Import

Converts the fine-tuned merged HuggingFace model to GGUF format using
llama.cpp, quantizes it to Q4_K_M, and registers it in Ollama as
'braincbrain-ft'.

Usage:
    python finetune/export_to_ollama.py
    python finetune/export_to_ollama.py --quant Q4_K_M --model-name braincbrain-ft
    python finetune/export_to_ollama.py --llama-cpp-dir ~/llama.cpp
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent

MERGED_DIR = HERE / "output" / "merged_model"
OUTPUT_DIR = HERE / "output"
SYSTEM_PROMPT_PATH = ROOT / "model" / "system_prompt.md"
MODELFILE_PATH = HERE / "output" / "Modelfile.ft"

_LLAMA_CPP_CANDIDATES = [
    Path.home() / "llama.cpp",
    Path("/opt/llama.cpp"),
    Path("/usr/local/llama.cpp"),
    Path.cwd() / "llama.cpp",
]


# ── llama.cpp detection ─────────────────────────────────────────────────────


def _find_llama_cpp() -> Path | None:
    for candidate in _LLAMA_CPP_CANDIDATES:
        if (candidate / "convert_hf_to_gguf.py").exists():
            return candidate
    return None


def _require_llama_cpp(override: Path | None) -> Path:
    llama_dir = override or _find_llama_cpp()
    if llama_dir and (llama_dir / "convert_hf_to_gguf.py").exists():
        return llama_dir
    print(
        "[error] llama.cpp not found.\n\n"
        "Install it:\n"
        "  git clone https://github.com/ggerganov/llama.cpp ~/llama.cpp\n"
        "  cd ~/llama.cpp && make -j$(nproc)\n"
        "  pip install -r ~/llama.cpp/requirements.txt\n"
    )
    raise SystemExit(1)


# ── Shell helpers ───────────────────────────────────────────────────────────


def _run(cmd: list[str | Path]) -> None:
    """Execute a command, raising SystemExit on failure."""
    str_cmd = [str(c) for c in cmd]
    print(f"  $ {' '.join(str_cmd)}")
    result = subprocess.run(str_cmd)
    if result.returncode != 0:
        print(f"[error] Command exited with code {result.returncode}")
        raise SystemExit(1)


# ── Conversion steps ────────────────────────────────────────────────────────


def convert_to_gguf(llama_dir: Path, merged_dir: Path, out_path: Path) -> None:
    """Convert a HuggingFace model directory to GGUF (float16)."""
    print(f"\nConverting to f16 GGUF → {out_path} ...")
    _run(
        [
            sys.executable,
            llama_dir / "convert_hf_to_gguf.py",
            merged_dir,
            "--outfile", out_path,
            "--outtype", "f16",
        ]
    )


def quantize_gguf(llama_dir: Path, src: Path, dst: Path, quant: str) -> None:
    """Quantize an f16 GGUF to the requested quantization level."""
    quantize_bin = llama_dir / "llama-quantize"
    if not quantize_bin.exists():
        quantize_bin = llama_dir / "quantize"  # older naming convention
    if not quantize_bin.exists():
        print(
            f"[error] llama-quantize binary not found in {llama_dir}.\n"
            f"  Build it: cd {llama_dir} && make -j$(nproc)"
        )
        raise SystemExit(1)
    print(f"Quantizing to {quant} → {dst} ...")
    _run([quantize_bin, src, dst, quant])


def generate_modelfile(gguf_path: Path, model_name: str) -> Path:
    """Write an Ollama Modelfile pointing to the quantized GGUF."""
    system_prompt = ""
    if SYSTEM_PROMPT_PATH.exists():
        system_prompt = SYSTEM_PROMPT_PATH.read_text().strip()

    content = f"""\
FROM {gguf_path.resolve()}

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER stop "<|im_end|>"

SYSTEM \"\"\"
{system_prompt}
\"\"\"
"""
    MODELFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODELFILE_PATH.write_text(content)
    print(f"  Modelfile written → {MODELFILE_PATH}")
    return MODELFILE_PATH


def register_with_ollama(modelfile_path: Path, model_name: str) -> None:
    """Create the model in Ollama."""
    if not shutil.which("ollama"):
        print("[warning] Ollama not found in PATH — skipping registration.")
        print(f"  Register manually: ollama create {model_name} -f {modelfile_path}")
        return
    print(f"\nRegistering '{model_name}' in Ollama ...")
    _run(["ollama", "create", model_name, "-f", modelfile_path])


def print_next_steps(model_name: str) -> None:
    print(
        f"\n── Done! ─────────────────────────────────────────────────────────────\n"
        f"'{model_name}' is now available in Ollama.\n\n"
        f"To switch BrainC API to the fine-tuned model, edit api/routes/chat.py:\n"
        f"  MODEL_NAME = \"{model_name}\"   # was: \"braincbrain\"\n\n"
        f"Restart the server:\n"
        f"  ./scripts/start.sh\n\n"
        f"To compare models:\n"
        f"  python finetune/ab_test.py --model-a braincbrain --model-b {model_name}\n"
        f"──────────────────────────────────────────────────────────────────────"
    )


# ── CLI ─────────────────────────────────────────────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser(
        description="Export fine-tuned BrainC model to GGUF and register in Ollama."
    )
    p.add_argument(
        "--merged-dir",
        type=Path,
        default=MERGED_DIR,
        help="Path to merged HuggingFace model (default: finetune/output/merged_model/)",
    )
    p.add_argument(
        "--quant",
        default="Q4_K_M",
        help="GGUF quantization type (default: Q4_K_M)",
    )
    p.add_argument(
        "--model-name",
        default="braincbrain-ft",
        help="Ollama model name to register (default: braincbrain-ft)",
    )
    p.add_argument(
        "--llama-cpp-dir",
        type=Path,
        default=None,
        help="Path to llama.cpp directory (auto-detected if not set)",
    )
    args = p.parse_args()

    if not args.merged_dir.exists():
        print(f"[error] Merged model not found: {args.merged_dir}")
        print("  Run: python finetune/train_unsloth.py")
        raise SystemExit(1)

    llama_dir = _require_llama_cpp(args.llama_cpp_dir)

    f16_gguf = OUTPUT_DIR / "braincbrain-finetuned-f16.gguf"
    quant_gguf = OUTPUT_DIR / "braincbrain-finetuned.gguf"

    convert_to_gguf(llama_dir, args.merged_dir, f16_gguf)
    quantize_gguf(llama_dir, f16_gguf, quant_gguf, args.quant)

    # Remove the large intermediate f16 file
    size_gb = f16_gguf.stat().st_size / 1e9
    print(f"Removing intermediate f16 file ({size_gb:.1f} GB) ...")
    f16_gguf.unlink()

    modelfile_path = generate_modelfile(quant_gguf, args.model_name)
    register_with_ollama(modelfile_path, args.model_name)
    print_next_steps(args.model_name)


if __name__ == "__main__":
    main()
