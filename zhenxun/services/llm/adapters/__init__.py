"""
LLM 适配器模块

提供不同LLM服务商的API适配器实现，统一接口调用方式。
"""

from .base import BaseAdapter, OpenAICompatAdapter, RequestData, ResponseData
from .factory import LLMAdapterFactory, get_adapter_for_api_type, register_adapter
from .gemini import GeminiAdapter
from .openai import DeepSeekAdapter, OpenAIAdapter, OpenAIImageAdapter

LLMAdapterFactory.initialize()

__all__ = [
    "BaseAdapter",
    "DeepSeekAdapter",
    "GeminiAdapter",
    "LLMAdapterFactory",
    "OpenAIAdapter",
    "OpenAICompatAdapter",
    "OpenAIImageAdapter",
    "RequestData",
    "ResponseData",
    "get_adapter_for_api_type",
    "register_adapter",
]
