from abc import ABC, abstractmethod
from typing import Any

from zhenxun.services.llm.adapters.base import ResponseData
from zhenxun.services.llm.config.generation import LLMGenerationConfig
from zhenxun.services.llm.types import LLMMessage
from zhenxun.services.llm.types.capabilities import ModelCapabilities
from zhenxun.services.llm.types.models import ModelDetail, ToolDefinition


class ConfigMapper(ABC):
    @abstractmethod
    def map_config(
        self,
        config: LLMGenerationConfig,
        model_detail: ModelDetail | None = None,
        capabilities: ModelCapabilities | None = None,
    ) -> dict[str, Any]:
        """将通用生成配置转换为特定 API 的参数字典"""
        ...


class MessageConverter(ABC):
    @abstractmethod
    def convert_messages(
        self, messages: list[LLMMessage]
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """将通用消息列表转换为特定 API 的消息格式"""
        ...


class ToolSerializer(ABC):
    @abstractmethod
    def serialize_tools(self, tools: list[ToolDefinition]) -> Any:
        """将通用工具定义转换为特定 API 的工具格式"""
        ...


class ResponseParser(ABC):
    @abstractmethod
    def parse(self, response_json: dict[str, Any]) -> ResponseData:
        """将特定 API 的响应解析为通用响应数据"""
        ...
