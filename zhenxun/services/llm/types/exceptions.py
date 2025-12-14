"""
LLM 异常类型定义
"""

from enum import Enum
from typing import Any


class LLMErrorCode(Enum):
    """LLM 服务相关的错误代码枚举"""

    MODEL_INIT_FAILED = 2000
    MODEL_NOT_FOUND = 2001
    API_REQUEST_FAILED = 2002
    API_RESPONSE_INVALID = 2003
    API_KEY_INVALID = 2004
    API_QUOTA_EXCEEDED = 2005
    API_TIMEOUT = 2006
    API_RATE_LIMITED = 2007
    NO_AVAILABLE_KEYS = 2008
    UNKNOWN_API_TYPE = 2009
    CONFIGURATION_ERROR = 2010
    RESPONSE_PARSE_ERROR = 2011
    CONTEXT_LENGTH_EXCEEDED = 2012
    CONTENT_FILTERED = 2013
    USER_LOCATION_NOT_SUPPORTED = 2014
    INVALID_PARAMETER = 2017
    GENERATION_FAILED = 2015
    EMBEDDING_FAILED = 2016


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
            safe_details = {k: v for k, v in self.details.items() if k != "api_key"}
            if safe_details:
                return (
                    f"{self.message} (错误码: {self.code.name}, 详情: {safe_details})"
                )
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
                "当前网络环境不支持此 AI 模型 (如 Gemini/OpenAI)。\n"
                "原因: 代理节点所在地区（如香港/国内/非支持区）被服务商屏蔽。\n"
                "建议: 请尝试更换代理节点至支持的地区（如美国/日本/新加坡）。"
            ),
            LLMErrorCode.API_REQUEST_FAILED: "AI服务请求失败，请稍后再试。",
            LLMErrorCode.API_RESPONSE_INVALID: "AI服务响应异常，请稍后再试。",
            LLMErrorCode.INVALID_PARAMETER: "请求参数错误，请检查输入内容。",
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

    if "timeout" in error_str or "timed out" in error_str:
        return "网络请求超时，请检查服务器网络或代理连接。"
    if "connect" in error_str and ("refused" in error_str or "error" in error_str):
        return "无法连接到 AI 服务商，请检查网络连接或代理设置。"
    if "proxy" in error_str:
        return "代理连接失败，请检查代理服务器是否正常运行。"
    if "ssl" in error_str or "certificate" in error_str:
        return "SSL 证书验证失败，请检查网络环境。"
    if "permission" in error_str or "forbidden" in error_str:
        return "权限不足，可能是 API Key 权限受限。"
    if "not found" in error_str:
        return "请求的资源未找到 (404)，请检查模型名称或端点配置。"
    if "invalid" in error_str or "无效" in error_str:
        return "请求参数无效，请检查输入。"

    return f"服务暂时不可用 ({type(error).__name__})，请稍后再试。"
