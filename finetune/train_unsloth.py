#!/usr/bin/env python3
"""BrainC v0.3 — Unsloth LoRA Training Script

Fast single-GPU fine-tuning using Unsloth + SFTTrainer (TRL).
Trains a LoRA adapter on your BrainC conversation history, then merges
the adapter into the base weights and saves a full HuggingFace model.

Usage:
    python finetune/train_unsloth.py
    python finetune/train_unsloth.py --epochs 1 --batch-size 2 --lr 2e-4
"""

import argparse
import json
from pathlib import Path

HERE = Path(__file__).parent
DATASETS_DIR = HERE / "datasets"
OUTPUT_DIR = HERE / "output"
ADAPTER_DIR = OUTPUT_DIR / "lora_adapter"
MERGED_DIR = OUTPUT_DIR / "merged_model"

BASE_MODEL = "unsloth/Qwen2.5-14B-Instruct"
MAX_SEQ_LEN = 4096
LORA_RANK = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.05
LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Fine-tune BrainC using Unsloth + SFTTrainer."
    )
    p.add_argument("--epochs", type=int, default=3, help="Training epochs (default: 3)")
    p.add_argument(
        "--batch-size", type=int, default=2, help="Per-device micro batch size (default: 2)"
    )
    p.add_argument(
        "--grad-accum",
        type=int,
        default=4,
        help="Gradient accumulation steps (default: 4)",
    )
    p.add_argument("--lr", type=float, default=2e-4, help="Learning rate (default: 2e-4)")
    p.add_argument(
        "--dataset",
        type=Path,
        default=DATASETS_DIR / "sharegpt_dataset.json",
        help="Path to the ShareGPT-format dataset",
    )
    return p.parse_args()


def load_dataset(dataset_path: Path) -> list[dict]:
    """Load ShareGPT records and convert to the messages format for SFTTrainer."""
    records = json.loads(dataset_path.read_text())
    formatted = []
    for record in records:
        messages = []
        for turn in record["conversations"]:
            role = "user" if turn["from"] == "human" else "assistant"
            messages.append({"role": role, "content": turn["value"]})
        formatted.append({"messages": messages})
    return formatted


def main() -> None:
    args = parse_args()

    # ── Deferred imports so the file is readable without a GPU env installed ──
    try:
        from unsloth import FastLanguageModel
        from unsloth.chat_templates import get_chat_template
        from trl import SFTTrainer
        from transformers import TrainingArguments
        from datasets import Dataset
    except ImportError as e:
        print(f"[error] Missing dependency: {e}")
        print("  Install: pip install torch --index-url https://download.pytorch.org/whl/cu124")
        print("           pip install -r finetune/requirements.txt")
        raise SystemExit(1)

    if not args.dataset.exists():
        print(f"[error] Dataset not found: {args.dataset}")
        print("  Run: python finetune/collect.py")
        raise SystemExit(1)

    for d in (OUTPUT_DIR, ADAPTER_DIR, MERGED_DIR):
        d.mkdir(parents=True, exist_ok=True)

    # ── Load model ─────────────────────────────────────────────────────────────
    print(f"\nLoading {BASE_MODEL} with Unsloth ...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=MAX_SEQ_LEN,
        load_in_4bit=True,
        dtype=None,  # auto-detect bfloat16 on Ampere+
    )
    tokenizer = get_chat_template(tokenizer, chat_template="chatml")

    # ── Apply LoRA ─────────────────────────────────────────────────────────────
    print("Applying LoRA adapters ...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_RANK,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules=LORA_TARGETS,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    # ── Dataset ────────────────────────────────────────────────────────────────
    print(f"Loading dataset from {args.dataset} ...")
    raw = load_dataset(args.dataset)
    if not raw:
        print("[error] Dataset is empty — run: python finetune/collect.py")
        raise SystemExit(1)

    def apply_template(examples):
        texts = []
        for msgs in examples["messages"]:
            text = tokenizer.apply_chat_template(
                msgs, tokenize=False, add_generation_prompt=False
            )
            texts.append(text)
        return {"text": texts}

    dataset = Dataset.from_list(raw).map(
        apply_template,
        batched=True,
        remove_columns=["messages"],
    )
    print(f"  {len(dataset)} training examples loaded.\n")

    # ── Train ──────────────────────────────────────────────────────────────────
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LEN,
        dataset_num_proc=2,
        args=TrainingArguments(
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            num_train_epochs=args.epochs,
            learning_rate=args.lr,
            lr_scheduler_type="cosine",
            warmup_steps=20,
            bf16=True,
            logging_steps=10,
            save_steps=100,
            save_total_limit=3,
            output_dir=str(ADAPTER_DIR),
            report_to="none",
            dataloader_num_workers=0,
        ),
    )

    print("── Starting training ─────────────────────────────────────────────────")
    print(
        f"  Model    : {BASE_MODEL}\n"
        f"  LoRA     : r={LORA_RANK}, alpha={LORA_ALPHA}\n"
        f"  Epochs   : {args.epochs}\n"
        f"  Batch    : {args.batch_size} × {args.grad_accum} accum = "
        f"{args.batch_size * args.grad_accum} effective\n"
        f"  Examples : {len(dataset)}\n"
    )
    trainer.train()

    # ── Save LoRA adapter ──────────────────────────────────────────────────────
    print(f"\nSaving LoRA adapter to {ADAPTER_DIR} ...")
    model.save_pretrained(str(ADAPTER_DIR))
    tokenizer.save_pretrained(str(ADAPTER_DIR))

    # ── Merge and save full model ──────────────────────────────────────────────
    print(f"Merging LoRA into base model → {MERGED_DIR} ...")
    model = FastLanguageModel.for_inference(model)
    model.save_pretrained_merged(str(MERGED_DIR), tokenizer, save_method="merged_16bit")

    print(
        f"\n✓ Training complete.\n"
        f"  Adapter : {ADAPTER_DIR}\n"
        f"  Merged  : {MERGED_DIR}\n"
        f"\nNext step: python finetune/export_to_ollama.py"
    )


if __name__ == "__main__":
    main()
