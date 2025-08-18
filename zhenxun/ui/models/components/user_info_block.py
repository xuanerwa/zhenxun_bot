from typing import Literal

from pydantic import Field

from ..core.base import RenderableComponent

__all__ = ["UserInfoBlock"]


class UserInfoBlock(RenderableComponent):
    """一个带头像、名称和副标题的用户信息块组件。"""

    component_type: Literal["user_info_block"] = "user_info_block"
    avatar_url: str = Field(..., description="用户头像的URL")
    name: str = Field(..., description="用户的名称")
    subtitle: str | None = Field(
        default=None, description="显示在名称下方的副标题 (如UID或角色)"
    )
    tags: list[str] = Field(default_factory=list, description="附加的标签列表")

    @property
    def template_name(self) -> str:
        return "components/widgets/user_info_block"
