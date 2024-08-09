from io import BytesIO
from pathlib import Path

from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot_plugin_alconna import At, Image, Text, UniMessage

from zhenxun.configs.config import NICKNAME
from zhenxun.services.log import logger
from zhenxun.utils._build_image import BuildImage

MESSAGE_TYPE = (
    str | int | float | Path | bytes | BytesIO | BuildImage | At | Image | Text
)


class MessageUtils:

    @classmethod
    def __build_message(cls, msg_list: list[MESSAGE_TYPE]) -> list[Text | Image]:
        """构造消息

        参数:
            msg_list: 消息列表

        返回:
            list[Text | Text]: 构造完成的消息列表
        """
        message_list = []
        for msg in msg_list:
            if isinstance(msg, (Image, Text, At)):
                message_list.append(msg)
            elif isinstance(msg, (str, int, float)):
                message_list.append(Text(str(msg)))
            elif isinstance(msg, Path):
                if msg.exists():
                    message_list.append(Image(path=msg))
                else:
                    logger.warning(f"图片路径不存在: {msg}")
            elif isinstance(msg, bytes):
                message_list.append(Image(raw=msg))
            elif isinstance(msg, BytesIO):
                message_list.append(Image(raw=msg))
            elif isinstance(msg, BuildImage):
                message_list.append(Image(raw=msg.pic2bytes()))
        return message_list

    @classmethod
    def build_message(
        cls, msg_list: MESSAGE_TYPE | list[MESSAGE_TYPE | list[MESSAGE_TYPE]]
    ) -> UniMessage:
        """构造消息

        参数:
            msg_list: 消息列表

        返回:
            UniMessage: 构造完成的消息列表
        """
        message_list = []
        if not isinstance(msg_list, list):
            msg_list = [msg_list]
        for m in msg_list:
            _data = m if isinstance(m, list) else [m]
            message_list += cls.__build_message(_data)  # type: ignore
        return UniMessage(message_list)

    @classmethod
    def custom_forward_msg(
        cls,
        msg_list: list[str | Message],
        uin: str,
        name: str = f"这里是{NICKNAME}",
    ) -> list[dict]:
        """生成自定义合并消息

        参数:
            msg_list: 消息列表
            uin: 发送者 QQ
            name: 自定义名称

        返回:
            list[dict]: 转发消息
        """
        mes_list = []
        for _message in msg_list:
            data = {
                "type": "node",
                "data": {
                    "name": name,
                    "uin": f"{uin}",
                    "content": _message,
                },
            }
            mes_list.append(data)
        return mes_list

    @classmethod
    def template2forward(cls, msg_list: list[UniMessage], uni: str) -> list[dict]:
        """模板转转发消息

        参数:
            msg_list: 消息列表
            uni: 发送者qq

        返回:
            list[dict]: 转发消息
        """
        forward_data = []
        for r_list in msg_list:
            s = ""
            if isinstance(r_list, (UniMessage, list)):
                for r in r_list:
                    if isinstance(r, Text):
                        s += str(r)
                    elif isinstance(r, Image):
                        if v := r.url or r.path:
                            s += MessageSegment.image(v)
            elif isinstance(r_list, Image):
                if v := r_list.url or r_list.path:
                    s = MessageSegment.image(v)
            else:
                s = str(r_list)
            forward_data.append(s)
        return cls.custom_forward_msg(forward_data, uni)