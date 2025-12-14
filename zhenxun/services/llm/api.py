"""
LLM 服务的高级 API 接口 - 便捷函数入口 (无状态)
"""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar, overload

from nonebot_plugin_alconna.uniseg import UniMessage
from pydantic import BaseModel

from zhenxun.services.log import logger

from .config import CommonOverrides
from .config.generation import (
    GenConfigBuilder,
    LLMEmbeddingConfig,
    LLMGenerationConfig,
    OutputConfig,
)
from .manager import get_model_instance
from .session import AI
from .types import (
    LLMContentPart,
    LLMErrorCode,
    LLMException,
    LLMMessage,
    LLMResponse,
    ModelName,
    ToolChoice,
)
from .types.exceptions import get_user_friendly_error_message
from .types.models import GeminiGoogleSearch
from .utils import create_multimodal_message

T = TypeVar("T", bound=BaseModel)


async def chat(
    message: str | UniMessage | LLMMessage | list[LLMContentPart],
    *,
    model: ModelName = None,
    instruction: str | None = None,
    tools: list[Any] | None = None,
    tool_choice: str | dict[str, Any] | ToolChoice | None = None,
    config: LLMGenerationConfig | GenConfigBuilder | None = None,
    timeout: float | None = None,
) -> LLMResponse:
    """
    无状态的聊天对话便捷函数，通过临时的AI会话实例与LLM模型交互。

    参数:
        message: 用户输入的消息内容，支持多种格式。
        model: 要使用的模型名称，如果为None则使用默认模型。
        instruction: 系统指令，用于指导AI的行为和回复风格。
        tools: 可用的工具列表，支持字典配置或字符串标识符。
        tool_choice: 工具选择策略，控制AI如何选择和使用工具。
        config: (可选) 生成配置对象，将与默认配置合并后传递。
        timeout: (可选) HTTP 请求超时时间（秒）。

    返回:
        LLMResponse: 包含AI回复内容、使用信息和工具调用等的完整响应对象。
    """
    try:
        ai_session = AI()

        return await ai_session.chat(
            message,
            model=model,
            instruction=instruction,
            tools=tools,
            tool_choice=tool_choice,
            config=config,
            timeout=timeout,
        )
    except LLMException:
        raise
    except Exception as e:
        friendly_msg = get_user_friendly_error_message(e)
        logger.error(f"执行 chat 函数失败: {e} | 建议: {friendly_msg}", e=e)
        raise LLMException(f"聊天执行失败: {friendly_msg}", cause=e)


async def code(
    prompt: str,
    *,
    model: ModelName = None,
    timeout: int | None = None,
) -> LLMResponse:
    """
    无状态的代码执行便捷函数，支持在沙箱环境中执行代码。

    参数:
        prompt: 代码执行的提示词，描述要执行的代码任务。
        model: 要使用的模型名称，默认使用Gemini/gemini-2.0-flash。
        timeout: 代码执行超时时间（秒），防止长时间运行的代码阻塞。

    返回:
        LLMResponse: 包含代码执行结果的完整响应对象。
    """
    resolved_model = model

    config = CommonOverrides.gemini_code_execution()
    if timeout:
        config.custom_params = config.custom_params or {}
        config.custom_params["code_execution_timeout"] = timeout

    return await chat(prompt, model=resolved_model, config=config)


async def embed(
    texts: list[str] | str,
    *,
    model: ModelName = None,
    config: LLMEmbeddingConfig | None = None,
) -> list[list[float]]:
    """
    无状态的文本嵌入便捷函数，将文本转换为向量表示。

    参数:
        texts: 要生成嵌入的文本内容，支持单个字符串或字符串列表。
        model: 要使用的嵌入模型名称，如果为None则使用默认模型。
        config: 嵌入配置对象。

    返回:
        list[list[float]]: 文本对应的嵌入向量列表，每个向量为浮点数列表。
    """
    if isinstance(texts, str):
        texts = [texts]
    if not texts:
        return []

    final_config = config or LLMEmbeddingConfig()

    try:
        async with await get_model_instance(model) as model_instance:
            return await model_instance.generate_embeddings(texts, config=final_config)
    except LLMException:
        raise
    except Exception as e:
        friendly_msg = get_user_friendly_error_message(e)
        logger.error(f"文本嵌入失败: {e} | 建议: {friendly_msg}", e=e)
        raise LLMException(
            f"文本嵌入失败: {friendly_msg}",
            code=LLMErrorCode.EMBEDDING_FAILED,
            cause=e,
        )


async def embed_query(
    text: str,
    *,
    model: ModelName = None,
    dimensions: int | None = None,
) -> list[float]:
    """
    语义化便捷 API：为检索查询生成嵌入。
    """
    config = LLMEmbeddingConfig(
        task_type="RETRIEVAL_QUERY",
        output_dimensionality=dimensions,
    )
    vectors = await embed([text], model=model, config=config)
    return vectors[0] if vectors else []


async def embed_documents(
    texts: list[str],
    *,
    model: ModelName = None,
    dimensions: int | None = None,
    title: str | None = None,
) -> list[list[float]]:
    """
    语义化便捷 API：为文档集合生成嵌入。
    """
    config = LLMEmbeddingConfig(
        task_type="RETRIEVAL_DOCUMENT",
        output_dimensionality=dimensions,
        title=title,
    )
    return await embed(texts, model=model, config=config)


async def generate_structured(
    message: str | UniMessage | LLMMessage | list[LLMContentPart],
    response_model: type[T],
    *,
    model: ModelName = None,
    tools: list[Any] | None = None,
    tool_choice: str | dict[str, Any] | ToolChoice | None = None,
    max_validation_retries: int | None = None,
    validation_callback: Callable[[T], Any | Awaitable[Any]] | None = None,
    error_prompt_template: str | None = None,
    auto_thinking: bool = False,
    instruction: str | None = None,
    timeout: float | None = None,
) -> T:
    """
    无状态地生成结构化响应，并自动解析为指定的Pydantic模型。

    参数:
        message: 用户输入的消息内容，支持多种格式。
        response_model: 用于解析和验证响应的Pydantic模型类。
        max_validation_retries: 校验失败时的最大重试次数，默认为 None (使用全局配置)。
        validation_callback: 自定义校验回调函数，抛出异常视为校验失败。
        error_prompt_template: 自定义错误反馈提示词模板。
        auto_thinking: 是否自动开启思维链 (CoT) 包装。适用于不支持原生思考的模型
        model: 要使用的模型名称，如果为None则使用默认模型。
        instruction: 系统指令，用于指导AI生成符合要求的结构化输出。
        timeout: HTTP 请求超时时间（秒）。

    返回:
        T: 解析后的Pydantic模型实例，类型为response_model指定的类型。
    """
    try:
        ai_session = AI()

        return await ai_session.generate_structured(
            message,
            response_model,
            model=model,
            tools=tools,
            tool_choice=tool_choice,
            max_validation_retries=max_validation_retries,
            validation_callback=validation_callback,
            error_prompt_template=error_prompt_template,
            auto_thinking=auto_thinking,
            instruction=instruction,
            timeout=timeout,
        )
    except LLMException:
        raise
    except Exception as e:
        friendly_msg = get_user_friendly_error_message(e)
        logger.error(f"生成结构化响应失败: {e} | 建议: {friendly_msg}", e=e)
        raise LLMException(f"生成结构化响应失败: {friendly_msg}", cause=e)


async def generate(
    messages: list[LLMMessage],
    *,
    model: ModelName = None,
    tools: list[Any] | None = None,
    tool_choice: str | dict[str, Any] | ToolChoice | None = None,
    config: LLMGenerationConfig | GenConfigBuilder | None = None,
) -> LLMResponse:
    """
    根据完整的消息列表生成一次性响应，这是一个无状态的底层函数。

    参数:
        messages: 完整的消息历史列表，包括系统指令、用户消息和助手回复。
        model: 要使用的模型名称，如果为None则使用默认模型。
        tools: 可用的工具列表，支持字典配置或字符串标识符。
        tool_choice: 工具选择策略，控制AI如何选择和使用工具。
        config: (可选) 生成配置对象，将与默认配置合并后传递。

    返回:
        LLMResponse: 包含AI回复内容、使用信息和工具调用等的完整响应对象。
    """
    try:
        if isinstance(config, GenConfigBuilder):
            config = config.build()

        async with await get_model_instance(
            model, override_config=None
        ) as model_instance:
            return await model_instance.generate_response(
                messages,
                config=config,
                tools=tools,  # type: ignore[arg-type]
                tool_choice=tool_choice,
            )
    except LLMException:
        raise
    except Exception as e:
        friendly_msg = get_user_friendly_error_message(e)
        logger.error(f"生成响应失败: {e} | 建议: {friendly_msg}", e=e)
        raise LLMException(f"生成响应失败: {friendly_msg}", cause=e)


async def _generate_image_from_message(
    message: UniMessage,
    model: ModelName = None,
    config: LLMGenerationConfig | GenConfigBuilder | None = None,
) -> LLMResponse:
    """
    [内部] 从 UniMessage 生成图片的核心辅助函数。
    """
    from .utils import normalize_to_llm_messages

    if isinstance(config, GenConfigBuilder):
        config = config.build()

    config = config or LLMGenerationConfig()

    config.validation_policy = {"require_image": True}
    if config.output is None:
        config.output = OutputConfig()
    config.output.response_modalities = ["IMAGE", "TEXT"]

    try:
        messages = await normalize_to_llm_messages(message)

        async with await get_model_instance(model) as model_instance:
            response = await model_instance.generate_response(messages, config=config)

            if not response.images:
                error_text = response.text or "模型未返回图片数据。"
                logger.warning(f"图片生成调用未返回图片，返回文本内容: {error_text}")

            return response
    except LLMException:
        raise
    except Exception as e:
        friendly_msg = get_user_friendly_error_message(e)
        logger.error(f"执行图片生成时发生未知错误: {e} | 建议: {friendly_msg}", e=e)
        raise LLMException(f"图片生成失败: {friendly_msg}", cause=e)


@overload
async def create_image(
    prompt: str | UniMessage,
    *,
    images: None = None,
    model: ModelName = None,
) -> LLMResponse:
    """根据文本提示生成一张新图片。"""
    ...


@overload
async def create_image(
    prompt: str | UniMessage,
    *,
    images: list[Path | bytes | str] | Path | bytes | str,
    model: ModelName = None,
) -> LLMResponse:
    """在给定图片的基础上，根据文本提示进行编辑或重新生成。"""
    ...


async def create_image(
    prompt: str | UniMessage,
    *,
    images: list[Path | bytes | str] | Path | bytes | str | None = None,
    model: ModelName = None,
    config: LLMGenerationConfig | GenConfigBuilder | None = None,
) -> LLMResponse:
    """
    智能图片生成/编辑函数。
    - 如果 `images` 为 None，执行文生图。
    - 如果提供了 `images`，执行图+文生图，支持多张图片输入。
    """
    text_prompt = (
        prompt.extract_plain_text() if isinstance(prompt, UniMessage) else str(prompt)
    )

    image_list = []
    if images:
        if isinstance(images, list):
            image_list.extend(images)
        else:
            image_list.append(images)

    message = create_multimodal_message(text=text_prompt, images=image_list)

    return await _generate_image_from_message(message, model=model, config=config)


async def search(
    query: str | UniMessage | LLMMessage | list[LLMContentPart],
    *,
    model: ModelName = None,
    instruction: str = (
        "你是一位强大的信息检索和整合专家。请利用可用的搜索工具，"
        "根据用户的查询找到最相关的信息，并进行总结和回答。"
    ),
    config: LLMGenerationConfig | GenConfigBuilder | None = None,
) -> LLMResponse:
    """
    无状态的信息搜索便捷函数，利用搜索工具获取实时信息。

    参数:
        query: 搜索查询内容，支持多种输入格式。
        model: 要使用的模型名称，如果为None则使用默认模型。
        config: (可选) 生成配置对象，将与预设配置合并后传递。
        instruction: 搜索任务的系统指令，指导AI如何处理搜索结果。

    返回:
        LLMResponse: 包含搜索结果和AI整合回复的完整响应对象。
    """
    logger.debug("执行无状态 'search' 任务...")
    search_config = CommonOverrides.gemini_grounding()

    if isinstance(config, GenConfigBuilder):
        config = config.build()

    final_config = search_config.merge_with(config)

    return await chat(
        query,
        model=model,
        instruction=instruction,
        config=final_config,
        tools=[GeminiGoogleSearch()],
    )
