"""
Configuration management with validation
Ensures all required environment variables are set before startup
"""

import os
import logging
from typing import List
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class ConfigError(Exception):
    """Raised when configuration is invalid"""
    pass


class Config:
    """Application configuration from environment variables"""
    
    # Required environment variables
    REQUIRED_VARS = [
        "GROQ_API_KEY",
        "TYPESENSE_API_KEY",
        "JWT_SECRET_KEY",
        "TYPESENSE_HOST",
        "DB_HOST",
        "DB_USER",
        "DB_PASSWORD",
        "DB_NAME",
    ]
    
    def __init__(self):
        """Load and validate configuration"""
        self._validate_required()
        self._load_config()
    
    def _validate_required(self):
        """Verify all required environment variables are present"""
        missing = []
        for var in self.REQUIRED_VARS:
            if not os.getenv(var):
                missing.append(var)
        
        if missing:
            error_msg = f"Missing required environment variables: {', '.join(missing)}"
            logger.error(f"❌ {error_msg}")
            raise ConfigError(error_msg)
        
        logger.info("✅ All required environment variables present")
    
    def _load_config(self):
        """Load configuration from environment variables"""
        # API Keys
        self.GROQ_API_KEY = os.getenv("GROQ_API_KEY")
        self.TYPESENSE_API_KEY = os.getenv("TYPESENSE_API_KEY")
        self.JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
        self.INTERNAL_SYNC_TOKEN = os.getenv("INTERNAL_SYNC_SECRET", "")
                
        # Typesense Configuration
        self.TYPESENSE_HOST = os.getenv("TYPESENSE_HOST", "localhost")
        self.TYPESENSE_PORT = int(os.getenv("TYPESENSE_PORT", "8108"))
        self.TYPESENSE_PROTOCOL = os.getenv("TYPESENSE_PROTOCOL", "http")
        self.TYPESENSE_TIMEOUT = int(os.getenv("TYPESENSE_TIMEOUT", "2"))
        
        # Database Configuration
        self.DB_HOST = os.getenv("DB_HOST", "localhost")
        self.DB_USER = os.getenv("DB_USER", "root")
        self.DB_PASSWORD = os.getenv("DB_PASSWORD", "")
        self.DB_NAME = os.getenv("DB_NAME", "shop_db")
        
        # Redis Configuration
        self.REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
        self.REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
        self.REDIS_DB = int(os.getenv("REDIS_DB", "0"))
        
        # Server Configuration
        self.HOST = os.getenv("HOST", "0.0.0.0")
        self.PORT = int(os.getenv("PORT", "8000"))
        self.WORKERS = int(os.getenv("WORKERS", "4"))
        
        # CORS Configuration
        allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "http://localhost:3001")
        self.ALLOWED_ORIGINS = [origin.strip() for origin in allowed_origins_str.split(",")]
        
        # Logging & Debug
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.DEBUG = os.getenv("DEBUG", "False").lower() == "true"
        
        # Feature Flags
        self.ENABLE_CACHE = os.getenv("ENABLE_CACHE", "True").lower() == "true"
        self.ENABLE_METRICS = os.getenv("ENABLE_METRICS", "True").lower() == "true"
    
    def is_production(self) -> bool:
        return (
            not self.DEBUG
            and self.LOG_LEVEL == "INFO"
            and "localhost" not in self.ALLOWED_ORIGINS
            and "127.0.0.1" not in self.ALLOWED_ORIGINS
            and os.getenv("ENVIRONMENT", "").lower() == "production"
        )
        
    def get_database_url(self) -> str:
        """Get database URL for reference"""
        return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}/{self.DB_NAME}"
    
    def get_redis_url(self) -> str:
        """Get Redis URL"""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    def __repr__(self):
        """String representation (safe - no secrets)"""
        return (
            f"Config(mode={'PRODUCTION' if self.is_production() else 'DEVELOPMENT'}, "
            f"host={self.HOST}, port={self.PORT}, "
            f"db={self.DB_HOST}, typesense={self.TYPESENSE_HOST})"
        )


# Initialize global config
try:
    config = Config()
    logger.info(f"✅ Configuration loaded: {config}")
except ConfigError as e:
    logger.critical(f"❌ Configuration error: {e}")
    raise