# Marketplace Backend Analysis

## Current Implementation Status

### ✅ Implemented Features

#### 1. Basic Marketplace Offers
- **Endpoint**: `GET /marketplace/offers`
- **Service**: `MarketplaceService.list_offers()`
- **Status**: ✅ Implemented (returns mock data)
- **Notes**: Returns hardcoded mock offers, not from database

#### 2. Marketplace Statistics
- **Endpoint**: `GET /marketplace/stats`
- **Service**: `MarketplaceService.get_stats()`
- **Status**: ✅ Implemented
- **Features**: 
  - Total offers count
  - Open capacity
  - Average price
  - Active bids count

#### 3. Marketplace Bids
- **Endpoint**: `POST /marketplace/bids`
- **Service**: `MarketplaceService.create_bid()`
- **Status**: ✅ Implemented
- **Features**: Create bids with provider, capacity, price, and notes

#### 4. Miner Offer Synchronization
- **Endpoint**: `POST /marketplace/sync-offers`
- **Service**: Creates offers from registered miners
- **Status**: ✅ Implemented (admin only)
- **Features**: 
  - Syncs online miners to marketplace offers
  - Extracts GPU capabilities from miner attributes
  - Creates offers with pricing, GPU model, memory, etc.

#### 5. Miner Offers List
- **Endpoint**: `GET /marketplace/miner-offers`
- **Service**: Lists offers created from miners
- **Status**: ✅ Implemented
- **Features**: Returns offers with detailed GPU information

### ❌ Missing Features (Expected by CLI)

#### 1. GPU-Specific Endpoints
The CLI expects a `/v1/marketplace/gpu/` prefix for all operations, but these are **NOT IMPLEMENTED**:

- `POST /v1/marketplace/gpu/register` - Register GPU in marketplace
- `GET /v1/marketplace/gpu/list` - List available GPUs
- `GET /v1/marketplace/gpu/{gpu_id}` - Get GPU details
- `POST /v1/marketplace/gpu/{gpu_id}/book` - Book/reserve a GPU
- `POST /v1/marketplace/gpu/{gpu_id}/release` - Release a booked GPU
- `GET /v1/marketplace/gpu/{gpu_id}/reviews` - Get GPU reviews
- `POST /v1/marketplace/gpu/{gpu_id}/reviews` - Add GPU review

#### 2. GPU Booking System
- **Status**: ❌ Not implemented
- **Missing Features**:
  - GPU reservation/booking logic
  - Booking duration tracking
  - Booking status management
  - Automatic release after timeout

#### 3. GPU Reviews System
- **Status**: ❌ Not implemented
- **Missing Features**:
  - Review storage and retrieval
  - Rating aggregation
  - Review moderation
  - Review-per-gpu association

#### 4. GPU Registry
- **Status**: ❌ Not implemented
- **Missing Features**:
  - Individual GPU registration
  - GPU specifications storage
  - GPU status tracking (available, booked, offline)
  - GPU health monitoring

#### 5. Order Management
- **Status**: ❌ Not implemented
- **CLI expects**: `GET /v1/marketplace/orders`
- **Missing Features**:
  - Order creation from bookings
  - Order tracking
  - Order history
  - Order status updates

#### 6. Pricing Information
- **Status**: ❌ Not implemented
- **CLI expects**: `GET /v1/marketplace/pricing/{model}`
- **Missing Features**:
  - Model-specific pricing
  - Dynamic pricing based on demand
  - Historical pricing data
  - Price recommendations

### 🔧 Data Model Issues

#### 1. MarketplaceOffer Model Limitations
Current model lacks GPU-specific fields:
```python
class MarketplaceOffer(SQLModel, table=True):
    id: str
    provider: str  # Miner ID
    capacity: int  # Number of concurrent jobs
    price: float  # Price per hour
    sla: str
    status: str  # open, closed, etc.
    created_at: datetime
    attributes: dict  # Contains GPU info but not structured
```

**Missing GPU-specific fields**:
- `gpu_id`: Unique GPU identifier
- `gpu_model`: GPU model name
- `gpu_memory`: GPU memory in GB
- `gpu_status`: available, booked, offline
- `booking_expires`: When current booking expires
- `total_bookings`: Number of times booked
- `average_rating`: Aggregated review rating

#### 2. No Booking/Order Models
Missing models for:
- `GPUBooking`: Track GPU reservations
- `GPUOrder`: Track completed GPU usage
- `GPUReview`: Store GPU reviews
- `GPUPricing`: Store pricing tiers

### 📊 API Endpoint Comparison

| CLI Command | Expected Endpoint | Implemented | Status |
|-------------|------------------|-------------|---------|
| `aitbc marketplace gpu register` | `POST /v1/marketplace/gpu/register` | ❌ | Missing |
| `aitbc marketplace gpu list` | `GET /v1/marketplace/gpu/list` | ❌ | Missing |
| `aitbc marketplace gpu details` | `GET /v1/marketplace/gpu/{id}` | ❌ | Missing |
| `aitbc marketplace gpu book` | `POST /v1/marketplace/gpu/{id}/book` | ❌ | Missing |
| `aitbc marketplace gpu release` | `POST /v1/marketplace/gpu/{id}/release` | ❌ | Missing |
| `aitbc marketplace reviews` | `GET /v1/marketplace/gpu/{id}/reviews` | ❌ | Missing |
| `aitbc marketplace review add` | `POST /v1/marketplace/gpu/{id}/reviews` | ❌ | Missing |
| `aitbc marketplace orders list` | `GET /v1/marketplace/orders` | ❌ | Missing |
| `aitbc marketplace pricing` | `GET /v1/marketplace/pricing/{model}` | ❌ | Missing |

### 🚀 Recommended Implementation Plan

#### Phase 1: Core GPU Marketplace
1. **Create GPU Registry Model**:
   ```python
   class GPURegistry(SQLModel, table=True):
       gpu_id: str = Field(primary_key=True)
       miner_id: str
       gpu_model: str
       gpu_memory_gb: int
       cuda_version: str
       status: str  # available, booked, offline
       current_booking_id: Optional[str] = None
       booking_expires: Optional[datetime] = None
       attributes: dict = Field(default_factory=dict)
   ```

2. **Implement GPU Endpoints**:
   - Add `/v1/marketplace/gpu/` router
   - Implement all CRUD operations for GPUs
   - Add booking/unbooking logic

3. **Create Booking System**:
   ```python
   class GPUBooking(SQLModel, table=True):
       booking_id: str = Field(primary_key=True)
       gpu_id: str
       client_id: str
       job_id: Optional[str]
       duration_hours: float
       start_time: datetime
       end_time: datetime
       total_cost: float
       status: str  # active, completed, cancelled
   ```

#### Phase 2: Reviews and Ratings
1. **Review System**:
   ```python
   class GPUReview(SQLModel, table=True):
       review_id: str = Field(primary_key=True)
       gpu_id: str
       client_id: str
       rating: int = Field(ge=1, le=5)
       comment: str
       created_at: datetime
   ```

2. **Rating Aggregation**:
   - Add `average_rating` to GPURegistry
   - Update rating on each new review
   - Implement rating history tracking

#### Phase 3: Orders and Pricing
1. **Order Management**:
   ```python
   class GPUOrder(SQLModel, table=True):
       order_id: str = Field(primary_key=True)
       booking_id: str
       client_id: str
       gpu_id: str
       status: str
       created_at: datetime
       completed_at: Optional[datetime]
   ```

2. **Dynamic Pricing**:
   ```python
   class GPUPricing(SQLModel, table=True):
       id: str = Field(primary_key=True)
       model_name: str
       base_price: float
       current_price: float
       demand_multiplier: float
       updated_at: datetime
   ```

### 🔍 Integration Points

#### 1. Miner Registration
- When miners register, automatically create GPU entries
- Sync GPU capabilities from miner registration
- Update GPU status based on miner heartbeat

#### 2. Job Assignment
- Check GPU availability before job assignment
- Book GPU for job duration
- Release GPU on job completion or failure

#### 3. Billing Integration
- Calculate costs from booking duration
- Create orders from completed bookings
- Handle refunds for early releases

### 📝 Implementation Notes

1. **API Versioning**: Use `/v1/marketplace/gpu/` as expected by CLI
2. **Authentication**: Use existing API key system
3. **Error Handling**: Follow existing error patterns
4. **Metrics**: Add Prometheus metrics for GPU operations
5. **Testing**: Create comprehensive test suite
6. **Documentation**: Update OpenAPI specs

### 🎯 Priority Matrix

| Feature | Priority | Effort | Impact |
|---------|----------|--------|--------|
| GPU Registry | High | Medium | High |
| GPU Booking | High | High | High |
| GPU List/Details | High | Low | High |
| Reviews System | Medium | Medium | Medium |
| Order Management | Medium | High | Medium |
| Dynamic Pricing | Low | High | Low |

### 💡 Quick Win

The fastest way to make the CLI work is to:
1. Create a new router `/v1/marketplace/gpu/`
2. Implement basic endpoints that return mock data
3. Map existing marketplace offers to GPU format
4. Add simple in-memory booking tracking

This would allow the CLI to function while the full backend is developed.
