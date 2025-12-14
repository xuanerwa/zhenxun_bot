import base64
import binascii
import json
from pathlib import Path
from typing import Any

from zhenxun.services.llm.adapters.base import ResponseData, process_image_data
from zhenxun.services.llm.adapters.components.interfaces import (
    ConfigMapper,
    MessageConverter,
    ResponseParser,
    ToolSerializer,
)
from zhenxun.services.llm.config.generation import (
    ImageAspectRatio,
    LLMGenerationConfig,
    ResponseFormat,
    StructuredOutputStrategy,
)
from zhenxun.services.llm.types import LLMMessage
from zhenxun.services.llm.types.capabilities import ModelCapabilities
from zhenxun.services.llm.types.exceptions import LLMErrorCode, LLMException
from zhenxun.services.llm.types.models import (
    LLMToolCall,
    LLMToolFunction,
    ModelDetail,
    ToolDefinition,
)
from zhenxun.services.llm.utils import sanitize_schema_for_llm
from zhenxun.services.log import logger
from zhenxun.utils.pydantic_compat import model_dump


class OpenAIConfigMapper(ConfigMapper):
    def __init__(self, api_type: str = "openai"):
        self.api_type = api_type

    def map_config(
        self,
        config: LLMGenerationConfig,
        model_detail: ModelDetail | None = None,
        capabilities: ModelCapabilities | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        strategy = config.output.structured_output_strategy if config.output else None
        if strategy is None:
            strategy = (
                StructuredOutputStrategy.TOOL_CALL
                if self.api_type == "deepseek"
                else StructuredOutputStrategy.NATIVE
            )

        if config.core:
            if config.core.temperature is not None:
                params["temperature"] = config.core.temperature
            if config.core.max_tokens is not None:
                params["max_tokens"] = config.core.max_tokens
            if config.core.top_k is not None:
                params["top_k"] = config.core.top_k
            if config.core.top_p is not None:
                params["top_p"] = config.core.top_p
            if config.core.frequency_penalty is not None:
                params["frequency_penalty"] = config.core.frequency_penalty
            if config.core.presence_penalty is not None:
                params["presence_penalty"] = config.core.presence_penalty
            if config.core.stop is not None:
                params["stop"] = config.core.stop

            if config.core.repetition_penalty is not None:
                if self.api_type == "openai":
                    logger.warning("OpenAI官方API不支持repetition_penalty参数，已忽略")
                else:
                    params["repetition_penalty"] = config.core.repetition_penalty

        if config.reasoning and config.reasoning.effort:
            params["reasoning_effort"] = config.reasoning.effort.value.lower()

        if config.output:
            if isinstance(config.output.response_format, dict):
                params["response_format"] = config.output.response_format
            elif (
                config.output.response_format == ResponseFormat.JSON
                and strategy == StructuredOutputStrategy.NATIVE
            ):
                if config.output.response_schema:
                    sanitized = sanitize_schema_for_llm(
                        config.output.response_schema, api_type="openai"
                    )
                    params["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "structured_response",
                            "schema": sanitized,
                            "strict": True,
                        },
                    }
                else:
                    params["response_format"] = {"type": "json_object"}

        if config.tool_config:
            mode = config.tool_config.mode
            if mode == "NONE":
                params["tool_choice"] = "none"
            elif mode == "AUTO":
                params["tool_choice"] = "auto"
            elif mode == "ANY":
                params["tool_choice"] = "required"

        if config.visual and config.visual.aspect_ratio:
            size_map = {
                ImageAspectRatio.SQUARE: "1024x1024",
                ImageAspectRatio.LANDSCAPE_16_9: "1792x1024",
                ImageAspectRatio.PORTRAIT_9_16: "1024x1792",
            }
            ar = config.visual.aspect_ratio
            if isinstance(ar, ImageAspectRatio):
                mapped_size = size_map.get(ar)
                if mapped_size:
                    params["size"] = mapped_size
            elif isinstance(ar, str):
                params["size"] = ar

        if config.custom_params:
            mapped_custom = config.custom_params.copy()
            if "repetition_penalty" in mapped_custom and self.api_type == "openai":
                mapped_custom.pop("repetition_penalty")

            if "stop" in mapped_custom:
                stop_value = mapped_custom["stop"]
                if isinstance(stop_value, str):
                    mapped_custom["stop"] = [stop_value]

            params.update(mapped_custom)

        return params


class OpenAIMessageConverter(MessageConverter):
    def convert_messages(self, messages: list[LLMMessage]) -> list[dict[str, Any]]:
        openai_messages: list[dict[str, Any]] = []
        for msg in messages:
            openai_msg: dict[str, Any] = {"role": msg.role}

            if msg.role == "tool":
                openai_msg["tool_call_id"] = msg.tool_call_id
                openai_msg["name"] = msg.name
                openai_msg["content"] = msg.content
            else:
                if isinstance(msg.content, str):
                    openai_msg["content"] = msg.content
                else:
                    content_parts = []
                    for part in msg.content:
                        if part.type == "text":
                            content_parts.append({"type": "text", "text": part.text})
                        elif part.type == "image":
                            content_parts.append(
                                {
                                    "type": "image_url",
                                    "image_url": {"url": part.image_source},
                                }
                            )
                    openai_msg["content"] = content_parts

            if msg.role == "assistant" and msg.tool_calls:
                assistant_tool_calls = []
                for call in msg.tool_calls:
                    assistant_tool_calls.append(
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            },
                        }
                    )
                openai_msg["tool_calls"] = assistant_tool_calls

            if msg.name and msg.role != "tool":
                openai_msg["name"] = msg.name

            openai_messages.append(openai_msg)
        return openai_messages


class OpenAIToolSerializer(ToolSerializer):
    def serialize_tools(
        self, tools: list[ToolDefinition]
    ) -> list[dict[str, Any]] | None:
        if not tools:
            return None

        openai_tools = []
        for tool in tools:
            tool_dict = model_dump(tool)
            parameters = tool_dict.get("parameters")
            if parameters:
                tool_dict["parameters"] = sanitize_schema_for_llm(
                    parameters, api_type="openai"
                )
            tool_dict["strict"] = True
            openai_tools.append({"type": "function", "function": tool_dict})
        return openai_tools


class OpenAIResponseParser(ResponseParser):
    def validate_response(self, response_json: dict[str, Any]) -> None:
        if response_json.get("error"):
            error_info = response_json["error"]
            if isinstance(error_info, dict):
                error_message = error_info.get("message", "未知错误")
                error_code = error_info.get("code", "unknown")

                error_code_mapping = {
                    "invalid_api_key": LLMErrorCode.API_KEY_INVALID,
                    "authentication_failed": LLMErrorCode.API_KEY_INVALID,
                    "insufficient_quota": LLMErrorCode.API_QUOTA_EXCEEDED,
                    "rate_limit_exceeded": LLMErrorCode.API_RATE_LIMITED,
                    "quota_exceeded": LLMErrorCode.API_RATE_LIMITED,
                    "model_not_found": LLMErrorCode.MODEL_NOT_FOUND,
                    "invalid_model": LLMErrorCode.MODEL_NOT_FOUND,
                    "context_length_exceeded": LLMErrorCode.CONTEXT_LENGTH_EXCEEDED,
                    "max_tokens_exceeded": LLMErrorCode.CONTEXT_LENGTH_EXCEEDED,
                    "invalid_request_error": LLMErrorCode.INVALID_PARAMETER,
                    "invalid_parameter": LLMErrorCode.INVALID_PARAMETER,
                }

                llm_error_code = error_code_mapping.get(
                    error_code, LLMErrorCode.API_RESPONSE_INVALID
                )
            else:
                error_message = str(error_info)
                error_code = "unknown"
                llm_error_code = LLMErrorCode.API_RESPONSE_INVALID

            raise LLMException(
                f"API请求失败: {error_message}",
                code=llm_error_code,
                details={"api_error": error_info, "error_code": error_code},
            )

    def parse(self, response_json: dict[str, Any]) -> ResponseData:
        self.validate_response(response_json)

        choices = response_json.get("choices", [])
        if not choices:
            return ResponseData(text="", raw_response=response_json)

        choice = choices[0]
        message = choice.get("message", {})
        content = message.get("content", "")
        reasoning_content = message.get("reasoning_content", None)
        refusal = message.get("refusal")

        if refusal:
            raise LLMException(
                f"模型拒绝生成请求: {refusal}",
                code=LLMErrorCode.CONTENT_FILTERED,
                details={"refusal": refusal},
                recoverable=False,
            )

        if content:
            content = content.strip()

        images_payload: list[bytes | Path] = []
        if content and content.startswith("{") and content.endswith("}"):
            try:
                content_json = json.loads(content)
                if "b64_json" in content_json:
                    b64_str = content_json["b64_json"]
                    if isinstance(b64_str, str) and b64_str.startswith("data:"):
                        b64_str = b64_str.split(",", 1)[1]
                    decoded = base64.b64decode(b64_str)
                    images_payload.append(process_image_data(decoded))
                    content = "[图片已生成]"
                elif "data" in content_json and isinstance(content_json["data"], str):
                    b64_str = content_json["data"]
                    if b64_str.startswith("data:"):
                        b64_str = b64_str.split(",", 1)[1]
                    decoded = base64.b64decode(b64_str)
                    images_payload.append(process_image_data(decoded))
                    content = "[图片已生成]"

            except (json.JSONDecodeError, KeyError, binascii.Error):
                pass
        elif (
            "images" in message
            and isinstance(message["images"], list)
            and message["images"]
        ):
            for image_info in message["images"]:
                if image_info.get("type") == "image_url":
                    image_url_obj = image_info.get("image_url", {})
                    url_str = image_url_obj.get("url", "")
                    if url_str.startswith("data:image"):
                        try:
                            b64_data = url_str.split(",", 1)[1]
                            decoded = base64.b64decode(b64_data)
                            images_payload.append(process_image_data(decoded))
                        except (IndexError, binascii.Error) as e:
                            logger.warning(f"解析OpenRouter Base64图片数据失败: {e}")

            if images_payload:
                content = content if content else "[图片已生成]"

        parsed_tool_calls: list[LLMToolCall] | None = None
        if message_tool_calls := message.get("tool_calls"):
            parsed_tool_calls = []
            for tc_data in message_tool_calls:
                try:
                    if tc_data.get("type") == "function":
                        parsed_tool_calls.append(
                            LLMToolCall(
                                id=tc_data["id"],
                                function=LLMToolFunction(
                                    name=tc_data["function"]["name"],
                                    arguments=tc_data["function"]["arguments"],
                                ),
                            )
                        )
                except KeyError as e:
                    logger.warning(
                        f"解析OpenAI工具调用数据时缺少键: {tc_data}, 错误: {e}"
                    )
                except Exception as e:
                    logger.warning(
                        f"解析OpenAI工具调用数据时出错: {tc_data}, 错误: {e}"
                    )
            if not parsed_tool_calls:
                parsed_tool_calls = None

        final_text = content if content is not None else ""
        if not final_text and parsed_tool_calls:
            final_text = f"请求调用 {len(parsed_tool_calls)} 个工具。"

        usage_info = response_json.get("usage")

        return ResponseData(
            text=final_text,
            tool_calls=parsed_tool_calls,
            usage_info=usage_info,
            images=images_payload if images_payload else None,
            raw_response=response_json,
            thought_text=reasoning_content,
        )
