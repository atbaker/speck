# RunPod notes

RunPod vLLM (single A40):
```
--host 0.0.0.0 --port 8000 --model hugging-quants/Meta-Llama-3.1-70B-Instruct-AWQ-INT4 --enforce-eager --gpu-memory-utilization 0.99 --tensor-parallel-size 1 --max-model-len 10240 --quantization awq --enable-prefix-caching
```

RunPod vLLM (2x A40):
```
--host 0.0.0.0 --port 8000 --model hugging-quants/Meta-Llama-3.1-70B-Instruct-AWQ-INT4 --enforce-eager --gpu-memory-utilization 0.99 --tensor-parallel-size 2 --max-model-len 32768 --quantization awq --enable-prefix-caching
```
