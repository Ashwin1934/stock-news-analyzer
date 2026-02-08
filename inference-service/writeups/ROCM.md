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
