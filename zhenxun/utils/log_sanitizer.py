import copy
import re
from typing import Any

from nonebot.adapters import Message, MessageSegment


def _truncate_base64_string(value: str, threshold: int = 256) -> str:
    """如果字符串是超长的base64或data URI，则截断它。"""
    if not isinstance(value, str):
        return value

    prefixes = ("base64://", "data:image", "data:video", "data:audio")
    if value.startswith(prefixes) and len(value) > threshold:
        prefix = next((p for p in prefixes if value.startswith(p)), "base64")
        return f"[{prefix}_data_omitted_len={len(value)}]"
    return value


def _sanitize_ui_html(html_string: str) -> str:
    """
    专门用于净化UI渲染调试HTML的函数。
    它会查找所有内联的base64数据（如字体、图片）并将其截断。
    """
    if not isinstance(html_string, str):
        return html_string

    pattern = re.compile(r"(data:[^;]+;base64,)[A-Za-z0-9+/=\s]{100,}")

    def replacer(match):
        prefix = match.group(1)
        original_len = len(match.group(0)) - len(prefix)
        return f"{prefix}[...base64_omitted_len={original_len}...]"

    return pattern.sub(replacer, html_string)


def _sanitize_nonebot_message(message: Message) -> Message:
    """净化nonebot.adapter.Message对象，用于日志记录。"""
    sanitized_message = copy.deepcopy(message)
    for seg in sanitized_message:
        seg: MessageSegment
        if seg.type in ("image", "record", "video"):
            file_info = seg.data.get("file", "")
            if isinstance(file_info, str):
                seg.data["file"] = _truncate_base64_string(file_info)
    return sanitized_message


def _sanitize_openai_response(response_json: dict) -> dict:
    """净化OpenAI兼容API的响应体。"""
    try:
        sanitized_json = copy.deepcopy(response_json)
        if "choices" in sanitized_json and isinstance(sanitized_json["choices"], list):
            for choice in sanitized_json["choices"]:
                if "message" in choice and isinstance(choice["message"], dict):
                    message = choice["message"]
                    if "images" in message and isinstance(message["images"], list):
                        for i, image_info in enumerate(message["images"]):
                            if "image_url" in image_info and isinstance(
                                image_info["image_url"], dict
                            ):
                                url = image_info["image_url"].get("url", "")
                                message["images"][i]["image_url"]["url"] = (
                                    _truncate_base64_string(url)
                                )
        return sanitized_json
    except Exception:
        return response_json


def _sanitize_openai_request(body: dict) -> dict:
    """净化OpenAI兼容API的请求体，主要截断图片base64。"""
    try:
        sanitized_json = copy.deepcopy(body)
        if "messages" in sanitized_json and isinstance(
            sanitized_json["messages"], list
        ):
            for message in sanitized_json["messages"]:
                if "content" in message and isinstance(message["content"], list):
                    for i, part in enumerate(message["content"]):
                        if part.get("type") == "image_url":
                            if "image_url" in part and isinstance(
                                part["image_url"], dict
                            ):
                                url = part["image_url"].get("url", "")
                                message["content"][i]["image_url"]["url"] = (
                                    _truncate_base64_string(url)
                                )
        return sanitized_json
    except Exception:
        return body


def _sanitize_gemini_response(response_json: dict) -> dict:
    """净化Gemini API的响应体，处理文本和图片生成两种格式。"""
    try:
        sanitized_json = copy.deepcopy(response_json)

        def _process_candidates(candidates_list: list):
            """辅助函数，用于处理任何 candidates 列表。"""
            if not isinstance(candidates_list, list):
                return
            for candidate in candidates_list:
                if "content" in candidate and isinstance(candidate["content"], dict):
                    content = candidate["content"]
                    if "parts" in content and isinstance(content["parts"], list):
                        for i, part in enumerate(content["parts"]):
                            if "inlineData" in part and isinstance(
                                part["inlineData"], dict
                            ):
                                data = part["inlineData"].get("data", "")
                                if isinstance(data, str) and len(data) > 256:
                                    content["parts"][i]["inlineData"]["data"] = (
                                        f"[base64_data_omitted_len={len(data)}]"
                                    )

        if "candidates" in sanitized_json:
            _process_candidates(sanitized_json["candidates"])

        if "image_generation" in sanitized_json and isinstance(
            sanitized_json["image_generation"], dict
        ):
            if "candidates" in sanitized_json["image_generation"]:
                _process_candidates(sanitized_json["image_generation"]["candidates"])

        return sanitized_json
    except Exception:
        return response_json


def _sanitize_gemini_request(body: dict) -> dict:
    """净化Gemini API的请求体，进行结构转换和总结。"""
    try:
        sanitized_body = copy.deepcopy(body)
        if "contents" in sanitized_body and isinstance(
            sanitized_body["contents"], list
        ):
            for content_item in sanitized_body["contents"]:
                if "parts" in content_item and isinstance(content_item["parts"], list):
                    media_summary = []
                    new_parts = []
                    for part in content_item["parts"]:
                        if "inlineData" in part and isinstance(
                            part["inlineData"], dict
                        ):
                            data = part["inlineData"].get("data")
                            if isinstance(data, str):
                                mime_type = part["inlineData"].get(
                                    "mimeType", "unknown"
                                )
                                media_summary.append(f"{mime_type} ({len(data)} chars)")
                                continue
                        new_parts.append(part)

                    if media_summary:
                        summary_text = (
                            f"[多模态内容: {len(media_summary)}个文件 - "
                            f"{', '.join(media_summary)}]"
                        )
                        new_parts.insert(0, {"text": summary_text})

                    content_item["parts"] = new_parts
        return sanitized_body
    except Exception:
        return body


def sanitize_for_logging(data: Any, context: str | None = None) -> Any:
    """
    统一的日志净化入口。

    Args:
        data: 需要净化的数据 (dict, Message, etc.).
        context: 净化场景的上下文标识，例如 'gemini_request', 'openai_response'.

    Returns:
        净化后的数据。
    """
    if context == "nonebot_message":
        if isinstance(data, Message):
            return _sanitize_nonebot_message(data)
    elif context == "openai_response":
        if isinstance(data, dict):
            return _sanitize_openai_response(data)
    elif context == "gemini_response":
        if isinstance(data, dict):
            return _sanitize_gemini_response(data)
    elif context == "gemini_request":
        if isinstance(data, dict):
            return _sanitize_gemini_request(data)
    elif context == "openai_request":
        if isinstance(data, dict):
            return _sanitize_openai_request(data)
    elif context == "ui_html":
        if isinstance(data, str):
            return _sanitize_ui_html(data)
    else:
        if isinstance(data, str):
            return _truncate_base64_string(data)

    return data
