import os

# Production Services Configuration
SERVICES_CONFIG = {
    'blockchain': {
        'host': '0.0.0.0',
        'port': 8545,
        'workers': 4,
        'log_level': 'INFO',
        'max_connections': 1000
    },
    'marketplace': {
        'host': '0.0.0.0',
        'port': 8002,
        'workers': 8,
        'log_level': 'INFO',
        'max_connections': 5000
    },
    'gpu_marketplace': {
        'host': '0.0.0.0',
        'port': 8003,
        'workers': 4,
        'log_level': 'INFO',
        'max_connections': 1000
    },
    'monitoring': {
        'host': '0.0.0.0',
        'port': 9000,
        'workers': 2,
        'log_level': 'INFO'
    }
}

# Production Logging
LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'production': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        }
    },
    'handlers': {
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/aitbc/production/services/aitbc.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
            'formatter': 'production'
        },
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'production'
        }
    },
    'root': {
        'level': 'INFO',
        'handlers': ['file', 'console']
    }
}
