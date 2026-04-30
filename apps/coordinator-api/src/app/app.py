# Import the FastAPI app from main.py for uvicorn compatibility
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .main import app
