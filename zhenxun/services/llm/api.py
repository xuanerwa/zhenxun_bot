"""
LLM 服务的高级 API 接口
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from nonebot_plugin_alconna.uniseg import UniMessage

from zhenxun.services.log import logger

from .config import CommonOverrides, LLMGenerationConfig
from .config.providers import get_ai_config
from .manager import get_global_default_model_name, get_model_instance
from .types import (
    EmbeddingTaskType,
    LLMContentPart,
    LLMErrorCode,
    LLMException,
    LLMMessage,
    LLMResponse,
    LLMTool,
    ModelName,
)
from .utils import create_multimodal_message, unimsg_to_llm_parts


class TaskType(Enum):
    """任务类型枚举"""

    CHAT = "chat"
    CODE = "code"
    SEARCH = "search"
    ANALYSIS = "analysis"
    GENERATION = "generation"
    MULTIMODAL = "multimodal"


@dataclass
class AIConfig:
    """AI配置类 - 简化版本"""

    model: ModelName = None
    default_embedding_model: ModelName = None
    temperature: float | None = None
    max_tokens: int | None = None
    enable_cache: bool = False
    enable_code: bool = False
    enable_search: bool = False
    timeout: int | None = None

    enable_gemini_json_mode: bool = False
    enable_gemini_thinking: bool = False
    enable_gemini_safe_mode: bool = False
    enable_gemini_multimodal: bool = False
    enable_gemini_grounding: bool = False

    def __post_init__(self):
        """初始化后从配置中读取默认值"""
        ai_config = get_ai_config()
        if self.model is None:
            self.model = ai_config.get("default_model_name")
        if self.timeout is None:
            self.timeout = ai_config.get("timeout", 180)


class AI:
    """统一的AI服务类 - 平衡设计版本

    提供三层API：
    1. 简单方法：ai.chat(), ai.code(), ai.search()
    2. 标准方法：ai.analyze() 支持复杂参数
    3. 高级方法：通过get_model_instance()直接访问
    """

    def __init__(
        self, config: AIConfig | None = None, history: list[LLMMessage] | None = None
    ):
        """
        初始化AI服务

        Args:
            config: AI 配置.
            history: 可选的初始对话历史.
        """
        self.config = config or AIConfig()
        self.history = history or []

    def clear_history(self):
        """清空当前会话的历史记录"""
        self.history = []
        logger.info("AI session history cleared.")

    async def chat(
        self,
        message: str | LLMMessage | list[LLMContentPart],
        *,
        model: ModelName = None,
        **kwargs: Any,
    ) -> str:
        """
        进行一次聊天对话。
        此方法会自动使用和更新会话内的历史记录。
        """
        current_message: LLMMessage
        if isinstance(message, str):
            current_message = LLMMessage.user(message)
        elif isinstance(message, list) and all(
            isinstance(part, LLMContentPart) for part in message
        ):
            current_message = LLMMessage.user(message)
        elif isinstance(message, LLMMessage):
            current_message = message
        else:
            raise LLMException(
                f"AI.chat 不支持的消息类型: {type(message)}. "
                "请使用 str, LLMMessage, 或 list[LLMContentPart]. "
                "对于更复杂的多模态输入或文件路径，请使用 AI.analyze().",
                code=LLMErrorCode.API_REQUEST_FAILED,
            )

        final_messages = [*self.history, current_message]

        response = await self._execute_generation(
            final_messages, model, "聊天失败", kwargs
        )

        self.history.append(current_message)
        self.history.append(LLMMessage.assistant_text_response(response.text))

        return response.text

    async def code(
        self,
        prompt: str,
        *,
        model: ModelName = None,
        timeout: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """代码执行"""
        resolved_model = model or self.config.model or "Gemini/gemini-2.0-flash"

        config = CommonOverrides.gemini_code_execution()
        if timeout:
            config.custom_params = config.custom_params or {}
            config.custom_params["code_execution_timeout"] = timeout

        messages = [LLMMessage.user(prompt)]

        response = await self._execute_generation(
            messages, resolved_model, "代码执行失败", kwargs, base_config=config
        )

        return {
            "text": response.text,
            "code_executions": response.code_executions or [],
            "success": True,
        }

    async def search(
        self,
        query: str | UniMessage,
        *,
        model: ModelName = None,
        instruction: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """信息搜索 - 支持多模态输入"""
        resolved_model = model or self.config.model or "Gemini/gemini-2.0-flash"
        config = CommonOverrides.gemini_grounding()

        if isinstance(query, str):
            messages = [LLMMessage.user(query)]
        elif isinstance(query, UniMessage):
            content_parts = await unimsg_to_llm_parts(query)

            final_messages: list[LLMMessage] = []
            if instruction:
                final_messages.append(LLMMessage.system(instruction))

            if not content_parts:
                if instruction:
                    final_messages.append(LLMMessage.user(instruction))
                else:
                    raise LLMException(
                        "搜索内容为空或无法处理。", code=LLMErrorCode.API_REQUEST_FAILED
                    )
            else:
                final_messages.append(LLMMessage.user(content_parts))

            messages = final_messages
        else:
            raise LLMException(
                f"不支持的搜索输入类型: {type(query)}. 请使用 str 或 UniMessage.",
                code=LLMErrorCode.API_REQUEST_FAILED,
            )

        response = await self._execute_generation(
            messages, resolved_model, "信息搜索失败", kwargs, base_config=config
        )

        result = {
            "text": response.text,
            "sources": [],
            "queries": [],
            "success": True,
        }

        if response.grounding_metadata:
            result["sources"] = response.grounding_metadata.grounding_attributions or []
            result["queries"] = response.grounding_metadata.web_search_queries or []

        return result

    async def analyze(
        self,
        message: UniMessage,
        *,
        instruction: str = "",
        model: ModelName = None,
        tools: list[dict[str, Any]] | None = None,
        tool_config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str | LLMResponse:
        """
        内容分析 - 接收 UniMessage 物件进行多模态分析和工具呼叫。
        这是处理复杂互动的主要方法。
        """
        content_parts = await unimsg_to_llm_parts(message)

        final_messages: list[LLMMessage] = []
        if instruction:
            final_messages.append(LLMMessage.system(instruction))

        if not content_parts:
            if instruction:
                final_messages.append(LLMMessage.user(instruction))
            else:
                raise LLMException(
                    "分析内容为空或无法处理。", code=LLMErrorCode.API_REQUEST_FAILED
                )
        else:
            final_messages.append(LLMMessage.user(content_parts))

        llm_tools = None
        if tools:
            llm_tools = []
            for tool_dict in tools:
                if isinstance(tool_dict, dict):
                    if "name" in tool_dict and "description" in tool_dict:
                        llm_tool = LLMTool(
                            type="function",
                            function={
                                "name": tool_dict["name"],
                                "description": tool_dict["description"],
                                "parameters": tool_dict.get("parameters", {}),
                            },
                        )
                        llm_tools.append(llm_tool)
                    else:
                        llm_tools.append(LLMTool(**tool_dict))
                else:
                    llm_tools.append(tool_dict)

        tool_choice = None
        if tool_config:
            mode = tool_config.get("mode", "auto")
            if mode == "auto":
                tool_choice = "auto"
            elif mode == "any":
                tool_choice = "any"
            elif mode == "none":
                tool_choice = "none"

        response = await self._execute_generation(
            final_messages,
            model,
            "内容分析失败",
            kwargs,
            llm_tools=llm_tools,
            tool_choice=tool_choice,
        )

        if response.tool_calls:
            return response
        return response.text

    async def _execute_generation(
        self,
        messages: list[LLMMessage],
        model_name: ModelName,
        error_message: str,
        config_overrides: dict[str, Any],
        llm_tools: list[LLMTool] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        base_config: LLMGenerationConfig | None = None,
    ) -> LLMResponse:
        """通用的生成执行方法，封装重复的模型获取、配置合并和异常处理逻辑"""
        try:
            resolved_model_name = self._resolve_model_name(
                model_name or self.config.model
            )
            final_config_dict = self._merge_config(
                config_overrides, base_config=base_config
            )

            async with await get_model_instance(
                resolved_model_name, override_config=final_config_dict
            ) as model_instance:
                return await model_instance.generate_response(
                    messages, tools=llm_tools, tool_choice=tool_choice
                )
        except LLMException:
            raise
        except Exception as e:
            logger.error(f"{error_message}: {e}", e=e)
            raise LLMException(f"{error_message}: {e}", cause=e)

    def _resolve_model_name(self, model_name: ModelName) -> str:
        """解析模型名称"""
        if model_name:
            return model_name

        default_model = get_global_default_model_name()
        if default_model:
            return default_model

        raise LLMException(
            "未指定模型名称且未设置全局默认模型",
            code=LLMErrorCode.MODEL_NOT_FOUND,
        )

    def _merge_config(
        self,
        user_config: dict[str, Any],
        base_config: LLMGenerationConfig | None = None,
    ) -> dict[str, Any]:
        """合并配置"""
        final_config = {}
        if base_config:
            final_config.update(base_config.to_dict())

        if self.config.temperature is not None:
            final_config["temperature"] = self.config.temperature
        if self.config.max_tokens is not None:
            final_config["max_tokens"] = self.config.max_tokens

        if self.config.enable_cache:
            final_config["enable_caching"] = True
        if self.config.enable_code:
            final_config["enable_code_execution"] = True
        if self.config.enable_search:
            final_config["enable_grounding"] = True

        if self.config.enable_gemini_json_mode:
            final_config["response_mime_type"] = "application/json"
        if self.config.enable_gemini_thinking:
            final_config["thinking_budget"] = 0.8
        if self.config.enable_gemini_safe_mode:
            final_config["safety_settings"] = (
                CommonOverrides.gemini_safe().safety_settings
            )
        if self.config.enable_gemini_multimodal:
            final_config.update(CommonOverrides.gemini_multimodal().to_dict())
        if self.config.enable_gemini_grounding:
            final_config["enable_grounding"] = True

        final_config.update(user_config)

        return final_config

    async def embed(
        self,
        texts: list[str] | str,
        *,
        model: ModelName = None,
        task_type: EmbeddingTaskType | str = EmbeddingTaskType.RETRIEVAL_DOCUMENT,
        **kwargs: Any,
    ) -> list[list[float]]:
        """生成文本嵌入向量"""
        if isinstance(texts, str):
            texts = [texts]
        if not texts:
            return []

        try:
            resolved_model_str = (
                model or self.config.default_embedding_model or self.config.model
            )
            if not resolved_model_str:
                raise LLMException(
                    "使用 embed 功能时必须指定嵌入模型名称，"
                    "或在 AIConfig 中配置 default_embedding_model。",
                    code=LLMErrorCode.MODEL_NOT_FOUND,
                )
            resolved_model_str = self._resolve_model_name(resolved_model_str)

            async with await get_model_instance(
                resolved_model_str,
                override_config=None,
            ) as embedding_model_instance:
                return await embedding_model_instance.generate_embeddings(
                    texts, task_type=task_type, **kwargs
                )
        except LLMException:
            raise
        except Exception as e:
            logger.error(f"文本嵌入失败: {e}", e=e)
            raise LLMException(
                f"文本嵌入失败: {e}", code=LLMErrorCode.EMBEDDING_FAILED, cause=e
            )


async def chat(
    message: str | LLMMessage | list[LLMContentPart],
    *,
    model: ModelName = None,
    **kwargs: Any,
) -> str:
    """聊天对话便捷函数"""
    ai = AI()
    return await ai.chat(message, model=model, **kwargs)


async def code(
    prompt: str,
    *,
    model: ModelName = None,
    timeout: int | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """代码执行便捷函数"""
    ai = AI()
    return await ai.code(prompt, model=model, timeout=timeout, **kwargs)


async def search(
    query: str | UniMessage,
    *,
    model: ModelName = None,
    instruction: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """信息搜索便捷函数"""
    ai = AI()
    return await ai.search(query, model=model, instruction=instruction, **kwargs)


async def analyze(
    message: UniMessage,
    *,
    instruction: str = "",
    model: ModelName = None,
    tools: list[dict[str, Any]] | None = None,
    tool_config: dict[str, Any] | None = None,
    **kwargs: Any,
) -> str | LLMResponse:
    """内容分析便捷函数"""
    ai = AI()
    return await ai.analyze(
        message,
        instruction=instruction,
        model=model,
        tools=tools,
        tool_config=tool_config,
        **kwargs,
    )


async def analyze_with_images(
    text: str,
    images: list[str | Path | bytes] | str | Path | bytes,
    *,
    instruction: str = "",
    model: ModelName = None,
    **kwargs: Any,
) -> str | LLMResponse:
    """图片分析便捷函数"""
    message = create_multimodal_message(text=text, images=images)
    return await analyze(message, instruction=instruction, model=model, **kwargs)


async def analyze_multimodal(
    text: str | None = None,
    images: list[str | Path | bytes] | str | Path | bytes | None = None,
    videos: list[str | Path | bytes] | str | Path | bytes | None = None,
    audios: list[str | Path | bytes] | str | Path | bytes | None = None,
    *,
    instruction: str = "",
    model: ModelName = None,
    **kwargs: Any,
) -> str | LLMResponse:
    """多模态分析便捷函数"""
    message = create_multimodal_message(
        text=text, images=images, videos=videos, audios=audios
    )
    return await analyze(message, instruction=instruction, model=model, **kwargs)


async def search_multimodal(
    text: str | None = None,
    images: list[str | Path | bytes] | str | Path | bytes | None = None,
    videos: list[str | Path | bytes] | str | Path | bytes | None = None,
    audios: list[str | Path | bytes] | str | Path | bytes | None = None,
    *,
    instruction: str = "",
    model: ModelName = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """多模态搜索便捷函数"""
    message = create_multimodal_message(
        text=text, images=images, videos=videos, audios=audios
    )
    ai = AI()
    return await ai.search(message, model=model, instruction=instruction, **kwargs)


async def embed(
    texts: list[str] | str,
    *,
    model: ModelName = None,
    task_type: EmbeddingTaskType | str = EmbeddingTaskType.RETRIEVAL_DOCUMENT,
    **kwargs: Any,
) -> list[list[float]]:
    """文本嵌入便捷函数"""
    ai = AI()
    return await ai.embed(texts, model=model, task_type=task_type, **kwargs)
