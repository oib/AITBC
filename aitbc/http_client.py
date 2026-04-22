"""
AITBC HTTP Client
Base HTTP client with common utilities for AITBC applications
"""

import requests
from typing import Dict, Any, Optional, Union
from .exceptions import NetworkError


class AITBCHTTPClient:
    """
    Base HTTP client for AITBC applications.
    Provides common HTTP methods with error handling.
    """
    
    def __init__(
        self,
        base_url: str = "",
        timeout: int = 30,
        headers: Optional[Dict[str, str]] = None
    ):
        """
        Initialize HTTP client.
        
        Args:
            base_url: Base URL for all requests
            timeout: Request timeout in seconds
            headers: Default headers for all requests
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = headers or {}
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def _build_url(self, endpoint: str) -> str:
        """
        Build full URL from base URL and endpoint.
        
        Args:
            endpoint: API endpoint
            
        Returns:
            Full URL
        """
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint
        return f"{self.base_url}/{endpoint.lstrip('/')}"
    
    def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Perform GET request.
        
        Args:
            endpoint: API endpoint
            params: Query parameters
            headers: Additional headers
            
        Returns:
            Response data as dictionary
            
        Raises:
            NetworkError: If request fails
        """
        url = self._build_url(endpoint)
        req_headers = {**self.headers, **(headers or {})}
        
        try:
            response = self.session.get(
                url,
                params=params,
                headers=req_headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise NetworkError(f"GET request failed: {e}")
    
    def post(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Perform POST request.
        
        Args:
            endpoint: API endpoint
            data: Form data
            json: JSON data
            headers: Additional headers
            
        Returns:
            Response data as dictionary
            
        Raises:
            NetworkError: If request fails
        """
        url = self._build_url(endpoint)
        req_headers = {**self.headers, **(headers or {})}
        
        try:
            response = self.session.post(
                url,
                data=data,
                json=json,
                headers=req_headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise NetworkError(f"POST request failed: {e}")
    
    def put(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Perform PUT request.
        
        Args:
            endpoint: API endpoint
            data: Form data
            json: JSON data
            headers: Additional headers
            
        Returns:
            Response data as dictionary
            
        Raises:
            NetworkError: If request fails
        """
        url = self._build_url(endpoint)
        req_headers = {**self.headers, **(headers or {})}
        
        try:
            response = self.session.put(
                url,
                data=data,
                json=json,
                headers=req_headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise NetworkError(f"PUT request failed: {e}")
    
    def delete(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Perform DELETE request.
        
        Args:
            endpoint: API endpoint
            params: Query parameters
            headers: Additional headers
            
        Returns:
            Response data as dictionary
            
        Raises:
            NetworkError: If request fails
        """
        url = self._build_url(endpoint)
        req_headers = {**self.headers, **(headers or {})}
        
        try:
            response = self.session.delete(
                url,
                params=params,
                headers=req_headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json() if response.content else {}
        except requests.RequestException as e:
            raise NetworkError(f"DELETE request failed: {e}")
    
    def close(self) -> None:
        """Close the HTTP session."""
        self.session.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
