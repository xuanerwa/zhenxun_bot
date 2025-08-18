from pydantic import BaseModel, Field

from ..core.base import RenderableComponent

__all__ = [
    "InfoCardData",
    "InfoCardMetadataItem",
    "InfoCardSection",
]


class InfoCardMetadataItem(BaseModel):
    """信息卡片元数据项"""

    label: str
    value: str | int


class InfoCardSection(BaseModel):
    """信息卡片内容区块"""

    title: str
    content: list[str] = Field(..., description="内容段落列表")


class InfoCardData(RenderableComponent):
    """通用信息卡片的数据模型"""

    style_name: str | None = None
    title: str = Field(..., description="卡片主标题")
    metadata: list[InfoCardMetadataItem] = Field(default_factory=list)
    sections: list[InfoCardSection] = Field(default_factory=list)

    @property
    def template_name(self) -> str:
        return "components/presets/info_card"
