"""
LLM 生成配置相关类和函数
"""

from collections.abc import Callable
from enum import Enum
from typing import Any, Literal
from typing_extensions import Self

from pydantic import BaseModel, ConfigDict, Field

from zhenxun.services.log import logger
from zhenxun.utils.pydantic_compat import model_copy, model_dump, model_validate

from ..types import LLMResponse, ResponseFormat, StructuredOutputStrategy
from ..types.exceptions import LLMErrorCode, LLMException
from .providers import get_gemini_safety_threshold


class ReasoningEffort(str, Enum):
    """推理努力程度枚举"""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ImageAspectRatio(str, Enum):
    """图像宽高比枚举"""

    SQUARE = "1:1"
    LANDSCAPE_16_9 = "16:9"
    PORTRAIT_9_16 = "9:16"
    LANDSCAPE_4_3 = "4:3"
    PORTRAIT_3_4 = "3:4"
    LANDSCAPE_3_2 = "3:2"
    PORTRAIT_2_3 = "2:3"


class ImageResolution(str, Enum):
    """图像分辨率/质量枚举"""

    STANDARD = "STANDARD"
    HD = "HD"


class CoreConfig(BaseModel):
    """核心生成参数"""

    temperature: float | None = Field(
        default=None, ge=0.0, le=2.0, description="生成温度"
    )
    """生成温度"""
    max_tokens: int | None = Field(default=None, gt=0, description="最大输出token数")
    """最大输出token数"""
    top_p: float | None = Field(default=None, ge=0.0, le=1.0, description="核采样参数")
    """核采样参数"""
    top_k: int | None = Field(default=None, gt=0, description="Top-K采样参数")
    """Top-K采样参数"""
    frequency_penalty: float | None = Field(
        default=None, ge=-2.0, le=2.0, description="频率惩罚"
    )
    """频率惩罚"""
    presence_penalty: float | None = Field(
        default=None, ge=-2.0, le=2.0, description="存在惩罚"
    )
    """存在惩罚"""
    repetition_penalty: float | None = Field(
        default=None, ge=0.0, le=2.0, description="重复惩罚"
    )
    """重复惩罚"""
    stop: list[str] | str | None = Field(default=None, description="停止序列")
    """停止序列"""


class ReasoningConfig(BaseModel):
    """推理能力配置"""

    effort: ReasoningEffort | None = Field(
        default=None, description="推理努力程度 (适用于 O1, Gemini 3)"
    )
    """推理努力程度 (适用于 O1, Gemini 3)"""
    budget_tokens: int | None = Field(
        default=None, description="具体的思考 Token 预算 (适用于 Gemini 2.5)"
    )
    """具体的思考 Token 预算 (适用于 Gemini 2.5)"""
    show_thoughts: bool | None = Field(
        default=None, description="是否在响应中显式包含思维链内容"
    )
    """是否在响应中显式包含思维链内容"""


class VisualConfig(BaseModel):
    """视觉生成配置"""

    aspect_ratio: ImageAspectRatio | str | None = Field(
        default=None, description="宽高比"
    )
    """宽高比"""
    resolution: ImageResolution | str | None = Field(
        default=None, description="生成质量/分辨率"
    )
    """生成质量/分辨率"""
    media_resolution: str | None = Field(
        default=None,
        description="输入媒体的解析度 (Gemini 3+): 'LOW', 'MEDIUM', 'HIGH'",
    )
    """输入媒体的解析度 (Gemini 3+): 'LOW', 'MEDIUM', 'HIGH'"""
    style: str | None = Field(
        default=None, description="图像风格 (如 DALL-E 3 vivid/natural)"
    )
    """图像风格 (如 DALL-E 3 vivid/natural)"""


class OutputConfig(BaseModel):
    """输出格式控制"""

    response_format: ResponseFormat | dict[str, Any] | None = Field(
        default=None, description="期望的响应格式"
    )
    """期望的响应格式"""
    response_mime_type: str | None = Field(
        default=None, description="响应MIME类型（Gemini专用）"
    )
    """响应MIME类型（Gemini专用）"""
    response_schema: dict[str, Any] | None = Field(
        default=None, description="JSON响应模式"
    )
    """JSON响应模式"""
    response_modalities: list[str] | None = Field(
        default=None, description="响应模态类型 (TEXT, IMAGE, AUDIO)"
    )
    """响应模态类型 (TEXT, IMAGE, AUDIO)"""
    structured_output_strategy: StructuredOutputStrategy | str | None = Field(
        default=None, description="结构化输出策略 (NATIVE/TOOL_CALL/PROMPT)"
    )
    """结构化输出策略 (NATIVE/TOOL_CALL/PROMPT)"""


class SafetyConfig(BaseModel):
    """安全设置"""

    safety_settings: dict[str, str] | None = Field(default=None, description="安全设置")
    """安全设置"""


class ToolConfig(BaseModel):
    """工具调用控制配置"""

    mode: Literal["AUTO", "ANY", "NONE"] = Field(
        default="AUTO",
        description="工具调用模式: AUTO(自动), ANY(强制), NONE(禁用)",
    )
    """工具调用模式: AUTO(自动), ANY(强制), NONE(禁用)"""
    allowed_function_names: list[str] | None = Field(
        default=None,
        description="当 mode 为 ANY 时，允许调用的函数名称白名单",
    )
    """当 mode 为 ANY 时，允许调用的函数名称白名单"""


class LLMGenerationConfig(BaseModel):
    """
    LLM 生成配置
    采用组件化设计，不再扁平化参数。
    """

    core: CoreConfig | None = Field(default=None, description="基础生成参数")
    """基础生成参数"""
    reasoning: ReasoningConfig | None = Field(default=None, description="推理能力配置")
    """推理能力配置"""
    visual: VisualConfig | None = Field(default=None, description="视觉生成配置")
    """视觉生成配置"""
    output: OutputConfig | None = Field(default=None, description="输出格式配置")
    """输出格式配置"""
    safety: SafetyConfig | None = Field(default=None, description="安全配置")
    """安全配置"""
    tool_config: ToolConfig | None = Field(default=None, description="工具调用策略配置")
    """工具调用策略配置"""

    enable_caching: bool | None = Field(default=None, description="是否启用响应缓存")
    """是否启用响应缓存"""

    custom_params: dict[str, Any] | None = Field(default=None, description="自定义参数")
    """自定义参数"""

    validation_policy: dict[str, Any] | None = Field(
        default=None, description="声明式的响应验证策略 (例如: {'require_image': True})"
    )
    """声明式的响应验证策略 (例如: {'require_image': True})"""
    response_validator: Callable[[LLMResponse], None] | None = Field(
        default=None,
        description="一个高级回调函数，用于验证响应，验证失败时应抛出异常",
    )
    """一个高级回调函数，用于验证响应，验证失败时应抛出异常"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def builder(cls) -> "GenConfigBuilder":
        """创建一个新的配置构建器"""
        return GenConfigBuilder()

    def to_dict(self) -> dict[str, Any]:
        """
        转换为字典，排除None值。
        注意：这会返回嵌套结构的字典。适配器需要处理这种嵌套。
        """
        return model_dump(self, exclude_none=True)

    def merge_with(self, other: "LLMGenerationConfig | None") -> "LLMGenerationConfig":
        """
        与另一个配置对象进行深度合并。
        other 中的非 None 字段会覆盖当前配置中的对应字段。
        返回一个新的配置对象，原对象不变。
        """
        if not other:
            return model_copy(self, deep=True)

        new_config = model_copy(self, deep=True)

        def _merge_component(base_comp, override_comp, comp_cls):
            if override_comp is None:
                return base_comp
            if base_comp is None:
                return override_comp
            updates = model_dump(override_comp, exclude_none=True)
            return model_copy(base_comp, update=updates)

        new_config.core = _merge_component(new_config.core, other.core, CoreConfig)
        new_config.reasoning = _merge_component(
            new_config.reasoning, other.reasoning, ReasoningConfig
        )
        new_config.visual = _merge_component(
            new_config.visual, other.visual, VisualConfig
        )
        new_config.output = _merge_component(
            new_config.output, other.output, OutputConfig
        )
        new_config.safety = _merge_component(
            new_config.safety, other.safety, SafetyConfig
        )
        new_config.tool_config = _merge_component(
            new_config.tool_config, other.tool_config, ToolConfig
        )

        if other.enable_caching is not None:
            new_config.enable_caching = other.enable_caching

        if other.custom_params:
            if new_config.custom_params is None:
                new_config.custom_params = {}
            new_config.custom_params.update(other.custom_params)

        if other.validation_policy:
            if new_config.validation_policy is None:
                new_config.validation_policy = {}
            new_config.validation_policy.update(other.validation_policy)

        if other.response_validator:
            new_config.response_validator = other.response_validator

        return new_config


class LLMEmbeddingConfig(BaseModel):
    """Embedding 专用配置"""

    task_type: str | None = Field(default=None, description="任务类型 (Gemini/Jina)")
    """任务类型 (Gemini/Jina)"""
    output_dimensionality: int | None = Field(
        default=None, description="输出维度/压缩维度 (Gemini/Jina/OpenAI)"
    )
    """输出维度/压缩维度 (Gemini/Jina/OpenAI)"""
    title: str | None = Field(
        default=None, description="仅用于 Gemini RETRIEVAL_DOCUMENT 任务的标题"
    )
    """仅用于 Gemini RETRIEVAL_DOCUMENT 任务的标题"""
    encoding_format: str | None = Field(
        default="float", description="编码格式 (float/base64)"
    )
    """编码格式 (float/base64)"""

    model_config = ConfigDict(arbitrary_types_allowed=True)


class GenConfigBuilder:
    """
    LLM 生成配置的语义化构建器。
    设计原则：高频业务场景优先，低频参数命名空间化。
    """

    def __init__(self):
        self._config = LLMGenerationConfig()

    def _ensure_core(self) -> CoreConfig:
        if self._config.core is None:
            self._config.core = CoreConfig()
        return self._config.core

    def _ensure_output(self) -> OutputConfig:
        if self._config.output is None:
            self._config.output = OutputConfig()
        return self._config.output

    def _ensure_reasoning(self) -> ReasoningConfig:
        if self._config.reasoning is None:
            self._config.reasoning = ReasoningConfig()
        return self._config.reasoning

    def as_json(self, schema: dict[str, Any] | None = None) -> Self:
        """
        [高频] 强制模型输出 JSON 格式。
        """
        out = self._ensure_output()
        out.response_format = ResponseFormat.JSON
        if schema:
            out.response_schema = schema
        return self

    def enable_thinking(
        self, budget_tokens: int = -1, show_thoughts: bool = False
    ) -> Self:
        """
        [高频] 启用模型的思考/推理能力 (如 Gemini 2.0 Flash Thinking, DeepSeek R1)。
        """
        reasoning = self._ensure_reasoning()
        reasoning.budget_tokens = budget_tokens
        reasoning.show_thoughts = show_thoughts
        return self

    def config_core(
        self,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        stop: list[str] | str | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
    ) -> Self:
        """
        [低频] 配置核心生成参数。
        """
        core = self._ensure_core()
        if temperature is not None:
            core.temperature = temperature
        if max_tokens is not None:
            core.max_tokens = max_tokens
        if top_p is not None:
            core.top_p = top_p
        if top_k is not None:
            core.top_k = top_k
        if stop is not None:
            core.stop = stop
        if frequency_penalty is not None:
            core.frequency_penalty = frequency_penalty
        if presence_penalty is not None:
            core.presence_penalty = presence_penalty
        return self

    def config_safety(self, settings: dict[str, str]) -> Self:
        """
        [低频] 配置安全过滤设置。
        """
        if self._config.safety is None:
            self._config.safety = SafetyConfig()
        self._config.safety.safety_settings = settings
        return self

    def config_visual(
        self,
        aspect_ratio: ImageAspectRatio | str | None = None,
        resolution: ImageResolution | str | None = None,
    ) -> Self:
        """
        [低频] 配置视觉生成参数 (DALL-E 3 / Gemini Imagen)。
        """
        if self._config.visual is None:
            self._config.visual = VisualConfig()
        if aspect_ratio:
            self._config.visual.aspect_ratio = aspect_ratio
        if resolution:
            self._config.visual.resolution = resolution
        return self

    def set_custom_param(self, key: str, value: Any) -> Self:
        """设置特定于厂商的自定义参数"""
        if self._config.custom_params is None:
            self._config.custom_params = {}
        self._config.custom_params[key] = value
        return self

    def build(self) -> LLMGenerationConfig:
        """构建最终的配置对象"""
        return self._config


def validate_override_params(
    override_config: dict[str, Any] | LLMGenerationConfig | None,
) -> LLMGenerationConfig:
    """验证和标准化覆盖参数"""
    if override_config is None:
        return LLMGenerationConfig()

    if isinstance(override_config, LLMGenerationConfig):
        return override_config

    if isinstance(override_config, dict):
        try:
            return model_validate(LLMGenerationConfig, override_config)
        except Exception as e:
            logger.warning(f"覆盖配置参数验证失败: {e}")
            raise LLMException(
                f"无效的覆盖配置参数: {e}",
                code=LLMErrorCode.CONFIGURATION_ERROR,
                cause=e,
            )

    raise LLMException(
        f"不支持的配置类型: {type(override_config)}",
        code=LLMErrorCode.CONFIGURATION_ERROR,
    )


class CommonOverrides:
    """常用的配置覆盖预设"""

    @staticmethod
    def gemini_json() -> LLMGenerationConfig:
        """Gemini JSON模式：强制JSON输出"""
        return LLMGenerationConfig(
            core=CoreConfig(),
            output=OutputConfig(
                response_format=ResponseFormat.JSON,
                response_mime_type="application/json",
            ),
        )

    @staticmethod
    def gemini_2_5_thinking(tokens: int = -1) -> LLMGenerationConfig:
        """Gemini 2.5 思考模式：默认 -1 (动态思考)，0 为禁用，>=1024 为固定预算"""
        return LLMGenerationConfig(
            core=CoreConfig(temperature=1.0),
            reasoning=ReasoningConfig(budget_tokens=tokens, show_thoughts=True),
        )

    @staticmethod
    def gemini_3_thinking(level: str = "HIGH") -> LLMGenerationConfig:
        """Gemini 3 深度思考模式：使用思考等级"""
        try:
            effort = ReasoningEffort(level.upper())
        except ValueError:
            effort = ReasoningEffort.HIGH

        return LLMGenerationConfig(
            core=CoreConfig(),
            reasoning=ReasoningConfig(effort=effort, show_thoughts=True),
        )

    @staticmethod
    def gemini_structured(schema: dict[str, Any]) -> LLMGenerationConfig:
        """Gemini 结构化输出：自定义JSON模式"""
        return LLMGenerationConfig(
            core=CoreConfig(),
            output=OutputConfig(
                response_mime_type="application/json", response_schema=schema
            ),
        )

    @staticmethod
    def gemini_safe() -> LLMGenerationConfig:
        """Gemini 安全模式：使用配置的安全设置"""
        threshold = get_gemini_safety_threshold()
        return LLMGenerationConfig(
            core=CoreConfig(),
            safety=SafetyConfig(
                safety_settings={
                    "HARM_CATEGORY_HARASSMENT": threshold,
                    "HARM_CATEGORY_HATE_SPEECH": threshold,
                    "HARM_CATEGORY_SEXUALLY_EXPLICIT": threshold,
                    "HARM_CATEGORY_DANGEROUS_CONTENT": threshold,
                }
            ),
        )

    @staticmethod
    def gemini_code_execution() -> LLMGenerationConfig:
        """Gemini 代码执行模式：启用代码执行功能"""
        return LLMGenerationConfig(
            core=CoreConfig(),
            custom_params={"code_execution_timeout": 30},
        )

    @staticmethod
    def gemini_grounding() -> LLMGenerationConfig:
        """Gemini 信息来源关联模式：启用Google搜索"""
        return LLMGenerationConfig(
            core=CoreConfig(),
            custom_params={
                "grounding_config": {"dynamicRetrievalConfig": {"mode": "MODE_DYNAMIC"}}
            },
        )

    @staticmethod
    def gemini_nano_banana(aspect_ratio: str = "16:9") -> LLMGenerationConfig:
        """Gemini Nano Banana Pro：自定义比例生图"""
        try:
            ar = ImageAspectRatio(aspect_ratio)
        except ValueError:
            ar = ImageAspectRatio.LANDSCAPE_16_9

        return LLMGenerationConfig(
            core=CoreConfig(),
            visual=VisualConfig(aspect_ratio=ar),
        )

    @staticmethod
    def gemini_high_res() -> LLMGenerationConfig:
        """Gemini 3: 强制使用高解析度处理输入媒体"""
        return LLMGenerationConfig(
            visual=VisualConfig(media_resolution="HIGH", resolution=ImageResolution.HD)
        )
