# stock-news-analyzer
Project to automate news analysis for stocks and experiment with inference on a custom built server with a basic GPU. This should be used in conjunction with the valuation project.


# Architecture Brainstorm

## Server Information

### Server 1 - Windows Box with no GPU

Server 1 is an old windows 10 box  [windows box](https://github.com/Ashwin1934/PortfolioAnalysisMonorepo?tab=readme-ov-file#custom-server-construction) that I built. It has a standard old Intel chip with 4 hyper threaded cores, 8 logical processors, and I believe 16GB of RAM. I initially wanted to run kafka on it, but pivoted from that and now run a couple containers including a postgres db with stocks and valuations, a fast api server that computes valuations and interfaces with the db, a UI to display and fetch valuations, and an apache web server that makes the web app accessible from other computers on the local subnet.  

### Server 2 - Windows Box with AMD Radeon Pro WX 4100

Server 2 is in the process of being constructed. It will have Windows 11, an Intel Chip with similar specs to server 1, probably the same RAM, but it also has this AMD GPU. The idea here is to experiment with inference on this server via the GPU and potentially small agents later on. The limitations of the server and chips should allow for useful experiments. I plan to test quantized models, distilled models, experiment with CPU cores, and GPU "cores"... 
#### AMD Radeon Pro WX 4100 GPU Specs
- Dedicated GPU - separate card with its own hardware
- 4GB GDDR5 VRAM - dedicated fast memory. Nothing compared to Blackwell / 
- ~2,000 GFLOPS compute performance (roughly 5x faster)
- TDP (Thermal Design Power): ~50W
#### Pitfalls
- 4GB VRAM limits you to smaller models
- AMD GPUs have less mature AI software support than NVIDIA
- ROCm (AMD's CUDA equivalent) support is improving but still behind
#### Contextualization with Enterprise AI Chips
- Blackwell GPUs each have 192 GB of memory
- Nvidia GB200 Chips feature 1 Grace CPU and 2 Blackwell GPUs, they communicate via NvLInk instead of PCIE
- My box is miniscule in comparison, uses slower memory bus PCIE instead of NvLink, and has much less memory..

## Two Server Architecture vs One Server Architecture

### Two Servers

Given that the database of stocks exists on Server 1, it might make sense to set up the Ingestion Service on Server 1 as part of a docker-compose with the valuation web app. It would use gRPC to communicate with Server 2, which would host the inference service. This might be a pain to test everyday but would help integrate the valuation process with the news
analysis process. A limitation of this is that it would only fetch news for stocks in that db that I added myself, so it wouldn't conduct analysis on all or new stocks. 

### One Server

I could just run both the ingestion service and the inference service on Server 2. I was thinking they could communicate with "shmem" or shared memory, which I've seen used in a high performance financial time series db. I can still use gRPC and make it portable between the two designs. This will be easier to test as well on one server. Need to read up on this, its been a while since I've read about communication between processes using RAM vs GPU VRAM etc...

## Agent Implementation

The agent would run on Server 2 and use MCP servers of the valuation web app to supplement stock news analysis and make investment recommendations and summaries.
