"""
LLM 适配器工厂类
"""

import fnmatch
from typing import TYPE_CHECKING, Any, ClassVar

from ..types.exceptions import LLMErrorCode, LLMException
from ..types.models import ToolChoice
from .base import BaseAdapter, RequestData, ResponseData

if TYPE_CHECKING:
    from ..config.generation import LLMEmbeddingConfig, LLMGenerationConfig
    from ..service import LLMModel
    from ..types import LLMMessage


class LLMAdapterFactory:
    """LLM适配器工厂类"""

    _adapters: ClassVar[dict[str, BaseAdapter]] = {}
    _api_type_mapping: ClassVar[dict[str, str]] = {}

    @classmethod
    def initialize(cls) -> None:
        """初始化默认适配器"""
        if cls._adapters:
            return

        from .gemini import GeminiAdapter
        from .openai import DeepSeekAdapter, OpenAIAdapter, OpenAIImageAdapter

        cls.register_adapter(OpenAIAdapter())
        cls.register_adapter(DeepSeekAdapter())
        cls.register_adapter(GeminiAdapter())
        cls.register_adapter(SmartAdapter())
        cls.register_adapter(OpenAIImageAdapter())

    @classmethod
    def register_adapter(cls, adapter: BaseAdapter) -> None:
        """注册适配器"""
        adapter_key = adapter.api_type
        cls._adapters[adapter_key] = adapter

        for api_type in adapter.supported_api_types:
            cls._api_type_mapping[api_type] = adapter_key

    @classmethod
    def get_adapter(cls, api_type: str) -> BaseAdapter:
        """获取适配器"""
        cls.initialize()

        adapter_key = cls._api_type_mapping.get(api_type)
        if not adapter_key:
            raise LLMException(
                f"不支持的API类型: {api_type}",
                code=LLMErrorCode.UNKNOWN_API_TYPE,
                details={
                    "api_type": api_type,
                    "supported_types": list(cls._api_type_mapping.keys()),
                },
            )

        return cls._adapters[adapter_key]

    @classmethod
    def list_supported_types(cls) -> list[str]:
        """列出所有支持的API类型"""
        cls.initialize()
        return list(cls._api_type_mapping.keys())

    @classmethod
    def list_adapters(cls) -> dict[str, BaseAdapter]:
        """列出所有注册的适配器"""
        cls.initialize()
        return cls._adapters.copy()


def get_adapter_for_api_type(api_type: str) -> BaseAdapter:
    """获取指定API类型的适配器"""
    return LLMAdapterFactory.get_adapter(api_type)


def register_adapter(adapter: BaseAdapter) -> None:
    """注册新的适配器"""
    LLMAdapterFactory.register_adapter(adapter)


class SmartAdapter(BaseAdapter):
    """
    智能路由适配器。
    本身不处理序列化，而是根据规则委托给 OpenAIAdapter 或 GeminiAdapter。
    """

    @property
    def log_sanitization_context(self) -> str:
        return "openai_request"

    _ROUTING_RULES: ClassVar[list[tuple[str, str]]] = [
        ("*nano-banana*", "gemini"),
        ("*gemini*", "gemini"),
    ]
    _DEFAULT_API_TYPE: ClassVar[str] = "openai"

    def __init__(self):
        self._adapter_cache: dict[str, BaseAdapter] = {}

    @property
    def api_type(self) -> str:
        return "smart"

    @property
    def supported_api_types(self) -> list[str]:
        return ["smart"]

    def _get_delegate_adapter(self, model: "LLMModel") -> BaseAdapter:
        """
        核心路由逻辑：决定使用哪个适配器 (带缓存)
        """
        if model.model_detail.api_type:
            return get_adapter_for_api_type(model.model_detail.api_type)

        model_name = model.model_name
        if model_name in self._adapter_cache:
            return self._adapter_cache[model_name]

        target_api_type = self._DEFAULT_API_TYPE
        model_name_lower = model_name.lower()

        for pattern, api_type in self._ROUTING_RULES:
            if fnmatch.fnmatch(model_name_lower, pattern):
                target_api_type = api_type
                break

        adapter = get_adapter_for_api_type(target_api_type)
        self._adapter_cache[model_name] = adapter
        return adapter

    async def prepare_advanced_request(
        self,
        model: "LLMModel",
        api_key: str,
        messages: list["LLMMessage"],
        config: "LLMGenerationConfig | None" = None,
        tools: list[Any] | None = None,
        tool_choice: "str | dict[str, Any] | ToolChoice | None" = None,
    ) -> RequestData:
        adapter = self._get_delegate_adapter(model)
        return await adapter.prepare_advanced_request(
            model, api_key, messages, config, tools, tool_choice
        )

    def parse_response(
        self,
        model: "LLMModel",
        response_json: dict[str, Any],
        is_advanced: bool = False,
    ) -> ResponseData:
        adapter = self._get_delegate_adapter(model)
        return adapter.parse_response(model, response_json, is_advanced)

    def prepare_embedding_request(
        self,
        model: "LLMModel",
        api_key: str,
        texts: list[str],
        config: "LLMEmbeddingConfig",
    ) -> RequestData:
        adapter = self._get_delegate_adapter(model)
        return adapter.prepare_embedding_request(model, api_key, texts, config)

    def parse_embedding_response(
        self, response_json: dict[str, Any]
    ) -> list[list[float]]:
        return get_adapter_for_api_type("openai").parse_embedding_response(
            response_json
        )

    def convert_generation_config(
        self, config: "LLMGenerationConfig", model: "LLMModel"
    ) -> dict[str, Any]:
        adapter = self._get_delegate_adapter(model)
        return adapter.convert_generation_config(config, model)
