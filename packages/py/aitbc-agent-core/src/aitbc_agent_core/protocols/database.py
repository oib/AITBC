"""
Database protocols for session management.
These protocols define the interface for database session handling.
"""

from abc import ABC, abstractmethod
from typing import Any


class ISessionProvider(ABC):
    """Protocol for database session management"""

    @abstractmethod
    def get_session(self) -> Any:
        """
        Get a database session.
        
        Returns:
            Database session object (typically SQLModel Session)
        """
        ...

    @abstractmethod
    def close_session(self, session: Any) -> None:
        """
        Close a database session.
        
        Args:
            session: Session object to close
        """
        ...
