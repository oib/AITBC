import os
import ssl

# Production Database Configuration
DATABASE_CONFIG = {
    'production': {
        'url': os.getenv('DATABASE_URL', 'postgresql://aitbc:password@localhost:5432/aitbc_prod'),
        'pool_size': 20,
        'max_overflow': 30,
        'pool_timeout': 30,
        'pool_recycle': 3600,
        'ssl_context': ssl.create_default_context()
    },
    'redis': {
        'host': os.getenv('REDIS_HOST', 'localhost'),
        'port': int(os.getenv('REDIS_PORT', 6379)),
        'db': int(os.getenv('REDIS_DB', 0)),
        'password': os.getenv('REDIS_PASSWORD', None),
        'ssl': os.getenv('REDIS_SSL', 'false').lower() == 'true'
    }
}
