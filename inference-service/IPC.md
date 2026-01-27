# Inference Service - IPC Architecture

This service uses gRPC streaming over Unix Domain Sockets (UDS) for high-performance inter-process communication between the ingestion and inference services.

## IPC Mechanism Comparison

### Unix Domain Socket (UDS) vs TCP
```
TCP Socket Path:
Application → TCP Stack → IP Stack → Loopback → IP Stack → TCP Stack → Application
              ‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾
                          Full network stack overhead

Unix Domain Socket Path:
Application → Kernel → Shared Memory → Kernel → Application
              ‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾
                   Direct memory copy
```

### Performance Characteristics

| Metric | TCP (localhost) | Unix Domain Socket |
|--------|----------------|-------------------|
| Latency | 50-100 μs | 10-20 μs |
| Throughput | ~4 GB/s | ~8 GB/s |
| CPU Overhead | Higher (protocol processing) | Lower (memory copy) |
| Context Switches | More | Fewer |

**Result:** UDS is ~5x faster for same-host communication.

## Why gRPC Streaming?

### Traditional Unary RPC
```
Client                          Server
  |                               |
  |─── Request 1 ────────────────>| 
  |                               | Process
  |<── Response 1 ────────────────|
  |                               |
  |─── Request 2 ────────────────>|
  |                               | Process
  |<── Response 2 ────────────────|
  
Each request = New connection overhead
```

### Our Streaming Approach
```
Client                          Server
  |                               |
  |═══ Open Stream ══════════════>|
  |                               |
  |─── Batch 1 ──────────────────>| Process
  |─── Batch 2 ──────────────────>| Process
  |─── Batch 3 ──────────────────>| Process
  |      ...                      |
  |─── Batch N ──────────────────>| Process
  |                               |
  |═══ Close Stream ═════════════>|
  |<── Summary ───────────────────|
  
One connection for entire session (1-4 hours)
```

### Benefits for Our Use Case

**FinnHub Ingestion Pattern:**
- API called every 2 seconds (rate limit)
- Each call returns multiple headlines (natural batch)
- Session runs for 1-4 hours = ~1,800-7,200 API calls

**Overhead Comparison:**

| Approach | Connection Setup | Messages | Latency Impact |
|----------|-----------------|----------|----------------|
| Unary RPC | 7,200 times | 7,200 req + 7,200 resp | High |
| Streaming | 1 time | 7,200 batches + 1 resp | Minimal |

## Data Flow
```
┌─────────────┐                    ┌─────────────┐
│  Ingestion  │                    │  Inference  │
│  Service    │                    │  Service    │
└──────┬──────┘                    └──────┬──────┘
       │                                  │
       │ Every 2s: Fetch from FinnHub     │
       │                                  │
       │         gRPC Stream              │
       │    (Unix Domain Socket)          │
       │                                  │
       ├──[HeadlineBatch]────────────────>│
       │   {headlines: [5 items],         │ Process batch
       │    timestamp: ...}               │ Run inference
       │                                  │
       ├──[HeadlineBatch]────────────────>│
       │   {headlines: [3 items],         │ Process batch
       │    timestamp: ...}               │ Run inference
       │                                  │
       │         (continues for           │
       │          1-4 hours)              │
       │                                  │
       ├──[Close Stream]─────────────────>│
       │                                  │
       │<─[StreamResponse]────────────────┤
       │   {processed: 12847,             │
       │    batches: 1800}                │
       │                                  │
```

## Configuration Modes

The service supports two modes via YAML configuration:

**UDS Mode** (Recommended for same-host):
```yaml
server:
  mode: uds
  uds_path: /tmp/inference.sock
```

**TCP Mode** (For distributed setup):
```yaml
server:
  mode: tcp
  host: 0.0.0.0
  port: 50051
```

## Why This Architecture?

1. **Low Latency**: UDS bypasses network stack (5x faster than TCP)
2. **High Throughput**: Single stream handles continuous data flow
3. **Natural Batching**: Preserves FinnHub API call boundaries
4. **Efficient**: Minimal connection overhead for long-running sessions
5. **Simple**: One connection, no batching logic on client side

## Running
```bash
# Build image
docker build -t inference-service .

# Run in UDS mode
docker run -e APP_PROFILE=uds -v /tmp:/tmp inference-service

# Run in TCP mode
docker run -e APP_PROFILE=tcp -p 50051:50051 inference-service
```