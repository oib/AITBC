# GPU Acceleration Benchmarks

Benchmark snapshots for common GPUs in the AITBC stack. Values are indicative and should be validated on target hardware.

## Throughput (TFLOPS, peak theoretical)
| GPU | FP32 TFLOPS | BF16/FP16 TFLOPS | Notes |
| --- | --- | --- | --- |
| NVIDIA H100 SXM | ~67 | ~989 (Tensor Core) | Best for large batch training/inference |
| NVIDIA A100 80GB | ~19.5 | ~312 (Tensor Core) | Strong balance of memory and throughput |
| RTX 4090 | ~82 | ~165 (Tensor Core) | High single-node perf; workstation-friendly |
| RTX 3080 | ~30 | ~59 (Tensor Core) | Cost-effective mid-tier |

## Latency (ms) — Transformer Inference (BERT-base, sequence=128)
| GPU | Batch 1 | Batch 8 | Notes |
| --- | --- | --- | --- |
| H100 | ~1.5 ms | ~2.3 ms | Best-in-class latency |
| A100 80GB | ~2.1 ms | ~3.0 ms | Stable at scale |
| RTX 4090 | ~2.5 ms | ~3.5 ms | Strong price/perf |
| RTX 3080 | ~3.4 ms | ~4.8 ms | Budget-friendly |

## Recommendations
- Prefer **H100/A100** for multi-tenant or high-throughput workloads.
- Use **RTX 4090** for cost-efficient single-node inference and fine-tuning.
- Tune batch size to balance latency vs. throughput; start with batch 8–16 for inference.
- Enable mixed precision (BF16/FP16) when supported to maximize Tensor Core throughput.

## Validation Checklist
- Run `nvidia-smi` under sustained load to confirm power/thermal headroom.
- Pin CUDA/cuDNN versions to tested combos (e.g., CUDA 12.x for H100, 11.8+ for A100/4090).
- Verify kernel autotuning (e.g., `torch.backends.cudnn.benchmark = True`) for steady workloads.
- Re-benchmark after driver updates or major framework upgrades.
