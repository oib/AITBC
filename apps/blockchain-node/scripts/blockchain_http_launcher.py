"""
Blockchain HTTP Launcher for AITBC Production
"""
import subprocess
from aitbc import get_logger
logger = get_logger(__name__)

def main():
    """Main blockchain HTTP launcher function"""
    logger.info('Starting AITBC Blockchain HTTP Launcher')
    try:
        logger.info('Launching blockchain HTTP API')
        subprocess.run(['/opt/aitbc/venv/bin/python', '-m', 'uvicorn', 'aitbc_chain.app:app', '--host', '0.0.0.0', '--port', '8005'], check=True)
    except subprocess.CalledProcessError as e:
        logger.error('Blockchain HTTP service failed with exit code %s: %s', e.returncode, e)
        import time
        while True:
            logger.info('Blockchain HTTP service heartbeat (fallback mode)')
            time.sleep(30)
    except (FileNotFoundError, PermissionError) as e:
        logger.error('Cannot launch blockchain HTTP service: %s: %s', type(e).__name__, e)
        import time
        while True:
            logger.info('Blockchain HTTP service heartbeat (fallback mode)')
            time.sleep(30)
    except Exception as e:
        logger.error('Unexpected error launching blockchain HTTP: %s: %s', type(e).__name__, e)
        import time
        while True:
            logger.info('Blockchain HTTP service heartbeat (fallback mode)')
            time.sleep(30)
if __name__ == '__main__':
    main()