"""
LLM 服务 - 会话记忆模块

定义了LLM会话记忆的存储、策略和处理接口。
"""

from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from zhenxun.services.llm.types import LLMMessage
from zhenxun.services.log import logger


class AIConfig(BaseModel):
    """AI配置类 (为保持独立性而在此处保留一个副本，实际使用中可能来自更高层)"""

    model: Any = None
    default_embedding_model: Any = None
    default_preserve_media_in_history: bool = False
    tool_providers: list[Any] = Field(default_factory=list)

    def __post_init__(self):
        """初始化后从配置中读取默认值"""
        pass


class BaseMessageStore(ABC):
    """
    底层存储接口 (DAO - Data Access Object)。

    这是一个抽象基类，定义了消息数据最底层的 **持久化与检索 (CRUD)** 接口。
    它只关心数据的存取，不涉及任何业务逻辑（如历史记录修剪）。

    开发者如果希望将对话历史存储到 Redis、数据库或其他持久化后端，
    应当实现这个接口。
    """

    @abstractmethod
    async def get_messages(self, session_id: str) -> list[LLMMessage]:
        """
        根据会话ID获取完整的消息列表。
        """
        raise NotImplementedError

    @abstractmethod
    async def add_messages(self, session_id: str, messages: list[LLMMessage]) -> None:
        """追加消息"""
        raise NotImplementedError

    @abstractmethod
    async def set_messages(self, session_id: str, messages: list[LLMMessage]) -> None:
        """
        完全覆盖指定会话ID的消息列表。
        主要用于历史记录修剪等场景。
        """
        raise NotImplementedError

    @abstractmethod
    async def clear(self, session_id: str) -> None:
        """清空指定会话ID的所有消息数据。"""
        raise NotImplementedError


class InMemoryMessageStore(BaseMessageStore):
    """
    一个基于内存的 `BaseMessageStore` 实现。

    它使用一个Python字典来存储所有会话的消息，提供了最简单、最快速的存储方案。
    这是框架的默认存储方式，实现了开箱即用。

    注意：此实现是 **非持久化** 的，当应用程序重启时，所有对话历史都会丢失。
    适用于测试、简单应用或不需要长期记忆的场景。
    """

    def __init__(self):
        self._data: dict[str, list[LLMMessage]] = defaultdict(list)

    async def get_messages(self, session_id: str) -> list[LLMMessage]:
        """从内存字典中获取消息列表的副本。"""
        return self._data.get(session_id, []).copy()

    async def add_messages(self, session_id: str, messages: list[LLMMessage]) -> None:
        """向内存中的消息列表追加消息。"""
        self._data[session_id].extend(messages)

    async def set_messages(self, session_id: str, messages: list[LLMMessage]) -> None:
        """在内存中直接替换指定会话的消息列表。"""
        self._data[session_id] = messages

    async def clear(self, session_id: str) -> None:
        """从内存字典中删除指定会话的条目。"""
        if session_id in self._data:
            del self._data[session_id]


class BaseMemory(ABC):
    """
    记忆系统上层逻辑基类 (Strategy Layer)。

    此抽象基类定义了记忆系统的 **策略层** 接口。它负责对外提供统一的记忆操作
    接口，并封装了具体的记忆管理策略，如历史记录的修剪、摘要生成等。

    `AI` 会话客户端直接与此接口交互，而不关心底层的存储实现。

    开发者可以通过实现此接口来创建自定义的记忆管理策略，例如：
    - `SummarizationMemory`: 在历史记录过长时，自动调用LLM生成摘要来压缩历史。
    - `VectorStoreMemory`: 将对话历史向量化并存入向量数据库，实现长期记忆检索。
    """

    @abstractmethod
    async def get_history(self, session_id: str) -> list[LLMMessage]:
        """获取用于构建模型输入的完整历史消息列表。"""
        raise NotImplementedError

    async def add_message(self, session_id: str, message: LLMMessage) -> None:
        """向记忆中添加单条消息。默认实现是调用 `add_messages`。"""
        await self.add_messages(session_id, [message])

    @abstractmethod
    async def add_messages(self, session_id: str, messages: list[LLMMessage]) -> None:
        """向记忆中添加多条消息，并可能触发内部的记忆管理策略（如修剪）。"""
        raise NotImplementedError

    @abstractmethod
    async def clear_history(self, session_id: str) -> None:
        """清空指定会话的全部记忆。"""
        raise NotImplementedError


class ChatMemory(BaseMemory):
    """
    标准聊天记忆实现：组合 Store + 滑动窗口策略。

    这是 `BaseMemory` 的默认实现，它通过组合一个 `BaseMessageStore` 实例来
    完成实际的数据存储，并在此之上实现了一个简单的“滑动窗口”记忆修剪策略。
    """

    def __init__(self, store: BaseMessageStore, max_messages: int = 50):
        self.store = store
        self._max_messages = max_messages

    async def _trim_history(self, session_id: str) -> None:
        """
        记忆修剪策略：确保历史记录不超过 `_max_messages` 条。

        如果存在系统消息 (System Prompt)，它将被永久保留在列表的第一位。
        """
        history = await self.store.get_messages(session_id)
        if len(history) <= self._max_messages:
            return

        has_system = history and history[0].role == "system"
        new_history: list[LLMMessage] = []

        if has_system:
            keep_count = max(0, self._max_messages - 1)
            new_history = [history[0], *history[-keep_count:]]
        else:
            new_history = history[-self._max_messages :]

        await self.store.set_messages(session_id, new_history)

    async def get_history(self, session_id: str) -> list[LLMMessage]:
        """直接从底层存储获取历史记录。"""
        return await self.store.get_messages(session_id)

    async def add_messages(self, session_id: str, messages: list[LLMMessage]) -> None:
        """添加消息到历史记录，并立即执行修剪策略。"""
        await self.store.add_messages(session_id, messages)
        await self._trim_history(session_id)

    async def clear_history(self, session_id: str) -> None:
        """清空底层存储中的历史记录。"""
        await self.store.clear(session_id)


class MemoryProcessor(ABC):
    """
    记忆处理器接口 (Hook/Observer)。

    这是一个扩展接口，允许开发者创建自定义的“记忆处理器”，以在记忆被修改后
    执行额外的操作（“钩子”）。

    当 `AI` 实例的记忆更新时，它会依次调用所有注册的 `MemoryProcessor`。

    使用场景示例：
    - `LoggingMemoryProcessor`: 将每一轮对话异步记录到外部日志系统。
    - `SummarizationProcessor`: 在后台任务中检查对话长度，并在需要时生成摘要。
    - `EntityExtractionProcessor`: 从对话中提取关键实体（如人名、地名）并存储。
    """

    @abstractmethod
    async def process(self, session_id: str, new_messages: list[LLMMessage]) -> None:
        """处理新添加到记忆中的消息。"""
        pass


_default_memory_factory: Callable[[], BaseMemory] | None = None


def set_default_memory_backend(factory: Callable[[], BaseMemory]):
    """
    设置全局默认记忆后端工厂，允许统一替换会话的记忆实现。

    这是一个高级依赖注入函数，允许插件或项目在启动时用自定义的 `BaseMemory`
    实现替换掉默认的 `ChatMemory(InMemoryMessageStore())`。

    Args:
        factory: 一个无参数的、返回 `BaseMemory` 实例的函数或类。
    """
    global _default_memory_factory
    _default_memory_factory = factory


def _get_default_memory() -> BaseMemory:
    """
    [内部函数] 获取一个默认的记忆后端实例。

    它会首先检查是否有通过 `set_default_memory_backend` 设置的全局工厂，
    如果有，则使用该工厂创建实例；否则，返回一个标准的内存记忆实例。
    """
    if _default_memory_factory:
        logger.debug("使用自定义的默认记忆后端工厂构建实例。")
        return _default_memory_factory()

    logger.debug("未配置自定义记忆后端，使用默认的 ChatMemory。")
    return ChatMemory(store=InMemoryMessageStore())


__all__ = [
    "AIConfig",
    "BaseMemory",
    "BaseMessageStore",
    "ChatMemory",
    "InMemoryMessageStore",
    "MemoryProcessor",
    "_get_default_memory",
    "set_default_memory_backend",
]
