"""
Certification and Partnership Service - Modular Implementation
Service facade for backward compatibility with the original monolithic file

This module provides a modular structure for certification, partnership, and badge systems:
- certification_system.py: Agent certification framework and verification
- partnership_manager.py: Partnership program management
- badge_system.py: Achievement and recognition badge system
- service.py: Main CertificationAndPartnershipService facade

The original certification_service.py has been deprecated in favor of this modular structure.
"""

from .badge_system import BadgeSystem
from .certification_system import CertificationSystem
from .partnership_manager import PartnershipManager
from .service import CertificationAndPartnershipService

__all__ = ['CertificationSystem', 'PartnershipManager', 'BadgeSystem', 'CertificationAndPartnershipService']
