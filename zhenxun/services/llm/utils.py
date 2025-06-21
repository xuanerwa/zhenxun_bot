"""
LLM 模块的工具和转换函数
"""

import base64
from pathlib import Path

from nonebot_plugin_alconna.uniseg import (
    At,
    File,
    Image,
    Reply,
    Text,
    UniMessage,
    Video,
    Voice,
)

from zhenxun.services.log import logger

from .types import LLMContentPart


async def unimsg_to_llm_parts(message: UniMessage) -> list[LLMContentPart]:
    """
    将 UniMessage 实例转换为一个 LLMContentPart 列表。
    这是处理多模态输入的核心转换逻辑。
    """
    parts: list[LLMContentPart] = []
    for seg in message:
        part = None
        if isinstance(seg, Text):
            if seg.text.strip():
                part = LLMContentPart.text_part(seg.text)
        elif isinstance(seg, Image):
            if seg.path:
                part = await LLMContentPart.from_path(seg.path, target_api="gemini")
            elif seg.url:
                part = LLMContentPart.image_url_part(seg.url)
            elif hasattr(seg, "raw") and seg.raw:
                mime_type = (
                    getattr(seg, "mimetype", "image/png")
                    if hasattr(seg, "mimetype")
                    else "image/png"
                )
                if isinstance(seg.raw, bytes):
                    b64_data = base64.b64encode(seg.raw).decode("utf-8")
                    part = LLMContentPart.image_base64_part(b64_data, mime_type)

        elif isinstance(seg, File | Voice | Video):
            if seg.path:
                part = await LLMContentPart.from_path(seg.path)
            elif seg.url:
                logger.warning(
                    f"直接使用 URL 的 {type(seg).__name__} 段，"
                    f"API 可能不支持: {seg.url}"
                )
                part = LLMContentPart.text_part(
                    f"[{type(seg).__name__.upper()} FILE: {seg.name or seg.url}]"
                )
            elif hasattr(seg, "raw") and seg.raw:
                mime_type = getattr(seg, "mimetype", None)
                if isinstance(seg.raw, bytes):
                    b64_data = base64.b64encode(seg.raw).decode("utf-8")

                    if isinstance(seg, Video):
                        if not mime_type:
                            mime_type = "video/mp4"
                        part = LLMContentPart.video_base64_part(
                            data=b64_data, mime_type=mime_type
                        )
                        logger.debug(
                            f"处理视频字节数据: {mime_type}, 大小: {len(seg.raw)} bytes"
                        )
                    elif isinstance(seg, Voice):
                        if not mime_type:
                            mime_type = "audio/wav"
                        part = LLMContentPart.audio_base64_part(
                            data=b64_data, mime_type=mime_type
                        )
                        logger.debug(
                            f"处理音频字节数据: {mime_type}, 大小: {len(seg.raw)} bytes"
                        )
                    else:
                        part = LLMContentPart.text_part(
                            f"[FILE: {mime_type or 'unknown'}, {len(seg.raw)} bytes]"
                        )
                        logger.debug(
                            f"处理其他文件字节数据: {mime_type}, "
                            f"大小: {len(seg.raw)} bytes"
                        )

        elif isinstance(seg, At):
            if seg.flag == "all":
                part = LLMContentPart.text_part("[Mentioned Everyone]")
            else:
                part = LLMContentPart.text_part(f"[Mentioned user: {seg.target}]")

        elif isinstance(seg, Reply):
            if seg.msg:
                try:
                    extract_method = getattr(seg.msg, "extract_plain_text", None)
                    if extract_method and callable(extract_method):
                        reply_text = str(extract_method()).strip()
                    else:
                        reply_text = str(seg.msg).strip()
                    if reply_text:
                        part = LLMContentPart.text_part(
                            f'[Replied to: "{reply_text[:50]}..."]'
                        )
                except Exception:
                    part = LLMContentPart.text_part("[Replied to a message]")

        if part:
            parts.append(part)

    return parts


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
    创建多模态消息的便捷函数，方便第三方调用。

    Args:
        text: 文本内容
        images: 图片数据，支持路径、字节数据或URL
        videos: 视频数据，支持路径、字节数据或URL
        audios: 音频数据，支持路径、字节数据或URL
        image_mimetypes: 图片MIME类型，当images为bytes时需要指定
        video_mimetypes: 视频MIME类型，当videos为bytes时需要指定
        audio_mimetypes: 音频MIME类型，当audios为bytes时需要指定

    Returns:
        UniMessage: 构建好的多模态消息

    Examples:
        # 纯文本
        msg = create_multimodal_message("请分析这段文字")

        # 文本 + 单张图片（路径）
        msg = create_multimodal_message("分析图片", images="/path/to/image.jpg")

        # 文本 + 多张图片
        msg = create_multimodal_message(
            "比较图片", images=["/path/1.jpg", "/path/2.jpg"]
        )

        # 文本 + 图片字节数据
        msg = create_multimodal_message(
            "分析", images=image_data, image_mimetypes="image/jpeg"
        )

        # 文本 + 视频
        msg = create_multimodal_message("分析视频", videos="/path/to/video.mp4")

        # 文本 + 音频
        msg = create_multimodal_message("转录音频", audios="/path/to/audio.wav")

        # 混合多模态
        msg = create_multimodal_message(
            "分析这些媒体文件",
            images="/path/to/image.jpg",
            videos="/path/to/video.mp4",
            audios="/path/to/audio.wav"
        )
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
    """添加媒体文件到 UniMessage 的辅助函数"""
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
