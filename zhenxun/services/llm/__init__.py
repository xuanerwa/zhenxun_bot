"""
LLM 服务模块 - 公共 API 入口

提供统一的 AI 服务调用接口、核心类型定义和模型管理功能。
"""

from .api import (
    AI,
    AIConfig,
    TaskType,
    analyze,
    analyze_multimodal,
    analyze_with_images,
    chat,
    code,
    embed,
    search,
    search_multimodal,
)
from .config import (
    CommonOverrides,
    LLMGenerationConfig,
    register_llm_configs,
)

register_llm_configs()
from .api import ModelName
from .manager import (
    clear_model_cache,
    get_cache_stats,
    get_global_default_model_name,
    get_model_instance,
    list_available_models,
    list_embedding_models,
    list_model_identifiers,
    set_global_default_model_name,
)
from .types import (
    EmbeddingTaskType,
    LLMContentPart,
    LLMErrorCode,
    LLMException,
    LLMMessage,
    LLMResponse,
    LLMTool,
    ModelDetail,
    ModelInfo,
    ModelProvider,
    ResponseFormat,
    ToolCategory,
    ToolMetadata,
    UsageInfo,
)
from .utils import create_multimodal_message, unimsg_to_llm_parts

__all__ = [
    "AI",
    "AIConfig",
    "CommonOverrides",
    "EmbeddingTaskType",
    "LLMContentPart",
    "LLMErrorCode",
    "LLMException",
    "LLMGenerationConfig",
    "LLMMessage",
    "LLMResponse",
    "LLMTool",
    "ModelDetail",
    "ModelInfo",
    "ModelName",
    "ModelProvider",
    "ResponseFormat",
    "TaskType",
    "ToolCategory",
    "ToolMetadata",
    "UsageInfo",
    "analyze",
    "analyze_multimodal",
    "analyze_with_images",
    "chat",
    "clear_model_cache",
    "code",
    "create_multimodal_message",
    "embed",
    "get_cache_stats",
    "get_global_default_model_name",
    "get_model_instance",
    "list_available_models",
    "list_embedding_models",
    "list_model_identifiers",
    "register_llm_configs",
    "search",
    "search_multimodal",
    "set_global_default_model_name",
    "unimsg_to_llm_parts",
]
