# Model and Dataset Licensing

BrainC's MIT license applies to project-owned integration code, prompts, configuration, and documentation. It does not automatically apply to model weights or training datasets.

## Default BrainC model reference

`model/Modelfile` currently starts from:

```text
FROM qwen2.5:14b
```

The corresponding Qwen2.5 14B Instruct model is published under the Apache License 2.0 by its upstream provider.

BrainC does not store the Qwen2.5 model weights in this repository. Users obtain models separately through their chosen runtime.

## Fine-tuned models

BrainC's fine-tuning pipeline can create LoRA adapters, merged models, GGUF files, and evaluation artifacts.

Those outputs are intentionally gitignored.

The license applicable to a fine-tuned model can depend on:

- the base model license;
- the training dataset license;
- the user's own contributed data;
- licenses of intermediate tools;
- any additional restrictions attached to the model or dataset.

Do not assume that a generated weight file becomes MIT merely because BrainC's training scripts are MIT.

## Conversation-derived datasets

The fine-tuning tools can export local conversation history into training datasets.

Users are responsible for ensuring they have the right to use and redistribute the source material in any dataset they create.

## Future release rule

A bundled model or dataset must document:

1. exact name and version;
2. upstream source;
3. governing license or terms;
4. redistribution permission;
5. attribution and notice requirements.
