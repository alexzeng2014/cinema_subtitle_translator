"""
安全配置管理系统
提供企业级的配置管理、敏感数据加密和运行时验证
"""

import os
import secrets
from pathlib import Path
from typing import Any, Dict, Optional, Union
from cryptography.fernet import Fernet
from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings
import yaml
import json
import structlog

logger = structlog.get_logger(__name__)


class EncryptionConfig:
    """敏感数据加密配置"""
    
    def __init__(self, encryption_key: Optional[str] = None):
        self.key = self._get_or_create_key(encryption_key)
        self.cipher = Fernet(self.key.encode() if isinstance(self.key, str) else self.key)
    
    def _get_or_create_key(self, key: Optional[str]) -> bytes:
        """获取或创建加密密钥"""
        if key:
            return key.encode()
        
        # 尝试从环境变量获取
        env_key = os.getenv("ENCRYPTION_KEY")
        if env_key:
            return env_key.encode()
        
        # 生成新密钥
        new_key = Fernet.generate_key()
        logger.warning("Generated new encryption key. Please set ENCRYPTION_KEY environment variable.")
        return new_key
    
    def encrypt(self, data: Union[str, bytes]) -> str:
        """加密敏感数据"""
        if isinstance(data, str):
            data = data.encode()
        return self.cipher.encrypt(data).decode()
    
    def decrypt(self, encrypted_data: str) -> str:
        """解密敏感数据"""
        return self.cipher.decrypt(encrypted_data.encode()).decode()


class APIConfig(BaseModel):
    """API配置"""
    deepseek_api_key: str = Field(..., description="DeepSeek API密钥")
    deepseek_api_base: str = Field(default="https://api.deepseek.com/v1", description="API基础URL")
    max_concurrent_requests: int = Field(default=5, ge=1, le=20, description="最大并发请求数")
    request_timeout: int = Field(default=30, ge=5, le=120, description="请求超时时间")
    retry_attempts: int = Field(default=3, ge=1, le=10, description="重试次数")
    
    @validator('deepseek_api_key')
    def validate_api_key(cls, v):
        if not v or len(v) < 10:
            raise ValueError("API密钥格式无效")
        return v


class CacheConfig(BaseModel):
    """缓存配置"""
    redis_host: str = Field(default="localhost", description="Redis主机")
    redis_port: int = Field(default=6379, ge=1, le=65535, description="Redis端口")
    redis_password: Optional[str] = Field(default=None, description="Redis密码")
    redis_db: int = Field(default=0, ge=0, le=15, description="Redis数据库")
    cache_ttl: int = Field(default=3600, ge=60, description="缓存TTL(秒)")
    enable_disk_cache: bool = Field(default=True, description="启用磁盘缓存")
    cache_dir: str = Field(default="./cache", description="缓存目录")
    
    @validator('cache_dir')
    def validate_cache_dir(cls, v):
        path = Path(v)
        path.mkdir(parents=True, exist_ok=True)
        return str(path.absolute())


class PerformanceConfig(BaseModel):
    """性能配置"""
    batch_size: int = Field(default=10, ge=1, le=50, description="批处理大小")
    enable_async: bool = Field(default=True, description="启用异步处理")
    memory_limit_mb: int = Field(default=1024, ge=256, description="内存限制(MB)")
    enable_metrics: bool = Field(default=True, description="启用性能监控")


class SecurityConfig(BaseModel):
    """安全配置"""
    encryption_key: str = Field(..., description="加密密钥")
    jwt_secret: str = Field(..., description="JWT密钥")
    log_sensitive_data: bool = Field(default=False, description="记录敏感数据")
    allowed_file_types: list[str] = Field(default=[".srt", ".ass", ".vtt"], description="允许的文件类型")
    max_file_size_mb: int = Field(default=50, ge=1, le=500, description="最大文件大小(MB)")


class SystemConfig(BaseSettings):
    """系统配置"""
    api: APIConfig
    cache: CacheConfig
    performance: PerformanceConfig
    security: SecurityConfig
    
    log_level: str = Field(default="INFO", description="日志级别")
    debug_mode: bool = Field(default=False, description="调试模式")
    
    class Config:
        env_prefix = ""
        env_nested_delimiter = "__"
        case_sensitive = False
    
    @validator('log_level')
    def validate_log_level(cls, v):
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"日志级别必须是: {valid_levels}")
        return v.upper()


class UserPreferences(BaseModel):
    """用户偏好配置"""
    default_style: str = Field(default="balanced", description="默认翻译风格")
    default_quality: str = Field(default="high", description="默认质量等级")
    favorite_movies: list[str] = Field(default=[], description="收藏的电影")
    custom_styles: Dict[str, str] = Field(default={}, description="自定义翻译风格")
    language_preferences: Dict[str, str] = Field(default={}, description="语言偏好")
    auto_save: bool = Field(default=True, description="自动保存")
    output_format: str = Field(default="srt", description="输出格式")


class ConfigManager:
    """配置管理器 - 核心配置管理类"""
    
    def __init__(self):
        self.encryption = EncryptionConfig()
        self._config: Optional[SystemConfig] = None
        self._user_prefs: Optional[UserPreferences] = None
        self._config_dir = Path.home() / ".cinema-translator"
        self._setup_config_dir()
    
    def _setup_config_dir(self):
        """设置配置目录"""
        self._config_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建子目录
        (self._config_dir / "cache").mkdir(exist_ok=True)
        (self._config_dir / "logs").mkdir(exist_ok=True)
        
        # 设置目录权限 (在Unix系统上)
        try:
            os.chmod(self._config_dir, 0o700)
        except AttributeError:
            # Windows系统不支持chmod
            pass
    
    def load_config(self) -> SystemConfig:
        """加载系统配置"""
        if self._config is None:
            # 1. 优先从环境变量加载
            try:
                self._config = SystemConfig()
            except Exception as e:
                logger.warning("环境变量配置不完整，尝试从配置文件加载", error=str(e))
                
                # 2. 从配置文件加载
                config_file = self._config_dir / "config.yaml"
                if config_file.exists():
                    self._config = self._load_from_yaml(config_file)
                else:
                    # 3. 创建默认配置
                    self._config = self._create_default_config()
                    self.save_config(self._config)
        
        return self._config
    
    def _load_from_yaml(self, config_file: Path) -> SystemConfig:
        """从YAML文件加载配置"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            # 解密敏感字段
            if 'api' in data and 'deepseek_api_key' in data['api']:
                data['api']['deepseek_api_key'] = self.encryption.decrypt(
                    data['api']['deepseek_api_key']
                )
            
            return SystemConfig(**data)
        except Exception as e:
            logger.error("配置文件加载失败", error=str(e))
            raise
    
    def save_config(self, config: SystemConfig):
        """保存配置到文件"""
        config_file = self._config_dir / "config.yaml"
        
        # 转换为字典并加密敏感字段
        config_dict = config.dict()
        if 'api' in config_dict and 'deepseek_api_key' in config_dict['api']:
            config_dict['api']['deepseek_api_key'] = self.encryption.encrypt(
                config_dict['api']['deepseek_api_key']
            )
        
        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                yaml.dump(config_dict, f, default_flow_style=False, allow_unicode=True)
            
            # 设置文件权限
            try:
                os.chmod(config_file, 0o600)
            except AttributeError:
                pass
                
            logger.info("配置文件保存成功", file=str(config_file))
        except Exception as e:
            logger.error("配置文件保存失败", error=str(e))
            raise
    
    def _create_default_config(self) -> SystemConfig:
        """创建默认配置"""
        return SystemConfig(
            api=APIConfig(
                deepseek_api_key="your_api_key_here",
                deepseek_api_base="https://api.deepseek.com/v1"
            ),
            cache=CacheConfig(),
            performance=PerformanceConfig(),
            security=SecurityConfig(
                encryption_key=self.encryption.key.decode(),
                jwt_secret=secrets.token_urlsafe(32)
            )
        )
    
    def load_user_preferences(self) -> UserPreferences:
        """加载用户偏好"""
        if self._user_prefs is None:
            prefs_file = self._config_dir / "user_preferences.yaml"
            if prefs_file.exists():
                with open(prefs_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                self._user_prefs = UserPreferences(**data)
            else:
                self._user_prefs = UserPreferences()
                self.save_user_preferences(self._user_prefs)
        
        return self._user_prefs
    
    def save_user_preferences(self, prefs: UserPreferences):
        """保存用户偏好"""
        prefs_file = self._config_dir / "user_preferences.yaml"
        with open(prefs_file, 'w', encoding='utf-8') as f:
            yaml.dump(prefs.dict(), f, default_flow_style=False, allow_unicode=True)
        self._user_prefs = prefs
    
    def get_config_dir(self) -> Path:
        """获取配置目录"""
        return self._config_dir
    
    def validate_configuration(self) -> bool:
        """验证配置完整性"""
        try:
            config = self.load_config()
            
            # 验证关键配置
            if not config.api.deepseek_api_key or config.api.deepseek_api_key == "your_api_key_here":
                logger.error("DeepSeek API密钥未配置")
                return False
            
            # 验证缓存目录
            cache_dir = Path(config.cache.cache_dir)
            if not cache_dir.exists():
                try:
                    cache_dir.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    logger.error("缓存目录创建失败", error=str(e))
                    return False
            
            logger.info("配置验证通过")
            return True
            
        except Exception as e:
            logger.error("配置验证失败", error=str(e))
            return False
    
    def initialize_setup(self):
        """初始化设置向导"""
        from rich.console import Console
        from rich.prompt import Prompt, Confirm
        
        console = Console()
        
        console.print("\n[bold blue]🎬 Cinema Subtitle Translator 初始化设置[/bold blue]")
        console.print("=" * 50)
        
        # API配置
        console.print("\n[bold]API 配置[/bold]")
        api_key = Prompt.ask("请输入 DeepSeek API 密钥", password=True)
        
        # 测试API连接
        if api_key:
            console.print("正在测试API连接...")
            # 这里可以添加API连接测试逻辑
        
        # 创建配置
        config = self._create_default_config()
        config.api.deepseek_api_key = api_key
        
        # 保存配置
        self.save_config(config)
        
        console.print("\n[green]✅ 配置保存成功！[/green]")
        console.print("配置文件位置:", self._config_dir / "config.yaml")


# 全局配置管理器实例
config_manager = ConfigManager()


def get_config() -> SystemConfig:
    """获取系统配置"""
    return config_manager.load_config()


def get_user_preferences() -> UserPreferences:
    """获取用户偏好"""
    return config_manager.load_user_preferences()


def get_encryption() -> EncryptionConfig:
    """获取加密配置"""
    return config_manager.encryption