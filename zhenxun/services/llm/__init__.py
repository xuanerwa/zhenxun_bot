"""
LLM 服务模块 - 公共 API 入口

提供统一的 AI 服务调用接口、核心类型定义和模型管理功能。
"""

from .api import (
    chat,
    code,
    create_image,
    embed,
    embed_documents,
    embed_query,
    generate,
    generate_structured,
    search,
)
from .config import (
    CommonOverrides,
    GenConfigBuilder,
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
from .memory import (
    AIConfig,
    BaseMemory,
    MemoryProcessor,
    set_default_memory_backend,
)
from .session import AI
from .tools import RunContext, ToolInvoker, function_tool, tool_provider_manager
from .types import (
    EmbeddingTaskType,
    LLMContentPart,
    LLMErrorCode,
    LLMException,
    LLMMessage,
    LLMResponse,
    ModelDetail,
    ModelInfo,
    ModelProvider,
    ResponseFormat,
    TaskType,
    ToolCategory,
    ToolMetadata,
    UsageInfo,
)
from .types.models import (
    GeminiCodeExecution,
    GeminiGoogleSearch,
    GeminiUrlContext,
)
from .utils import create_multimodal_message, message_to_unimessage, unimsg_to_llm_parts

__all__ = [
    "AI",
    "AIConfig",
    "BaseMemory",
    "CommonOverrides",
    "EmbeddingTaskType",
    "GeminiCodeExecution",
    "GeminiGoogleSearch",
    "GeminiUrlContext",
    "GenConfigBuilder",
    "LLMContentPart",
    "LLMErrorCode",
    "LLMException",
    "LLMGenerationConfig",
    "LLMMessage",
    "LLMResponse",
    "MemoryProcessor",
    "ModelDetail",
    "ModelInfo",
    "ModelName",
    "ModelProvider",
    "ResponseFormat",
    "RunContext",
    "TaskType",
    "ToolCategory",
    "ToolInvoker",
    "ToolMetadata",
    "UsageInfo",
    "chat",
    "clear_model_cache",
    "code",
    "create_image",
    "create_multimodal_message",
    "embed",
    "embed_documents",
    "embed_query",
    "function_tool",
    "generate",
    "generate_structured",
    "get_cache_stats",
    "get_global_default_model_name",
    "get_model_instance",
    "list_available_models",
    "list_embedding_models",
    "list_model_identifiers",
    "message_to_unimessage",
    "register_llm_configs",
    "search",
    "set_default_memory_backend",
    "set_global_default_model_name",
    "tool_provider_manager",
    "unimsg_to_llm_parts",
]
