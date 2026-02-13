# ROCm Setup Guide for Stock News Analyzer

## What is ROCm?

ROCm (Radeon Open Compute) is AMD's open-source computing platform for GPU acceleration. It's AMD's equivalent to Nvidia's CUDA - it allows PyTorch and other ML frameworks to leverage AMD GPUs for parallel computing.

In my case, I have an AMD WX 4100 GPU with:
- 4GB dedicated VRAM
- 7.9GB shared memory (from system RAM)
- Total: 11.9GB usable for models and data

## ROCm vs CUDA

| Aspect | CUDA | ROCm |
|--------|------|------|
| **Creator** | Nvidia (proprietary) | AMD (open-source) |
| **GPU Support** | Nvidia GPUs only | AMD GPUs (RDNA, RDNA2, MI series) |
| **Licensing** | Proprietary | Open-source (MIT license) |
| **Maturity** | Very mature (20+ years) | Growing, but rapidly improving |
| **Ecosystem** | Larger community | Expanding ecosystem |

ROCm enables my AMD WX 4100 to accelerate PyTorch inference, whereas CUDA would not work with AMD hardware.

## Hardware & OS Stack

My system has:
1. **Windows Host OS** - Where the AMD WX 4100 GPU and its driver are installed
2. **AMD GPU Driver** - Installed on the host; enables OS to recognize and manage the GPU
3. **Docker Container** - Lightweight virtualization that runs the inference service

## Architecture Diagram: Hardware to Application

```
┌─────────────────────────────────────────────────────┐
│                    HOST SYSTEM                       │
│                  (Your Windows PC)                   │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │    AMD GPU Driver (installed on host)        │  │
│  └──────────────────────────────────────────────┘  │
│                      ▲                              │
│                      │ (Manages GPU)                │
│                      │                              │
│  ┌──────────────────┴──────────────────────────┐  │
│  │    Physical AMD WX 4100 GPU                 │  │
│  │  (4GB VRAM + 7.9GB shared system RAM)       │  │
│  │  (4,096 stream cores for parallel compute) │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
└─────────────────────────────────────────────────────┘
                      ▲
                      │ (GPU passthrough via
                      │  docker --gpus flag)
                      │
        ┌─────────────┴──────────────────┐
        │                                │
┌───────▼───────────────────────────────▼────────┐
│            DOCKER CONTAINER                    │
├─────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────┐  │
│  │   Your Application                      │  │
│  │ (inference_server.py with PyTorch)      │  │
│  └──────────────────┬──────────────────────┘  │
│                     │                          │
│  ┌──────────────────▼──────────────────────┐  │
│  │   PyTorch Libraries                     │  │
│  │ (checks device config: cpu/rocm)        │  │
│  └──────────────────┬──────────────────────┘  │
│                     │                          │
│  ┌──────────────────▼──────────────────────┐  │
│  │   ROCm Libraries (HIP Runtime)          │  │
│  │ (abstraction layer for AMD GPU)         │  │
│  └──────────────────┬──────────────────────┘  │
│                     │                          │
│  ┌──────────────────▼──────────────────────┐  │
│  │   GPU Device Files (/dev/dri/*)         │  │
│  │   (mapped from host)                    │  │
│  └──────────────────┬──────────────────────┘  │
│                     │                          │
└─────────────────────┼──────────────────────────┘
                      │ (device mapping)
                      ▼
           Physical GPU on Host
```

## How It Works During Inference

When I run my FinBERT inference service with `device: rocm`:

```
1. My Python Application (finbert_inference_service.py)
         │
         ▼
   PyTorch.device("rocm")
         │
         ├──> Queries: Is ROCm available?
         │
   ROCm Runtime (HIP)
         │
         ├──> GPU Detection: Found AMD WX 4100
         ├──> Memory: 4GB dedicated + 7.9GB shared = 11.9GB total
         │
         ▼
   Model Loading
         │
         ├──> Load FinBERT weights into GPU VRAM (4GB)
         ├──> If model > 4GB: Spill to shared RAM (slower but works)
         │
         ▼
   Inference
         │
         ├──> Move input tensors to GPU
         ├──> Run forward pass on 4,096 stream cores (parallel)
         ├──> Execute in parallel (much faster than CPU)
         │
         ▼
   GPU Memory Management
         │
         ├──> Clean up intermediate tensors
         ├──> Call torch.cuda.empty_cache() (works with ROCm too)
         │
         ▼
   Return Results
```

## Key Points

1. **Shared Memory**: The 7.9GB is not separate GPU memory - it's system RAM that the GPU can access. It's slower than the dedicated 4GB VRAM but extends available memory.

2. **Docker GPU Passthrough**: When I run the Docker container with `docker run --gpus all`, the container gets direct access to the GPU device files. This is how the container "sees" the GPU.

3. **ROCm in Docker**: I included ROCm libraries in the Docker image (`rocm/pytorch:latest` base image). This ensures PyTorch can communicate with the GPU through the ROCm abstraction layer.

4. **Configuration Flexibility**: My YAML profiles (`experiment1.yaml` with `cpu`, `experiment2.yaml` with `rocm`) let me choose at runtime which device to use. PyTorch will use whichever device I specify - no code changes needed.

5. **Backward Compatibility**: If I specify `device: cpu`, ROCm libraries are still in the image but simply aren't used. No performance penalty for having them.

## Testing Setup

Before running inference with ROCm:

```bash
# Check if AMD GPU driver is installed
# (Device Manager shows AMD WX 4100 ✓)

# Build Docker image with ROCm support
docker build -f inference-service/Dockerfile -t inference-server:2026-02-08 .

# Run with GPU (requires --gpus flag)
docker run --gpus all -e APP_PROFILE=experiment2 inference-server:2026-02-08

# Run CPU-only (for comparison)
docker run -e APP_PROFILE=experiment1 inference-server:2026-02-08
```

The difference you'll see:
- **CPU mode**: Slower inference, lower memory usage, works everywhere
- **ROCm mode**: 5-10x faster inference, uses GPU memory, leverages 4,096 parallel cores

## What I Changed

1. **Dockerfile**: Updated base image to `rocm/pytorch:latest` (includes ROCm and PyTorch with AMD support)
2. **finbert_inference_service.py**: Added `rocm` as valid device option in validation
3. **application-experiment2.yaml**: Changed device from `cuda` to `rocm`

Now my inference service supports both CPU and GPU (via ROCm) with zero code changes - just configuration switching.

## Practical Questions

### Question: Model Size > GPU VRAM - Where Do Input Tensors Actually Go?

**My Question:**
Let's say the model size is greater than 4GB, which exceeds the GPU VRAM. We then say that we are putting the rest into system RAM, via the 7.9GB of sharable memory. My question is related to the inference step, "move input tensors to GPU". Are we really moving it to the GPU VRAM? Or are we simply keeping it in the system RAM, which is available to the GPU? Wouldn't this be faster than actually having to move the tensors?

**Initial Answer:**

When you call `.to(device)` on a tensor with ROCm:

1. **PyTorch checks available GPU VRAM** - "Do I have space in the 4GB?"
2. **If YES** - Moves tensor to GPU VRAM (fast execution)
3. **If NO** - Keeps it in system RAM (slower execution, but avoids unnecessary copying)

The GPU can directly access system RAM through the unified memory architecture. So ROCm intelligently decides:
- Move to VRAM if there's space (fastest)
- Keep in system RAM if VRAM is full (avoids the copy overhead)

**Why keeping it in system RAM is actually faster in the full-model case:**

```
Scenario 1: Model in VRAM, Inputs in VRAM
├─ Input: Already in fast VRAM
├─ Model weights: Already in fast VRAM
├─ Execution: Very fast
└─ Total: Minimal overhead

Scenario 2: Model spilled to system RAM, Inputs moved to VRAM
├─ Input: Copy to VRAM (overhead!)
├─ Model weights: Must fetch from system RAM during execution (slow!)
├─ Execution: Slow (constant system RAM access)
└─ Total: High overhead (extra copy + slow execution)

Scenario 3: Model spilled to system RAM, Inputs stay in system RAM
├─ Input: Already in system RAM
├─ Model weights: In system RAM
├─ Execution: Slower than Scenario 1, but no copying overhead
└─ Total: Better than Scenario 2
```

**My Follow-up Correction:**
But for scenario 3, aren't only some of the model weights in system RAM? Aren't some in GPU VRAM?

**Corrected Explanation:**

Yes, that's absolutely correct! Here's the more accurate picture:

**Scenario 3 (corrected): Model split between VRAM and system RAM, Inputs in system RAM**

```
├─ Model weights distribution:
│  ├─ 4GB in GPU VRAM (fast)
│  └─ 1GB in system RAM (slower)
│
├─ Input tensors: In system RAM
│
├─ Execution: 
│  ├─ When GPU needs weights from VRAM: Fast access
│  ├─ When GPU needs weights from system RAM: Slower access
│  ├─ When GPU needs input data: Slower access (also system RAM)
│
└─ Total: Variable speed depending on which weights are accessed
```

So yes, during inference:
- Some weight fetches hit fast GPU VRAM → fast
- Some weight fetches hit system RAM → slower
- All input fetches hit system RAM → slower

The benefit of keeping inputs in system RAM (rather than copying them) is still that you **avoid the copy overhead**. But you're correct that you don't get the speed benefit of having everything in VRAM.

**The tradeoff is:**
- Moving inputs to VRAM: Costs time for copying + wastes limited VRAM space
- Keeping inputs in system RAM: No copy cost, but still slow access during execution

Given that inputs are typically much smaller than the model itself, keeping them in system RAM is usually the right choice. But it's definitely a slower scenario than having everything in VRAM.

## Image Sizes
Note that the image I built with ROCm support is ~42GB on docker desktop... so I built a separate image that uses ```FROM python:3.10-slim``` instead of ```rocm/pytorch:latest```. The end result was a cpu based image of ~12GB. This shouldn't affect the runtime but is good to know for dev ops and cloud purposes, since pushing/pulling/storing a huge image is painful and costly. Just good to know, will still need the ROCm image for the main experiments.
