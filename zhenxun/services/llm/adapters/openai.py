"""
OpenAI API 适配器

支持 OpenAI、DeepSeek 和其他 OpenAI 兼容的 API 服务。
"""

from typing import TYPE_CHECKING

from .base import OpenAICompatAdapter, RequestData

if TYPE_CHECKING:
    from ..service import LLMModel


class OpenAIAdapter(OpenAICompatAdapter):
    """OpenAI兼容API适配器"""

    @property
    def api_type(self) -> str:
        return "openai"

    @property
    def supported_api_types(self) -> list[str]:
        return ["openai", "deepseek", "general_openai_compat"]

    def get_chat_endpoint(self) -> str:
        """返回聊天完成端点"""
        return "/v1/chat/completions"

    def get_embedding_endpoint(self) -> str:
        """返回嵌入端点"""
        return "/v1/embeddings"

    def prepare_simple_request(
        self,
        model: "LLMModel",
        api_key: str,
        prompt: str,
        history: list[dict[str, str]] | None = None,
    ) -> RequestData:
        """准备简单文本生成请求 - OpenAI优化实现"""
        url = self.get_api_url(model, self.get_chat_endpoint())
        headers = self.get_base_headers(api_key)

        messages = []
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})

        body = {
            "model": model.model_name,
            "messages": messages,
        }

        body = self.apply_config_override(model, body)

        return RequestData(url=url, headers=headers, body=body)
