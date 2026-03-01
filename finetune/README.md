# BrainC Fine-Tuning Pipeline — v0.3

Fine-tune BrainC on your own conversation history using LoRA. The pipeline
covers every step: dataset export, quality analysis, training, GGUF conversion,
Ollama registration, and A/B testing against the base model.

---

## Prerequisites

- Python 3.11+
- NVIDIA GPU with 12+ GB VRAM (RTX 5070 tested; 8 GB GPUs work with batch-size 1)
- Ollama installed with `braincbrain` available (`ollama list`)
- A HuggingFace account — run `huggingface-cli login` before training to authorize the model download
- llama.cpp (for GGUF export) — see Step 4

Install Python dependencies:

```bash
# 1. PyTorch with CUDA (do this first — order matters)
pip install torch --index-url https://download.pytorch.org/whl/cu124

# 2. Fine-tuning stack
pip install -r finetune/requirements.txt
```

---

## Step-by-Step Workflow

### Step 1 — Collect Dataset

Export your BrainC conversation history into training formats:

```bash
python finetune/collect.py
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--min-words` | `20` | Minimum word count for both instruction and output |
| `--output-dir` | `finetune/datasets/` | Where to write the dataset files |
| `--db` | `memory/conversations.db` | Path to the SQLite database |

**Outputs:**
- `finetune/datasets/alpaca_dataset.json` — Alpaca instruction-following format
- `finetune/datasets/sharegpt_dataset.json` — ShareGPT / Axolotl format

---

### Step 2 — Analyze Dataset Quality

Before training, check what you're working with:

```bash
python finetune/analyze_dataset.py
```

This prints total pairs, average/min/max lengths, ASCII histograms, and flags:
- Outputs shorter than `--short-threshold` words (default: 30)
- Duplicate instructions
- Records with error-like content

**Target:** 500+ quality pairs. Under 100 pairs will produce unreliable results.

---

### Step 3 — Train

#### Option A — Unsloth (Recommended: single GPU, fastest)

```bash
python finetune/train_unsloth.py
```

| Flag | Default | Description |
|------|---------|-------------|
| `--epochs` | `3` | Training epochs |
| `--batch-size` | `2` | Per-device micro batch size |
| `--grad-accum` | `4` | Gradient accumulation steps |
| `--lr` | `2e-4` | Learning rate |

**Outputs:**
- `finetune/output/lora_adapter/` — LoRA adapter weights only
- `finetune/output/merged_model/` — Full merged HuggingFace model (ready for GGUF)

**Expected time on RTX 5070 (12 GB VRAM):**

| Dataset size | 3 epochs |
|---|---|
| 200 pairs | ~1–2 hours |
| 500 pairs | ~2–3 hours |
| 1,000 pairs | ~4–6 hours |

#### Option B — Axolotl (multi-GPU, more config options)

Edit `finetune/axolotl_config.yml` as needed, then:

```bash
axolotl train finetune/axolotl_config.yml
```

---

### Step 4 — Export to Ollama

Convert the merged model to GGUF and register it in Ollama:

```bash
# Install llama.cpp (required once)
git clone https://github.com/ggerganov/llama.cpp ~/llama.cpp
cd ~/llama.cpp && make -j$(nproc)
pip install -r ~/llama.cpp/requirements.txt

# Export
python finetune/export_to_ollama.py
```

| Flag | Default | Description |
|------|---------|-------------|
| `--merged-dir` | `finetune/output/merged_model/` | Input model path |
| `--quant` | `Q4_K_M` | GGUF quantization level |
| `--model-name` | `braincbrain-ft` | Ollama model name |
| `--llama-cpp-dir` | auto-detected | Path to llama.cpp checkout |

This creates `finetune/output/braincbrain-finetuned.gguf` and registers
`braincbrain-ft` in Ollama.

---

### Step 5 — A/B Test

Compare the base model against the fine-tuned one:

```bash
python finetune/ab_test.py
```

| Flag | Default | Description |
|------|---------|-------------|
| `--model-a` | `braincbrain` | Base model |
| `--model-b` | `braincbrain-ft` | Fine-tuned model |
| `--prompts` | `finetune/test_prompts.txt` | Prompt file |
| `--timeout` | `120` | Seconds per response |

Side-by-side output is printed to the terminal. Full results are saved to
`finetune/ab_results/result_TIMESTAMP.json`.

---

### Step 6 — Switch the API

Once satisfied with the A/B results, point BrainC at the fine-tuned model.

Edit `api/routes/chat.py`:

```python
MODEL_NAME = "braincbrain-ft"   # was: "braincbrain"
```

Restart:

```bash
./scripts/start.sh
```

Revert any time by changing `MODEL_NAME` back.

---

## Hardware Requirements

| | Minimum | Recommended |
|---|---|---|
| GPU | 8 GB VRAM | 12 GB VRAM (RTX 5070) |
| System RAM | 32 GB | 64 GB |
| Disk (model + GGUF) | 80 GB free | 150 GB free |

---

## Tips for Dataset Quality

- **Volume matters more than perfection.** 2,000 filtered pairs will outperform
  200 manually curated ones.
- **Diversity by topic** produces better generalization than same-domain depth.
- **Raise `--min-words`.** Using `--min-words 30` or higher tends to eliminate
  low-signal exchanges that hurt training.
- **Analyze before every training run.** A single `analyze_dataset.py` run can
  catch issues that would waste hours of GPU time.
- **Iterate.** Fine-tune → A/B test → have more conversations → fine-tune again.
  The dataset improves every time you use BrainC.

---

## File Layout

```
finetune/
├── collect.py            # Export conversations → Alpaca + ShareGPT
├── analyze_dataset.py    # Quality report + histograms
├── train_unsloth.py      # Unsloth LoRA training (recommended)
├── axolotl_config.yml    # Axolotl config (multi-GPU / alternative)
├── export_to_ollama.py   # GGUF conversion + Ollama registration
├── ab_test.py            # Side-by-side model comparison
├── test_prompts.txt      # 10 default test prompts
├── requirements.txt      # Fine-tuning Python dependencies
├── datasets/             # Generated datasets (git-ignored; .gitkeep committed)
├── ab_results/           # A/B result JSON files (git-ignored; .gitkeep committed)
└── output/               # Training outputs (git-ignored; .gitkeep committed)
```
