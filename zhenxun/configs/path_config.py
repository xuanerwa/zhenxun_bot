from pathlib import Path

# 图片路径
IMAGE_PATH = Path() / "resources" / "image"
# 语音路径
RECORD_PATH = Path() / "resources" / "record"
# 文本路径
TEXT_PATH = Path() / "resources" / "text"
# 日志路径
LOG_PATH = Path() / "log"
# 字体路径
FONT_PATH = Path() / "resources" / "font"
# 数据路径
DATA_PATH = Path() / "data"
# 临时数据路径
TEMP_PATH = Path() / "resources" / "temp"
# 网页模板路径
THEMES_PATH = Path() / "resources" / "themes"
# [新增] UI渲染服务的统一缓存路径
UI_CACHE_PATH = TEMP_PATH / "ui_cache"


IMAGE_PATH.mkdir(parents=True, exist_ok=True)
RECORD_PATH.mkdir(parents=True, exist_ok=True)
TEXT_PATH.mkdir(parents=True, exist_ok=True)
LOG_PATH.mkdir(parents=True, exist_ok=True)
FONT_PATH.mkdir(parents=True, exist_ok=True)
DATA_PATH.mkdir(parents=True, exist_ok=True)
TEMP_PATH.mkdir(parents=True, exist_ok=True)
UI_CACHE_PATH.mkdir(parents=True, exist_ok=True)
