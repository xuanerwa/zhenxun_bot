import base64
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
    ReasoningEffort,
    ResponseFormat,
)
from zhenxun.services.llm.config.providers import get_gemini_safety_threshold
from zhenxun.services.llm.types import (
    CodeExecutionOutcome,
    LLMContentPart,
    LLMMessage,
)
from zhenxun.services.llm.types.capabilities import ModelCapabilities
from zhenxun.services.llm.types.exceptions import LLMErrorCode, LLMException
from zhenxun.services.llm.types.models import (
    LLMGroundingAttribution,
    LLMGroundingMetadata,
    LLMToolCall,
    LLMToolFunction,
    ModelDetail,
    ToolDefinition,
)
from zhenxun.services.llm.utils import (
    resolve_json_schema_refs,
    sanitize_schema_for_llm,
)
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.pydantic_compat import model_copy, model_dump


class GeminiConfigMapper(ConfigMapper):
    def map_config(
        self,
        config: LLMGenerationConfig,
        model_detail: ModelDetail | None = None,
        capabilities: ModelCapabilities | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}

        if config.core:
            if config.core.temperature is not None:
                params["temperature"] = config.core.temperature
            if config.core.max_tokens is not None:
                params["maxOutputTokens"] = config.core.max_tokens
            if config.core.top_k is not None:
                params["topK"] = config.core.top_k
            if config.core.top_p is not None:
                params["topP"] = config.core.top_p

        if config.output:
            if config.output.response_format == ResponseFormat.JSON:
                params["responseMimeType"] = "application/json"
                if config.output.response_schema:
                    params["responseJsonSchema"] = config.output.response_schema
            elif config.output.response_mime_type is not None:
                params["responseMimeType"] = config.output.response_mime_type

            if (
                config.output.response_schema is not None
                and "responseJsonSchema" not in params
            ):
                params["responseJsonSchema"] = config.output.response_schema
            if config.output.response_modalities:
                params["responseModalities"] = config.output.response_modalities

        if config.tool_config:
            fc_config: dict[str, Any] = {"mode": config.tool_config.mode}
            if (
                config.tool_config.allowed_function_names
                and config.tool_config.mode == "ANY"
            ):
                builtins = {"code_execution", "google_search", "google_map"}
                user_funcs = [
                    name
                    for name in config.tool_config.allowed_function_names
                    if name not in builtins
                ]
                if user_funcs:
                    fc_config["allowedFunctionNames"] = user_funcs
            params["toolConfig"] = {"functionCallingConfig": fc_config}

        if config.reasoning:
            thinking_config = params.setdefault("thinkingConfig", {})

            if config.reasoning.budget_tokens is not None:
                if (
                    config.reasoning.budget_tokens <= 0
                    or config.reasoning.budget_tokens >= 1
                ):
                    budget_value = int(config.reasoning.budget_tokens)
                else:
                    budget_value = int(config.reasoning.budget_tokens * 32768)
                thinking_config["thinkingBudget"] = budget_value
            elif config.reasoning.effort:
                if config.reasoning.effort == ReasoningEffort.MEDIUM:
                    thinking_config["thinkingLevel"] = "HIGH"
                else:
                    thinking_config["thinkingLevel"] = config.reasoning.effort.value

            if config.reasoning.show_thoughts is not None:
                thinking_config["includeThoughts"] = config.reasoning.show_thoughts
            elif capabilities and capabilities.reasoning_visibility == "visible":
                thinking_config["includeThoughts"] = True

        if config.visual:
            image_config: dict[str, Any] = {}

            if config.visual.aspect_ratio is not None:
                ar_value = (
                    config.visual.aspect_ratio.value
                    if isinstance(config.visual.aspect_ratio, ImageAspectRatio)
                    else config.visual.aspect_ratio
                )
                image_config["aspectRatio"] = ar_value

            if config.visual.resolution:
                image_config["imageSize"] = config.visual.resolution

            if image_config:
                params["imageConfig"] = image_config

            if config.visual.media_resolution:
                media_value = config.visual.media_resolution.upper()
                if not media_value.startswith("MEDIA_RESOLUTION_"):
                    media_value = f"MEDIA_RESOLUTION_{media_value}"
                params["mediaResolution"] = media_value

        if config.custom_params:
            mapped_custom = config.custom_params.copy()
            if "max_tokens" in mapped_custom:
                mapped_custom["maxOutputTokens"] = mapped_custom.pop("max_tokens")
            if "top_k" in mapped_custom:
                mapped_custom["topK"] = mapped_custom.pop("top_k")
            if "top_p" in mapped_custom:
                mapped_custom["topP"] = mapped_custom.pop("top_p")

            for key in (
                "code_execution_timeout",
                "grounding_config",
                "dynamic_threshold",
                "user_location",
                "reflexion_retries",
            ):
                mapped_custom.pop(key, None)

            for unsupported in [
                "frequency_penalty",
                "presence_penalty",
                "repetition_penalty",
            ]:
                if unsupported in mapped_custom:
                    mapped_custom.pop(unsupported)

            params.update(mapped_custom)

        safety_settings: list[dict[str, Any]] = []
        if config.safety and config.safety.safety_settings:
            for category, threshold in config.safety.safety_settings.items():
                safety_settings.append({"category": category, "threshold": threshold})
        else:
            threshold = get_gemini_safety_threshold()
            for category in [
                "HARM_CATEGORY_HARASSMENT",
                "HARM_CATEGORY_HATE_SPEECH",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "HARM_CATEGORY_DANGEROUS_CONTENT",
            ]:
                safety_settings.append({"category": category, "threshold": threshold})

        if safety_settings:
            params["safetySettings"] = safety_settings

        return params


class GeminiMessageConverter(MessageConverter):
    async def convert_part(self, part: LLMContentPart) -> dict[str, Any]:
        """将单个内容部分转换为 Gemini API 格式"""

        def _get_gemini_resolution_dict() -> dict[str, Any]:
            if part.media_resolution:
                value = part.media_resolution.upper()
                if not value.startswith("MEDIA_RESOLUTION_"):
                    value = f"MEDIA_RESOLUTION_{value}"
                return {"media_resolution": {"level": value}}
            return {}

        if part.type == "text":
            return {"text": part.text}

        if part.type == "thought":
            return {"text": part.thought_text, "thought": True}

        if part.type == "image":
            if not part.image_source:
                raise ValueError("图像类型的内容必须包含image_source")

            if part.is_image_base64():
                base64_info = part.get_base64_data()
                if base64_info:
                    mime_type, data = base64_info
                    payload = {"inlineData": {"mimeType": mime_type, "data": data}}
                    payload.update(_get_gemini_resolution_dict())
                    return payload
                raise ValueError(f"无法解析Base64图像数据: {part.image_source[:50]}...")
            if part.is_image_url():
                logger.debug(f"正在为Gemini下载并编码URL图片: {part.image_source}")
                try:
                    image_bytes = await AsyncHttpx.get_content(part.image_source)
                    mime_type = part.mime_type or "image/jpeg"
                    base64_data = base64.b64encode(image_bytes).decode("utf-8")
                    payload = {
                        "inlineData": {"mimeType": mime_type, "data": base64_data}
                    }
                    payload.update(_get_gemini_resolution_dict())
                    return payload
                except Exception as e:
                    logger.error(f"下载或编码URL图片失败: {e}", e=e)
                    raise ValueError(f"无法处理图片URL: {e}")
            raise ValueError(f"不支持的图像源格式: {part.image_source[:50]}...")

        if part.type == "video":
            if not part.video_source:
                raise ValueError("视频类型的内容必须包含video_source")

            if part.video_source.startswith("data:"):
                try:
                    header, data = part.video_source.split(",", 1)
                    mime_type = header.split(";")[0].replace("data:", "")
                    payload = {"inlineData": {"mimeType": mime_type, "data": data}}
                    payload.update(_get_gemini_resolution_dict())
                    return payload
                except (ValueError, IndexError):
                    raise ValueError(
                        f"无法解析Base64视频数据: {part.video_source[:50]}..."
                    )
            raise ValueError(
                "Gemini API 的视频处理需要通过 File API 上传，不支持直接 URL"
            )

        if part.type == "audio":
            if not part.audio_source:
                raise ValueError("音频类型的内容必须包含audio_source")

            if part.audio_source.startswith("data:"):
                try:
                    header, data = part.audio_source.split(",", 1)
                    mime_type = header.split(";")[0].replace("data:", "")
                    payload = {"inlineData": {"mimeType": mime_type, "data": data}}
                    payload.update(_get_gemini_resolution_dict())
                    return payload
                except (ValueError, IndexError):
                    raise ValueError(
                        f"无法解析Base64音频数据: {part.audio_source[:50]}..."
                    )
            raise ValueError(
                "Gemini API 的音频处理需要通过 File API 上传，不支持直接 URL"
            )

        if part.type == "file":
            if part.file_uri:
                payload = {
                    "fileData": {"mimeType": part.mime_type, "fileUri": part.file_uri}
                }
                payload.update(_get_gemini_resolution_dict())
                return payload
            if part.file_source:
                file_name = (
                    part.metadata.get("name", "file") if part.metadata else "file"
                )
                return {"text": f"[文件: {file_name}]\n{part.file_source}"}
            raise ValueError("文件类型的内容必须包含file_uri或file_source")

        raise ValueError(f"不支持的内容类型: {part.type}")

    async def convert_messages_async(
        self, messages: list[LLMMessage]
    ) -> list[dict[str, Any]]:
        gemini_contents: list[dict[str, Any]] = []

        for msg in messages:
            current_parts: list[dict[str, Any]] = []
            if msg.role == "system":
                continue

            elif msg.role == "user":
                if isinstance(msg.content, str):
                    current_parts.append({"text": msg.content})
                elif isinstance(msg.content, list):
                    for part_obj in msg.content:
                        current_parts.append(await self.convert_part(part_obj))
                gemini_contents.append({"role": "user", "parts": current_parts})

            elif msg.role == "assistant" or msg.role == "model":
                if isinstance(msg.content, str) and msg.content:
                    current_parts.append({"text": msg.content})
                elif isinstance(msg.content, list):
                    for part_obj in msg.content:
                        part_dict = await self.convert_part(part_obj)

                        if "executableCode" in part_dict:
                            part_dict["executable_code"] = part_dict.pop(
                                "executableCode"
                            )

                        if "codeExecutionResult" in part_dict:
                            part_dict["code_execution_result"] = part_dict.pop(
                                "codeExecutionResult"
                            )

                        if (
                            part_obj.metadata
                            and "thought_signature" in part_obj.metadata
                        ):
                            part_dict["thoughtSignature"] = part_obj.metadata[
                                "thought_signature"
                            ]
                        current_parts.append(part_dict)

                if msg.tool_calls:
                    for call in msg.tool_calls:
                        fc_part = {
                            "functionCall": {
                                "name": call.function.name,
                                "args": json.loads(call.function.arguments),
                            }
                        }
                        if call.thought_signature:
                            fc_part["thoughtSignature"] = call.thought_signature
                        current_parts.append(fc_part)
                if current_parts:
                    gemini_contents.append({"role": "model", "parts": current_parts})

            elif msg.role == "tool":
                if not msg.name:
                    raise ValueError("Gemini 工具消息必须包含 'name' 字段（函数名）。")

                try:
                    content_str = (
                        msg.content
                        if isinstance(msg.content, str)
                        else str(msg.content)
                    )
                    tool_result_obj = json.loads(content_str)
                except json.JSONDecodeError:
                    content_str = (
                        msg.content
                        if isinstance(msg.content, str)
                        else str(msg.content)
                    )
                    tool_result_obj = {"raw_output": content_str}

                if isinstance(tool_result_obj, list):
                    final_response_payload = {"result": tool_result_obj}
                elif not isinstance(tool_result_obj, dict):
                    final_response_payload = {"result": tool_result_obj}
                else:
                    final_response_payload = tool_result_obj

                current_parts.append(
                    {
                        "functionResponse": {
                            "name": msg.name,
                            "response": final_response_payload,
                        }
                    }
                )
                if gemini_contents and gemini_contents[-1]["role"] == "function":
                    gemini_contents[-1]["parts"].extend(current_parts)
                else:
                    gemini_contents.append({"role": "function", "parts": current_parts})

        return gemini_contents

    def convert_messages(self, messages: list[LLMMessage]) -> list[dict[str, Any]]:
        raise NotImplementedError("Use convert_messages_async for Gemini")


class GeminiToolSerializer(ToolSerializer):
    def serialize_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        function_declarations: list[dict[str, Any]] = []
        for tool_def in tools:
            tool_copy = model_copy(tool_def)
            tool_copy.parameters = resolve_json_schema_refs(tool_copy.parameters)
            tool_copy.parameters = sanitize_schema_for_llm(
                tool_copy.parameters, api_type="gemini"
            )
            function_declarations.append(model_dump(tool_copy))
        return function_declarations


class GeminiResponseParser(ResponseParser):
    def validate_response(self, response_json: dict[str, Any]) -> None:
        if error := response_json.get("error"):
            code = error.get("code")
            message = error.get("message", "")
            status = error.get("status")
            details = error.get("details", [])

            if code == 429 or status == "RESOURCE_EXHAUSTED":
                is_quota = any(
                    d.get("reason") in ("QUOTA_EXCEEDED", "SERVICE_DISABLED")
                    for d in details
                    if isinstance(d, dict)
                )
                if is_quota or "quota" in message.lower():
                    raise LLMException(
                        f"Gemini配额耗尽: {message}",
                        code=LLMErrorCode.API_QUOTA_EXCEEDED,
                        details=error,
                    )
                raise LLMException(
                    f"Gemini速率限制: {message}",
                    code=LLMErrorCode.API_RATE_LIMITED,
                    details=error,
                )

            if code == 400 or status in ("INVALID_ARGUMENT", "FAILED_PRECONDITION"):
                raise LLMException(
                    f"Gemini参数错误: {message}",
                    code=LLMErrorCode.INVALID_PARAMETER,
                    details=error,
                    recoverable=False,
                )

        if prompt_feedback := response_json.get("promptFeedback"):
            if block_reason := prompt_feedback.get("blockReason"):
                raise LLMException(
                    f"内容被安全过滤: {block_reason}",
                    code=LLMErrorCode.CONTENT_FILTERED,
                    details={
                        "block_reason": block_reason,
                        "safety_ratings": prompt_feedback.get("safetyRatings"),
                    },
                )

    def parse(self, response_json: dict[str, Any]) -> ResponseData:
        self.validate_response(response_json)

        if "image_generation" in response_json and isinstance(
            response_json["image_generation"], dict
        ):
            candidates_source = response_json["image_generation"]
        else:
            candidates_source = response_json

        candidates = candidates_source.get("candidates", [])
        usage_info = response_json.get("usageMetadata")

        if not candidates:
            return ResponseData(text="", raw_response=response_json)

        candidate = candidates[0]
        thought_signature: str | None = None

        content_data = candidate.get("content", {})
        parts = content_data.get("parts", [])

        text_content = ""
        images_payload: list[bytes | Path] = []
        parsed_tool_calls: list[LLMToolCall] | None = None
        parsed_code_executions: list[dict[str, Any]] = []
        content_parts: list[LLMContentPart] = []
        thought_summary_parts: list[str] = []
        answer_parts = []

        for part in parts:
            part_signature = part.get("thoughtSignature")
            if part_signature and thought_signature is None:
                thought_signature = part_signature
            part_metadata: dict[str, Any] | None = None
            if part_signature:
                part_metadata = {"thought_signature": part_signature}

            if part.get("thought") is True:
                t_text = part.get("text", "")
                thought_summary_parts.append(t_text)
                content_parts.append(LLMContentPart.thought_part(t_text))

            elif "text" in part:
                answer_parts.append(part["text"])
                c_part = LLMContentPart(
                    type="text", text=part["text"], metadata=part_metadata
                )
                content_parts.append(c_part)

            elif "thoughtSummary" in part:
                thought_summary_parts.append(part["thoughtSummary"])
                content_parts.append(
                    LLMContentPart.thought_part(part["thoughtSummary"])
                )

            elif "inlineData" in part:
                inline_data = part["inlineData"]
                if "data" in inline_data:
                    decoded = base64.b64decode(inline_data["data"])
                    images_payload.append(process_image_data(decoded))

            elif "functionCall" in part:
                if parsed_tool_calls is None:
                    parsed_tool_calls = []
                fc_data = part["functionCall"]
                fc_sig = part_signature
                try:
                    call_id = f"call_gemini_{len(parsed_tool_calls)}"
                    parsed_tool_calls.append(
                        LLMToolCall(
                            id=call_id,
                            thought_signature=fc_sig,
                            function=LLMToolFunction(
                                name=fc_data["name"],
                                arguments=json.dumps(fc_data["args"]),
                            ),
                        )
                    )
                except Exception as e:
                    logger.warning(
                        f"解析Gemini functionCall时出错: {fc_data}, 错误: {e}"
                    )
            elif "executableCode" in part:
                exec_code = part["executableCode"]
                lang = exec_code.get("language", "PYTHON")
                code = exec_code.get("code", "")
                content_parts.append(LLMContentPart.executable_code_part(lang, code))
                answer_parts.append(f"\n[生成代码 ({lang})]:\n```python\n{code}\n```\n")

            elif "codeExecutionResult" in part:
                result = part["codeExecutionResult"]
                outcome = result.get("outcome", CodeExecutionOutcome.OUTCOME_UNKNOWN)
                output = result.get("output", "")

                content_parts.append(
                    LLMContentPart.execution_result_part(outcome, output)
                )

                parsed_code_executions.append(result)

                if outcome == CodeExecutionOutcome.OUTCOME_OK:
                    answer_parts.append(f"\n[代码执行结果]:\n```\n{output}\n```\n")
                else:
                    answer_parts.append(f"\n[代码执行失败 ({outcome})]:\n{output}\n")

        full_answer = "".join(answer_parts).strip()
        text_content = full_answer
        final_thought_text = (
            "\n\n".join(thought_summary_parts).strip()
            if thought_summary_parts
            else None
        )

        grounding_metadata_obj = None
        if grounding_data := candidate.get("groundingMetadata"):
            try:
                sep_content = None
                sep_field = grounding_data.get("searchEntryPoint")
                if isinstance(sep_field, dict):
                    sep_content = sep_field.get("renderedContent")

                attributions = []
                if chunks := grounding_data.get("groundingChunks"):
                    for chunk in chunks:
                        if web := chunk.get("web"):
                            attributions.append(
                                LLMGroundingAttribution(
                                    title=web.get("title"),
                                    uri=web.get("uri"),
                                    snippet=web.get("snippet"),
                                    confidence_score=None,
                                )
                            )

                grounding_metadata_obj = LLMGroundingMetadata(
                    web_search_queries=grounding_data.get("webSearchQueries"),
                    grounding_attributions=attributions or None,
                    search_suggestions=grounding_data.get("searchSuggestions"),
                    search_entry_point=sep_content,
                    map_widget_token=grounding_data.get("googleMapsWidgetContextToken"),
                )
            except Exception as e:
                logger.warning(f"无法解析Grounding元数据: {grounding_data}, {e}")

        return ResponseData(
            text=text_content,
            tool_calls=parsed_tool_calls,
            code_executions=parsed_code_executions if parsed_code_executions else None,
            content_parts=content_parts if content_parts else None,
            images=images_payload if images_payload else None,
            usage_info=usage_info,
            raw_response=response_json,
            grounding_metadata=grounding_metadata_obj,
            thought_text=final_thought_text,
            thought_signature=thought_signature,
        )
