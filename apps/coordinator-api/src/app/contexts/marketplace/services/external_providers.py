"""External Provider Service for AWS/GCP/Azure integrations."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlmodel import Session, desc, select

from aitbc import get_logger

from ..domain.gpu_marketplace import ExternalProvider, GPURegistry, ProviderMapping, SyncStatus

logger = get_logger(__name__)

class ExternalProviderService:
    """Service for integrating with external GPU providers."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def register_provider(self, provider_name: str, provider_type: str, api_key: str, api_secret: str, region: str='', sync_interval_minutes: int=60) -> ExternalProvider:
        """Register a new external provider."""
        provider = ExternalProvider(provider_name=provider_name, provider_type=provider_type, api_key=api_key, api_secret=api_secret, region=region, sync_interval_minutes=sync_interval_minutes)
        self.session.add(provider)
        self.session.commit()
        self.session.refresh(provider)
        return provider

    def sync_resources(self, provider_id: str) -> SyncStatus:
        """Fetch external resources from provider."""
        try:
            provider = self.session.scalars(select(ExternalProvider).where(ExternalProvider.id == provider_id)).first()
            if not provider:
                raise ValueError(f'Provider {provider_id} not found')
            sync_status = SyncStatus(provider_id=provider_id, status='in_progress')
            self.session.add(sync_status)
            self.session.commit()
            if provider.provider_type == 'aws':
                resources = self._fetch_aws_resources(provider)
            elif provider.provider_type == 'gcp':
                resources = self._fetch_gcp_resources(provider)
            elif provider.provider_type == 'azure':
                resources = self._fetch_azure_resources(provider)
            else:
                raise ValueError(f'Unsupported provider type: {provider.provider_type}')
            synced_count = 0
            failed_count = 0
            for resource in resources:
                try:
                    self._map_to_internal(provider_id, resource)
                    synced_count += 1
                except Exception as e:
                    logger.error('Failed to map resource %s: %s', resource.get('id'), e)
                    failed_count += 1
            sync_status.resources_synced = synced_count
            sync_status.resources_failed = failed_count
            sync_status.status = 'completed'
            sync_status.completed_at = datetime.now(UTC)
            provider.last_sync = datetime.now(UTC)
            self.session.commit()
            self.session.refresh(sync_status)
            return sync_status
        except Exception as e:
            logger.error('Failed to sync resources: %s', e)
            sync_status.status = 'failed'
            sync_status.error_message = str(e)
            sync_status.completed_at = datetime.now(UTC)
            self.session.commit()
            return sync_status

    def map_to_internal(self, provider_id: str, external_resource_id: str) -> GPURegistry:
        """Map external resource to internal GPU registry."""
        provider = self.session.scalars(select(ExternalProvider).where(ExternalProvider.id == provider_id)).first()
        if not provider:
            raise ValueError(f'Provider {provider_id} not found')
        existing_mapping = self.session.scalars(select(ProviderMapping).where(ProviderMapping.provider_id == provider_id, ProviderMapping.external_resource_id == external_resource_id)).first()
        if existing_mapping:
            internal_gpu = self.session.scalars(select(GPURegistry).where(GPURegistry.id == existing_mapping.internal_resource_id)).first()
            if internal_gpu:
                return internal_gpu
        internal_gpu = GPURegistry(id=f'gpu_{uuid4().hex[:8]}', miner_id=f'external_{provider.provider_name}', model='External GPU', memory_gb=40, cuda_version='11.8', region=provider.region, price_per_hour=0.5, status='available', capabilities=['inference', 'training'])
        self.session.add(internal_gpu)
        self.session.commit()
        self.session.refresh(internal_gpu)
        mapping = ProviderMapping(provider_id=provider_id, external_resource_id=external_resource_id, internal_resource_id=internal_gpu.id)
        self.session.add(mapping)
        self.session.commit()
        return internal_gpu

    def get_sync_status(self, provider_id: str) -> SyncStatus | None:
        """Check sync status for a provider."""
        sync_status = self.session.scalars(select(SyncStatus).where(SyncStatus.provider_id == provider_id).order_by(desc(SyncStatus.started_at))).first()
        return sync_status

    def _fetch_aws_resources(self, provider: ExternalProvider) -> list[dict[str, Any]]:
        """Fetch GPU resources from AWS EC2."""
        logger.info('Fetching AWS resources for provider %s', provider.provider_name)
        return [{'id': 'i-12345', 'type': 'p3.2xlarge', 'memory': 32, 'price': 3.06}, {'id': 'i-67890', 'type': 'p3.8xlarge', 'memory': 128, 'price': 12.24}]

    def _fetch_gcp_resources(self, provider: ExternalProvider) -> list[dict[str, Any]]:
        """Fetch GPU resources from GCP."""
        logger.info('Fetching GCP resources for provider %s', provider.provider_name)
        return [{'id': 'gcp-12345', 'type': 'n1-standard-4', 'memory': 16, 'price': 0.5}, {'id': 'gcp-67890', 'type': 'n1-highmem-8', 'memory': 64, 'price': 1.2}]

    def _fetch_azure_resources(self, provider: ExternalProvider) -> list[dict[str, Any]]:
        """Fetch GPU resources from Azure."""
        logger.info('Fetching Azure resources for provider %s', provider.provider_name)
        return [{'id': 'azure-12345', 'type': 'Standard_NC6', 'memory': 112, 'price': 0.9}, {'id': 'azure-67890', 'type': 'Standard_NC12', 'memory': 224, 'price': 1.8}]

    def _map_to_internal(self, provider_id: str, resource: dict[str, Any]) -> None:
        """Helper method to map a single resource."""
        self.map_to_internal(provider_id, resource['id'])
