"""
DeepSeek API客户端
提供高效的异步API调用和错误处理
"""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
import aiohttp
import structlog
from asyncio_throttle import Throttler

from ..security.config import get_config

logger = structlog.get_logger(__name__)


@dataclass
class ChatMessage:
    """聊天消息"""
    role: str
    content: str


@dataclass
class ChatCompletionResponse:
    """聊天完成响应"""
    id: str
    object: str
    created: int
    model: str
    choices: List[Dict[str, Any]]
    usage: Dict[str, int]


@dataclass
class APIError(Exception):
    """API错误"""
    status_code: int
    message: str
    type: Optional[str] = None
    param: Optional[str] = None
    code: Optional[str] = None


class DeepSeekClient:
    """DeepSeek API客户端"""
    
    def __init__(self):
        self.config = get_config()
        self.api_key = self.config.api.deepseek_api_key
        self.api_base = self.config.api.deepseek_api_base
        
        # 设置请求限制
        self.throttler = Throttler(
            rate_limit=self.config.api.max_concurrent_requests,
            period=1.0
        )
        
        # 创建会话
        self.session: Optional[aiohttp.ClientSession] = None
        self._session_lock = asyncio.Lock()
        
        # 统计信息
        self.request_count = 0
        self.total_tokens = 0
        self.total_request_time = 0
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建HTTP会话"""
        if self.session is None or self.session.closed:
            async with self._session_lock:
                if self.session is None or self.session.closed:
                    timeout = aiohttp.ClientTimeout(total=self.config.api.request_timeout)
                    self.session = aiohttp.ClientSession(
                        timeout=timeout,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json"
                        }
                    )
        return self.session
    
    async def close(self):
        """关闭客户端"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """发起API请求"""
        
        url = f"{self.api_base}/{endpoint.lstrip('/')}"
        
        async with self.throttler:
            start_time = time.time()
            
            try:
                session = await self._get_session()
                
                async with session.request(
                    method=method,
                    url=url,
                    json=json_data,
                    params=params
                ) as response:
                    
                    request_time = time.time() - start_time
                    
                    # 更新统计
                    self.request_count += 1
                    self.total_request_time += request_time
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # 更新token统计
                        if 'usage' in data:
                            self.total_tokens += data['usage'].get('total_tokens', 0)
                        
                        logger.debug(
                            "API请求成功",
                            endpoint=endpoint,
                            status_code=response.status,
                            request_time=f"{request_time:.2f}s",
                            usage=data.get('usage', {})
                        )
                        
                        return data
                    
                    else:
                        error_data = await response.json()
                        error_msg = error_data.get('error', {}).get('message', 'Unknown error')
                        
                        logger.error(
                            "API请求失败",
                            endpoint=endpoint,
                            status_code=response.status,
                            error=error_msg,
                            request_time=f"{request_time:.2f}s"
                        )
                        
                        raise APIError(
                            status_code=response.status,
                            message=error_msg,
                            type=error_data.get('error', {}).get('type'),
                            param=error_data.get('error', {}).get('param'),
                            code=error_data.get('error', {}).get('code')
                        )
            
            except aiohttp.ClientError as e:
                request_time = time.time() - start_time
                logger.error(
                    "网络请求失败",
                    endpoint=endpoint,
                    error=str(e),
                    request_time=f"{request_time:.2f}s"
                )
                raise APIError(status_code=0, message=f"Network error: {str(e)}")
            
            except asyncio.TimeoutError:
                request_time = time.time() - start_time
                logger.error(
                    "API请求超时",
                    endpoint=endpoint,
                    request_time=f"{request_time:.2f}s"
                )
                raise APIError(status_code=0, message="Request timeout")
    
    async def chat_completion(
        self,
        messages: List[Union[Dict[str, str], ChatMessage]],
        model: str = "deepseek-chat",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        top_p: float = 1.0,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
        stop: Optional[Union[str, List[str]]] = None,
        stream: bool = False
    ) -> ChatCompletionResponse:
        """聊天完成接口"""
        
        # 转换消息格式
        formatted_messages = []
        for msg in messages:
            if isinstance(msg, ChatMessage):
                formatted_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
            else:
                formatted_messages.append(msg)
        
        payload = {
            "model": model,
            "messages": formatted_messages,
            "temperature": temperature,
            "top_p": top_p,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty,
            "stream": stream
        }
        
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        if stop:
            payload["stop"] = stop
        
        # 重试逻辑
        retry_count = 0
        last_error = None
        
        while retry_count < self.config.api.retry_attempts:
            try:
                data = await self._make_request("POST", "chat/completions", payload)
                return ChatCompletionResponse(
                    id=data["id"],
                    object=data["object"],
                    created=data["created"],
                    model=data["model"],
                    choices=data["choices"],
                    usage=data.get("usage", {})
                )
            
            except APIError as e:
                last_error = e
                
                # 对于服务器错误或限流错误，进行重试
                if e.status_code >= 500 or e.status_code == 429:
                    retry_count += 1
                    if retry_count < self.config.api.retry_attempts:
                        # 指数退避
                        wait_time = min(2 ** retry_count, 10)
                        logger.warning(
                            "API请求失败，准备重试",
                            attempt=retry_count,
                            max_attempts=self.config.api.retry_attempts,
                            wait_time=wait_time,
                            error=e.message
                        )
                        await asyncio.sleep(wait_time)
                        continue
                
                # 对于其他错误，直接抛出
                raise e
        
        # 重试次数用完，抛出最后一个错误
        if last_error:
            raise last_error
        else:
            raise APIError(status_code=0, message="Max retry attempts exceeded")
    
    async def get_models(self) -> List[Dict[str, Any]]:
        """获取可用模型列表"""
        data = await self._make_request("GET", "models")
        return data.get("data", [])
    
    async def get_model_info(self, model_id: str) -> Dict[str, Any]:
        """获取模型信息"""
        data = await self._make_request("GET", f"models/{model_id}")
        return data
    
    def get_stats(self) -> Dict[str, Any]:
        """获取API使用统计"""
        avg_request_time = self.total_request_time / self.request_count if self.request_count > 0 else 0
        
        return {
            "request_count": self.request_count,
            "total_tokens": self.total_tokens,
            "total_request_time": self.total_request_time,
            "avg_request_time": avg_request_time,
            "tokens_per_request": self.total_tokens / self.request_count if self.request_count > 0 else 0
        }
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            await self.get_models()
            return True
        except Exception as e:
            logger.error("API健康检查失败", error=str(e))
            return False


# 全局DeepSeek客户端实例
deepseek_client = DeepSeekClient()