# On-Chain Model Marketplace Implementation Plan

## Executive Summary

This document outlines a detailed implementation plan for extending the AITBC platform with an on-chain AI model marketplace. The implementation leverages existing infrastructure (GPU marketplace, smart contracts, token economy) while introducing model-specific trading, licensing, and royalty distribution mechanisms.

## Current Infrastructure Analysis

### Existing Components to Leverage

#### 1. Smart Contract Foundation
- **AIToken.sol**: ERC20 token with receipt-based minting
- **AccessControl**: Role-based permissions (COORDINATOR_ROLE, ATTESTOR_ROLE)
- **Signature Verification**: ECDSA-based attestation system
- **Replay Protection**: Consumed receipt tracking

#### 2. Privacy & Verification Infrastructure
- **ZK Proof System** (`/apps/coordinator-api/src/app/services/zk_proofs.py`):
  - Circom circuit compilation and proof generation
  - Groth16 proof system integration
  - Receipt attestation circuits with Poseidon hashing
- **Encryption Service** (`/apps/coordinator-api/src/app/services/encryption.py`):
  - AES-256-GCM symmetric encryption
  - X25519 asymmetric key exchange
  - Multi-party encryption with key escrow
- **ZK Circuits** (`/apps/zk-circuits/`):
  - `receipt_simple.circom`: Basic receipt verification
  - `MembershipProof`: Merkle tree membership proofs
  - `BidRangeProof`: Range proofs for bids

#### 3. Marketplace Infrastructure
- **MarketplaceOffer/Bid Models**: SQLModel-based offer/bid system
- **MarketplaceService**: Business logic for marketplace operations
- **API Router**: RESTful endpoints (/marketplace/offers, /marketplace/bids)
- **GPU Marketplace**: Existing GPU trading infrastructure
- **Metrics Integration**: Prometheus monitoring

#### 4. Coordinator API
- **Database Layer**: SQLModel with PostgreSQL/SQLite
- **Service Architecture**: Modular service design
- **Authentication**: JWT-based auth system
- **Schema Validation**: Pydantic models

## Additional Marketplace Considerations

### Gas Optimization Strategies

#### Royalty Distribution Efficiency
- **Batch Royalty Processing**: Implement batched royalty payouts to reduce gas costs per transaction
- **Layer 2 Solutions**: Consider Polygon or Optimism for lower gas fees on frequent royalty distributions
- **Threshold-Based Payouts**: Accumulate royalties until they exceed minimum payout thresholds
- **Gasless Transactions**: Implement meta-transactions for royalty claims to shift gas costs to platform

#### Smart Contract Optimizations
- **Storage Optimization**: Use efficient data structures and pack variables to minimize storage costs
- **Function Selectors**: Optimize contract function signatures for gas efficiency
- **Assembly Optimization**: Use Yul assembly for critical gas-intensive operations

### Storage Reliability Enhancements

#### Multi-Storage Backend Architecture
- **IPFS Primary Storage**: Decentralized storage with pinning services
- **Arweave Fallback**: Permanent storage with "pay once, store forever" model
- **Automatic Failover**: Smart routing between storage backends based on availability
- **Content Verification**: Cross-validate content integrity across multiple storage systems

#### Storage Monitoring & Management
- **Pinning Service Health Checks**: Monitor IPFS pinning service availability
- **Replication Strategy**: Maintain multiple copies across different storage networks
- **Cost Optimization**: Balance storage costs between IPFS and Arweave based on access patterns

### Legal and Liability Framework

#### Model Creator Liability Management
- **Training Data Transparency**: Require disclosure of training data sources and licenses
- **Model Output Disclaimers**: Standardized disclaimers for model outputs and potential biases
- **Creator Verification**: KYC process for model creators with legal entity validation
- **Insurance Integration**: Platform-provided insurance options for high-risk model categories

#### Platform Liability Protections
- **Terms of Service**: Comprehensive ToS covering model usage, liability limitations
- **Indemnification Clauses**: Creator indemnification for model-related claims
- **Jurisdiction Selection**: Clear legal jurisdiction and dispute resolution mechanisms
- **Regular Legal Audits**: Periodic review of legal frameworks and compliance requirements

### Digital Rights Management (DRM)

#### Watermarking and Tracking Systems
- **Invisible Watermarking**: Embed imperceptible watermarks in model weights for ownership tracking
- **Usage Fingerprinting**: Track model usage patterns and deployment locations
- **License Key Management**: Cryptographic license keys tied to specific deployments
- **Tamper Detection**: Detect unauthorized modifications to model files

#### Piracy Prevention Measures
- **Model Encryption**: Encrypt model files with user-specific keys
- **Access Control Lists**: Granular permissions for model access and usage
- **Revocation Mechanisms**: Ability to revoke access to compromised or pirated models
- **Forensic Analysis**: Tools to trace pirated model usage back to source

### Quality Assurance and Security

#### Pre-Listing Validation Pipeline
- **Malware Scanning**: Automated scanning for malicious code in model files
- **Model Quality Metrics**: Automated evaluation of model performance and safety
- **Training Data Validation**: Verification of training data quality and ethical sourcing
- **Bias and Fairness Testing**: Automated testing for harmful biases in model outputs

#### Continuous Monitoring
- **Model Performance Tracking**: Monitor deployed model performance and accuracy
- **Security Vulnerability Scanning**: Regular security audits of deployed models
- **Usage Pattern Analysis**: Detect anomalous usage that may indicate security issues
- **Automated Retraining Triggers**: Alert creators when models need updates

### GPU Inference Integration

#### Automated Model Deployment
- **One-Click GPU Deployment**: Seamless integration between marketplace purchases and GPU job scheduling
- **Model Format Standardization**: Convert purchased models to optimal formats for GPU inference
- **Resource Auto-Allocation**: Automatically allocate appropriate GPU resources based on model requirements
- **Performance Optimization**: Apply model optimizations (quantization, pruning) for target hardware

#### Inference Job Orchestration
- **Job Queue Integration**: Link purchased models to existing GPU job queue system
- **Load Balancing**: Distribute inference jobs across available GPU resources
- **Cost Tracking**: Monitor and bill for GPU usage separate from model purchase costs
- **Result Caching**: Cache inference results to reduce redundant computations

### NFT Integration Framework

#### ERC-721 Model Wrappers
- **Model Ownership NFTs**: ERC-721 tokens representing ownership of specific model versions
- **Metadata Standardization**: Standard metadata schema for AI model NFTs
- **Transfer Restrictions**: Implement transfer controls based on license agreements
- **Royalty Automation**: Automatic royalty distribution through NFT smart contracts

#### Soulbound Achievement Badges
- **Creator Badges**: Non-transferable badges for verified creators and contributors
- **Model Quality Badges**: Badges for models meeting quality and safety standards
- **Community Recognition**: Badges for community contributions and model usage
- **Verification Status**: Visual indicators of model verification and security status

### FHE Marketplace Features
- **Privacy Tier Pricing**: Different pricing tiers based on privacy level requirements
- **FHE Performance Metrics**: Transparent reporting of FHE inference latency and costs
- **Compatibility Verification**: Ensure models are compatible with FHE requirements
- **Hybrid Inference Options**: Choose between standard and FHE inference modes

## Additional Marketplace Gaps & Solutions

### Security Audits & Timeline

#### Smart Contract Audit Requirements
- **Comprehensive Audit**: Full security audit by leading firms (OpenZeppelin, Trail of Bits, or Certik)
- **ZK Circuit Audit**: Specialized audit for zero-knowledge circuits and cryptographic proofs
- **Timeline**: Weeks 10-11 (after core functionality is complete)
- **Budget**: $50,000-75,000 for combined smart contract and ZK audit
- **Scope**: Reentrancy, access control, overflow/underflow, oracle manipulation, cryptographic correctness

#### Audit Deliverables
- **Security Report**: Detailed findings with severity levels and remediation steps
- **Gas Optimization**: Contract optimization recommendations
- **Test Coverage**: Requirements for additional test scenarios
- **Monitoring Recommendations**: On-chain monitoring and alerting setup

### Model Versioning & Upgrade Mechanism

#### Version Control System
```solidity
// Enhanced ModelListing with versioning
struct ModelVersion {
    uint256 versionNumber;
    string modelHash;
    string changelog;
    uint256 releaseDate;
    bool isActive;
    uint256 cumulativeDownloads;
    uint256 averageRating;
}

mapping(uint256 => ModelVersion[]) public modelVersions;
mapping(uint256 => uint256) public latestVersion;

// Version upgrade mechanism
function upgradeModel(
    uint256 modelId,
    string memory newModelHash,
    string memory changelog,
    bool maintainPricing
) external onlyRole(MODEL_CREATOR_ROLE) {
    // Verify ownership
    require(modelListings[modelId].creator == msg.sender, "Not model owner");
    
    uint256 newVersion = latestVersion[modelId] + 1;
    modelVersions[modelId].push(ModelVersion({
        versionNumber: newVersion,
        modelHash: newModelHash,
        changelog: changelog,
        releaseDate: block.timestamp,
        isActive: true,
        cumulativeDownloads: 0,
        averageRating: 0
    }));
    
    latestVersion[modelId] = newVersion;
    
    // Optional: Update pricing for new version
    if (!maintainPricing) {
        // Allow pricing adjustment for upgrades
    }
    
    emit ModelUpgraded(modelId, newVersion, newModelHash);
}
```

#### Database Extensions
```python
class ModelVersion(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    model_id: str = Field(foreign_key="aimodel.id", index=True)
    version_number: int = Field(default=1)
    model_hash: str = Field(index=True)
    changelog: Optional[str] = None
    release_date: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True)
    downloads: int = Field(default=0)
    average_rating: float = Field(default=0.0)
    file_size_mb: int
    performance_delta: dict = Field(default_factory=dict, sa_column=Column(JSON))  # Performance changes
```

### Platform Economics & Revenue Model

#### Fee Structure
- **Listing Fee**: 0.1 AIT per model listing (covers IPFS/Arweave storage costs)
- **Platform Sales Cut**: 2.5% of all sales (0.5% platform, 2% miner rewards pool)
- **Premium Features**: Additional fees for FHE inference (5 AIT/setup), priority verification (1 AIT), featured listings (10 AIT/week)
- **Subscription Tiers**: Creator premium subscriptions (50 AIT/month) for advanced analytics and marketing tools

#### Revenue Sharing with Miners
- **Inference Revenue Split**: 70% to miners, 20% to model creators, 10% platform
- **Quality-Based Rewards**: Higher rewards for miners with better performance/reliability scores
- **Staking Multipliers**: Miners staking AIT tokens get 2x reward multipliers
- **Geographic Bonuses**: Extra rewards for serving underserved regions

#### Economic Incentives
- **Creator Rewards**: Royalties, platform referrals, quality bonuses
- **Miner Rewards**: Inference payments, staking rewards, performance bonuses
- **User Benefits**: Volume discounts, loyalty rewards, early access to new models

### Secure Preview Sandbox

#### Sandbox Architecture
```python
class ModelSandbox:
    """Secure environment for model previews and testing"""
    
    def __init__(self, docker_client: DockerClient, security_scanner: SecurityScanner):
        self.docker_client = docker_client
        self.security_scanner = security_scanner
        self.resource_limits = {
            "cpu": 0.5,      # 50% of one CPU core
            "memory": "512m", # 512MB RAM limit
            "disk": "1GB",    # 1GB disk space
            "time": 300       # 5 minute execution limit
        }
    
    async def create_preview_environment(
        self,
        model_hash: str,
        test_inputs: List[dict],
        user_id: str
    ) -> SandboxSession:
        """Create isolated preview environment"""
        
        # Security scan of inputs
        security_check = await self.security_scanner.scan_inputs(test_inputs)
        if not security_check.safe:
            raise SecurityViolation(f"Unsafe inputs detected: {security_check.issues}")
        
        # Create isolated container
        container_config = {
            "image": "aitbc/sandbox:latest",
            "cpu_quota": self.resource_limits["cpu"] * 100000,
            "mem_limit": self.resource_limits["memory"],
            "network_mode": "none",  # No network access
            "readonly_rootfs": True,  # Immutable filesystem
            "tmpfs": {"/tmp": f"size={self.resource_limits['disk']}"}
        }
        
        container = await self.docker_client.containers.create(**container_config)
        
        # Load model in sandbox
        await self._load_model_in_sandbox(container, model_hash)
        
        # Execute preview inferences
        results = []
        for test_input in test_inputs[:3]:  # Limit to 3 test cases
            result = await self._execute_sandbox_inference(container, test_input)
            results.append(result)
            
            # Check for resource violations
            if result.execution_time > self.resource_limits["time"]:
                await container.stop()
                raise ResourceLimitExceeded("Execution time limit exceeded")
        
        await container.stop()
        await container.remove()
        
        return SandboxSession(
            session_id=uuid4().hex,
            results=results,
            resource_usage=container.stats(),
            security_status="passed"
        )
```

#### API Endpoints
```python
@router.post("/model-marketplace/models/{model_id}/preview")
async def preview_model(
    model_id: str,
    preview_request: ModelPreviewRequest,
    session: SessionDep,
    current_user: CurrentUserDep
) -> PreviewResult:
    """Execute model preview in secure sandbox"""
    service = ModelMarketplaceService(session, blockchain_service, zk_service, encryption_service)
    return await service.execute_model_preview(model_id, preview_request, current_user.id)
```

### Large File Handling (>10GB Models)

#### Chunked Upload System
```python
class ChunkedUploadService:
    """Handle large model file uploads with resumable chunking"""
    
    def __init__(self, storage_service: MultiStorageService):
        self.storage_service = storage_service
        self.chunk_size = 100 * 1024 * 1024  # 100MB chunks
        self.max_file_size = 100 * 1024 * 1024 * 1024  # 100GB limit
    
    async def initiate_upload(
        self,
        file_name: str,
        file_size: int,
        metadata: dict
    ) -> UploadSession:
        """Start resumable chunked upload"""
        
        if file_size > self.max_file_size:
            raise FileTooLargeError(f"File size {file_size} exceeds limit {self.max_file_size}")
        
        session_id = uuid4().hex
        num_chunks = math.ceil(file_size / self.chunk_size)
        
        upload_session = UploadSession(
            session_id=session_id,
            file_name=file_name,
            file_size=file_size,
            num_chunks=num_chunks,
            uploaded_chunks=set(),
            metadata=metadata,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=24)
        )
        
        await self._save_upload_session(upload_session)
        return upload_session
    
    async def upload_chunk(
        self,
        session_id: str,
        chunk_number: int,
        chunk_data: bytes
    ) -> ChunkUploadResult:
        """Upload individual file chunk"""
        
        session = await self._get_upload_session(session_id)
        if session.expires_at < datetime.utcnow():
            raise UploadSessionExpired()
        
        # Validate chunk
        expected_size = min(self.chunk_size, session.file_size - (chunk_number * self.chunk_size))
        if len(chunk_data) != expected_size:
            raise InvalidChunkSize()
        
        # Store chunk
        chunk_hash = hashlib.sha256(chunk_data).hexdigest()
        await self.storage_service.store_chunk(
            session_id=session_id,
            chunk_number=chunk_number,
            chunk_data=chunk_data,
            chunk_hash=chunk_hash
        )
        
        # Update session
        session.uploaded_chunks.add(chunk_number)
        await self._update_upload_session(session)
        
        # Check if upload complete
        if len(session.uploaded_chunks) == session.num_chunks:
            final_hash = await self._assemble_file(session)
            return ChunkUploadResult(
                complete=True,
                final_hash=final_hash,
                session_id=session_id
            )
        
        return ChunkUploadResult(
            complete=False,
            session_id=session_id,
            chunks_remaining=session.num_chunks - len(session.uploaded_chunks)
        )
```

#### Streaming Download
```python
@router.get("/model-marketplace/models/{model_id}/download")
async def stream_model_download(
    model_id: str,
    session: SessionDep,
    current_user: CurrentUserDep,
    range_header: str = Header(None, alias="Range")
) -> StreamingResponse:
    """Stream large model files with range support"""
    
    service = ModelMarketplaceService(session, blockchain_service, zk_service, encryption_service)
    
    # Verify license
    license = await service.verify_download_license(model_id, current_user.address)
    
    # Get file info
    file_info = await service.get_model_file_info(model_id)
    
    # Handle range requests for resumable downloads
    if range_header:
        start, end = parse_range_header(range_header, file_info.size)
        file_stream = await service.stream_file_chunk(model_id, start, end)
        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_info.size}",
            "Accept-Ranges": "bytes"
        }
        return StreamingResponse(
            file_stream,
            status_code=206,
            headers=headers,
            media_type="application/octet-stream"
        )
    else:
        # Full file download
        file_stream = await service.stream_full_file(model_id)
        return StreamingResponse(
            file_stream,
            headers={"Content-Length": str(file_info.size)},
            media_type="application/octet-stream"
        )
```

### Official SDK & Developer Tools

#### SDK Architecture
```python
# Python SDK
class AITBCModelMarketplace:
    """Official Python SDK for AITBC Model Marketplace"""
    
    def __init__(self, api_key: str, network: str = "mainnet"):
        self.client = httpx.AsyncClient(
            base_url=f"https://api.aitbc.{network}.com",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        self.web3_client = Web3Client(network)
    
    async def list_model(
        self,
        model_path: str,
        metadata: dict,
        price: float,
        royalty_bps: int = 250
    ) -> ModelListing:
        """List a model on the marketplace"""
        
        # Auto-detect model framework and type
        model_info = await self._analyze_model(model_path)
        metadata.update(model_info)
        
        # Upload model files (with chunking for large files)
        upload_session = await self._upload_model_files(model_path)
        
        # Create listing
        listing_request = {
            "model_files": upload_session.file_hashes,
            "metadata": metadata,
            "price": price,
            "royalty_bps": royalty_bps
        }
        
        response = await self.client.post("/model-marketplace/list", json=listing_request)
        return ModelListing(**response.json())
    
    async def run_inference(
        self,
        model_id: str,
        inputs: Union[dict, List[dict]],
        privacy_level: str = "standard"
    ) -> InferenceResult:
        """Run inference on a purchased model"""
        
        inference_request = {
            "inputs": inputs,
            "privacy_level": privacy_level
        }
        
        response = await self.client.post(
            f"/model-marketplace/models/{model_id}/inference",
            json=inference_request
        )
        return InferenceResult(**response.json())
    
    async def get_model_recommendations(
        self,
        task_type: str,
        performance_requirements: dict = None,
        max_price: float = None
    ) -> List[ModelRecommendation]:
        """Get AI-powered model recommendations"""
        
        params = {
            "task_type": task_type,
            "performance": json.dumps(performance_requirements or {}),
            "max_price": max_price
        }
        
        response = await self.client.get("/model-marketplace/recommendations", params=params)
        return [ModelRecommendation(**rec) for rec in response.json()]

# JavaScript SDK
class AITBCSDK {
    constructor(apiKey, network = 'mainnet') {
        this.apiKey = apiKey;
        this.baseURL = `https://api.aitbc.${network}.com`;
        this.web3 = new Web3(network === 'mainnet' ? MAINNET_RPC : TESTNET_RPC);
    }
    
    async listModel(modelFiles, metadata, price, options = {}) {
        // Handle file uploads with progress callbacks
        const uploadProgress = options.onProgress || (() => {});
        
        const formData = new FormData();
        modelFiles.forEach((file, index) => {
            formData.append(`model_files`, file);
            uploadProgress(index / modelFiles.length);
        });
        
        formData.append('metadata', JSON.stringify(metadata));
        formData.append('price', price.toString());
        formData.append('royalty_bps', (options.royaltyBps || 250).toString());
        
        const response = await fetch(`${this.baseURL}/model-marketplace/list`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.apiKey}`
            },
            body: formData
        });
        
        return await response.json();
    }
    
    async purchaseModel(modelId, options = {}) {
        const purchaseRequest = {
            model_id: modelId,
            buyer_address: options.buyerAddress || await this.web3.getAddress()
        };
        
        const response = await this._authenticatedRequest(
            `/model-marketplace/purchase`,
            purchaseRequest
        );
        
        return response;
    }
}
```

### Creator Reputation & Quality Scoring

#### Reputation System
```python
class ReputationEngine:
    """Calculate and maintain creator reputation scores"""
    
    def __init__(self, session: SessionDep):
        self.session = session
        self.weights = {
            "model_quality": 0.3,
            "user_ratings": 0.25,
            "download_volume": 0.15,
            "uptime_reliability": 0.15,
            "community_feedback": 0.1,
            "audit_compliance": 0.05
        }
    
    async def calculate_reputation_score(self, creator_address: str) -> ReputationScore:
        """Calculate comprehensive reputation score"""
        
        # Get creator's models
        models = await self._get_creator_models(creator_address)
        
        # Model quality scores
        quality_scores = []
        for model in models:
            quality = await self._calculate_model_quality_score(model)
            quality_scores.append(quality)
        
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
        
        # User ratings (weighted by recency and volume)
        user_ratings = await self._calculate_weighted_ratings(models)
        
        # Download volume (logarithmic scaling)
        total_downloads = sum(model.downloads for model in models)
        download_score = min(math.log10(total_downloads + 1) / 2, 1.0) if total_downloads > 0 else 0
        
        # Uptime/reliability (based on inference success rates)
        reliability_score = await self._calculate_reliability_score(creator_address)
        
        # Community feedback
        community_score = await self._calculate_community_score(creator_address)
        
        # Audit compliance
        audit_score = await self._check_audit_compliance(creator_address)
        
        # Calculate weighted score
        final_score = (
            self.weights["model_quality"] * avg_quality +
            self.weights["user_ratings"] * user_ratings +
            self.weights["download_volume"] * download_score +
            self.weights["uptime_reliability"] * reliability_score +
            self.weights["community_feedback"] * community_score +
            self.weights["audit_compliance"] * audit_score
        )
        
        # Determine reputation tier
        tier = self._determine_reputation_tier(final_score)
        
        return ReputationScore(
            creator_address=creator_address,
            overall_score=round(final_score * 100, 2),
            tier=tier,
            components={
                "model_quality": avg_quality,
                "user_ratings": user_ratings,
                "download_volume": download_score,
                "reliability": reliability_score,
                "community": community_score,
                "audit": audit_score
            },
            last_updated=datetime.utcnow()
        )
    
    def _determine_reputation_tier(self, score: float) -> str:
        """Determine reputation tier based on score"""
        if score >= 0.9:
            return "Diamond"
        elif score >= 0.8:
            return "Platinum"
        elif score >= 0.7:
            return "Gold"
        elif score >= 0.6:
            return "Silver"
        elif score >= 0.5:
            return "Bronze"
        else:
            return "Unrated"
```

#### Database Extensions
```python
class CreatorReputation(SQLModel, table=True):
    creator_address: str = Field(primary_key=True)
    overall_score: float = Field(default=0.0)
    tier: str = Field(default="Unrated")  # Diamond, Platinum, Gold, Silver, Bronze, Unrated
    components: dict = Field(default_factory=dict, sa_column=Column(JSON))
    total_models: int = Field(default=0)
    total_downloads: int = Field(default=0)
    avg_rating: float = Field(default=0.0)
    reputation_badge: Optional[str] = None
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    verification_status: str = Field(default="unverified")  # verified, pending, rejected
```

### Regulatory Compliance & KYC/AML

#### EU AI Act Compliance
- **Risk Classification**: Automatic model risk assessment (unacceptable, high, medium, low risk)
- **Transparency Requirements**: Mandatory disclosure of training data, model capabilities, and limitations
- **Data Governance**: GDPR-compliant data handling with right to explanation and erasure
- **Conformity Assessment**: Third-party auditing for high-risk AI systems

#### KYC/AML Framework
```python
class ComplianceService:
    """Handle KYC/AML and regulatory compliance"""
    
    def __init__(self, kyc_provider: KYCProvider, aml_service: AMLService):
        self.kyc_provider = kyc_provider
        self.aml_service = aml_service
        self.regulatory_limits = {
            "max_transaction_value": 10000,  # EUR
            "daily_limit": 50000,
            "monthly_limit": 200000
        }
    
    async def perform_kyc_check(self, user_address: str, user_data: dict) -> KYCResult:
        """Perform Know Your Customer verification"""
        
        # Identity verification
        identity_check = await self.kyc_provider.verify_identity(user_data)
        
        # Address verification
        address_check = await self.kyc_provider.verify_address(user_data)
        
        # Accreditation check (for institutional investors)
        accreditation_check = await self._check_accreditation_status(user_address)
        
        # Sanctions screening
        sanctions_check = await self.aml_service.screen_sanctions(user_address, user_data)
        
        # PEP (Politically Exposed Person) screening
        pep_check = await self.aml_service.screen_pep(user_address)
        
        # Overall compliance status
        is_compliant = all([
            identity_check.verified,
            address_check.verified,
            not sanctions_check.flagged,
            not pep_check.flagged
        ])
        
        return KYCResult(
            user_address=user_address,
            is_compliant=is_compliant,
            verification_level=self._determine_verification_level(user_data),
            checks={
                "identity": identity_check,
                "address": address_check,
                "accreditation": accreditation_check,
                "sanctions": sanctions_check,
                "pep": pep_check
            },
            expires_at=datetime.utcnow() + timedelta(days=365)  # Annual refresh
        )
    
    async def check_transaction_compliance(
        self,
        buyer_address: str,
        seller_address: str,
        transaction_value: float,
        transaction_type: str
    ) -> ComplianceCheck:
        """Check transaction compliance with regulatory limits"""
        
        # Check KYC status
        buyer_kyc = await self.get_kyc_status(buyer_address)
        seller_kyc = await self.get_kyc_status(seller_address)
        
        if not buyer_kyc.is_compliant or not seller_kyc.is_compliant:
            return ComplianceCheck(
                approved=False,
                reason="KYC verification required",
                required_action="complete_kyc"
            )
        
        # Check transaction limits
        daily_volume = await self._get_user_daily_volume(buyer_address)
        if daily_volume + transaction_value > self.regulatory_limits["daily_limit"]:
            return ComplianceCheck(
                approved=False,
                reason="Daily transaction limit exceeded",
                required_action="reduce_amount"
            )
        
        # AML transaction monitoring
        risk_score = await self.aml_service.assess_transaction_risk(
            buyer_address, seller_address, transaction_value, transaction_type
        )
        
        if risk_score > 0.8:  # High risk
            return ComplianceCheck(
                approved=False,
                reason="Transaction flagged for manual review",
                required_action="manual_review"
            )
        
        return ComplianceCheck(approved=True)
```

#### Regulatory Database Models
```python
class KYCRecord(SQLModel, table=True):
    user_address: str = Field(primary_key=True)
    verification_level: str = Field(default="none")  # none, basic, enhanced, institutional
    is_compliant: bool = Field(default=False)
    verification_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    provider_reference: Optional[str] = None
    documents_submitted: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    risk_score: float = Field(default=0.0)

class ComplianceLog(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    user_address: str = Field(index=True)
    action_type: str = Field()  # transaction, listing, download, etc.
    compliance_status: str = Field()  # approved, rejected, flagged
    risk_score: float = Field(default=0.0)
    regulatory_flags: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    reviewer_address: Optional[str] = None
```

### Performance Optimization & Efficient Lookups

#### Optimized Smart Contract Lookups
```solidity
// Replace O(n) tokenURI loop with efficient mapping
contract AIModelMarketplace is AccessControl, ReentrancyGuard, ERC721 {
    // Bidirectional mapping for O(1) lookups
    mapping(uint256 => uint256) public modelToTokenId;
    mapping(uint256 => uint256) public tokenToModelId;
    
    // Efficient tokenURI implementation
    function tokenURI(uint256 tokenId) public view override returns (string memory) {
        require(_exists(tokenId), "Token does not exist");
        
        uint256 modelId = tokenToModelId[tokenId];
        ModelListing memory model = modelListings[modelId];
        
        // Return metadata URI
        return string(abi.encodePacked(_baseURI(), model.metadataHash));
    }
    
    function _mint(address to, uint256 tokenId) internal override {
        super._mint(to, tokenId);
        // Update bidirectional mapping
        uint256 modelId = modelToTokenId[tokenId];  // Set during listing
        tokenToModelId[tokenId] = modelId;
    }
    
    // Batch operations for gas efficiency
    function batchGetModelInfo(uint256[] calldata modelIds) 
        external view returns (ModelInfo[] memory) 
    {
        ModelInfo[] memory results = new ModelInfo[](modelIds.length);
        
        for (uint256 i = 0; i < modelIds.length; i++) {
            ModelListing memory model = modelListings[modelIds[i]];
            results[i] = ModelInfo({
                id: model.id,
                creator: model.creator,
                price: model.price,
                isActive: model.isActive,
                supportsFHE: model.supportsFHE
            });
        }
        
        return results;
    }
}
```

#### Off-Chain Indexing Service
```python
class MarketplaceIndexer:
    """Maintain efficient off-chain indexes for fast lookups"""
    
    def __init__(self, redis_client: RedisClient, db_session: SessionDep):
        self.redis = redis_client
        self.session = db_session
    
    async def index_model(self, model: AIModel):
        """Index model for fast retrieval"""
        
        # Creator index
        await self.redis.sadd(f"creator:{model.creator_address}:models", model.id)
        
        # Category index
        await self.redis.sadd(f"category:{model.category}:models", model.id)
        
        # Framework index
        await self.redis.sadd(f"framework:{model.framework}:models", model.id)
        
        # Price range index (using sorted set)
        await self.redis.zadd("models:by_price", {model.id: model.price})
        
        # Quality score index
        await self.redis.zadd("models:by_quality", {model.id: model.quality_score})
        
        # Full-text search index
        await self._index_for_search(model)
    
    async def search_models(
        self,
        query: str = None,
        filters: dict = None,
        sort_by: str = "created_at",
        limit: int = 50
    ) -> List[str]:
        """Fast model search with filters"""
        
        # Start with broad set
        candidate_ids = await self.redis.smembers("all_models")
        
        # Apply filters
        if filters:
            for filter_type, filter_value in filters.items():
                filter_key = f"{filter_type}:{filter_value}:models"
                filter_ids = await self.redis.smembers(filter_key)
                candidate_ids = candidate_ids.intersection(filter_ids)
        
        # Apply search query
        if query:
            search_results = await self._perform_text_search(query)
            candidate_ids = candidate_ids.intersection(search_results)
        
        # Sort results
        if sort_by == "price":
            sorted_ids = await self.redis.zrange("models:by_price", 0, -1, withscores=True)
        elif sort_by == "quality":
            sorted_ids = await self.redis.zrevrange("models:by_quality", 0, -1, withscores=True)
        else:
            # Default: sort by creation date (would need timestamp index)
            sorted_ids = await self._get_sorted_by_date(candidate_ids)
        
        return [model_id for model_id, _ in sorted_ids[:limit]]
```

### Dispute Resolution & Governance

#### Dispute Resolution Framework
```solidity
contract ModelDisputeResolution is AccessControl {
    enum DisputeStatus { Open, UnderReview, Resolved, Appealed }
    enum DisputeType { LicenseViolation, QualityIssue, PaymentDispute, IPInfringement }
    
    struct Dispute {
        uint256 id;
        uint256 modelId;
        address complainant;
        address respondent;
        DisputeType disputeType;
        string description;
        DisputeStatus status;
        uint256 createdAt;
        uint256 resolvedAt;
        address resolver;
        string resolution;
        uint256 compensation; // Amount to be paid
    }
    
    mapping(uint256 => Dispute) public disputes;
    mapping(address => uint256[]) public userDisputes;
    
    event DisputeFiled(uint256 indexed disputeId, uint256 indexed modelId, address complainant);
    event DisputeResolved(uint256 indexed disputeId, string resolution, uint256 compensation);
    
    function fileDispute(
        uint256 modelId,
        DisputeType disputeType,
        string memory description
    ) external payable returns (uint256) {
        require(msg.value >= DISPUTE_FILING_FEE, "Filing fee required");
        
        uint256 disputeId = ++nextDisputeId;
        disputes[disputeId] = Dispute({
            id: disputeId,
            modelId: modelId,
            complainant: msg.sender,
            respondent: modelListings[modelId].creator,
            disputeType: disputeType,
            description: description,
            status: DisputeStatus.Open,
            createdAt: block.timestamp,
            resolvedAt: 0,
            resolver: address(0),
            resolution: "",
            compensation: 0
        });
        
        userDisputes[msg.sender].push(disputeId);
        userDisputes[modelListings[modelId].creator].push(disputeId);
        
        emit DisputeFiled(disputeId, modelId, msg.sender);
        return disputeId;
    }
    
    function resolveDispute(
        uint256 disputeId,
        string memory resolution,
        uint256 compensation
    ) external onlyRole(DISPUTE_RESOLVER_ROLE) {
        Dispute storage dispute = disputes[disputeId];
        require(dispute.status == DisputeStatus.UnderReview, "Dispute not under review");
        
        dispute.status = DisputeStatus.Resolved;
        dispute.resolvedAt = block.timestamp;
        dispute.resolver = msg.sender;
        dispute.resolution = resolution;
        dispute.compensation = compensation;
        
        // Execute compensation if applicable
        if (compensation > 0) {
            if (dispute.complainant == modelListings[dispute.modelId].creator) {
                // Creator wins - platform pays
                payable(dispute.complainant).transfer(compensation);
            } else {
                // User wins - creator pays
                payable(dispute.complainant).transfer(compensation);
                // Creator pays from escrow or future earnings
            }
        }
        
        emit DisputeResolved(disputeId, resolution, compensation);
    }
}
```

#### Usage-Based Licensing
```solidity
contract UsageBasedLicensing {
    struct UsageLicense {
        uint256 modelId;
        address licensee;
        uint256 usageLimit;     // Max API calls or compute hours
        uint256 usedAmount;     // Current usage
        uint256 ratePerUnit;    // Cost per API call or hour
        uint256 expiresAt;
        bool autoRenew;
    }
    
    mapping(bytes32 => UsageLicense) public licenses;
    
    function createUsageLicense(
        uint256 modelId,
        address licensee,
        uint256 usageLimit,
        uint256 ratePerUnit,
        uint256 duration
    ) external onlyRole(MODEL_CREATOR_ROLE) returns (bytes32) {
        bytes32 licenseId = keccak256(abi.encodePacked(
            modelId, licensee, block.timestamp
        ));
        
        licenses[licenseId] = UsageLicense({
            modelId: modelId,
            licensee: licensee,
            usageLimit: usageLimit,
            usedAmount: 0,
            ratePerUnit: ratePerUnit,
            expiresAt: block.timestamp + duration,
            autoRenew: false
        });
        
        return licenseId;
    }
    
    function recordUsage(
        bytes32 licenseId,
        uint256 amount
    ) external onlyAuthorizedServices {
        UsageLicense storage license = licenses[licenseId];
        require(license.usedAmount + amount <= license.usageLimit, "Usage limit exceeded");
        
        license.usedAmount += amount;
        
        // Auto-billing
        uint256 cost = amount * license.ratePerUnit;
        _processPayment(license.licensee, license.modelId, cost);
    }
}
```

### Semantic Search & Recommendations

#### AI-Powered Discovery Engine
```python
class SemanticSearchEngine:
    """Semantic search and recommendation system"""
    
    def __init__(self, embedding_model: str = "text-embedding-ada-002"):
        self.embedding_client = OpenAIClient(api_key=settings.OPENAI_API_KEY)
        self.embedding_model = embedding_model
        self.index = faiss.IndexFlatIP(1536)  # Cosine similarity index
        self.model_metadata = {}  # Store model info for retrieval
    
    async def index_model(self, model: AIModel):
        """Create semantic embeddings for model"""
        
        # Create rich text representation
        model_text = f"""
        Model: {model.name}
        Description: {model.description}
        Category: {model.category}
        Framework: {model.framework}
        Type: {model.model_type}
        Tags: {', '.join(model.tags)}
        Performance: {json.dumps(model.performance_metrics)}
        """
        
        # Generate embeddings
        embeddings = await self.embedding_client.embeddings.create(
            input=model_text,
            model=self.embedding_model
        )
        
        # Add to vector index
        self.index.add(np.array([embeddings.data[0].embedding], dtype=np.float32))
        self.model_metadata[len(self.model_metadata)] = {
            "id": model.id,
            "name": model.name,
            "score": 0  # Will be updated with popularity/quality scores
        }
    
    async def semantic_search(
        self,
        query: str,
        filters: dict = None,
        limit: int = 20
    ) -> List[ModelRecommendation]:
        """Perform semantic search on models"""
        
        # Generate query embedding
        query_embedding = await self.embedding_client.embeddings.create(
            input=query,
            model=self.embedding_model
        )
        
        # Search vector index
        query_vector = np.array([query_embedding.data[0].embedding], dtype=np.float32)
        scores, indices = self.index.search(query_vector, limit * 2)  # Get more candidates
        
        # Apply filters and rerank
        results = []
        for idx, score in zip(indices[0], scores[0]):
            if idx in self.model_metadata:
                model_info = self.model_metadata[idx]
                
                # Apply filters
                if filters:
                    if not self._matches_filters(model_info, filters):
                        continue
                
                # Boost score with quality/popularity metrics
                boosted_score = score * (1 + model_info.get("score", 0))
                
                results.append(ModelRecommendation(
                    model_id=model_info["id"],
                    name=model_info["name"],
                    relevance_score=float(boosted_score),
                    match_reason=self._generate_match_reason(query, model_info)
                ))
        
        # Sort by boosted score and return top results
        results.sort(key=lambda x: x.relevance_score, reverse=True)
        return results[:limit]
    
    async def get_recommendations(
        self,
        user_id: str,
        context: dict = None,
        limit: int = 10
    ) -> List[ModelRecommendation]:
        """Generate personalized recommendations"""
        
        # Get user history
        user_history = await self._get_user_history(user_id)
        
        # Collaborative filtering
        similar_users = await self._find_similar_users(user_id)
        similar_models = await self._get_models_from_similar_users(similar_users)
        
        # Content-based filtering
        preferred_categories = self._extract_preferences(user_history)
        
        # Hybrid recommendation
        candidates = set(similar_models)
        for category in preferred_categories:
            category_models = await self._get_models_by_category(category)
            candidates.update(category_models)
        
        # Score and rank recommendations
        recommendations = []
        for model_id in candidates:
            if model_id not in user_history:
                score = await self._calculate_recommendation_score(model_id, user_id, context)
                recommendations.append(ModelRecommendation(
                    model_id=model_id,
                    relevance_score=score,
                    match_reason="Based on your interests and similar users"
                ))
        
        recommendations.sort(key=lambda x: x.relevance_score, reverse=True)
        return recommendations[:limit]
```

### CDN Caching & Performance Infrastructure

#### Global CDN Integration
```python
class CDNManager:
    """Manage CDN caching for model files and metadata"""
    
    def __init__(self, cdn_provider: CDNProvider, storage_service: MultiStorageService):
        self.cdn = cdn_provider
        self.storage = storage_service
        self.cache_ttl = {
            "metadata": 3600,     # 1 hour
            "model_files": 86400, # 24 hours
            "thumbnails": 604800  # 1 week
        }
    
    async def cache_model_assets(self, model_id: str, model: AIModel):
        """Cache model assets in CDN"""
        
        # Cache metadata
        metadata_url = await self.cdn.upload_file(
            content=json.dumps({
                "name": model.name,
                "description": model.description,
                "category": model.category,
                "framework": model.framework,
                "performance": model.performance_metrics
            }),
            key=f"models/{model_id}/metadata.json",
            content_type="application/json",
            ttl=self.cache_ttl["metadata"]
        )
        
        # Cache thumbnail/preview (if available)
        if hasattr(model, 'thumbnail_hash'):
            await self.cdn.upload_from_ipfs(
                ipfs_hash=model.thumbnail_hash,
                key=f"models/{model_id}/thumbnail.jpg",
                ttl=self.cache_ttl["thumbnails"]
            )
        
        # Cache model files (for popular models only)
        if await self._is_popular_model(model_id):
            await self.cdn.upload_from_ipfs(
                ipfs_hash=model.model_hash,
                key=f"models/{model_id}/model.bin",
                ttl=self.cache_ttl["model_files"]
            )
    
    async def get_cached_url(self, model_id: str, asset_type: str) -> str:
        """Get CDN URL for cached asset"""
        return self.cdn.get_url(f"models/{model_id}/{asset_type}")
    
    async def invalidate_cache(self, model_id: str):
        """Invalidate CDN cache for model updates"""
        await self.cdn.invalidate_pattern(f"models/{model_id}/*")
```

#### Ollama Auto-Quantization Pipeline
```python
class OllamaOptimizationPipeline:
    """Automatic model quantization and optimization for Ollama"""
    
    def __init__(self, quantization_service: QuantizationService):
        self.quantization = quantization_service
        self.supported_formats = ["gguf", "ggml", "awq", "gptq"]
    
    async def optimize_for_ollama(
        self,
        model_path: str,
        target_hardware: str,
        performance_requirements: dict
    ) -> OptimizedModel:
        """Optimize model for Ollama deployment"""
        
        # Analyze target hardware
        hardware_caps = await self._analyze_hardware(target_hardware)
        
        # Determine optimal quantization strategy
        quantization_config = self._select_quantization_strategy(
            hardware_caps, performance_requirements
        )
        
        # Perform quantization
        quantized_model = await self.quantization.quantize_model(
            model_path=model_path,
            config=quantization_config
        )
        
        # Generate Ollama configuration
        ollama_config = await self._generate_ollama_config(
            quantized_model, hardware_caps
        )
        
        # Test inference performance
        performance_metrics = await self._benchmark_inference(
            quantized_model, ollama_config
        )
        
        return OptimizedModel(
            original_hash=hashlib.sha256(open(model_path, 'rb').read()).hexdigest(),
            optimized_hash=quantized_model.hash,
            quantization_method=quantization_config.method,
            file_size_mb=quantized_model.size_mb,
            performance_metrics=performance_metrics,
            ollama_config=ollama_config,
            target_hardware=target_hardware
        )
    
    def _select_quantization_strategy(
        self,
        hardware_caps: dict,
        requirements: dict
    ) -> QuantizationConfig:
        """Select optimal quantization based on hardware and requirements"""
        
        memory_limit = hardware_caps.get("memory_gb", 8)
        compute_capability = hardware_caps.get("compute_capability", 7.0)
        precision_requirement = requirements.get("min_precision", 0.8)
        
        # Choose quantization method
        if memory_limit >= 24 and compute_capability >= 8.0:
            return QuantizationConfig(method="fp16", bits=16)
        elif memory_limit >= 16:
            return QuantizationConfig(method="gptq", bits=4, group_size=128)
        elif memory_limit >= 8:
            return QuantizationConfig(method="awq", bits=4)
        else:
            return QuantizationConfig(method="gguf", bits=3, context_size=2048)
    
    async def _generate_ollama_config(
        self,
        quantized_model: QuantizedModel,
        hardware_caps: dict
    ) -> dict:
        """Generate optimal Ollama configuration"""
        
        config = {
            "model": quantized_model.path,
            "context": min(hardware_caps.get("max_context", 4096), 4096),
            "threads": min(hardware_caps.get("cpu_cores", 4), 8),
            "gpu_layers": hardware_caps.get("gpu_layers", 0),
            "low_vram": hardware_caps.get("memory_gb", 16) < 8,
            "mmap": True,
            "mlock": False
        }
        
        # Adjust for quantization method
        if quantized_model.quantization_method in ["gptq", "awq"]:
            config["gpu_layers"] = min(config["gpu_layers"], 20)
        elif quantized_model.quantization_method == "gguf":
            config["gpu_layers"] = 0  # CPU-only for extreme quantization
        
        return config
```

#### 1.1 AIModelMarketplace Contract
```solidity
// Location: packages/solidity/aitbc-token/contracts/AIModelMarketplace.sol
contract AIModelMarketplace is AccessControl, ReentrancyGuard, ERC721 {
    using SafeMath for uint256;
    
    // Roles
    bytes32 public constant MODEL_CREATOR_ROLE = keccak256("MODEL_CREATOR_ROLE");
    bytes32 public constant MARKETPLACE_ADMIN_ROLE = keccak256("MARKETPLACE_ADMIN_ROLE");
    bytes32 public constant VERIFIER_ROLE = keccak256("VERIFIER_ROLE");
    
    // NFT Metadata
    string public constant name = "AITBC Model Ownership";
    string public constant symbol = "AITBC-MODEL";
    
    // Core structures
    struct ModelListing {
        uint256 id;
        address creator;
        string modelHash;        // IPFS/Arweave hash of model files
        string metadataHash;     // IPFS hash of metadata
        uint256 price;          // Price in AIT tokens
        uint256 royaltyBps;     // Royalty basis points (e.g., 250 = 2.5%)
        bool isActive;
        uint256 created_at;
        uint256 version;
        bool supportsFHE;       // FHE inference capability
        uint256 fhePrice;       // Additional cost for FHE inference
    }
    
    struct License {
        uint256 modelId;
        address buyer;
        uint256 purchased_at;
        uint256 expires_at;     // 0 for perpetual
        bool is_revocable;
        bool fhe_enabled;       // FHE inference access
    }
    
    // Gas optimization structures
    struct RoyaltyAccumulation {
        uint256 totalAccumulated;
        uint256 lastPayoutBlock;
        mapping(address => uint256) creatorShares;
    }
    
    // State variables
    uint256 public nextModelId = 1;
    uint256 public nextTokenId = 1;
    uint256 public constant MIN_ROYALTY_PAYOUT = 10 * 10**18; // 10 AIT minimum payout
    
    mapping(uint256 => ModelListing) public modelListings;
    mapping(address => uint256[]) public creatorModels;
    mapping(uint256 => License[]) public modelLicenses;
    mapping(address => mapping(uint256 => bool)) public userLicenses;
    mapping(uint256 => RoyaltyAccumulation) public royaltyPools;
    mapping(uint256 => uint256) public modelToTokenId; // Model ID to NFT token ID
    
    // Soulbound badges (non-transferable)
    mapping(address => mapping(bytes32 => bool)) public soulboundBadges;
    bytes32 public constant VERIFIED_CREATOR = keccak256("VERIFIED_CREATOR");
    bytes32 public constant QUALITY_MODEL = keccak256("QUALITY_MODEL");
    bytes32 public constant HIGH_USAGE = keccak256("HIGH_USAGE");
    
    // Events
    event ModelListed(uint256 indexed modelId, address indexed creator, uint256 price, uint256 royaltyBps);
    event ModelPurchased(uint256 indexed modelId, address indexed buyer, uint256 price);
    event RoyaltyDistributed(uint256 indexed modelId, address indexed creator, uint256 amount);
    event ModelNFTMinted(uint256 indexed modelId, uint256 indexed tokenId, address indexed owner);
    event BadgeAwarded(address indexed recipient, bytes32 indexed badgeType);
    event FHEInferenceExecuted(uint256 indexed modelId, address indexed user, bytes32 resultHash);
    
    constructor() ERC721("AITBC Model Ownership", "AITBC-MODEL") {
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(MARKETPLACE_ADMIN_ROLE, msg.sender);
    }
    
    // Model listing with NFT minting
    function listModel(
        string memory modelHash,
        string memory metadataHash,
        uint256 price,
        uint256 royaltyBps,
        bool supportsFHE,
        uint256 fhePrice
    ) external onlyRole(MODEL_CREATOR_ROLE) returns (uint256) {
        require(royaltyBps <= 10000, "Royalty too high"); // Max 100%
        
        uint256 modelId = nextModelId++;
        modelListings[modelId] = ModelListing({
            id: modelId,
            creator: msg.sender,
            modelHash: modelHash,
            metadataHash: metadataHash,
            price: price,
            royaltyBps: royaltyBps,
            isActive: true,
            created_at: block.timestamp,
            version: 1,
            supportsFHE: supportsFHE,
            fhePrice: fhePrice
        });
        
        creatorModels[msg.sender].push(modelId);
        
        // Mint NFT for model ownership
        uint256 tokenId = nextTokenId++;
        _mint(msg.sender, tokenId);
        modelToTokenId[modelId] = tokenId;
        
        emit ModelListed(modelId, msg.sender, price, royaltyBps);
        emit ModelNFTMinted(modelId, tokenId, msg.sender);
        
        return modelId;
    }
    
    // Purchase with batched royalty accumulation
    function purchaseModel(uint256 modelId) external nonReentrant {
        ModelListing storage model = modelListings[modelId];
        require(model.isActive, "Model not active");
        
        // Transfer payment
        require(AIToken(address(this)).transferFrom(msg.sender, address(this), model.price), "Payment failed");
        
        // Create license
        License memory license = License({
            modelId: modelId,
            buyer: msg.sender,
            purchased_at: block.timestamp,
            expires_at: 0, // Perpetual
            is_revocable: false,
            fhe_enabled: false
        });
        
        modelLicenses[modelId].push(license);
        userLicenses[msg.sender][modelId] = true;
        
        // Accumulate royalties instead of immediate payout
        uint256 royaltyAmount = model.price.mul(model.royaltyBps).div(10000);
        royaltyPools[modelId].totalAccumulated = royaltyPools[modelId].totalAccumulated.add(royaltyAmount);
        royaltyPools[modelId].creatorShares[model.creator] = royaltyPools[modelId].creatorShares[model.creator].add(royaltyAmount);
        
        emit ModelPurchased(modelId, msg.sender, model.price);
    }
    
    // Batch royalty payout to reduce gas costs
    function claimRoyalties(uint256 modelId) external {
        RoyaltyAccumulation storage pool = royaltyPools[modelId];
        require(pool.creatorShares[msg.sender] >= MIN_ROYALTY_PAYOUT, "Minimum payout not reached");
        require(pool.lastPayoutBlock < block.number, "Already paid this block");
        
        uint256 amount = pool.creatorShares[msg.sender];
        require(amount > 0, "No royalties to claim");
        
        pool.creatorShares[msg.sender] = 0;
        pool.totalAccumulated = pool.totalAccumulated.sub(amount);
        pool.lastPayoutBlock = block.number;
        
        require(AIToken(address(this)).transfer(msg.sender, amount), "Royalty transfer failed");
        
        emit RoyaltyDistributed(modelId, msg.sender, amount);
    }
    
    // Soulbound badge awarding
    function awardBadge(address recipient, bytes32 badgeType) external onlyRole(MARKETPLACE_ADMIN_ROLE) {
        require(!soulboundBadges[recipient][badgeType], "Badge already awarded");
        soulboundBadges[recipient][badgeType] = true;
        emit BadgeAwarded(recipient, badgeType);
    }
    
    // Override ERC721 transfers to make badges soulbound
    function _beforeTokenTransfer(address from, address to, uint256 tokenId, uint256 batchSize) internal override {
        // Allow initial minting but prevent transfers for soulbound badges
        require(from == address(0) || to == address(0), "Soulbound: transfers not allowed");
    }
    
    // Token URI for NFT metadata
    function tokenURI(uint256 tokenId) public view override returns (string memory) {
        uint256 modelId = _getModelIdFromTokenId(tokenId);
        ModelListing memory model = modelListings[modelId];
        return string(abi.encodePacked(_baseURI(), model.metadataHash));
    }
    
    function _getModelIdFromTokenId(uint256 tokenId) internal view returns (uint256) {
        // Reverse lookup - in production, maintain bidirectional mapping
        for (uint256 i = 1; i < nextModelId; i++) {
            if (modelToTokenId[i] == tokenId) {
                return i;
            }
        }
        revert("Token not found");
    }
}
```
```

#### 1.2 ModelVerification Contract
```solidity
// Location: packages/solidity/aitbc-token/contracts/ModelVerification.sol
contract ModelVerification is AccessControl {
    using ECDSA for bytes32;
    
    bytes32 public constant VERIFIER_ROLE = keccak256("VERIFIER_ROLE");
    
    // Model verification status
    enum VerificationStatus { Unverified, Pending, Verified, Rejected }
    
    struct ModelVerification {
        bytes32 modelHash;
        address submitter;
        VerificationStatus status;
        bytes32 verificationProof;  // ZK proof hash
        uint256 submittedAt;
        uint256 verifiedAt;
        address verifier;
        string rejectionReason;
    }
    
    mapping(uint256 => ModelVerification) public modelVerifications;
    mapping(bytes32 => uint256) public hashToModelId;
    
    event ModelVerificationSubmitted(uint256 indexed modelId, bytes32 modelHash, address submitter);
    event ModelVerified(uint256 indexed modelId, bytes32 proofHash, address verifier);
    event ModelVerificationRejected(uint256 indexed modelId, string reason);
    
    function submitForVerification(
        uint256 modelId,
        bytes32 modelHash,
        bytes32 verificationProof
    ) external onlyRole(MODEL_CREATOR_ROLE) {
        require(modelVerifications[modelId].status == VerificationStatus.Unverified, "Already submitted");
        
        modelVerifications[modelId] = ModelVerification({
            modelHash: modelHash,
            submitter: msg.sender,
            status: VerificationStatus.Pending,
            verificationProof: verificationProof,
            submittedAt: block.timestamp,
            verifiedAt: 0,
            verifier: address(0),
            rejectionReason: ""
        });
        
        hashToModelId[modelHash] = modelId;
        
        emit ModelVerificationSubmitted(modelId, modelHash, msg.sender);
    }
    
    function verifyModel(uint256 modelId, bool approved, string memory reason) 
        external onlyRole(VERIFIER_ROLE) 
    {
        ModelVerification storage verification = modelVerifications[modelId];
        require(verification.status == VerificationStatus.Pending, "Not pending verification");
        
        if (approved) {
            verification.status = VerificationStatus.Verified;
            verification.verifiedAt = block.timestamp;
            verification.verifier = msg.sender;
            emit ModelVerified(modelId, verification.verificationProof, msg.sender);
        } else {
            verification.status = VerificationStatus.Rejected;
            verification.rejectionReason = reason;
            emit ModelVerificationRejected(modelId, reason);
        }
    }
    
    function getVerificationStatus(uint256 modelId) external view returns (VerificationStatus) {
        return modelVerifications[modelId].status;
    }
}
```

#### 1.3 RoyaltyDistributor Contract
```solidity
// Location: packages/solidity/aitbc-token/contracts/RoyaltyDistributor.sol
contract RoyaltyDistributor {
    using SafeMath for uint256;
    
    struct RoyaltyPool {
        uint256 totalCollected;
        uint256 totalDistributed;
        mapping(address => uint256) creatorEarnings;
        mapping(address => uint256) creatorClaimable;
    }
    
    mapping(uint256 => RoyaltyPool) public royaltyPools;
    IAIToken public aitoken;
    
    function distributeRoyalty(uint256 modelId, uint256 saleAmount) external;
    function claimRoyalties(address creator) external;
    function getCreatorEarnings(address creator) external view returns (uint256);
}
```

### Phase 2: Backend Integration (Week 3-4)

#### 2.1 Database Models
```python
# Location: apps/coordinator-api/src/app/domain/model_marketplace.py
class AIModel(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    onchain_model_id: int = Field(index=True)  # Blockchain model ID
    creator_address: str = Field(index=True)
    model_hash: str = Field(index=True)  # IPFS hash
    metadata_hash: str
    name: str
    description: str
    category: str
    tags: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    price: float
    royalty_bps: int = Field(default=0)  # Basis points
    is_active: bool = Field(default=True)
    version: int = Field(default=1)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Verification and quality assurance
    verification_status: str = Field(default="unverified")  # unverified, pending, verified, rejected
    verification_proof_hash: Optional[str] = Field(default=None)
    verified_at: Optional[datetime] = None
    verified_by: Optional[str] = Field(default=None)  # verifier address
    rejection_reason: Optional[str] = None
    
    # Privacy and security
    encryption_scheme: Optional[str] = Field(default=None)  # FHE scheme used
    is_privacy_preserved: bool = Field(default=False)
    zk_proof_available: bool = Field(default=False)
    
    # Model-specific attributes
    model_type: str  # "llm", "cv", "audio", etc.
    framework: str   # "pytorch", "tensorflow", "onnx"
    hardware_requirements: dict = Field(default_factory=dict, sa_column=Column(JSON))
    performance_metrics: dict = Field(default_factory=dict, sa_column=Column(JSON))
    file_size_mb: int
    license_type: str = Field(default="commercial")  # "commercial", "research", "custom"

class ModelLicense(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    model_id: str = Field(foreign_key="aimodel.id", index=True)
    buyer_address: str = Field(index=True)
    purchase_transaction_hash: str = Field(index=True)
    purchased_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    is_revocable: bool = Field(default=False)
    is_active: bool = Field(default=True)
    usage_count: int = Field(default=0)
    last_used_at: Optional[datetime] = None

class ModelReview(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    model_id: str = Field(foreign_key="aimodel.id", index=True)
    reviewer_address: str = Field(index=True)
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_verified_purchase: bool = Field(default=False)
```

#### 2.2 Service Layer
```python
# Location: apps/coordinator-api/src/app/services/model_marketplace.py
class ModelMarketplaceService:
    def __init__(self, session: SessionDep, blockchain_service: BlockchainService, 
                 zk_service: ZKProofService, encryption_service: EncryptionService):
        self.session = session
        self.blockchain = blockchain_service
        self.zk_service = zk_service
        self.encryption_service = encryption_service
        self.ipfs_client = IPFSClient()
        self.arweave_client = ArweaveClient()
        self.gpu_service = gpu_service
    
    async def list_model(self, request: ModelListingRequest) -> ModelListing:
        """List a new model with comprehensive validation and quality scanning"""
        # 1. Pre-listing quality scan
        quality_report = await self._scan_model_quality(request.model_files, request.metadata)
        if not quality_report.passed:
            raise ValidationError(f"Quality scan failed: {quality_report.issues}")
        
        # 2. Generate verification proof and watermark
        verification_proof = await self._generate_model_verification_proof(request.model_files)
        watermarked_files = await self._apply_digital_watermarking(request.model_files, request.creator_address)
        
        # 3. Multi-storage upload (IPFS + Arweave fallback)
        storage_result = await self._upload_to_redundant_storage(watermarked_files, request.metadata)
        model_hash = storage_result.primary_hash
        fallback_hash = storage_result.fallback_hash
        
        # 4. Encrypt model if privacy preservation requested
        if request.privacy_preserved:
            encrypted_model, encryption_keys = await self._encrypt_model_files(
                watermarked_files, request.allowed_recipients
            )
            model_hash = await self.ipfs_client.upload_files(encrypted_model)
            encryption_scheme = "FHE-BFV"
        else:
            encryption_scheme = None
        
        # 5. Submit for verification and mint NFT
        verification_tx = await self.blockchain.submit_model_for_verification(
            model_hash=model_hash,
            verification_proof=verification_proof
        )
        
        listing_tx = await self.blockchain.list_model_with_nft(
            creator=request.creator_address,
            model_hash=model_hash,
            metadata_hash=storage_result.metadata_hash,
            price=request.price,
            royalty_bps=request.royalty_bps,
            supports_fhe=request.supports_fhe,
            fhe_price=request.fhe_price
        )
        
        # 6. Create database record with enhanced fields
        model = AIModel(
            onchain_model_id=await self.blockchain.get_model_id_from_tx(listing_tx),
            creator_address=request.creator_address,
            model_hash=model_hash,
            fallback_hash=fallback_hash,
            metadata_hash=storage_result.metadata_hash,
            name=request.metadata["name"],
            description=request.metadata["description"],
            category=request.metadata["category"],
            price=request.price,
            royalty_bps=request.royalty_bps,
            verification_status="pending",
            verification_proof_hash=verification_proof.hex(),
            encryption_scheme=encryption_scheme,
            is_privacy_preserved=request.privacy_preserved,
            zk_proof_available=True,
            supports_fhe=request.supports_fhe,
            fhe_price=request.fhe_price,
            quality_score=quality_report.score,
            malware_free=quality_report.malware_free,
            bias_score=quality_report.bias_score,
            model_type=request.metadata["model_type"],
            framework=request.metadata["framework"],
            hardware_requirements=request.metadata["hardware_requirements"],
            performance_metrics=request.metadata["performance_metrics"],
            file_size_mb=request.metadata["file_size_mb"],
            license_type=request.metadata.get("license_type", "commercial")
        )
        
        self.session.add(model)
        await self.session.commit()
        
        return ModelListing.from_orm(model)
    
    async def _scan_model_quality(self, model_files: List[bytes], metadata: dict) -> QualityReport:
        """Comprehensive quality scanning for model files"""
        report = QualityReport()
        
        # Malware scanning
        report.malware_free = await self._scan_for_malware(model_files)
        
        # Model quality metrics
        report.score = await self._evaluate_model_quality(model_files, metadata)
        
        # Bias and fairness testing
        report.bias_score = await self._test_model_bias(model_files, metadata)
        
        # Performance validation
        report.performance_validated = await self._validate_performance_claims(metadata)
        
        report.passed = (report.malware_free and report.score >= 0.7 and 
                        report.bias_score >= 0.6 and report.performance_validated)
        
        return report
    
    async def _upload_to_redundant_storage(self, files: List[bytes], metadata: dict) -> StorageResult:
        """Upload to multiple storage backends with fallback"""
        # Primary: IPFS
        try:
            primary_hash = await self.ipfs_client.upload_files(files)
            metadata_hash = await self.ipfs_client.upload_json(metadata)
        except Exception as e:
            logger.error(f"IPFS upload failed: {e}")
            raise
        
        # Fallback: Arweave
        try:
            fallback_hash = await self.arweave_client.upload_files(files)
        except Exception as e:
            logger.warning(f"Arweave upload failed: {e}")
            fallback_hash = None
        
        return StorageResult(
            primary_hash=primary_hash,
            fallback_hash=fallback_hash,
            metadata_hash=metadata_hash
        )
    
    async def execute_gpu_inference(
        self,
        model_id: str,
        input_data: dict,
        user_address: str,
        privacy_level: str = "standard"
    ) -> InferenceResult:
        """Execute model inference with automatic GPU allocation"""
        # 1. Verify license
        license = await self._verify_license(model_id, user_address)
        if not license or not license.is_active:
            raise PermissionError("No valid license found")
        
        # 2. Get model and optimize for GPU
        model = await self._get_model(model_id)
        optimized_model = await self._optimize_model_for_gpu(model, privacy_level)
        
        # 3. Allocate GPU resources
        gpu_allocation = await self.gpu_service.allocate_optimal_gpu(
            model.hardware_requirements,
            input_data["estimated_compute"]
        )
        
        # 4. Execute inference job
        job_spec = {
            "model_hash": optimized_model.model_hash,
            "input_data": input_data,
            "privacy_level": privacy_level,
            "gpu_requirements": gpu_allocation,
            "user_license": license.id
        }
        
        job_id = await self.coordinator.submit_job(job_spec)
        result = await self.coordinator.wait_for_job(job_id, timeout=300)
        
        # 5. Track usage and billing
        await self._track_inference_usage(model_id, user_address, gpu_allocation, result)
        
        return InferenceResult(
            output=result["output"],
            execution_time=result["execution_time"],
            cost=result["cost"],
            gpu_used=gpu_allocation["gpu_id"]
        )
    
    async def _generate_model_verification_proof(self, model_files: List[bytes]) -> bytes:
        """Generate ZK proof for model integrity verification"""
        # Create circuit inputs for model verification
        model_hash = self._calculate_model_hash(model_files)
        
        # Generate proof using existing ZK infrastructure
        proof = await self.zk_service.generate_proof(
            circuit_name="model_integrity",
            public_inputs={"model_hash": model_hash},
            private_inputs={"model_data": model_files}
        )
        
        return proof
    
    async def _encrypt_model_files(self, model_files: List[bytes], recipients: List[str]) -> Tuple[List[bytes], dict]:
        """Encrypt model files for privacy preservation"""
        # Use existing encryption service for multi-party encryption
        encrypted_data = await self.encryption_service.encrypt_files(
            files=model_files,
            participants=recipients,
            include_audit=True
        )
        
        return encrypted_data.ciphertext, encrypted_data.encrypted_keys
    
    async def purchase_model_license(self, request: ModelPurchaseRequest) -> ModelLicense:
        """Purchase a license for a model"""
        # 1. Get model details
        model = await self._get_active_model(request.model_id)
        
        # 2. Process payment via smart contract
        tx_hash = await self.blockchain.purchase_model_license(
            model_id=model.onchain_model_id,
            buyer=request.buyer_address,
            price=model.price
        )
        
        # 3. Create license record
        license = ModelLicense(
            model_id=model.id,
            buyer_address=request.buyer_address,
            purchase_transaction_hash=tx_hash,
            expires_at=request.expires_at,
            is_revocable=model.license_type == "commercial"
        )
        
        self.session.add(license)
        await self.session.commit()
        
        # 4. Distribute royalties if applicable
        if model.royalty_bps > 0:
            await self.blockchain.distribute_royalty(
                model_id=model.onchain_model_id,
                sale_amount=model.price
            )
        
        return ModelLicense.from_orm(license)
    
    async def get_model_files(self, model_id: str, requester_address: str) -> bytes:
        """Get model files if user has valid license"""
        # 1. Verify license
        license = await self._verify_license(model_id, requester_address)
        if not license or not license.is_active:
            raise PermissionError("No valid license found")
        
        # 2. Update usage tracking
        license.usage_count += 1
        license.last_used_at = datetime.utcnow()
        await self.session.commit()
        
        # 3. Fetch from IPFS
        model = await self._get_model(model_id)
        return await self.ipfs_client.download_files(model.model_hash)
```

#### 2.3 API Endpoints
```python
# Location: apps/coordinator-api/src/app/routers/model_marketplace.py
router = APIRouter(tags=["model-marketplace"])

@router.post("/model-marketplace/list", response_model=ModelListing)
async def list_model(
    request: ModelListingRequest,
    session: SessionDep,
    current_user: CurrentUserDep
) -> ModelListing:
    """List a new model on the marketplace with verification and privacy options"""
    service = ModelMarketplaceService(session, blockchain_service, zk_service, encryption_service)
    return await service.list_model(request)

@router.post("/model-marketplace/{model_id}/verify", response_model=VerificationResponse)
async def submit_model_for_verification(
    model_id: str,
    verification_request: VerificationRequest,
    session: SessionDep,
    current_user: CurrentUserDep
) -> VerificationResponse:
    """Submit model for verification with ZK proof"""
    service = ModelMarketplaceService(session, blockchain_service, zk_service, encryption_service)
    return await service.submit_for_verification(model_id, verification_request)

@router.get("/model-marketplace/models", response_model=List[ModelView])
async def list_models(
    *,
    session: SessionDep,
    category_filter: Optional[str] = Query(None),
    creator_filter: Optional[str] = Query(None),
    verification_filter: Optional[str] = Query(None),  # verified, unverified, pending
    privacy_filter: Optional[bool] = Query(None),     # privacy preserved models only
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    sort_by: str = Query("created_at", regex="^(created_at|price|rating|downloads)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
) -> List[ModelView]:
    """Browse models with enhanced filters including verification and privacy"""
    service = ModelMarketplaceService(session, blockchain_service, zk_service, encryption_service)
    return await service.list_models(
        category=category_filter,
        creator=creator_filter,
        verification_status=verification_filter,
        privacy_preserved=privacy_filter,
        price_range=(min_price, max_price),
        sort_by=sort_by,
        limit=limit,
        offset=offset
    )

@router.post("/model-marketplace/purchase", response_model=ModelLicense)
async def purchase_model(
    request: ModelPurchaseRequest,
    session: SessionDep,
    current_user: CurrentUserDep
) -> ModelLicense:
    """Purchase a model license"""
    service = ModelMarketplaceService(session, blockchain_service)
    return await service.purchase_model_license(request)

@router.get("/model-marketplace/models/{model_id}/download")
async def download_model(
    model_id: str,
    session: SessionDep,
    current_user: CurrentUserDep
) -> StreamingResponse:
    """Download model files (requires valid license)"""
    service = ModelMarketplaceService(session, blockchain_service)
    model_files = await service.get_model_files(model_id, current_user.address)
    return StreamingResponse(
        io.BytesIO(model_files),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename=model_{model_id}.zip"}
    )
```

### Phase 3: Frontend Integration (Week 5-6)

#### 3.1 Model Marketplace Web Interface
```typescript
// Location: apps/model-marketplace-web/src/components/ModelCard.tsx
interface ModelCardProps {
  model: ModelView;
  onPurchase: (modelId: string) => void;
  onPreview: (modelId: string) => void;
}

export const ModelCard: React.FC<ModelCardProps> = ({ model, onPurchase, onPreview }) => {
  return (
    <div className="model-card">
      <div className="model-header">
        <h3>{model.name}</h3>
        <div className="model-category">{model.category}</div>
      </div>
      
      <div className="model-description">
        {model.description}
      </div>
      
      <div className="model-specs">
        <div className="spec">
          <span className="label">Framework:</span>
          <span>{model.framework}</span>
        </div>
        <div className="spec">
          <span className="label">Size:</span>
          <span>{model.file_size_mb}MB</span>
        </div>
        <div className="spec">
          <span className="label">Rating:</span>
          <Rating value={model.average_rating} readonly />
        </div>
      </div>
      
      <div className="model-footer">
        <div className="price">
          {model.price} AIT
          {model.royalty_bps > 0 && (
            <span className="royalty">+{model.royalty_bps / 100}% royalty</span>
          )}
        </div>
        <div className="actions">
          <button onClick={() => onPreview(model.id)}>Preview</button>
          <button 
            className="purchase-btn"
            onClick={() => onPurchase(model.id)}
          >
            Purchase
          </button>
        </div>
      </div>
    </div>
  );
};
```

#### 3.2 Model Upload Interface
```typescript
// Location: apps/model-marketplace-web/src/components/ModelUpload.tsx
export const ModelUpload: React.FC = () => {
  const [uploadProgress, setUploadProgress] = useState(0);
  const [modelFiles, setModelFiles] = useState<File[]>([]);
  const [metadata, setMetadata] = useState<ModelMetadata>({
    name: "",
    description: "",
    category: "",
    model_type: "",
    framework: "",
    hardware_requirements: {},
    performance_metrics: {},
    license_type: "commercial"
  });
  
  const handleUpload = async () => {
    try {
      const formData = new FormData();
      modelFiles.forEach(file => formData.append("files", file));
      formData.append("metadata", JSON.stringify(metadata));
      formData.append("price", price.toString());
      formData.append("royalty_bps", royaltyBps.toString());
      
      const response = await fetch("/api/model-marketplace/list", {
        method: "POST",
        body: formData,
        onUploadProgress: (progressEvent) => {
          const progress = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total
          );
          setUploadProgress(progress);
        }
      });
      
      if (response.ok) {
        // Handle success
        navigate("/my-models");
      }
    } catch (error) {
      // Handle error
    }
  };
  
  return (
    <div className="model-upload">
      <h2>List Your Model</h2>
      
      <FileUpload
        files={modelFiles}
        onChange={setModelFiles}
        accept=".zip,.tar.gz,.pth,.h5,.onnx"
        maxSize="10GB"
      />
      
      <MetadataForm
        metadata={metadata}
        onChange={setMetadata}
      />
      
      <PricingSection
        price={price}
        royaltyBps={royaltyBps}
        onPriceChange={setPrice}
        onRoyaltyChange={setRoyaltyBps}
      />
      
      <UploadProgress progress={uploadProgress} />
      
      <button 
        onClick={handleUpload}
        disabled={uploadProgress > 0 && uploadProgress < 100}
      >
        {uploadProgress > 0 ? "Uploading..." : "List Model"}
      </button>
    </div>
  );
};
```

### Phase 4: Integration Testing (Week 7)

#### 4.1 Smart Contract Tests
```javascript
// Location: packages/solidity/aitbc-token/test/ModelMarketplace.test.js
describe("AIModelMarketplace", function () {
  let marketplace, aitoken, modelRegistry;
  let owner, creator, buyer;
  
  beforeEach(async function () {
    [owner, creator, buyer] = await ethers.getSigners();
    
    aitoken = await AIToken.deploy(owner.address);
    marketplace = await AIModelMarketplace.deploy(owner.address);
    modelRegistry = await ModelRegistry.deploy();
    
    await marketplace.grantRole(await marketplace.MODEL_CREATOR_ROLE(), creator.address);
  });
  
  it("Should list a new model", async function () {
    const modelHash = "QmTest123";
    const metadataHash = "QmMetadata456";
    const price = ethers.parseEther("100");
    const royaltyBps = 250; // 2.5%
    
    await expect(marketplace.connect(creator).listModel(
      modelHash,
      metadataHash,
      price,
      royaltyBps
    )).to.emit(marketplace, "ModelListed")
     .withArgs(1, creator.address, price, royaltyBps);
    
    const model = await marketplace.modelListings(1);
    expect(model.creator).to.equal(creator.address);
    expect(model.price).to.equal(price);
    expect(model.royaltyBps).to.equal(royaltyBps);
  });
  
  it("Should purchase model and distribute royalties", async function () {
    // First list a model
    await marketplace.connect(creator).listModel(
      "QmTest123",
      "QmMetadata456",
      ethers.parseEther("100"),
      250
    );
    
    // Mint tokens to buyer
    await aitoken.mint(buyer.address, ethers.parseEther("1000"));
    await aitoken.connect(buyer).approve(marketplace.getAddress(), ethers.parseEther("100"));
    
    // Purchase model
    await expect(marketplace.connect(buyer).purchaseModel(1))
      .to.emit(marketplace, "ModelPurchased")
      .withArgs(1, buyer.address, ethers.parseEther("100"));
    
    // Check royalty distribution
    const royaltyPool = await marketplace.royaltyPools(1);
    expect(royaltyPool.totalCollected).to.equal(ethers.parseEther("2.5")); // 2.5% royalty
  });
});
```

#### 4.2 Integration Tests
```python
# Location: tests/integration/test_model_marketplace.py
@pytest.mark.asyncio
async def test_model_listing_workflow(coordinator_client, test_wallet):
    """Test complete model listing workflow"""
    # 1. Prepare model data
    model_files = create_test_model_files()
    metadata = {
        "name": "Test Model",
        "description": "A test model for integration testing",
        "category": "nlp",
        "model_type": "llm",
        "framework": "pytorch",
        "hardware_requirements": {"gpu_memory_gb": 8, "ram_gb": 16},
        "performance_metrics": {"accuracy": 0.95, "inference_time_ms": 100},
        "file_size_mb": 1024
    }
    
    # 2. List model
    listing_request = ModelListingRequest(
        creator_address=test_wallet.address,
        model_files=model_files,
        metadata=metadata,
        price=100.0,
        royalty_bps=250
    )
    
    response = await coordinator_client.post("/model-marketplace/list", json=listing_request.dict())
    assert response.status_code == 200
    
    model_listing = ModelListing(**response.json())
    assert model_listing.name == "Test Model"
    assert model_listing.price == 100.0
    assert model_listing.royalty_bps == 250
    
    # 3. Verify on-chain listing
    onchain_model = await blockchain_client.get_model_listing(model_listing.onchain_model_id)
    assert onchain_model["creator"] == test_wallet.address
    assert onchain_model["price"] == 100 * 10**18  # Wei
    
    # 4. Purchase model
    purchase_request = ModelPurchaseRequest(
        model_id=model_listing.id,
        buyer_address=test_wallet.address
    )
    
    response = await coordinator_client.post("/model-marketplace/purchase", json=purchase_request.dict())
    assert response.status_code == 200
    
    license_info = ModelLicense(**response.json())
    assert license_info.buyer_address == test_wallet.address
    assert license_info.is_active == True
    
    # 5. Download model files
    response = await coordinator_client.get(f"/model-marketplace/models/{model_listing.id}/download")
    assert response.status_code == 200
    assert len(response.content) > 0
    
    # 6. Verify royalty tracking
    royalties = await blockchain_client.get_royalty_pool(model_listing.onchain_model_id)
    assert royalties["total_collected"] == 2.5 * 10**18  # 2.5% of 100 AIT
```

### Phase 5: Deployment & Monitoring (Week 8)

#### 5.1 Smart Contract Deployment
```bash
# Location: packages/solidity/aitbc-token/scripts/deploy-model-marketplace.sh
#!/bin/bash

# Deploy Model Marketplace Contracts
echo "Deploying AI Model Marketplace contracts..."

# Deploy ModelRegistry
npx hardhat run scripts/deploy-model-registry.js --network mainnet
MODEL_REGISTRY_ADDRESS=$(cat deployments/mainnet/ModelRegistry.json | jq -r '.address')

# Deploy AIModelMarketplace
npx hardhat run scripts/deploy-model-marketplace.js --network mainnet
MARKETPLACE_ADDRESS=$(cat deployments/mainnet/AIModelMarketplace.json | jq -r '.address')

# Deploy RoyaltyDistributor
npx hardhat run scripts/deploy-royalty-distributor.js --network mainnet
ROYALTY_DISTRIBUTOR_ADDRESS=$(cat deployments/mainnet/RoyaltyDistributor.json | jq -r '.address')

# Verify contracts
npx hardhat verify --network mainnet $MODEL_REGISTRY_ADDRESS
npx hardhat verify --network mainnet $MARKETPLACE_ADDRESS
npx hardhat verify --network mainnet $ROYALTY_DISTRIBUTOR_ADDRESS

echo "Deployment complete:"
echo "ModelRegistry: $MODEL_REGISTRY_ADDRESS"
echo "AIModelMarketplace: $MARKETPLACE_ADDRESS"
echo "RoyaltyDistributor: $ROYALTY_DISTRIBUTOR_ADDRESS"
```

#### 5.2 Monitoring & Metrics
```python
# Location: apps/coordinator-api/src/app/metrics/model_marketplace.py
from prometheus_client import Counter, Histogram, Gauge

# Model marketplace metrics
model_listings_total = Counter(
    'model_marketplace_listings_total',
    'Total number of models listed',
    ['category', 'creator']
)

model_purchases_total = Counter(
    'model_marketplace_purchases_total',
    'Total number of model purchases',
    ['model_category', 'price_range']
)

model_royalties_total = Counter(
    'model_marketplace_royalties_total',
    'Total royalties distributed',
    ['creator']
)

model_download_duration = Histogram(
    'model_marketplace_download_duration_seconds',
    'Time spent downloading model files',
    ['model_size_mb']
)

active_models_gauge = Gauge(
    'model_marketplace_active_models',
    'Number of active models',
    ['category']
)
```

## Risk Assessment & Mitigation

### Technical Risks

#### 1. IPFS Storage Reliability
- **Risk**: IPFS pinning service failure, content availability
- **Mitigation**: Multiple pinning providers, local caching, content verification

#### 2. Smart Contract Security
- **Risk**: Reentrancy attacks, access control bypass
- **Mitigation**: OpenZeppelin libraries, comprehensive testing, security audits

#### 3. Model File Integrity
- **Risk**: Model tampering, corrupted downloads
- **Mitigation**: Hash verification, version control, integrity checks with ZK proofs

#### 4. ZK Proof Performance
- **Risk**: Proof generation too slow for large models
- **Mitigation**: Recursive proof techniques, model compression, proof caching

#### 5. Privacy Mechanism Overhead
- **Risk**: FHE operations too expensive for practical use
- **Mitigation**: Model optimization, selective encryption, hybrid approaches

### Business Risks

#### 1. Model Piracy
- **Risk**: Unauthorized redistribution of purchased models
- **Mitigation**: License tracking, watermarking, legal terms, privacy-preserving access controls

#### 2. Quality Control
- **Risk**: Low-quality or malicious models
- **Mitigation**: Review process, rating system, creator verification, automated model validation

#### 3. Privacy vs Usability Trade-offs
- **Risk**: Privacy features reduce model usability
- **Mitigation**: Configurable privacy levels, hybrid approaches, user education

### Privacy-Specific Risks

#### 1. Key Management Complexity
- **Risk**: Secure distribution of encryption keys
- **Mitigation**: Multi-party computation, threshold cryptography, hardware security modules

#### 2. ZK Proof Verification Overhead
- **Risk**: Verification too expensive for frequent operations
- **Mitigation**: Batch verification, proof aggregation, optimized circuits

## Success Metrics

### Technical Metrics
- **Model Listing Success Rate**: >95%
- **Download Success Rate**: >98%
- **Transaction Confirmation Time**: <5 minutes
- **Smart Contract Gas Efficiency**: <200k gas per operation

### Business Metrics
- **Models Listed**: 100+ in first quarter
- **Active Creators**: 50+ in first quarter
- **Model Purchases**: 500+ transactions in first quarter
- **Royalty Distribution**: $10k+ in first quarter

## Timeline Summary

| Week | Phase | Key Deliverables |
|------|-------|------------------|
| 1-2 | Smart Contract Development | AIModelMarketplace, ModelVerification, RoyaltyDistributor contracts with privacy features |
| 3-4 | Backend Integration | Database models with verification fields, service layer with ZK/FHE integration, API endpoints |
| 5-6 | Frontend Integration | Model marketplace UI with privacy options, upload interface with verification, purchase flow |
| 7-8 | Privacy & Verification Testing | Smart contract tests, API integration tests, ZK proof validation, FHE testing, end-to-end tests |
| 9-10 | Advanced Features & Optimization | Batch verification, proof aggregation, model compression, performance optimization |
| 11-12 | Deployment & Monitoring | Contract deployment with privacy features, monitoring setup, documentation, security audits |

## Resource Requirements

### Development Team
- **Smart Contract Developer**: 1 FTE (Weeks 1-2, 8, 12)
- **Cryptography Engineer**: 1 FTE (Weeks 1-4, 7-10) - ZK proofs and privacy mechanisms
- **Backend Developer**: 1.5 FTE (Weeks 3-4, 7-8, 10-12) - Enhanced with privacy integration
- **Frontend Developer**: 1 FTE (Weeks 5-6, 9-10) - Privacy options and verification UI
- **DevOps Engineer**: 1 FTE (Weeks 8, 11-12) - Privacy infrastructure deployment
- **Security Researcher**: 0.5 FTE (Weeks 7-12) - Privacy and verification security analysis

### Infrastructure
- **IPFS Cluster**: 3 nodes for redundancy
- **Blockchain Node**: Dedicated node for contract interactions
- **ZK Proving Service**: Cloud-based proving service for large circuits
- **FHE Computation Nodes**: Specialized hardware for homomorphic operations
- **Database Storage**: Additional 200GB for model metadata and verification data
- **Monitoring**: Enhanced Prometheus/Grafana with privacy metrics

### Budget Estimate
- **Development**: ~300 hours total (increased due to privacy complexity)
- **Cryptography Research**: ~100 hours for ZK/FHE optimization
- **Infrastructure**: $3,000/month additional (ZK proving, FHE nodes)
- **Security Audit**: $25,000 (including privacy audit)
- **IPFS Storage**: $500/month
- **Specialized Hardware**: $5,000 one-time for FHE acceleration

## Conclusion

The on-chain model marketplace implementation leverages existing AITBC infrastructure while introducing sophisticated model trading, licensing, and royalty mechanisms. The phased approach ensures manageable development cycles with clear deliverables and risk mitigation strategies.

The implementation positions AITBC as a leader in decentralized AI model economies, providing creators with monetization opportunities and users with access to verified, high-quality models through a transparent blockchain-based marketplace.
