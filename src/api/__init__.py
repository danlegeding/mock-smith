"""接口层：把 LangGraph 图包成 HTTP 服务。"""

from src.api.routes import api_router

__all__ = ["api_router"]
