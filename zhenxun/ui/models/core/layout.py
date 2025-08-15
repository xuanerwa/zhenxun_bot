from typing import Any

from pydantic import BaseModel, Field

__all__ = ["LayoutData", "LayoutItem"]


class LayoutItem(BaseModel):
    """布局中的单个项目，通常是一张图片"""

    src: str = Field(..., description="图片的Base64数据URI")
    metadata: dict[str, Any] | None = Field(None, description="传递给模板的额外元数据")


class LayoutData(BaseModel):
    """布局构建器的数据模型"""

    style_name: str | None = None
    items: list[LayoutItem] = Field(
        default_factory=list, description="要布局的项目列表"
    )
    options: dict[str, Any] = Field(
        default_factory=dict, description="传递给模板的布局选项"
    )
