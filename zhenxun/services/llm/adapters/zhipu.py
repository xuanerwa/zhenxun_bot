"""
智谱 AI API 适配器

支持智谱 AI 的 GLM 系列模型，使用 OpenAI 兼容的接口格式。
"""

from typing import TYPE_CHECKING

from .base import OpenAICompatAdapter, RequestData

if TYPE_CHECKING:
    from ..service import LLMModel


class ZhipuAdapter(OpenAICompatAdapter):
    """智谱AI适配器 - 使用智谱AI专用的OpenAI兼容接口"""

    @property
    def api_type(self) -> str:
        return "zhipu"

    @property
    def supported_api_types(self) -> list[str]:
        return ["zhipu"]

    def get_chat_endpoint(self) -> str:
        """返回智谱AI聊天完成端点"""
        return "/api/paas/v4/chat/completions"

    def get_embedding_endpoint(self) -> str:
        """返回智谱AI嵌入端点"""
        return "/v4/embeddings"

    def prepare_simple_request(
        self,
        model: "LLMModel",
        api_key: str,
        prompt: str,
        history: list[dict[str, str]] | None = None,
    ) -> RequestData:
        """准备简单文本生成请求 - 智谱AI优化实现"""
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
