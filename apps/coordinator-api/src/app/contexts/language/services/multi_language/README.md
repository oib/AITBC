# Multi-Language API Service

## Overview

The Multi-Language API service provides comprehensive translation, language detection, and localization capabilities for the AITBC platform. This service enables global agent interactions and marketplace listings with support for 50+ languages.

## Features

### Core Capabilities
- **Multi-Provider Translation**: OpenAI GPT-4, Google Translate, DeepL, and local models
- **Intelligent Fallback**: Automatic provider switching based on language pair and quality
- **Language Detection**: Ensemble detection using langdetect, Polyglot, and FastText
- **Quality Assurance**: BLEU scores, semantic similarity, and consistency checks
- **Redis Caching**: High-performance caching with intelligent eviction
- **Real-time Translation**: WebSocket support for live conversations

### Integration Points
- **Agent Communication**: Automatic message translation between agents
- **Marketplace Localization**: Multi-language listings and search
- **User Preferences**: Per-user language settings and auto-translation
- **Cultural Intelligence**: Regional communication style adaptation

## Architecture

### Service Components

```
multi_language/
├── __init__.py                 # Service initialization and dependency injection
├── translation_engine.py      # Core translation orchestration
├── language_detector.py       # Multi-method language detection
├── translation_cache.py       # Redis-based caching layer
├── quality_assurance.py       # Translation quality assessment
├── agent_communication.py     # Enhanced agent messaging
├── marketplace_localization.py # Marketplace content localization
├── api_endpoints.py          # REST API endpoints
├── config.py                 # Configuration management
├── database_schema.sql        # Database migrations
├── test_multi_language.py    # Comprehensive test suite
└── requirements.txt          # Dependencies
```

### Data Flow

1. **Translation Request** → Language Detection → Provider Selection → Translation → Quality Check → Cache
2. **Agent Message** → Language Detection → Auto-Translation (if needed) → Delivery
3. **Marketplace Listing** → Batch Translation → Quality Assessment → Search Indexing

## API Endpoints

### Translation
- `POST /api/v1/multi-language/translate` - Single text translation
- `POST /api/v1/multi-language/translate/batch` - Batch translation
- `GET /api/v1/multi-language/languages` - Supported languages

### Language Detection
- `POST /api/v1/multi-language/detect-language` - Detect text language
- `POST /api/v1/multi-language/detect-language/batch` - Batch detection

### Cache Management
- `GET /api/v1/multi-language/cache/stats` - Cache statistics
- `POST /api/v1/multi-language/cache/clear` - Clear cache entries
- `POST /api/v1/multi-language/cache/optimize` - Optimize cache

### Health & Monitoring
- `GET /api/v1/multi-language/health` - Service health check
- `GET /api/v1/multi-language/cache/top-translations` - Popular translations

## Configuration

### Environment Variables

```bash
# Translation Providers
OPENAI_API_KEY=your_openai_api_key
GOOGLE_TRANSLATE_API_KEY=your_google_api_key
DEEPL_API_KEY=your_deepl_api_key

# Cache Configuration
REDIS_URL=redis://localhost:6379
REDIS_PASSWORD=your_redis_password
REDIS_DB=0

# Database
DATABASE_URL=postgresql://user:pass@localhost/aitbc

# FastText Model
FASTTEXT_MODEL_PATH=models/lid.176.bin

# Service Settings
ENVIRONMENT=development
LOG_LEVEL=INFO
PORT=8000
```

### Configuration Structure

```python
{
    "translation": {
        "providers": {
            "openai": {"api_key": "...", "model": "gpt-4"},
            "google": {"api_key": "..."},
            "deepl": {"api_key": "..."}
        },
        "fallback_strategy": {
            "primary": "openai",
            "secondary": "google",
            "tertiary": "deepl"
        }
    },
    "cache": {
        "redis": {"url": "redis://localhost:6379"},
        "default_ttl": 86400,
        "max_cache_size": 100000
    },
    "quality": {
        "thresholds": {
            "overall": 0.7,
            "bleu": 0.3,
            "semantic_similarity": 0.6
        }
    }
}
```

## Database Schema

### Core Tables
- `translation_cache` - Cached translation results
- `supported_languages` - Language registry
- `agent_message_translations` - Agent communication translations
- `marketplace_listings_i18n` - Multi-language marketplace listings
- `translation_quality_logs` - Quality assessment logs
- `translation_statistics` - Usage analytics

### Key Relationships
- Agents → Language Preferences
- Listings → Localized Content
- Messages → Translations
- Users → Language Settings

## Performance Metrics

### Target Performance
- **Single Translation**: <200ms
- **Batch Translation (100 items)**: <2s
- **Language Detection**: <50ms
- **Cache Hit Ratio**: >85%
- **API Response Time**: <100ms

### Scaling Considerations
- **Horizontal Scaling**: Multiple service instances behind load balancer
- **Cache Sharding**: Redis cluster for high-volume caching
- **Provider Rate Limiting**: Intelligent request distribution
- **Database Partitioning**: Time-based partitioning for logs

## Quality Assurance

### Translation Quality Metrics
- **BLEU Score**: Reference-based quality assessment
- **Semantic Similarity**: NLP-based meaning preservation
- **Length Ratio**: Appropriate length preservation
- **Consistency**: Internal translation consistency
- **Confidence Scoring**: Provider confidence aggregation

### Quality Thresholds
- **Minimum Confidence**: 0.6 for cache eligibility
- **Quality Threshold**: 0.7 for user-facing translations
- **Auto-Retry**: Below 0.4 confidence triggers retry

## Security & Privacy

### Data Protection
- **Encryption**: All API communications encrypted
- **Data Retention**: Minimal cache retention policies
- **Privacy Options**: On-premise models for sensitive data
- **Compliance**: GDPR and regional privacy law compliance

### Access Control
- **API Authentication**: JWT-based authentication
- **Rate Limiting**: Tiered rate limiting by user type
- **Audit Logging**: Complete translation audit trail
- **Role-Based Access**: Different access levels for different user types

## Monitoring & Observability

### Metrics Collection
- **Translation Volume**: Requests per language pair
- **Provider Performance**: Response times and error rates
- **Cache Performance**: Hit ratios and eviction rates
- **Quality Metrics**: Average quality scores by provider

### Health Checks
- **Service Health**: Provider availability checks
- **Cache Health**: Redis connectivity and performance
- **Database Health**: Connection pool and query performance
- **Quality Health**: Quality assessment system status

### Alerting
- **Error Rate**: >5% error rate triggers alerts
- **Response Time**: P95 >1s triggers alerts
- **Cache Performance**: Hit ratio <70% triggers alerts
- **Quality Score**: Average quality <60% triggers alerts

## Deployment

### Service Dependencies
- **Redis**: For translation caching
- **PostgreSQL**: For persistent storage and analytics
- **External APIs**: OpenAI, Google Translate, DeepL
- **NLP Models**: spaCy models for quality assessment

### Deployment Steps
1. Install dependencies: `pip install -r requirements.txt`
2. Configure environment variables
3. Run database migrations: `psql -f database_schema.sql`
4. Download NLP models: `python -m spacy download en_core_web_sm`
5. Start service: `uvicorn main:app --host 0.0.0.0 --port 8000`

### Docker-Free Deployment
```bash
# Systemd service configuration
sudo cp multi-language.service /etc/systemd/system/
sudo systemctl enable multi-language
sudo systemctl start multi-language
```

## Testing

### Test Coverage
- **Unit Tests**: Individual component testing
- **Integration Tests**: Service interaction testing
- **Performance Tests**: Load and stress testing
- **Quality Tests**: Translation quality validation

### Running Tests
```bash
# Run all tests
pytest test_multi_language.py -v

# Run specific test categories
pytest test_multi_language.py::TestTranslationEngine -v
pytest test_multi_language.py::TestIntegration -v

# Run with coverage
pytest test_multi_language.py --cov=. --cov-report=html
```

## Usage Examples

### Basic Translation
```python
from app.services.multi_language import initialize_multi_language_service

# Initialize service
service = await initialize_multi_language_service()

# Translate text
result = await service.translation_engine.translate(
    TranslationRequest(
        text="Hello world",
        source_language="en",
        target_language="es"
    )
)

print(result.translated_text)  # "Hola mundo"
```

### Agent Communication
```python
# Register agent language profile
profile = AgentLanguageProfile(
    agent_id="agent1",
    preferred_language="es",
    supported_languages=["es", "en"],
    auto_translate_enabled=True
)

await agent_comm.register_agent_language_profile(profile)

# Send message (auto-translated)
message = AgentMessage(
    id="msg1",
    sender_id="agent2",
    receiver_id="agent1",
    message_type=MessageType.AGENT_TO_AGENT,
    content="Hello from agent2"
)

translated_message = await agent_comm.send_message(message)
print(translated_message.translated_content)  # "Hola del agente2"
```

### Marketplace Localization
```python
# Create localized listing
listing = {
    "id": "service1",
    "type": "service",
    "title": "AI Translation Service",
    "description": "High-quality translation service",
    "keywords": ["translation", "AI"]
}

localized = await marketplace_loc.create_localized_listing(listing, ["es", "fr"])

# Search in specific language
results = await marketplace_loc.search_localized_listings(
    "traducción", "es"
)
```

## Troubleshooting

### Common Issues
1. **API Key Errors**: Verify environment variables are set correctly
2. **Cache Connection Issues**: Check Redis connectivity and configuration
3. **Model Loading Errors**: Ensure NLP models are downloaded
4. **Performance Issues**: Monitor cache hit ratio and provider response times

### Debug Mode
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
export DEBUG=true

# Run with detailed logging
uvicorn main:app --log-level debug
```

## Future Enhancements

### Short-term (3 months)
- **Voice Translation**: Real-time audio translation
- **Document Translation**: Bulk document processing
- **Custom Models**: Domain-specific translation models
- **Enhanced Quality**: Advanced quality assessment metrics

### Long-term (6+ months)
- **Neural Machine Translation**: Custom NMT model training
- **Cross-Modal Translation**: Image/video description translation
- **Agent Language Learning**: Adaptive language learning
- **Blockchain Integration**: Decentralized translation verification

## Support & Maintenance

### Regular Maintenance
- **Cache Optimization**: Weekly cache cleanup and optimization
- **Model Updates**: Monthly NLP model updates
- **Performance Monitoring**: Continuous performance monitoring
- **Quality Audits**: Regular translation quality audits

### Support Channels
- **Documentation**: Comprehensive API documentation
- **Monitoring**: Real-time service monitoring dashboard
- **Alerts**: Automated alerting for critical issues
- **Logs**: Structured logging for debugging

This Multi-Language API service provides a robust, scalable foundation for global AI agent interactions and marketplace localization within the AITBC ecosystem.
