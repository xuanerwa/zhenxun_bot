# Zhenxun LLM 服务模块

## 📑 目录

- [📖 概述](#-概述)
- [🌟 主要特性](#-主要特性)
- [🚀 快速开始](#-快速开始)
- [📚 API 参考](#-api-参考)
- [⚙️ 配置](#️-配置)
- [🔧 高级功能](#-高级功能)
- [🏗️ 架构设计](#️-架构设计)
- [🔌 支持的提供商](#-支持的提供商)
- [🎯 使用场景](#-使用场景)
- [📊 性能优化](#-性能优化)
- [🛠️ 故障排除](#️-故障排除)
- [❓ 常见问题](#-常见问题)
- [📝 示例项目](#-示例项目)
- [🤝 贡献](#-贡献)
- [📄 许可证](#-许可证)

## 📖 概述

Zhenxun LLM 服务模块是一个现代化的AI服务框架，提供统一的接口来访问多个大语言模型提供商。该模块采用模块化设计，支持异步操作、智能重试、Key轮询和负载均衡等高级功能。

### 🌟 主要特性

- **多提供商支持**: OpenAI、Gemini、智谱AI、DeepSeek等
- **统一接口**: 简洁一致的API设计
- **智能Key轮询**: 自动负载均衡和故障转移
- **异步高性能**: 基于asyncio的并发处理
- **模型缓存**: 智能缓存机制提升性能
- **工具调用**: 支持Function Calling
- **嵌入向量**: 文本向量化支持
- **错误处理**: 完善的异常处理和重试机制
- **多模态支持**: 文本、图像、音频、视频处理
- **代码执行**: Gemini代码执行功能
- **搜索增强**: Google搜索集成

## 🚀 快速开始

### 基本使用

```python
from zhenxun.services.llm import chat, code, search, analyze

# 简单聊天
response = await chat("你好，请介绍一下自己")
print(response)

# 代码执行
result = await code("计算斐波那契数列的前10项")
print(result["text"])
print(result["code_executions"])

# 搜索功能
search_result = await search("Python异步编程最佳实践")
print(search_result["text"])

# 多模态分析
from nonebot_plugin_alconna.uniseg import UniMessage, Image, Text
message = UniMessage([
    Text("分析这张图片"),
    Image(path="image.jpg")
])
analysis = await analyze(message, model="Gemini/gemini-2.0-flash")
print(analysis)
```

### 使用AI类

```python
from zhenxun.services.llm import AI, AIConfig, CommonOverrides

# 创建AI实例
ai = AI(AIConfig(model="OpenAI/gpt-4"))

# 聊天对话
response = await ai.chat("解释量子计算的基本原理")

# 多模态分析
from nonebot_plugin_alconna.uniseg import UniMessage, Image, Text

multimodal_msg = UniMessage([
    Text("这张图片显示了什么？"),
    Image(path="image.jpg")
])
result = await ai.analyze(multimodal_msg)

# 便捷的多模态函数
result = await analyze_with_images(
    "分析这张图片",
    images="image.jpg",
    model="Gemini/gemini-2.0-flash"
)
```

## 📚 API 参考

### 快速函数

#### `chat(message, *, model=None, **kwargs) -> str`
简单聊天对话

**参数:**
- `message`: 消息内容（字符串、LLMMessage或内容部分列表）
- `model`: 模型名称（可选）
- `**kwargs`: 额外配置参数

#### `code(prompt, *, model=None, timeout=None, **kwargs) -> dict`
代码执行功能

**返回:**
```python
{
    "text": "执行结果说明",
    "code_executions": [{"code": "...", "output": "..."}],
    "success": True
}
```

#### `search(query, *, model=None, instruction="", **kwargs) -> dict`
搜索增强生成

**返回:**
```python
{
    "text": "搜索结果和分析",
    "grounding_metadata": {...},
    "success": True
}
```

#### `analyze(message, *, instruction="", model=None, tools=None, tool_config=None, **kwargs) -> str | LLMResponse`
高级分析功能，支持多模态输入和工具调用

#### `analyze_with_images(text, images, *, instruction="", model=None, **kwargs) -> str`
图片分析便捷函数

#### `analyze_multimodal(text=None, images=None, videos=None, audios=None, *, instruction="", model=None, **kwargs) -> str`
多模态分析便捷函数

#### `embed(texts, *, model=None, task_type="RETRIEVAL_DOCUMENT", **kwargs) -> list[list[float]]`
文本嵌入向量

### AI类方法

#### `AI.chat(message, *, model=None, **kwargs) -> str`
聊天对话方法，支持简单多模态输入

#### `AI.analyze(message, *, instruction="", model=None, tools=None, tool_config=None, **kwargs) -> str | LLMResponse`
高级分析方法，接收UniMessage进行多模态分析和工具调用

### 模型管理

```python
from zhenxun.services.llm import (
    get_model_instance,
    list_available_models,
    set_global_default_model_name,
    clear_model_cache
)

# 获取模型实例
model = await get_model_instance("OpenAI/gpt-4o")

# 列出可用模型
models = list_available_models()

# 设置默认模型
set_global_default_model_name("Gemini/gemini-2.0-flash")

# 清理缓存
clear_model_cache()
```

## ⚙️ 配置

### 预设配置

```python
from zhenxun.services.llm import CommonOverrides

# 创意模式
creative_config = CommonOverrides.creative()

# 精确模式
precise_config = CommonOverrides.precise()

# Gemini特殊功能
json_config = CommonOverrides.gemini_json()
thinking_config = CommonOverrides.gemini_thinking()
code_exec_config = CommonOverrides.gemini_code_execution()
grounding_config = CommonOverrides.gemini_grounding()
```

### 自定义配置

```python
from zhenxun.services.llm import LLMGenerationConfig

config = LLMGenerationConfig(
    temperature=0.7,
    max_tokens=2048,
    top_p=0.9,
    frequency_penalty=0.1,
    presence_penalty=0.1,
    stop=["END", "STOP"],
    response_mime_type="application/json",
    enable_code_execution=True,
    enable_grounding=True
)

response = await chat("你的问题", override_config=config)
```

## 🔧 高级功能

### 工具调用 (Function Calling)

```python
from zhenxun.services.llm import LLMTool, get_model_instance

# 定义工具
tools = [
    LLMTool(
        name="get_weather",
        description="获取天气信息",
        parameters={
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名称"}
            },
            "required": ["city"]
        }
    )
]

# 工具执行器
async def tool_executor(tool_name: str, args: dict) -> str:
    if tool_name == "get_weather":
        return f"{args['city']}今天晴天，25°C"
    return "未知工具"

# 使用工具
model = await get_model_instance("OpenAI/gpt-4")
response = await model.generate_response(
    messages=[{"role": "user", "content": "北京天气如何？"}],
    tools=tools,
    tool_executor=tool_executor
)
```

### 多模态处理

```python
from zhenxun.services.llm import create_multimodal_message, analyze_multimodal, analyze_with_images

# 方法1：使用便捷函数
result = await analyze_multimodal(
    text="分析这些媒体文件",
    images="image.jpg",
    audios="audio.mp3",
    model="Gemini/gemini-2.0-flash"
)

# 方法2：使用create_multimodal_message
message = create_multimodal_message(
    text="分析这张图片和音频",
    images="image.jpg",
    audios="audio.mp3"
)
result = await analyze(message)

# 方法3：图片分析专用函数
result = await analyze_with_images(
    "这张图片显示了什么？",
    images=["image1.jpg", "image2.jpg"]
)
```

## 🛠️ 故障排除

### 常见错误

1. **配置错误**: 检查API密钥和模型配置
2. **网络问题**: 检查代理设置和网络连接
3. **模型不可用**: 使用 `list_available_models()` 检查可用模型
4. **超时错误**: 调整timeout参数或使用更快的模型

### 调试技巧

```python
from zhenxun.services.llm import get_cache_stats
from zhenxun.services.log import logger

# 查看缓存状态
stats = get_cache_stats()
print(f"缓存命中率: {stats['hit_rate']}")

# 启用详细日志
logger.setLevel("DEBUG")
```

## ❓ 常见问题


### Q: 如何处理多模态输入？

**A:** 有多种方式处理多模态输入：
```python
# 方法1：使用便捷函数
result = await analyze_with_images("分析这张图片", images="image.jpg")

# 方法2：使用analyze函数
from nonebot_plugin_alconna.uniseg import UniMessage, Image, Text
message = UniMessage([Text("分析这张图片"), Image(path="image.jpg")])
result = await analyze(message)

# 方法3：使用create_multimodal_message
from zhenxun.services.llm import create_multimodal_message
message = create_multimodal_message(text="分析这张图片", images="image.jpg")
result = await analyze(message)
```

### Q: 如何自定义工具调用？

**A:** 使用analyze函数的tools参数：
```python
# 定义工具
tools = [{
    "name": "calculator",
    "description": "计算数学表达式",
    "parameters": {
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "数学表达式"}
        },
        "required": ["expression"]
    }
}]

# 使用工具
from nonebot_plugin_alconna.uniseg import UniMessage, Text
message = UniMessage([Text("计算 2+3*4")])
response = await analyze(message, tools=tools, tool_config={"mode": "auto"})

# 如果返回LLMResponse，说明有工具调用
if hasattr(response, 'tool_calls'):
    for tool_call in response.tool_calls:
        print(f"调用工具: {tool_call.function.name}")
        print(f"参数: {tool_call.function.arguments}")
```


### Q: 如何确保输出格式？

**A:** 使用结构化输出：
```python
# JSON格式输出
config = CommonOverrides.gemini_json()

# 自定义Schema
schema = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "confidence": {"type": "number"}
    }
}
config = CommonOverrides.gemini_structured(schema)
```

## 📝 示例项目

### 完整示例

#### 1. 智能客服机器人

```python
from zhenxun.services.llm import AI, CommonOverrides
from typing import Dict, List

class CustomerService:
    def __init__(self):
        self.ai = AI()
        self.sessions: Dict[str, List[dict]] = {}

    async def handle_query(self, user_id: str, query: str) -> str:
        # 获取或创建会话历史
        if user_id not in self.sessions:
            self.sessions[user_id] = []

        history = self.sessions[user_id]

        # 添加系统提示
        if not history:
            history.append({
                "role": "system",
                "content": "你是一个专业的客服助手，请友好、准确地回答用户问题。"
            })

        # 添加用户问题
        history.append({"role": "user", "content": query})

        # 生成回复
        response = await self.ai.chat(
            query,
            history=history[-20:],  # 保留最近20轮对话
            override_config=CommonOverrides.balanced()
        )

        # 保存回复到历史
        history.append({"role": "assistant", "content": response})

        return response
```

#### 2. 文档智能问答

```python
from zhenxun.services.llm import embed, analyze
import numpy as np
from typing import List, Tuple

class DocumentQA:
    def __init__(self):
        self.documents: List[str] = []
        self.embeddings: List[List[float]] = []

    async def add_document(self, text: str):
        """添加文档到知识库"""
        self.documents.append(text)

        # 生成嵌入向量
        embedding = await embed([text])
        self.embeddings.extend(embedding)

    async def query(self, question: str, top_k: int = 3) -> str:
        """查询文档并生成答案"""
        if not self.documents:
            return "知识库为空，请先添加文档。"

        # 生成问题的嵌入向量
        question_embedding = await embed([question])

        # 计算相似度并找到最相关的文档
        similarities = []
        for doc_embedding in self.embeddings:
            similarity = np.dot(question_embedding[0], doc_embedding)
            similarities.append(similarity)

        # 获取最相关的文档
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        relevant_docs = [self.documents[i] for i in top_indices]

        # 构建上下文
        context = "\n\n".join(relevant_docs)
        prompt = f"""
基于以下文档内容回答问题：

文档内容：
{context}

问题：{question}

请基于文档内容给出准确的答案，如果文档中没有相关信息，请说明。
"""

        result = await analyze(prompt)
        return result["text"]
```

#### 3. 代码审查助手

```python
from zhenxun.services.llm import code, analyze
import os

class CodeReviewer:
    async def review_file(self, file_path: str) -> dict:
        """审查代码文件"""
        if not os.path.exists(file_path):
            return {"error": "文件不存在"}

        with open(file_path, 'r', encoding='utf-8') as f:
            code_content = f.read()

        prompt = f"""
请审查以下代码，提供详细的反馈：

文件：{file_path}
代码：
```
{code_content}
```

请从以下方面进行审查：
1. 代码质量和可读性
2. 潜在的bug和安全问题
3. 性能优化建议
4. 最佳实践建议
5. 代码风格问题

请以JSON格式返回结果。
"""

        result = await analyze(
            prompt,
            model="DeepSeek/deepseek-coder",
            override_config=CommonOverrides.gemini_json()
        )

        return {
            "file": file_path,
            "review": result["text"],
            "success": True
        }

    async def suggest_improvements(self, code: str, language: str = "python") -> str:
        """建议代码改进"""
        prompt = f"""
请改进以下{language}代码，使其更加高效、可读和符合最佳实践：

原代码：
```{language}
{code}
```

请提供改进后的代码和说明。
"""

        result = await code(prompt, model="DeepSeek/deepseek-coder")
        return result["text"]
```


## 🏗️ 架构设计

### 模块结构

```
zhenxun/services/llm/
├── __init__.py          # 包入口，导入和暴露公共API
├── api.py              # 高级API接口（AI类、便捷函数）
├── core.py             # 核心基础设施（HTTP客户端、重试逻辑、KeyStore）
├── service.py          # LLM模型实现类
├── utils.py            # 工具和转换函数
├── manager.py          # 模型管理和缓存
├── adapters/           # 适配器模块
│   ├── __init__.py    # 适配器包入口
│   ├── base.py        # 基础适配器
│   ├── factory.py     # 适配器工厂
│   ├── openai.py      # OpenAI适配器
│   ├── gemini.py      # Gemini适配器
│   └── zhipu.py       # 智谱AI适配器
├── config/            # 配置模块
│   ├── __init__.py    # 配置包入口
│   ├── generation.py  # 生成配置
│   ├── presets.py     # 预设配置
│   └── providers.py   # 提供商配置
└── types/             # 类型定义
    ├── __init__.py    # 类型包入口
    ├── content.py     # 内容类型
    ├── enums.py       # 枚举定义
    ├── exceptions.py  # 异常定义
    └── models.py      # 数据模型
```

### 模块职责

- **`__init__.py`**: 纯粹的包入口，只负责导入和暴露公共API
- **`api.py`**: 高级API接口，包含AI类和所有便捷函数
- **`core.py`**: 核心基础设施，包含HTTP客户端管理、重试逻辑和KeyStore
- **`service.py`**: LLM模型实现类，专注于模型逻辑
- **`utils.py`**: 工具和转换函数，如多模态消息处理
- **`manager.py`**: 模型管理和缓存机制
- **`adapters/`**: 各大提供商的适配器模块，负责与不同API的交互
  - `base.py`: 定义适配器的基础接口
  - `factory.py`: 适配器工厂，用于动态加载和实例化适配器
  - `openai.py`: OpenAI API适配器
  - `gemini.py`: Google Gemini API适配器
  - `zhipu.py`: 智谱AI API适配器
- **`config/`**: 配置管理模块
  - `generation.py`: 生成配置和预设
  - `presets.py`: 预设配置
  - `providers.py`: 提供商配置
- **`types/`**: 类型定义模块
  - `content.py`: 内容类型定义
  - `enums.py`: 枚举定义
  - `exceptions.py`: 异常定义
  - `models.py`: 数据模型定义

## 🔌 支持的提供商

### OpenAI 兼容

- **OpenAI**: GPT-4o, GPT-3.5-turbo等
- **DeepSeek**: deepseek-chat, deepseek-reasoner等
- **其他OpenAI兼容API**: 支持自定义端点

```python
# OpenAI
await chat("Hello", model="OpenAI/gpt-4o")

# DeepSeek
await chat("写代码", model="DeepSeek/deepseek-reasoner")
```

### Google Gemini

- **Gemini Pro**: gemini-2.5-flash-preview-05-20 gemini-2.0-flash等
- **特殊功能**: 代码执行、搜索增强、思考模式

```python
# 基础使用
await chat("你好", model="Gemini/gemini-2.0-flash")

# 代码执行
await code("计算质数", model="Gemini/gemini-2.0-flash")

# 搜索增强
await search("最新AI发展", model="Gemini/gemini-2.5-flash-preview-05-20")
```

### 智谱AI

- **GLM系列**: glm-4, glm-4v等
- **支持功能**: 文本生成、多模态理解

```python
await chat("介绍北京", model="Zhipu/glm-4")
```

## 🎯 使用场景

### 1. 聊天机器人

```python
from zhenxun.services.llm import AI, CommonOverrides

class ChatBot:
    def __init__(self):
        self.ai = AI()
        self.history = []

    async def chat(self, user_input: str) -> str:
        # 添加历史记录
        self.history.append({"role": "user", "content": user_input})

        # 生成回复
        response = await self.ai.chat(
            user_input,
            history=self.history[-10:],  # 保留最近10轮对话
            override_config=CommonOverrides.balanced()
        )

        self.history.append({"role": "assistant", "content": response})
        return response
```

### 2. 代码助手

```python
async def code_assistant(task: str) -> dict:
    """代码生成和执行助手"""
    result = await code(
        f"请帮我{task}，并执行代码验证结果",
        model="Gemini/gemini-2.0-flash",
        timeout=60
    )

    return {
        "explanation": result["text"],
        "code_blocks": result["code_executions"],
        "success": result["success"]
    }

# 使用示例
result = await code_assistant("实现快速排序算法")
```

### 3. 文档分析

```python
from zhenxun.services.llm import analyze_with_images

async def analyze_document(image_path: str, question: str) -> str:
    """分析文档图片并回答问题"""
    result = await analyze_with_images(
        f"请分析这个文档并回答：{question}",
        images=image_path,
        model="Gemini/gemini-2.0-flash"
    )
    return result
```

### 4. 智能搜索

```python
async def smart_search(query: str) -> dict:
    """智能搜索和总结"""
    result = await search(
        query,
        model="Gemini/gemini-2.0-flash",
        instruction="请提供准确、最新的信息，并注明信息来源"
    )

    return {
        "summary": result["text"],
        "sources": result.get("grounding_metadata", {}),
        "confidence": result.get("confidence_score", 0.0)
    }
```

## 🔧 配置管理


### 动态配置

```python
from zhenxun.services.llm import set_global_default_model_name

# 运行时更改默认模型
set_global_default_model_name("OpenAI/gpt-4")

# 检查可用模型
models = list_available_models()
for model in models:
    print(f"{model.provider}/{model.name} - {model.description}")
```

