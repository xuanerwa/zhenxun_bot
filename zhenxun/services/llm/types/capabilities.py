"""
LLM 模型能力定义模块

定义模型的输入输出模态、工具调用支持等核心能力。
"""

from enum import Enum
import fnmatch
from typing import Literal

from pydantic import BaseModel, Field

from zhenxun.services.log import logger


class ModelModality(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    EMBEDDING = "embedding"


class ReasoningMode(str, Enum):
    """推理/思考模式类型"""

    NONE = "none"
    BUDGET = "budget"
    LEVEL = "level"
    EFFORT = "effort"


PATTERNS_GEMINI_2_5 = [
    "gemini-2.5*",
    "gemini-flash*",
    "gemini*lite*",
    "gemini-flash-latest",
]

PATTERNS_GEMINI_3 = [
    "gemini-3*",
    "gemini-exp*",
]

PATTERNS_OPENAI_REASONING = [
    "o1-*",
    "o3-*",
    "deepseek-r1*",
    "deepseek-reasoner",
]


class ModelCapabilities(BaseModel):
    """定义一个模型的核心、稳定能力。"""

    input_modalities: set[ModelModality] = Field(default={ModelModality.TEXT})
    output_modalities: set[ModelModality] = Field(default={ModelModality.TEXT})
    supports_tool_calling: bool = False
    is_embedding_model: bool = False
    reasoning_mode: ReasoningMode = ReasoningMode.NONE
    reasoning_visibility: Literal["visible", "hidden", "none"] = "none"


STANDARD_TEXT_TOOL_CAPABILITIES = ModelCapabilities(
    input_modalities={ModelModality.TEXT},
    output_modalities={ModelModality.TEXT},
    supports_tool_calling=True,
)

CAP_GEMINI_2_5 = ModelCapabilities(
    input_modalities={
        ModelModality.TEXT,
        ModelModality.IMAGE,
        ModelModality.AUDIO,
        ModelModality.VIDEO,
    },
    output_modalities={ModelModality.TEXT},
    supports_tool_calling=True,
    reasoning_mode=ReasoningMode.BUDGET,
    reasoning_visibility="visible",
)

CAP_GEMINI_3 = ModelCapabilities(
    input_modalities={
        ModelModality.TEXT,
        ModelModality.IMAGE,
        ModelModality.AUDIO,
        ModelModality.VIDEO,
    },
    output_modalities={ModelModality.TEXT},
    supports_tool_calling=True,
    reasoning_mode=ReasoningMode.LEVEL,
    reasoning_visibility="visible",
)

CAP_GEMINI_IMAGE_GEN = ModelCapabilities(
    input_modalities={ModelModality.TEXT, ModelModality.IMAGE},
    output_modalities={ModelModality.TEXT, ModelModality.IMAGE},
    supports_tool_calling=True,
)

CAP_OPENAI_REASONING = ModelCapabilities(
    input_modalities={ModelModality.TEXT, ModelModality.IMAGE},
    output_modalities={ModelModality.TEXT},
    supports_tool_calling=True,
    reasoning_mode=ReasoningMode.EFFORT,
    reasoning_visibility="hidden",
)

CAP_GPT_ADVANCED = ModelCapabilities(
    input_modalities={ModelModality.TEXT, ModelModality.IMAGE},
    output_modalities={ModelModality.TEXT},
    supports_tool_calling=True,
)

CAP_GPT_MULTIMODAL_IO = ModelCapabilities(
    input_modalities={ModelModality.TEXT, ModelModality.AUDIO, ModelModality.IMAGE},
    output_modalities={ModelModality.TEXT, ModelModality.AUDIO},
    supports_tool_calling=True,
)

GPT_IMAGE_GENERATION_CAPABILITIES = ModelCapabilities(
    input_modalities={ModelModality.TEXT, ModelModality.IMAGE},
    output_modalities={ModelModality.IMAGE},
    supports_tool_calling=True,
)

GPT_VIDEO_GENERATION_CAPABILITIES = ModelCapabilities(
    input_modalities={ModelModality.TEXT, ModelModality.IMAGE, ModelModality.VIDEO},
    output_modalities={ModelModality.VIDEO},
    supports_tool_calling=True,
)

EMBEDDING_CAPABILITIES = ModelCapabilities(
    input_modalities={ModelModality.TEXT},
    output_modalities={ModelModality.EMBEDDING},
    is_embedding_model=True,
)

DEFAULT_PERMISSIVE_CAPABILITIES = ModelCapabilities(
    input_modalities={
        ModelModality.TEXT,
        ModelModality.IMAGE,
        ModelModality.AUDIO,
        ModelModality.VIDEO,
    },
    output_modalities={
        ModelModality.TEXT,
        ModelModality.IMAGE,
        ModelModality.AUDIO,
        ModelModality.VIDEO,
    },
    supports_tool_calling=True,
)


DOUBAO_ADVANCED_MULTIMODAL_CAPABILITIES = ModelCapabilities(
    input_modalities={ModelModality.TEXT, ModelModality.IMAGE, ModelModality.VIDEO},
    output_modalities={ModelModality.TEXT},
    supports_tool_calling=True,
)


MODEL_ALIAS_MAPPING: dict[str, str] = {
    "deepseek-v3*": "deepseek-chat",
    "deepseek-ai/DeepSeek-V3": "deepseek-chat",
    "deepseek-r1*": "deepseek-reasoner",
}


def _build_registry() -> dict[str, ModelCapabilities]:
    """构建模型能力注册表，展开模式列表以减少冗余"""
    registry: dict[str, ModelCapabilities] = {}

    def register_family(patterns: list[str], cap: ModelCapabilities) -> None:
        for pattern in patterns:
            registry[pattern] = cap

    register_family(
        ["*gemini-*-image-preview*", "gemini-*-image*"], CAP_GEMINI_IMAGE_GEN
    )

    register_family(PATTERNS_GEMINI_2_5, CAP_GEMINI_2_5)
    register_family(PATTERNS_GEMINI_3, CAP_GEMINI_3)

    register_family(PATTERNS_OPENAI_REASONING, CAP_OPENAI_REASONING)

    registry["gemini-*-tts"] = ModelCapabilities(
        input_modalities={ModelModality.TEXT},
        output_modalities={ModelModality.AUDIO},
    )
    registry["gemini-*-native-audio-*"] = ModelCapabilities(
        input_modalities={ModelModality.TEXT, ModelModality.AUDIO, ModelModality.VIDEO},
        output_modalities={ModelModality.TEXT, ModelModality.AUDIO},
        supports_tool_calling=True,
    )
    registry["gemini-2.0-flash-preview-image-generation"] = ModelCapabilities(
        input_modalities={
            ModelModality.TEXT,
            ModelModality.IMAGE,
            ModelModality.AUDIO,
            ModelModality.VIDEO,
        },
        output_modalities={ModelModality.TEXT, ModelModality.IMAGE},
        supports_tool_calling=True,
    )

    registry["GLM-4V-Flash"] = ModelCapabilities(
        input_modalities={ModelModality.TEXT, ModelModality.IMAGE},
        output_modalities={ModelModality.TEXT},
        supports_tool_calling=True,
    )
    registry["GLM-4V-Plus*"] = ModelCapabilities(
        input_modalities={ModelModality.TEXT, ModelModality.IMAGE, ModelModality.VIDEO},
        output_modalities={ModelModality.TEXT},
        supports_tool_calling=True,
    )

    register_family(
        ["glm-4-*", "glm-z1-*", "deepseek-chat"], STANDARD_TEXT_TOOL_CAPABILITIES
    )
    register_family(
        ["doubao-seed-*", "doubao-1-5-thinking-vision-pro"],
        DOUBAO_ADVANCED_MULTIMODAL_CAPABILITIES,
    )

    register_family(["gpt-5*", "gpt-4.1*", "o4-mini*"], CAP_GPT_ADVANCED)
    registry["gpt-4o*"] = CAP_GPT_MULTIMODAL_IO

    registry["gpt image*"] = GPT_IMAGE_GENERATION_CAPABILITIES
    registry["sora*"] = GPT_VIDEO_GENERATION_CAPABILITIES

    registry["*embedding*"] = EMBEDDING_CAPABILITIES

    return registry


MODEL_CAPABILITIES_REGISTRY = _build_registry()


def get_model_capabilities(model_name: str) -> ModelCapabilities:
    """
    从注册表获取模型能力，支持别名映射和通配符匹配。
    查找顺序: 1. 标准化名称 -> 2. 精确匹配 -> 3. 通配符匹配 -> 4. 默认值
    """
    canonical_name = model_name
    for alias_pattern, c_name in MODEL_ALIAS_MAPPING.items():
        if fnmatch.fnmatch(model_name, alias_pattern):
            canonical_name = c_name
            break

    parts = canonical_name.split("/")
    names_to_check = ["/".join(parts[i:]) for i in range(len(parts))]

    logger.trace(f"为 '{model_name}' 生成的检查列表: {names_to_check}")

    for name in names_to_check:
        if name in MODEL_CAPABILITIES_REGISTRY:
            logger.debug(f"模型 '{model_name}' 通过精确匹配 '{name}' 找到能力定义。")
            return MODEL_CAPABILITIES_REGISTRY[name]

        for pattern, capabilities in MODEL_CAPABILITIES_REGISTRY.items():
            if "*" in pattern and fnmatch.fnmatch(name, pattern):
                logger.debug(
                    f"模型 '{model_name}' 通过通配符匹配 '{name}'(pattern: '{pattern}')"
                    f"找到能力定义。"
                )
                return capabilities

    logger.warning(
        f"模型 '{model_name}' 的能力定义未在注册表中找到，将使用默认的'全功能'回退配置"
    )
    return DEFAULT_PERMISSIVE_CAPABILITIES
