"""
LLM 异常类型定义
"""

from typing import Any

from .enums import LLMErrorCode


class LLMException(Exception):
    """LLM 服务相关的基础异常类"""

    def __init__(
        self,
        message: str,
        code: LLMErrorCode = LLMErrorCode.API_REQUEST_FAILED,
        details: dict[str, Any] | None = None,
        recoverable: bool = True,
        cause: Exception | None = None,
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        self.recoverable = recoverable
        self.cause = cause
        super().__init__(message)

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} (错误码: {self.code.name}, 详情: {self.details})"
        return f"{self.message} (错误码: {self.code.name})"

    @property
    def user_friendly_message(self) -> str:
        """返回适合向用户展示的错误消息"""
        error_messages = {
            LLMErrorCode.MODEL_NOT_FOUND: "AI模型未找到，请检查配置或联系管理员。",
            LLMErrorCode.API_KEY_INVALID: "API密钥无效，请联系管理员更新配置。",
            LLMErrorCode.API_QUOTA_EXCEEDED: (
                "API使用配额已用尽，请稍后再试或联系管理员。"
            ),
            LLMErrorCode.API_TIMEOUT: "AI服务响应超时，请稍后再试。",
            LLMErrorCode.API_RATE_LIMITED: "请求过于频繁，已被AI服务限流，请稍后再试。",
            LLMErrorCode.MODEL_INIT_FAILED: "AI模型初始化失败，请联系管理员检查配置。",
            LLMErrorCode.NO_AVAILABLE_KEYS: (
                "当前所有API密钥均不可用，请稍后再试或联系管理员。"
            ),
            LLMErrorCode.USER_LOCATION_NOT_SUPPORTED: (
                "当前地区暂不支持此AI服务，请联系管理员或尝试其他模型。"
            ),
            LLMErrorCode.API_REQUEST_FAILED: "AI服务请求失败，请稍后再试。",
            LLMErrorCode.API_RESPONSE_INVALID: "AI服务响应异常，请稍后再试。",
            LLMErrorCode.CONFIGURATION_ERROR: "AI服务配置错误，请联系管理员。",
            LLMErrorCode.CONTEXT_LENGTH_EXCEEDED: "输入内容过长，请缩短后重试。",
            LLMErrorCode.CONTENT_FILTERED: "内容被安全过滤，请修改后重试。",
            LLMErrorCode.RESPONSE_PARSE_ERROR: "AI服务响应解析失败，请稍后再试。",
            LLMErrorCode.UNKNOWN_API_TYPE: "不支持的AI服务类型，请联系管理员。",
        }
        return error_messages.get(self.code, "AI服务暂时不可用，请稍后再试。")


def get_user_friendly_error_message(error: Exception) -> str:
    """将任何异常转换为用户友好的错误消息"""
    if isinstance(error, LLMException):
        return error.user_friendly_message

    error_str = str(error).lower()

    if "timeout" in error_str or "超时" in error_str:
        return "请求超时，请稍后再试。"
    elif "connection" in error_str or "连接" in error_str:
        return "网络连接失败，请检查网络后重试。"
    elif "permission" in error_str or "权限" in error_str:
        return "权限不足，请联系管理员。"
    elif "not found" in error_str or "未找到" in error_str:
        return "请求的资源未找到，请检查配置。"
    elif "invalid" in error_str or "无效" in error_str:
        return "请求参数无效，请检查输入。"
    else:
        return "服务暂时不可用，请稍后再试。"
