import os
import logging
from typing import Any, Dict, Optional, Union, Tuple
from vllm import AsyncLLMEngine, AsyncEngineArgs, SamplingParams
from constants import sampling_param_types, DEFAULT_BATCH_SIZE, DEFAULT_MAX_CONCURRENCY
from transformers import AutoTokenizer

logging.basicConfig(level=logging.INFO)

 

class ServerlessConfig:
    def __init__(self):
        self._max_concurrency = int(os.environ.get('MAX_CONCURRENCY', DEFAULT_MAX_CONCURRENCY))
        self._default_batch_size = int(os.environ.get('DEFAULT_BATCH_SIZE', DEFAULT_BATCH_SIZE))

    @property
    def max_concurrency(self):
        return self._max_concurrency

    @property
    def default_batch_size(self):
        return self._default_batch_size

class EngineConfig:
    def __init__(self):
        self.model_name = os.getenv('MODEL_NAME', 'default_model')
        self.tokenizer = os.getenv('TOKENIZER', self.model_name)
        self.model_base_path = os.getenv('MODEL_BASE_PATH', "/runpod-volume/")
        self.num_gpu_shard = int(os.getenv('NUM_GPU_SHARD', 1))
        self.use_full_metrics = os.getenv('USE_FULL_METRICS', 'True') == 'True'
        self.quantization = os.getenv('QUANTIZATION', None)
        self.dtype = "float16"  #"auto" if self.quantization is None else "half"
        self.disable_log_stats = os.getenv('DISABLE_LOG_STATS', 'True') == 'True'
        self.gpu_memory_utilization = float(os.getenv('GPU_MEMORY_UTILIZATION', 0.98))
        os.makedirs(self.model_base_path, exist_ok=True)

class Tokenizer:
    def __init__(self, tokenizer_name: str):
        self.tokenizer = AutoTokenizer.from_pretrained(tokenizer_name)
    
    def apply_chat_template(self, input: Union[str, list[dict[str, str]]]) -> str:
        messages = input if isinstance(input, list) else [{"role": "user", "content": input}]
        return self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

def initialize_llm_engine() -> Tuple[AsyncLLMEngine, Tokenizer]:
    try:
        config = EngineConfig()
        engine_args = AsyncEngineArgs(
            model=config.model_name,
            download_dir=config.model_base_path,
            tokenizer=config.tokenizer,
            tensor_parallel_size=config.num_gpu_shard,
            dtype=config.dtype,
            disable_log_stats=config.disable_log_stats,
            quantization=config.quantization,
            gpu_memory_utilization=config.gpu_memory_utilization,
        )
        return AsyncLLMEngine.from_engine_args(engine_args), Tokenizer(config.tokenizer)
    except Exception as e:
        logging.error(f"Error initializing vLLM engine: {e}")
        raise
    

def validate_and_convert_sampling_params(params: Dict[str, Any]) -> Dict[str, Any]:
    validated_params = {}

    for key, value in params.items():
        expected_type = sampling_param_types.get(key)
        if value is None:
            validated_params[key] = None
            continue

        if expected_type is None:
            continue

        if not isinstance(expected_type, tuple):
            expected_type = (expected_type,)

        if any(isinstance(value, t) for t in expected_type):
            validated_params[key] = value
        else:
            try:
                casted_value = next(
                    t(value) for t in expected_type
                    if isinstance(value, t)
                )
                validated_params[key] = casted_value
            except (TypeError, ValueError, StopIteration):
                continue

    return SamplingParams(**validated_params)