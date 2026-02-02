# Headlines Client - Architecture

This document explains how the FinnHub Headlines Client works and its threading model.

## Architecture Overview

The client is a **single-threaded producer** that continuously fetches headlines from FinnHub and streams them to the inference server via gRPC.

```
┌────────────────────────────────────────────────────────────┐
│  Single Application Thread                                 │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ Main Loop (Running Forever)                          │ │
│  │                                                      │ │
│  │  while True:                                         │ │
│  │    ├─ Fetch from FinnHub (AAPL)   ··· API call     │ │
│  │    ├─ Fetch from FinnHub (MSFT)   ··· API call     │ │
│  │    ├─ Deduplicate headlines                         │ │
│  │    ├─ Build HeadlineBatch protobuf                  │ │
│  │    ├─ Yield to gRPC stream        ────┐             │ │
│  │    │                                   ↓             │ │
│  │    │ gRPC handles serialization       Serial         │ │
│  │    │ and network I/O                                │ │
│  │    │                                                │ │
│  │    └─ Sleep 2 seconds                               │ │
│  │                                                      │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
│  Network Layer (handled by gRPC + OS):                    │
│    gRPC serializes → TCP/UDS → Kernel → Network/Socket  │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

## Data Flow Timeline

Here's what happens in a typical 2-second cycle:

```
Time    Client Thread                      FinnHub         Server
────────────────────────────────────────────────────────────────────

 0ms    start = 0
        │
 2ms    ├─ Call FinnHub API (AAPL)  ─────────────────────────→
        │                                   (HTTP request)
        │
25ms    │                            ←───── 10 headlines
        │                                   (HTTP response)
        │
30ms    ├─ Call FinnHub API (MSFT)  ─────────────────────────→
        │                                   (HTTP request)
        │
50ms    │                            ←───── 8 headlines
        │                                   (HTTP response)
        │
55ms    ├─ Deduplicate (18 → 15 new)
        │
60ms    ├─ Build HeadlineBatch
        │
62ms    ├─ Serialize protobuf
        │
65ms    ├─ Stream to server  ─────────────────────────────────→
        │                                                       (queued)
        │                                                       ↓
        │                                      [Server processes batch]
        │
68ms    ├─ Sleep until next iteration
        │  (1932ms remaining)
        │
2000ms  └─ Repeat (every 2000ms)
```

## Threading Model

The client is **inherently single-threaded** with the following characteristics:

### Thread Execution
```
┌─────────────────────────────────────────────┐
│ Main Thread                                 │
│                                             │
│ • Runs FinnHub API calls sequentially       │
│ • Runs deduplication logic sequentially     │
│ • Yields batches to gRPC sequentially       │
│ • Sleeps for remaining time                 │
│                                             │
│ Total work per cycle: ~65-100ms             │
│ Idle time per cycle: ~1900-1935ms           │
│                                             │
└─────────────────────────────────────────────┘
                    ↓ (passes to)
┌─────────────────────────────────────────────┐
│ OS/Network Layer (via gRPC)                 │
│                                             │
│ • gRPC serialization (non-blocking)         │
│ • TCP/UDS transmission (non-blocking)       │
│ • Kernel socket buffer management           │
│                                             │
└─────────────────────────────────────────────┘
```

### Why Single-Threaded is Fine

```
Synchronous Model (Current):
┌─────────────┐
│ FinnHub     │  Fetch 1: 20ms ┐
│ API Calls   │  Fetch 2: 20ms ├─ Total: 40ms
│             │                ┘
└─────────────┘
       ↓
┌─────────────┐
│ Deduplicate │  5ms
└─────────────┘
       ↓
┌─────────────┐
│ Serialize & │  10ms
│ Stream      │
└─────────────┘
       ↓
   Sleep 1945ms
   
Total: 2000ms (exactly 2 second intervals)
```

The 2-second poll interval means the client is idle **97.5%** of the time. Adding threads would waste resources without benefit because:

1. **I/O-bound dominance**: ~95% of time is sleeping or waiting for network
2. **No CPU contention**: Only one thread doing work, no parallelization needed
3. **Simple logic**: No complex synchronization or race conditions
4. **Memory efficient**: No thread overhead

## Code Flow

```
1. main()
   │
   ├─ Load config (YAML)
   ├─ Load FinnHub API key (.env)
   │
   ├─ Create HeadlinesStreamClient
   │  │
   │  └─ Initialize:
   │     ├─ finnhub.Client(api_key)
   │     ├─ Load symbols from config
   │     ├─ Set poll_interval
   │
   ├─ client.connect()
   │  │
   │  └─ Establish gRPC channel (TCP or UDS)
   │
   └─ client.stream_headlines()
      │
      ├─ Call stub.IngestHeadlines(generator)
      │
      └─ For each iteration:
         │
         ├─ _headline_batch_generator()
         │  │
         │  ├─ For each symbol (AAPL, MSFT, ...):
         │  │  │
         │  │  ├─ Call finnhub_client.company_news()
         │  │  ├─ Extract headlines
         │  │  ├─ Deduplicate
         │  │  └─ Build HeadlineRequest protos
         │  │
         │  ├─ Yield HeadlineBatch
         │  │
         │  └─ sleep(2)
         │
         └─ [repeat]
```

## Memory Efficiency

The generator pattern keeps memory usage minimal:

```
At any point in time, only these are in memory:

┌────────────────────────────────────────┐
│ Per-Symbol Tracking (set)              │
│ - Last 100 seen headlines per symbol   │  ~25 KB per symbol
│ - Tuple of (text, timestamp)           │
└────────────────────────────────────────┘
         ↓
┌────────────────────────────────────────┐
│ Current Batch (ephemeral)              │
│ - ~5-15 headlines per poll             │  ~50-100 KB per batch
│ - Only exists briefly before yield     │
└────────────────────────────────────────┘
         ↓
┌────────────────────────────────────────┐
│ Total: ~75-150 KB at any moment        │  (2+ symbols)
└────────────────────────────────────────┘

NOT stored: entire session's headlines (would be 100s of MB)
```

## Configuration Flexibility

The client supports two deployment modes via YAML:

### Local Development (UDS)
```yaml
server:
  mode: uds
  uds_path: /tmp/inference.sock
```
- Same machine communication
- Fastest: ~10-20 μs latency
- Shares memory via kernel

### Docker / Remote (TCP)
```yaml
server:
  mode: tcp
  host: inference-service  # Docker DNS
  port: 50051
```
- Container-to-container communication
- Standard: ~50-100 μs latency
- Full network stack

## Deduplication Strategy

```
Poll 1 (t=0s):
  FinnHub returns: [Headline A, B, C]
  → all_headlines = {A, B, C}
  → Yield batch

Poll 2 (t=2s):
  FinnHub returns: [Headline A, B, D, E]
  → Filter: A and B already seen
  → all_headlines = {D, E}
  → Yield batch

Poll 3 (t=4s):
  FinnHub returns: [Headline F, G]
  → all_headlines = {F, G}
  → Yield batch

Memory tracking per symbol:
  last_headlines[symbol] = {A, B, C, D, E, F, G}
  (limited to 100 most recent)
```

This ensures:
- No duplicate headlines sent to server
- Memory usage stays bounded
- Natural API call batching preserved

## Future Scaling

If you need to scale beyond single-threaded:

**Option 1: Multiple Symbols (Current)**
- Add more symbols to config
- Still single-threaded, sequential API calls
- ~20ms per symbol = feasible for 10-20 symbols

**Option 2: Async I/O (if needed)**
```python
# Would require:
# - Use aiohttp instead of finnhub library
# - Make calls concurrently
# - Still one thread, better CPU usage during I/O wait
```

**Option 3: Multiple Instances**
```bash
# Run separate client for different symbol groups
docker run -e SYMBOLS="AAPL,MSFT" ...
docker run -e SYMBOLS="GOOGL,AMZN" ...
# Each streams to same server via gRPC
```

## Summary

| Aspect | Design |
|--------|--------|
| **Threading** | Single thread (async I/O handled by OS/gRPC) |
| **Concurrency** | Sequential API calls, parallel network I/O |
| **Memory** | ~100-200 KB (generator pattern) |
| **Latency** | 2-second poll interval |
| **Throughput** | ~1800 batches/hour (~3-5 headlines/batch) |
| **Reliability** | Deduplication prevents duplicate processing |
