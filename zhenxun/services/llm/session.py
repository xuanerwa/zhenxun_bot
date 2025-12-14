"""
LLM 服务 - 会话客户端

提供一个有状态的、面向会话的 LLM 客户端，用于进行多轮对话和复杂交互。
"""

from collections.abc import Awaitable, Callable
import copy
import json
from typing import Any, TypeVar, cast
import uuid

from jinja2 import Template
from nonebot.utils import is_coroutine_callable
from nonebot_plugin_alconna.uniseg import UniMessage
from pydantic import BaseModel

from zhenxun.services.log import logger
from zhenxun.utils.pydantic_compat import model_json_schema

from .config import (
    CommonOverrides,
    GenConfigBuilder,
    LLMEmbeddingConfig,
    LLMGenerationConfig,
)
from .config.generation import OutputConfig
from .config.providers import get_llm_config
from .manager import get_global_default_model_name, get_model_instance
from .memory import (
    AIConfig,
    BaseMemory,
    MemoryProcessor,
    _get_default_memory,
)
from .tools import tool_provider_manager
from .types import (
    LLMContentPart,
    LLMErrorCode,
    LLMException,
    LLMMessage,
    LLMResponse,
    ModelName,
    ResponseFormat,
    StructuredOutputStrategy,
    ToolChoice,
    ToolExecutable,
)
from .types.models import (
    GeminiCodeExecution,
    GeminiGoogleSearch,
)
from .utils import (
    create_cot_wrapper,
    normalize_to_llm_messages,
    parse_and_validate_json,
    should_apply_autocot,
)

T = TypeVar("T", bound=BaseModel)

DEFAULT_IVR_TEMPLATE = (
    "你的响应未能通过结构校验。\n"
    "错误详情: {error_msg}\n\n"
    "请执行以下步骤进行修正：\n"
    "1. 反思：分析为什么会出现这个错误。\n"
    "2. 修正：生成一个新的、符合 Schema 要求的 JSON 对象。\n"
    "请直接输出修正后的 JSON，不要包含 Markdown 标记或其他解释。"
)


class AI:
    """
    统一的AI服务类 - 提供了带记忆的会话接口。
    不再执行自主工具循环，当LLM返回工具调用时，会直接将请求返回给调用者。
    """

    def __init__(
        self,
        session_id: str | None = None,
        config: AIConfig | None = None,
        memory: BaseMemory | None = None,
        default_generation_config: LLMGenerationConfig | None = None,
        processors: list[MemoryProcessor] | None = None,
    ):
        """
        初始化AI服务

        参数:
            session_id: 唯一的会话ID，用于隔离记忆。
            config: AI 配置.
            memory: 可选的自定义记忆后端。如果为None，则使用默认的 ChatMemory
            (InMemoryMessageStore)。
            default_generation_config: 此AI实例的默认生成配置。
            processors: 记忆处理器列表，在添加记忆后触发。
        """
        self.session_id = session_id or str(uuid.uuid4())
        self.config = config or AIConfig()
        self.memory = memory or _get_default_memory()
        self.default_generation_config = (
            default_generation_config or LLMGenerationConfig()
        )
        self.processors = processors or []

        global_providers = tool_provider_manager._providers
        config_providers = self.config.tool_providers
        self._tool_providers = list(dict.fromkeys(global_providers + config_providers))
        self.message_buffer: list[LLMMessage] = []

    async def clear_history(self):
        """清空当前会话的历史记录。"""
        await self.memory.clear_history(self.session_id)
        logger.info(f"AI会话历史记录已清空 (session_id: {self.session_id})")

    async def add_observation(
        self, message: str | UniMessage | LLMMessage | list[LLMContentPart]
    ):
        """
        将一条观察消息加入缓冲区，不立即触发模型调用。

        返回:
            int: 缓冲区中消息的数量。
        """
        current_message = await self._normalize_input_to_message(message)
        self.message_buffer.append(current_message)
        content_preview = str(current_message.content)[:50]
        logger.debug(
            f"[放入观察] {content_preview} (缓冲区大小: {len(self.message_buffer)})",
            "AI_MEMORY",
        )
        return len(self.message_buffer)

    async def add_user_message_to_history(
        self, message: str | LLMMessage | list[LLMContentPart]
    ):
        """
        将一条用户消息标准化并添加到会话历史中。

        参数:
            message: 用户消息内容。
        """
        user_message = await self._normalize_input_to_message(message)
        await self.memory.add_message(self.session_id, user_message)

    async def add_assistant_response_to_history(self, response_text: str):
        """
        将助手的文本回复添加到会话历史中。

        参数:
            response_text: 助手的回复文本。
        """
        assistant_message = LLMMessage.assistant_text_response(response_text)
        await self.memory.add_message(self.session_id, assistant_message)

    def _sanitize_message_for_history(self, message: LLMMessage) -> LLMMessage:
        """
        净化用于存入历史记录的消息。
        将非文本的多模态内容部分替换为文本占位符，以避免重复处理。
        """
        if not isinstance(message.content, list):
            return message

        sanitized_message = copy.deepcopy(message)
        content_list = sanitized_message.content
        if not isinstance(content_list, list):
            return sanitized_message

        new_content_parts: list[LLMContentPart] = []
        has_multimodal_content = False

        for part in content_list:
            if isinstance(part, LLMContentPart) and part.type == "text":
                new_content_parts.append(part)
            else:
                has_multimodal_content = True

        if has_multimodal_content:
            placeholder = "[用户发送了媒体文件，内容已在首次分析时处理]"
            text_part_found = False
            for part in new_content_parts:
                if part.type == "text":
                    part.text = f"{placeholder} {part.text or ''}".strip()
                    text_part_found = True
                    break
            if not text_part_found:
                new_content_parts.insert(0, LLMContentPart.text_part(placeholder))

        sanitized_message.content = new_content_parts
        return sanitized_message

    async def _normalize_input_to_message(
        self, message: str | UniMessage | LLMMessage | list[LLMContentPart]
    ) -> LLMMessage:
        """
        内部辅助方法，将各种输入类型统一转换为单个 LLMMessage 对象。
        它调用共享的工具函数并提取最后一条消息（通常是用户输入）。
        """
        messages = await normalize_to_llm_messages(message)

        if not messages:
            raise LLMException(
                "无法将输入标准化为有效的消息。", code=LLMErrorCode.CONFIGURATION_ERROR
            )
        return messages[-1]

    async def generate_internal(
        self,
        messages: list[LLMMessage],
        *,
        model: ModelName = None,
        config: LLMGenerationConfig | GenConfigBuilder | None = None,
        tools: list[Any] | dict[str, ToolExecutable] | None = None,
        tool_choice: str | dict[str, Any] | ToolChoice | None = None,
        timeout: float | None = None,
        model_instance: Any = None,
    ) -> LLMResponse:
        """
        内部生成核心方法，负责配置合并、工具解析和模型调用。
        此方法不处理历史记录的存储，供 AgentExecutor 或 chat 方法调用。
        """
        final_config = self.default_generation_config
        if isinstance(config, GenConfigBuilder):
            config = config.build()

        if config:
            final_config = final_config.merge_with(config)

        final_tools_list = []
        if tools:
            if isinstance(tools, dict):
                final_tools_list = list(tools.values())
            elif isinstance(tools, list):
                to_resolve: list[Any] = []
                for t in tools:
                    if isinstance(t, str | dict):
                        to_resolve.append(t)
                    else:
                        final_tools_list.append(t)

                if to_resolve:
                    resolved_dict = await self._resolve_tools(to_resolve)
                    final_tools_list.extend(resolved_dict.values())

        if model_instance:
            return await model_instance.generate_response(
                messages,
                config=final_config,
                tools=final_tools_list if final_tools_list else None,
                tool_choice=tool_choice,
                timeout=timeout,
            )

        resolved_model_name = self._resolve_model_name(model or self.config.model)
        async with await get_model_instance(
            resolved_model_name,
            override_config=None,
        ) as instance:
            return await instance.generate_response(
                messages,
                config=final_config,
                tools=final_tools_list if final_tools_list else None,
                tool_choice=tool_choice,
                timeout=timeout,
            )

    async def chat(
        self,
        message: str | UniMessage | LLMMessage | list[LLMContentPart] | None,
        *,
        model: ModelName = None,
        instruction: str | None = None,
        template_vars: dict[str, Any] | None = None,
        preserve_media_in_history: bool | None = None,
        tools: list[Any] | dict[str, ToolExecutable] | None = None,
        tool_choice: str | dict[str, Any] | ToolChoice | None = None,
        config: LLMGenerationConfig | GenConfigBuilder | None = None,
        use_buffer: bool = False,
        timeout: float | None = None,
    ) -> LLMResponse:
        """
        核心交互方法，管理会话历史并执行单次LLM调用。

        参数:
            message: 用户输入的消息内容，支持文本、UniMessage、LLMMessage或
                    内容部分列表。
            model: 要使用的模型名称，如果为None则使用配置中的默认模型。
            instruction: 本次调用的特定系统指令，会与全局指令合并。
            template_vars: 模板变量字典，用于在指令中进行变量替换。
            preserve_media_in_history: 是否在历史记录中保留媒体内容，
                                     None时使用默认配置。
            tools: 可用的工具列表或工具字典，支持临时工具和预配置工具。
            tool_choice: 工具选择策略，控制AI如何选择和使用工具。
            config: 生成配置对象，用于覆盖默认的生成参数。
            use_buffer: 是否刷新并包含消息缓冲区的内容，在此次对话中一次性提交。
            timeout: HTTP 请求超时时间（秒）。

        返回:
            LLMResponse: 包含AI回复、工具调用请求、使用信息等的完整响应对象。
        """
        messages_to_add: list[LLMMessage] = []
        if message:
            current_message = await self._normalize_input_to_message(message)
            messages_to_add.append(current_message)

        if use_buffer and self.message_buffer:
            messages_to_add = self.message_buffer + messages_to_add
            self.message_buffer.clear()

        messages_for_run = []
        final_instruction = instruction

        if final_instruction and template_vars:
            try:
                template = Template(final_instruction)
                final_instruction = template.render(**template_vars)
                logger.debug(f"渲染后的系统指令: {final_instruction}")
            except Exception as e:
                logger.error(f"渲染系统指令模板失败: {e}", e=e)

        if final_instruction:
            messages_for_run.append(LLMMessage.system(final_instruction))

        current_history = await self.memory.get_history(self.session_id)
        messages_for_run.extend(current_history)
        messages_for_run.extend(messages_to_add)

        try:
            response = await self.generate_internal(
                messages_for_run,
                model=model,
                config=config,
                tools=tools,
                tool_choice=tool_choice,
                timeout=timeout,
            )

            should_preserve = (
                preserve_media_in_history
                if preserve_media_in_history is not None
                else self.config.default_preserve_media_in_history
            )
            msgs_to_store: list[LLMMessage] = []
            for msg in messages_to_add:
                store_msg = (
                    msg if should_preserve else self._sanitize_message_for_history(msg)
                )
                msgs_to_store.append(store_msg)

            if response.content_parts:
                assistant_response_msg = LLMMessage(
                    role="assistant",
                    content=response.content_parts,
                    tool_calls=response.tool_calls,
                )
            else:
                assistant_response_msg = LLMMessage.assistant_text_response(
                    response.text
                )
                if response.tool_calls:
                    assistant_response_msg = LLMMessage.assistant_tool_calls(
                        response.tool_calls, response.text
                    )

            await self.memory.add_messages(
                self.session_id, [*msgs_to_store, assistant_response_msg]
            )

            if self.processors:
                for processor in self.processors:
                    await processor.process(
                        self.session_id, [*msgs_to_store, assistant_response_msg]
                    )

            return response

        except Exception as e:
            raise (
                e
                if isinstance(e, LLMException)
                else LLMException(f"聊天执行失败: {e}", cause=e)
            )

    async def code(
        self,
        prompt: str,
        *,
        model: ModelName = None,
        timeout: int | None = None,
        config: LLMGenerationConfig | GenConfigBuilder | None = None,
    ) -> LLMResponse:
        """
        代码执行

        参数:
            prompt: 代码执行的提示词。
            model: 要使用的模型名称。
            timeout: 代码执行超时时间（秒）。
            config: (可选) 覆盖默认的生成配置。

        返回:
            LLMResponse: 包含执行结果的完整响应对象。
        """
        resolved_model = model or self.config.model

        code_config = CommonOverrides.gemini_code_execution()
        if timeout:
            code_config.custom_params = code_config.custom_params or {}
            code_config.custom_params["code_execution_timeout"] = timeout

        if isinstance(config, GenConfigBuilder):
            config = config.build()

        if config:
            code_config = code_config.merge_with(config)

        return await self.chat(prompt, model=resolved_model, config=code_config)

    async def search(
        self,
        query: UniMessage,
        *,
        model: ModelName = None,
        instruction: str = (
            "你是一位强大的信息检索和整合专家。请利用可用的搜索工具，"
            "根据用户的查询找到最相关的信息，并进行总结和回答。"
        ),
        template_vars: dict[str, Any] | None = None,
        config: LLMGenerationConfig | GenConfigBuilder | None = None,
    ) -> LLMResponse:
        """
        信息搜索的便捷入口，原生支持多模态查询。
        """
        logger.info("执行 'search' 任务...")
        search_config = CommonOverrides.gemini_grounding()

        if isinstance(config, GenConfigBuilder):
            config = config.build()

        if config:
            search_config = search_config.merge_with(config)

        return await self.chat(
            query,
            model=model,
            instruction=instruction,
            template_vars=template_vars,
            config=search_config,
            tools=[GeminiGoogleSearch()],
        )

    async def generate_structured(
        self,
        message: str | UniMessage | LLMMessage | list[LLMContentPart] | None,
        response_model: type[T],
        *,
        model: ModelName = None,
        tools: list[Any] | dict[str, ToolExecutable] | None = None,
        tool_choice: str | dict[str, Any] | ToolChoice | None = None,
        instruction: str | None = None,
        timeout: float | None = None,
        template_vars: dict[str, Any] | None = None,
        config: LLMGenerationConfig | GenConfigBuilder | None = None,
        max_validation_retries: int | None = None,
        validation_callback: Callable[[T], Any | Awaitable[Any]] | None = None,
        error_prompt_template: str | None = None,
        auto_thinking: bool = False,
    ) -> T:
        """
        生成结构化响应，并自动解析为指定的Pydantic模型。

        参数:
            message: 用户输入的消息内容，支持多种格式。为None时只使用历史+缓冲区。
            response_model: 用于解析和验证响应的Pydantic模型类。
            model: 要使用的模型名称，如果为None则使用配置中的默认模型。
            instruction: 本次调用的特定系统指令，会与JSON Schema指令合并。
            timeout: HTTP 请求超时时间（秒）。
            template_vars: 系统指令中的模板变量，用于动态渲染。
            config: 生成配置对象，用于覆盖默认的生成参数。

        返回:
            T: 解析后的Pydantic模型实例，类型为response_model指定的类型。

        异常:
            LLMException: 如果模型返回的不是有效的JSON或验证失败。
        """
        if isinstance(config, GenConfigBuilder):
            config = config.build()

        final_config = self.default_generation_config.merge_with(config)

        if final_config is None:
            final_config = LLMGenerationConfig()

        if max_validation_retries is None:
            max_validation_retries = get_llm_config().client_settings.structured_retries

        resolved_model_name = self._resolve_model_name(model or self.config.model)

        request_autocot = True if auto_thinking is False else auto_thinking
        effective_auto_thinking = should_apply_autocot(
            request_autocot, resolved_model_name, final_config
        )

        target_model: type[T] = response_model
        if effective_auto_thinking:
            target_model = cast(type[T], create_cot_wrapper(response_model))
            response_model = target_model

            cot_instruction = (
                "请务必先在 `reasoning` 字段中进行详细的一步步推理，确保逻辑正确，"
                "然后再填充 `result` 字段。"
            )
            if instruction:
                instruction = f"{instruction}\n\n{cot_instruction}"
            else:
                instruction = cot_instruction

        final_instruction = instruction
        if final_instruction and template_vars:
            try:
                template = Template(final_instruction)
                final_instruction = template.render(**template_vars)
            except Exception as e:
                logger.error(f"渲染结构化指令模板失败: {e}", e=e)

        try:
            json_schema = model_json_schema(response_model)
        except AttributeError:
            json_schema = response_model.schema()

        schema_str = json.dumps(json_schema, ensure_ascii=False, indent=2)

        prompt_prefix = f"{final_instruction}\n\n" if final_instruction else ""
        structured_strategy = (
            final_config.output.structured_output_strategy
            if final_config.output
            else None
        )
        if structured_strategy == StructuredOutputStrategy.TOOL_CALL:
            system_prompt = prompt_prefix + "请调用提供的工具提交结构化数据。"
        else:
            system_prompt = (
                prompt_prefix
                + "请严格按照以下 JSON Schema 格式进行响应。不应包含任何额外的解释、"
                "注释或代码块标记，只返回一个合法的 JSON 对象。\n\n"
            )
            system_prompt += f"JSON Schema:\n```json\n{schema_str}\n```"

        structured_strategy = (
            final_config.output.structured_output_strategy
            if final_config.output
            else StructuredOutputStrategy.NATIVE
        )

        final_tools_list: list[ToolExecutable] | None = None
        if structured_strategy != StructuredOutputStrategy.NATIVE:
            if tools:
                final_tools_list = []
                if isinstance(tools, dict):
                    final_tools_list = list(tools.values())
                elif isinstance(tools, list):
                    to_resolve: list[Any] = []
                    for t in tools:
                        if isinstance(t, str | dict):
                            to_resolve.append(t)
                        else:
                            final_tools_list.append(t)
                    if to_resolve:
                        resolved_dict = await self._resolve_tools(to_resolve)
                        final_tools_list.extend(resolved_dict.values())
        elif tools:
            logger.warning(
                "检测到在 generate_structured (NATIVE 策略) 中传入了 tools。"
                "为了避免 API 冲突(Gemini)及输出歧义(OpenAI)，这些"
                "tools 将被本次请求忽略。"
                "若需使用工具，请使用 chat() 方法或 Agent 流程。"
            )

        if final_config.output is None:
            final_config.output = OutputConfig()

        final_config.output.response_format = ResponseFormat.JSON
        final_config.output.response_schema = json_schema

        messages_for_run = [LLMMessage.system(system_prompt)]
        current_history = await self.memory.get_history(self.session_id)
        messages_for_run.extend(current_history)
        messages_for_run.extend(self.message_buffer)
        if message:
            normalized_message = await self._normalize_input_to_message(message)
            messages_for_run.append(normalized_message)

        ivr_messages = list(messages_for_run)
        last_exception: Exception | None = None

        for attempt in range(max_validation_retries + 1):
            current_response_text: str = ""

            async with await get_model_instance(
                resolved_model_name,
                override_config=None,
            ) as model_instance:
                response = await model_instance.generate_response(
                    ivr_messages,
                    config=final_config,
                    tools=final_tools_list if final_tools_list else None,
                    tool_choice=tool_choice,
                    timeout=timeout,
                )
                current_response_text = response.text

            try:
                parsed_obj = parse_and_validate_json(response.text, target_model)

                final_obj: T = cast(T, parsed_obj)
                if effective_auto_thinking:
                    logger.debug(
                        f"AutoCoT 思考过程: {getattr(parsed_obj, 'reasoning', '')}"
                    )
                    final_obj = cast(T, getattr(parsed_obj, "result"))

                if validation_callback:
                    if is_coroutine_callable(validation_callback):
                        await validation_callback(final_obj)
                    else:
                        validation_callback(final_obj)

                return final_obj

            except Exception as e:
                is_llm_error = isinstance(e, LLMException)
                llm_error: LLMException | None = (
                    cast(LLMException, e) if is_llm_error else None
                )
                last_exception = e

                if attempt < max_validation_retries:
                    error_msg = (
                        llm_error.details.get("validation_error", str(e))
                        if llm_error
                        else str(e)
                    )
                    raw_response = current_response_text or (
                        llm_error.details.get("raw_response", "") if llm_error else ""
                    )
                    logger.warning(
                        f"结构化校验失败 (尝试 {attempt + 1}/"
                        f"{max_validation_retries + 1})。正在尝试 IVR 修复... 错误:"
                        f"{error_msg}"
                    )

                    if raw_response:
                        ivr_messages.append(
                            LLMMessage.assistant_text_response(raw_response)
                        )
                    else:
                        logger.warning(
                            "IVR 警告: 无法获取上一轮生成的原始文本，"
                            "模型将在无上下文情况下尝试修复。"
                        )

                    template = error_prompt_template or DEFAULT_IVR_TEMPLATE
                    feedback_prompt = template.format(error_msg=error_msg)
                    ivr_messages.append(LLMMessage.user(feedback_prompt))
                    continue

                if llm_error and not llm_error.recoverable:
                    raise llm_error

        if last_exception:
            raise last_exception
        raise LLMException(
            "IVR 循环异常结束，未能生成有效结果。", code=LLMErrorCode.GENERATION_FAILED
        )

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

    async def embed(
        self,
        texts: list[str] | str,
        *,
        model: ModelName = None,
        config: LLMEmbeddingConfig | None = None,
    ) -> list[list[float]]:
        """
        生成文本嵌入向量，将文本转换为数值向量表示。

        参数:
            texts: 要生成嵌入的文本内容，支持单个字符串或字符串列表。
            model: 嵌入模型名称，如果为None则使用配置中的默认嵌入模型。
            config: 嵌入配置

        返回:
            list[list[float]]: 文本对应的嵌入向量列表，每个向量为浮点数列表。

        异常:
            LLMException: 当嵌入生成失败或模型配置错误时抛出
        """
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
                    "使用 embed 方法时未指定嵌入模型名称，"
                    "且 AIConfig 未设置 default_embedding_model。",
                    code=LLMErrorCode.MODEL_NOT_FOUND,
                )
            resolved_model_str = self._resolve_model_name(resolved_model_str)

            final_config = config or LLMEmbeddingConfig()

            async with await get_model_instance(
                resolved_model_str,
                override_config=None,
            ) as embedding_model_instance:
                return await embedding_model_instance.generate_embeddings(
                    texts, config=final_config
                )
        except LLMException:
            raise
        except Exception as e:
            logger.error(f"文本嵌入失败: {e}", e=e)
            raise LLMException(
                f"文本嵌入失败: {e}", code=LLMErrorCode.EMBEDDING_FAILED, cause=e
            )

    async def _resolve_tools(
        self,
        tool_configs: list[Any],
    ) -> dict[str, ToolExecutable]:
        """
        使用注入的 ToolProvider 异步解析 ad-hoc（临时）工具配置。
        返回一个从工具名称到可执行对象的字典。
        """
        resolved: dict[str, ToolExecutable] = {}

        for config in tool_configs:
            if isinstance(config, str):
                if config == "google_search":
                    resolved[config] = GeminiGoogleSearch()  # type: ignore[arg-type]
                    continue
                elif config == "code_execution":
                    resolved[config] = GeminiCodeExecution()  # type: ignore[arg-type]
                    continue
                elif config == "url_context":
                    pass
            name = config if isinstance(config, str) else config.get("name")
            if not name:
                raise LLMException(
                    "工具配置字典必须包含 'name' 字段。",
                    code=LLMErrorCode.CONFIGURATION_ERROR,
                )

            if isinstance(config, str):
                config_dict = {"name": name, "type": "function"}
            elif isinstance(config, dict):
                config_dict = config
            else:
                raise TypeError(f"不支持的工具配置类型: {type(config)}")

            executable = None
            for provider in self._tool_providers:
                executable = await provider.get_tool_executable(name, config_dict)
                if executable:
                    break

            if not executable:
                raise LLMException(
                    f"没有为 ad-hoc 工具 '{name}' 找到合适的提供者。",
                    code=LLMErrorCode.CONFIGURATION_ERROR,
                )

            resolved[name] = executable

        return resolved
