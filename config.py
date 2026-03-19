import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', os.urandom(24).hex())
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    PORT = int(os.getenv('PORT', 5000))
    
    # Rate limiting
    RATELIMIT_DEFAULT = "200 per day, 50 per hour"
    RATELIMIT_STORAGE_URL = os.getenv('REDIS_URL', 'memory://')
    
    # Supported platforms
    SUPPORTED_PLATFORMS = [
        'instagram', 'tiktok', 'youtube', 'twitter',
        'facebook', 'reddit', 'pinterest', 'imgur'
    ]
    
    # Max file size (500 MB)
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024
    
    # Temp file cleanup (1 hour)
    TEMP_FILE_AGE = 3600
