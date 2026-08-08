# Agent2 model card

## Composition

- Base model: Qwen2.5-VL-7B-Instruct, loaded from a local directory.
- Adaptation: PEFT LoRA, rank 8, alpha 16, dropout 0.05, target modules `q_proj` and `v_proj`.
- Inference: 4-bit NF4, double quantization, float16 compute, deterministic generation (`do_sample=false`).
- Inputs: one pre-disaster image and one post-disaster image.
- Model output: one English change-description paragraph, always marked unverified.
- Adapter output: the unchanged paragraph plus a deterministic `claim_list` (`sentence-span-v1`). This postprocessor does not retrain or re-prompt the model and does not claim semantic decomposition of every compound sentence.

Neither the base model nor LoRA weights are stored in Git. Local weight record:

| Asset | Local filename | Size (bytes) | SHA-256 |
|---|---|---:|---|
| LoRA weights | `adapter_model.safetensors` | 10,108,960 | `c0bf7411325e2909ed4277ecb991f940a8d3477edda3e8c3ea78769872c49774` |

Prompt hashes used by the retained ablation run:

- paired: `1826dfebd330f75b53a0d00919c3454453176d975e2c60aceba8362b7ed82e0f`
- post-only: `254a9512f23e7166f49cef17f91d86c793f575365b8ecf2a135b4debb2c1ae7a`

## Intended use

Generate a candidate description of visible remote-sensing changes for subsequent evidence verification. The output must not independently assert casualties, economic loss, rescue status, or other facts that are not visually supported.

## Known limitations

- The legacy project contains inference and ablation code but no Agent2 fine-tuning training source or recoverable training manifest. Training is therefore not fully reproducible from this repository.
- The 20-sample EBD test selection is separate from the local EBD split used by Agent1, but overlap with the unavailable LoRA training manifest cannot be ruled out.
- No base-model-without-LoRA comparison was run, so observed behavior cannot be attributed solely to LoRA.
- The paired ablation has automatic analysis only; two-reviewer blind verification is pending.
- Current migration has not been integrated with the React frontend or real Agent3/4 services.

## Local acceptance

The migrated adapter was accepted locally on a CUDA machine with the recorded LoRA and one known pre/post sample. It completed deterministic generation and returned only relative Artifact paths. This is a local smoke acceptance, not a benchmark or end-to-end multi-agent validation. Do not publish local paths, offload files, raw images, or per-sample responses.
