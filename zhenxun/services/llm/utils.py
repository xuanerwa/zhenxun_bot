"""
LLM 模块的工具和转换函数
"""

import base64
from collections.abc import Awaitable, Callable
import io
from pathlib import Path
from typing import Any, TypeVar

import aiofiles
import json_repair
from nonebot.adapters import Message as PlatformMessage
from nonebot.compat import type_validate_json
from nonebot_plugin_alconna.uniseg import (
    At,
    File,
    Image,
    Reply,
    Segment,
    Text,
    UniMessage,
    Video,
    Voice,
)
from PIL.Image import Image as PILImageType
from pydantic import BaseModel, Field, ValidationError, create_model

from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.pydantic_compat import model_validate

from .types import LLMContentPart, LLMErrorCode, LLMException, LLMMessage
from .types.capabilities import ReasoningMode, get_model_capabilities

T = TypeVar("T", bound=BaseModel)


S = TypeVar("S", bound=Segment)
_SEGMENT_HANDLERS: dict[
    type[Segment], Callable[[Any], Awaitable[LLMContentPart | None]]
] = {}


def register_segment_handler(seg_type: type[S]):
    """装饰器：注册 Uniseg 消息段的处理器"""

    def decorator(func: Callable[[S], Awaitable[LLMContentPart | None]]):
        _SEGMENT_HANDLERS[seg_type] = func
        return func

    return decorator


async def _process_media_data(seg: Any, default_mime: str) -> tuple[str, str] | None:
    """
    [内部复用] 通用媒体数据处理：获取 Base64 数据和 MIME 类型。
    优先顺序：Raw -> Path -> URL (下载)
    """
    mime_type = getattr(seg, "mimetype", None) or default_mime
    b64_data = None

    if hasattr(seg, "raw") and seg.raw:
        if isinstance(seg.raw, bytes):
            b64_data = base64.b64encode(seg.raw).decode("utf-8")

    elif getattr(seg, "path", None):
        try:
            path = Path(seg.path)
            if path.exists():
                async with aiofiles.open(path, "rb") as f:
                    content = await f.read()
                b64_data = base64.b64encode(content).decode("utf-8")
        except Exception as e:
            logger.error(f"读取媒体文件失败: {seg.path}, 错误: {e}")

    elif getattr(seg, "url", None):
        try:
            logger.debug(f"检测到媒体URL，开始下载: {seg.url}")
            media_bytes = await AsyncHttpx.get_content(seg.url)
            b64_data = base64.b64encode(media_bytes).decode("utf-8")
            logger.debug(f"媒体文件下载成功，大小: {len(media_bytes)} bytes")
        except Exception as e:
            logger.error(f"从URL下载媒体失败: {seg.url}, 错误: {e}")
            return None

    if b64_data:
        return mime_type, b64_data
    return None


@register_segment_handler(Text)
async def _handle_text(seg: Text) -> LLMContentPart | None:
    if seg.text.strip():
        return LLMContentPart.text_part(seg.text)
    return None


@register_segment_handler(Image)
async def _handle_image(seg: Image) -> LLMContentPart | None:
    media_info = await _process_media_data(seg, "image/png")
    if media_info:
        mime, data = media_info
        return LLMContentPart.image_base64_part(data, mime)
    return None


@register_segment_handler(Voice)
async def _handle_voice(seg: Voice) -> LLMContentPart | None:
    media_info = await _process_media_data(seg, "audio/wav")
    if media_info:
        mime, data = media_info
        return LLMContentPart.audio_base64_part(data, mime)
    return LLMContentPart.text_part(f"[语音消息: {seg.id or 'unknown'}]")


@register_segment_handler(Video)
async def _handle_video(seg: Video) -> LLMContentPart | None:
    media_info = await _process_media_data(seg, "video/mp4")
    if media_info:
        mime, data = media_info
        return LLMContentPart.video_base64_part(data, mime)
    return LLMContentPart.text_part(f"[视频消息: {seg.id or 'unknown'}]")


@register_segment_handler(File)
async def _handle_file(seg: File) -> LLMContentPart | None:
    if seg.path:
        return await LLMContentPart.from_path(seg.path)
    return LLMContentPart.text_part(f"[文件: {seg.name} (ID: {seg.id})]")


@register_segment_handler(At)
async def _handle_at(seg: At) -> LLMContentPart | None:
    if seg.flag == "all":
        return LLMContentPart.text_part("[提及所有人]")
    return LLMContentPart.text_part(f"[提及用户: {seg.target}]")


@register_segment_handler(Reply)
async def _handle_reply(seg: Reply) -> LLMContentPart | None:
    text = str(seg.msg) if seg.msg else ""
    if text:
        return LLMContentPart.text_part(f'[回复消息: "{text[:50]}..."]')
    return LLMContentPart.text_part("[回复了一条消息]")


async def _transform_to_content_part(item: Any) -> LLMContentPart:
    """
    将混合输入转换为统一的 LLMContentPart，便于 normalize_to_llm_messages 使用。
    """
    if isinstance(item, LLMContentPart):
        return item

    if isinstance(item, str):
        return LLMContentPart.text_part(item)

    if isinstance(item, Path):
        part = await LLMContentPart.from_path(item)
        if part is None:
            raise ValueError(f"无法从路径加载内容: {item}")
        return part

    if isinstance(item, dict):
        return LLMContentPart(**item)

    if PILImageType and isinstance(item, PILImageType):
        buffer = io.BytesIO()
        fmt = item.format or "PNG"
        item.save(buffer, format=fmt)
        b64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
        mime_type = f"image/{fmt.lower()}"
        return LLMContentPart.image_base64_part(b64_data, mime_type)

    raise TypeError(f"不支持的输入类型用于构建 ContentPart: {type(item)}")


async def unimsg_to_llm_parts(message: UniMessage) -> list[LLMContentPart]:
    """
    将 UniMessage 实例转换为一个 LLMContentPart 列表。
    这是处理多模态输入的核心转换逻辑。

    参数:
        message: 要转换的UniMessage实例。

    返回:
        list[LLMContentPart]: 转换后的内容部分列表。
    """
    if not _SEGMENT_HANDLERS:
        pass

    parts: list[LLMContentPart] = []
    for seg in message:
        handler = _SEGMENT_HANDLERS.get(type(seg))
        if handler:
            try:
                part = await handler(seg)
                if part:
                    parts.append(part)
            except Exception as e:
                logger.warning(f"处理消息段 {seg} 失败: {e}", "LLMUtils")

    return parts


async def normalize_to_llm_messages(
    message: str | UniMessage | LLMMessage | list[Any],
    instruction: str | None = None,
) -> list[LLMMessage]:
    """
    将多种输入格式标准化为 LLMMessage 列表，并可选地添加系统指令。
    这是处理 LLM 输入的核心工具函数。

    参数:
        message: 要标准化的输入消息。
        instruction: 可选的系统指令。

    返回:
        list[LLMMessage]: 标准化后的消息列表。
    """
    messages = []
    if instruction:
        messages.append(LLMMessage.system(instruction))

    if isinstance(message, LLMMessage):
        messages.append(message)
    elif isinstance(message, list) and all(isinstance(m, LLMMessage) for m in message):
        messages.extend(message)
    elif isinstance(message, str):
        messages.append(LLMMessage.user(message))
    elif isinstance(message, UniMessage):
        content_parts = await unimsg_to_llm_parts(message)
        messages.append(LLMMessage.user(content_parts))
    elif isinstance(message, list):
        parts = []
        for item in message:
            parts.append(await _transform_to_content_part(item))
        messages.append(LLMMessage.user(parts))
    else:
        raise TypeError(f"不支持的消息类型: {type(message)}")

    return messages


def create_multimodal_message(
    text: str | None = None,
    images: list[str | Path | bytes] | str | Path | bytes | None = None,
    videos: list[str | Path | bytes] | str | Path | bytes | None = None,
    audios: list[str | Path | bytes] | str | Path | bytes | None = None,
    image_mimetypes: list[str] | str | None = None,
    video_mimetypes: list[str] | str | None = None,
    audio_mimetypes: list[str] | str | None = None,
) -> UniMessage:
    """
    创建多模态消息的便捷函数

    参数:
        text: 文本内容
        images: 图片数据，支持路径、字节数据或URL
        videos: 视频数据
        audios: 音频数据
        image_mimetypes: 图片MIME类型，bytes数据时需要指定
        video_mimetypes: 视频MIME类型，bytes数据时需要指定
        audio_mimetypes: 音频MIME类型，bytes数据时需要指定

    返回:
        UniMessage: 构建好的多模态消息
    """
    message = UniMessage()

    if text:
        message.append(Text(text))

    if images is not None:
        _add_media_to_message(message, images, image_mimetypes, Image, "image/png")

    if videos is not None:
        _add_media_to_message(message, videos, video_mimetypes, Video, "video/mp4")

    if audios is not None:
        _add_media_to_message(message, audios, audio_mimetypes, Voice, "audio/wav")

    return message


def _add_media_to_message(
    message: UniMessage,
    media_items: list[str | Path | bytes] | str | Path | bytes,
    mimetypes: list[str] | str | None,
    media_class: type,
    default_mimetype: str,
) -> None:
    """添加媒体文件到 UniMessage"""
    if not isinstance(media_items, list):
        media_items = [media_items]

    mime_list = []
    if mimetypes is not None:
        if isinstance(mimetypes, str):
            mime_list = [mimetypes] * len(media_items)
        else:
            mime_list = list(mimetypes)

    for i, item in enumerate(media_items):
        if isinstance(item, str | Path):
            if str(item).startswith(("http://", "https://")):
                message.append(media_class(url=str(item)))
            else:
                message.append(media_class(path=Path(item)))
        elif isinstance(item, bytes):
            mimetype = mime_list[i] if i < len(mime_list) else default_mimetype
            message.append(media_class(raw=item, mimetype=mimetype))


def message_to_unimessage(message: PlatformMessage) -> UniMessage:
    """
    将平台特定的 Message 对象转换为通用的 UniMessage。
    主要用于处理引用消息等未被自动转换的消息体。

    参数:
        message: 平台特定的Message对象。

    返回:
        UniMessage: 转换后的通用消息对象。
    """
    return UniMessage.of(message)


def resolve_json_schema_refs(schema: dict) -> dict:
    """
    递归解析 JSON Schema 中的 $ref，将其替换为 $defs/definitions 中的定义。
    用于兼容不支持 $ref 的 Gemini API。
    """
    definitions = schema.get("$defs") or schema.get("definitions") or {}

    def _resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref_name = node["$ref"].split("/")[-1]
                if ref_name in definitions:
                    return _resolve(definitions[ref_name])

            return {
                key: _resolve(value)
                for key, value in node.items()
                if key not in ("$defs", "definitions")
            }

        if isinstance(node, list):
            return [_resolve(item) for item in node]

        return node

    return _resolve(schema)


def sanitize_schema_for_llm(schema: Any, api_type: str) -> Any:
    """
    递归地净化 JSON Schema，移除特定 LLM API 不支持的关键字。
    """
    if isinstance(schema, list):
        return [sanitize_schema_for_llm(item, api_type) for item in schema]
    if isinstance(schema, dict):
        schema_copy = schema.copy()

        if api_type == "gemini":
            if "const" in schema_copy:
                schema_copy["enum"] = [schema_copy.pop("const")]

            if "type" in schema_copy and isinstance(schema_copy["type"], list):
                types_list = schema_copy["type"]
                if "null" in types_list:
                    schema_copy["nullable"] = True
                    types_list = [t for t in types_list if t != "null"]
                    if len(types_list) == 1:
                        schema_copy["type"] = types_list[0]
                    else:
                        schema_copy["type"] = types_list

            if "anyOf" in schema_copy:
                any_of = schema_copy["anyOf"]
                has_null = any(
                    isinstance(x, dict) and x.get("type") == "null" for x in any_of
                )
                if has_null:
                    schema_copy["nullable"] = True
                    new_any_of = [
                        x
                        for x in any_of
                        if not (isinstance(x, dict) and x.get("type") == "null")
                    ]
                    if len(new_any_of) == 1:
                        schema_copy.update(new_any_of[0])
                        schema_copy.pop("anyOf", None)
                    else:
                        schema_copy["anyOf"] = new_any_of

            unsupported_keys = [
                "exclusiveMinimum",
                "exclusiveMaximum",
                "default",
                "title",
                "additionalProperties",
                "$schema",
                "$id",
            ]
            for key in unsupported_keys:
                schema_copy.pop(key, None)

            if schema_copy.get("format") and schema_copy["format"] not in [
                "enum",
                "date-time",
            ]:
                schema_copy.pop("format", None)

        elif api_type == "openai":
            unsupported_keys = [
                "default",
                "minLength",
                "maxLength",
                "pattern",
                "format",
                "minimum",
                "maximum",
                "multipleOf",
                "patternProperties",
                "minItems",
                "maxItems",
                "uniqueItems",
                "$schema",
                "title",
            ]
            for key in unsupported_keys:
                schema_copy.pop(key, None)

            if "$ref" in schema_copy:
                ref_key = schema_copy["$ref"].split("/")[-1]
                defs = schema_copy.get("$defs") or schema_copy.get("definitions")
                if defs and ref_key in defs:
                    schema_copy.pop("$ref", None)
                    schema_copy.update(defs[ref_key])
                else:
                    return {"$ref": schema_copy["$ref"]}

            is_object = (
                schema_copy.get("type") == "object" or "properties" in schema_copy
            )
            if is_object:
                schema_copy["type"] = "object"
                schema_copy["additionalProperties"] = False

                properties = schema_copy.get("properties", {})
                required = schema_copy.get("required", [])
                if properties:
                    existing_req = set(required)
                    for prop in properties.keys():
                        if prop not in existing_req:
                            required.append(prop)
                    schema_copy["required"] = required

        for def_key in ["$defs", "definitions"]:
            if def_key in schema_copy and isinstance(schema_copy[def_key], dict):
                schema_copy[def_key] = {
                    k: sanitize_schema_for_llm(v, api_type)
                    for k, v in schema_copy[def_key].items()
                }

        recursive_keys = ["properties", "items", "allOf", "anyOf", "oneOf"]
        for key in recursive_keys:
            if key in schema_copy:
                if key == "properties" and isinstance(schema_copy[key], dict):
                    schema_copy[key] = {
                        k: sanitize_schema_for_llm(v, api_type)
                        for k, v in schema_copy[key].items()
                    }
                else:
                    schema_copy[key] = sanitize_schema_for_llm(
                        schema_copy[key], api_type
                    )

        return schema_copy
    else:
        return schema


def extract_text_from_content(
    content: str | list[LLMContentPart] | None,
) -> str:
    """
    从消息内容中提取纯文本，自动过滤非文本部分，防止污染 Prompt。
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            part.text for part in content if part.type == "text" and part.text
        )
    return str(content)


def parse_and_validate_json(text: str, response_model: type[T]) -> T:
    """
    通用工具：尝试将文本解析为指定的 Pydantic 模型，并统一处理异常。
    """
    try:
        return type_validate_json(response_model, text)
    except (ValidationError, ValueError) as e:
        try:
            logger.warning(f"标准JSON解析失败，尝试使用json_repair修复: {e}")
            repaired_obj = json_repair.loads(text, skip_json_loads=True)
            return model_validate(response_model, repaired_obj)
        except Exception as repair_error:
            logger.error(
                f"LLM结构化输出校验最终失败: {repair_error}",
                e=repair_error,
            )
            raise LLMException(
                "LLM返回的JSON未能通过结构验证。",
                code=LLMErrorCode.RESPONSE_PARSE_ERROR,
                details={
                    "raw_response": text,
                    "validation_error": str(repair_error),
                    "original_error": repair_error,
                },
                cause=repair_error,
            )
    except Exception as e:
        logger.error(f"解析LLM结构化输出时发生未知错误: {e}", e=e)
        raise LLMException(
            "解析LLM的JSON输出时失败。",
            code=LLMErrorCode.RESPONSE_PARSE_ERROR,
            details={"raw_response": text},
            cause=e,
        )


def create_cot_wrapper(inner_model: type[BaseModel]) -> type[BaseModel]:
    """
    [动态运行时封装]
    创建一个包含思维链 (Chain of Thought) 的包装模型。
    强制模型在生成最终 JSON 结构前，先输出一个 reasoning 字段进行思考。
    """
    wrapper_name = f"CoT_{inner_model.__name__}"

    return create_model(
        wrapper_name,
        reasoning=(
            str,
            Field(
                ...,
                min_length=10,
                description=(
                    "在生成最终结果之前，请务必在此字段中详细描述你的推理步骤、计算过程或思考逻辑。禁止留空。"
                ),
            ),
        ),
        result=(
            inner_model,
            Field(
                ...,
            ),
        ),
    )


def should_apply_autocot(
    requested: bool,
    model_name: str | None,
    config: Any,
) -> bool:
    """
    [智能决策管道]
    判断是否应该应用 AutoCoT (显式思维链包装)。
    防止在模型已有原生思维能力时进行“双重思考”。
    """
    if not requested:
        return False

    if config:
        thinking_budget = getattr(config, "thinking_budget", 0) or 0
        if thinking_budget > 0:
            return False
        if getattr(config, "thinking_level", None) is not None:
            return False

    if model_name:
        caps = get_model_capabilities(model_name)
        if caps.reasoning_mode != ReasoningMode.NONE:
            return False

    return True
