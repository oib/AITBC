-- Multi-Language Support Database Schema
-- Migration script for adding multi-language support to AITBC platform

-- 1. Translation cache table
CREATE TABLE IF NOT EXISTS translation_cache (
    id SERIAL PRIMARY KEY,
    cache_key VARCHAR(255) UNIQUE NOT NULL,
    source_text TEXT NOT NULL,
    source_language VARCHAR(10) NOT NULL,
    target_language VARCHAR(10) NOT NULL,
    translated_text TEXT NOT NULL,
    provider VARCHAR(50) NOT NULL,
    confidence FLOAT NOT NULL,
    processing_time_ms INTEGER NOT NULL,
    context TEXT,
    domain VARCHAR(50),
    access_count INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW(),
    last_accessed TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,
    
    -- Indexes for performance
    INDEX idx_cache_key (cache_key),
    INDEX idx_source_target (source_language, target_language),
    INDEX idx_provider (provider),
    INDEX idx_created_at (created_at),
    INDEX idx_expires_at (expires_at)
);

-- 2. Supported languages registry
CREATE TABLE IF NOT EXISTS supported_languages (
    id VARCHAR(10) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    native_name VARCHAR(100) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    translation_engine VARCHAR(50),
    detection_supported BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 3. Agent language preferences
ALTER TABLE agents ADD COLUMN IF NOT EXISTS preferred_language VARCHAR(10) DEFAULT 'en';
ALTER TABLE agents ADD COLUMN IF NOT EXISTS supported_languages TEXT[] DEFAULT ARRAY['en'];
ALTER TABLE agents ADD COLUMN IF NOT EXISTS auto_translate_enabled BOOLEAN DEFAULT TRUE;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS translation_quality_threshold FLOAT DEFAULT 0.7;

-- 4. Multi-language marketplace listings
CREATE TABLE IF NOT EXISTS marketplace_listings_i18n (
    id SERIAL PRIMARY KEY,
    listing_id INTEGER NOT NULL REFERENCES marketplace_listings(id) ON DELETE CASCADE,
    language VARCHAR(10) NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    keywords TEXT[],
    features TEXT[],
    requirements TEXT[],
    translated_at TIMESTAMP DEFAULT NOW(),
    translation_confidence FLOAT,
    translator_provider VARCHAR(50),
    
    -- Unique constraint per listing and language
    UNIQUE(listing_id, language),
    
    -- Indexes
    INDEX idx_listing_language (listing_id, language),
    INDEX idx_language (language),
    INDEX idx_keywords USING GIN (keywords),
    INDEX idx_translated_at (translated_at)
);

-- 5. Agent communication translations
CREATE TABLE IF NOT EXISTS agent_message_translations (
    id SERIAL PRIMARY KEY,
    message_id INTEGER NOT NULL REFERENCES agent_messages(id) ON DELETE CASCADE,
    source_language VARCHAR(10) NOT NULL,
    target_language VARCHAR(10) NOT NULL,
    original_text TEXT NOT NULL,
    translated_text TEXT NOT NULL,
    provider VARCHAR(50) NOT NULL,
    confidence FLOAT NOT NULL,
    translation_time_ms INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    
    -- Indexes
    INDEX idx_message_id (message_id),
    INDEX idx_source_target (source_language, target_language),
    INDEX idx_created_at (created_at)
);

-- 6. Translation quality logs
CREATE TABLE IF NOT EXISTS translation_quality_logs (
    id SERIAL PRIMARY KEY,
    source_text TEXT NOT NULL,
    translated_text TEXT NOT NULL,
    source_language VARCHAR(10) NOT NULL,
    target_language VARCHAR(10) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    overall_score FLOAT NOT NULL,
    bleu_score FLOAT,
    semantic_similarity FLOAT,
    length_ratio FLOAT,
    confidence_score FLOAT,
    consistency_score FLOAT,
    passed_threshold BOOLEAN NOT NULL,
    recommendations TEXT[],
    processing_time_ms INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    
    -- Indexes
    INDEX idx_provider_date (provider, created_at),
    INDEX idx_score (overall_score),
    INDEX idx_threshold (passed_threshold),
    INDEX idx_created_at (created_at)
);

-- 7. User language preferences
CREATE TABLE IF NOT EXISTS user_language_preferences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    language VARCHAR(10) NOT NULL,
    is_primary BOOLEAN DEFAULT FALSE,
    auto_translate BOOLEAN DEFAULT TRUE,
    show_original BOOLEAN DEFAULT FALSE,
    quality_threshold FLOAT DEFAULT 0.7,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Unique constraint per user and language
    UNIQUE(user_id, language),
    
    -- Indexes
    INDEX idx_user_id (user_id),
    INDEX idx_language (language),
    INDEX idx_primary (is_primary)
);

-- 8. Translation statistics
CREATE TABLE IF NOT EXISTS translation_statistics (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    source_language VARCHAR(10) NOT NULL,
    target_language VARCHAR(10) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    total_translations INTEGER DEFAULT 0,
    successful_translations INTEGER DEFAULT 0,
    failed_translations INTEGER DEFAULT 0,
    cache_hits INTEGER DEFAULT 0,
    cache_misses INTEGER DEFAULT 0,
    avg_confidence FLOAT DEFAULT 0,
    avg_processing_time_ms INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Unique constraint per date and language pair
    UNIQUE(date, source_language, target_language, provider),
    
    -- Indexes
    INDEX idx_date (date),
    INDEX idx_language_pair (source_language, target_language),
    INDEX idx_provider (provider)
);

-- 9. Content localization templates
CREATE TABLE IF NOT EXISTS localization_templates (
    id SERIAL PRIMARY KEY,
    template_key VARCHAR(255) NOT NULL,
    language VARCHAR(10) NOT NULL,
    content TEXT NOT NULL,
    variables TEXT[],
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Unique constraint per template key and language
    UNIQUE(template_key, language),
    
    -- Indexes
    INDEX idx_template_key (template_key),
    INDEX idx_language (language)
);

-- 10. Translation API usage logs
CREATE TABLE IF NOT EXISTS translation_api_logs (
    id SERIAL PRIMARY KEY,
    endpoint VARCHAR(255) NOT NULL,
    method VARCHAR(10) NOT NULL,
    source_language VARCHAR(10),
    target_language VARCHAR(10),
    text_length INTEGER,
    processing_time_ms INTEGER NOT NULL,
    status_code INTEGER NOT NULL,
    error_message TEXT,
    user_id INTEGER REFERENCES users(id),
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    
    -- Indexes
    INDEX idx_endpoint (endpoint),
    INDEX idx_created_at (created_at),
    INDEX idx_status_code (status_code),
    INDEX idx_user_id (user_id)
);

-- Insert supported languages
INSERT INTO supported_languages (id, name, native_name, is_active, translation_engine, detection_supported) VALUES
('en', 'English', 'English', TRUE, 'openai', TRUE),
('zh', 'Chinese', '中文', TRUE, 'openai', TRUE),
('zh-cn', 'Chinese (Simplified)', '简体中文', TRUE, 'openai', TRUE),
('zh-tw', 'Chinese (Traditional)', '繁體中文', TRUE, 'openai', TRUE),
('es', 'Spanish', 'Español', TRUE, 'openai', TRUE),
('fr', 'French', 'Français', TRUE, 'deepl', TRUE),
('de', 'German', 'Deutsch', TRUE, 'deepl', TRUE),
('ja', 'Japanese', '日本語', TRUE, 'openai', TRUE),
('ko', 'Korean', '한국어', TRUE, 'openai', TRUE),
('ru', 'Russian', 'Русский', TRUE, 'openai', TRUE),
('ar', 'Arabic', 'العربية', TRUE, 'openai', TRUE),
('hi', 'Hindi', 'हिन्दी', TRUE, 'openai', TRUE),
('pt', 'Portuguese', 'Português', TRUE, 'openai', TRUE),
('it', 'Italian', 'Italiano', TRUE, 'deepl', TRUE),
('nl', 'Dutch', 'Nederlands', TRUE, 'google', TRUE),
('sv', 'Swedish', 'Svenska', TRUE, 'google', TRUE),
('da', 'Danish', 'Dansk', TRUE, 'google', TRUE),
('no', 'Norwegian', 'Norsk', TRUE, 'google', TRUE),
('fi', 'Finnish', 'Suomi', TRUE, 'google', TRUE),
('pl', 'Polish', 'Polski', TRUE, 'google', TRUE),
('tr', 'Turkish', 'Türkçe', TRUE, 'google', TRUE),
('th', 'Thai', 'ไทย', TRUE, 'openai', TRUE),
('vi', 'Vietnamese', 'Tiếng Việt', TRUE, 'openai', TRUE),
('id', 'Indonesian', 'Bahasa Indonesia', TRUE, 'google', TRUE),
('ms', 'Malay', 'Bahasa Melayu', TRUE, 'google', TRUE),
('tl', 'Filipino', 'Filipino', TRUE, 'google', TRUE),
('sw', 'Swahili', 'Kiswahili', TRUE, 'google', TRUE),
('zu', 'Zulu', 'IsiZulu', TRUE, 'google', TRUE),
('xh', 'Xhosa', 'isiXhosa', TRUE, 'google', TRUE),
('af', 'Afrikaans', 'Afrikaans', TRUE, 'google', TRUE),
('is', 'Icelandic', 'Íslenska', TRUE, 'google', TRUE),
('mt', 'Maltese', 'Malti', TRUE, 'google', TRUE),
('cy', 'Welsh', 'Cymraeg', TRUE, 'google', TRUE),
('ga', 'Irish', 'Gaeilge', TRUE, 'google', TRUE),
('gd', 'Scottish Gaelic', 'Gàidhlig', TRUE, 'google', TRUE),
('eu', 'Basque', 'Euskara', TRUE, 'google', TRUE),
('ca', 'Catalan', 'Català', TRUE, 'google', TRUE),
('gl', 'Galician', 'Galego', TRUE, 'google', TRUE),
('ast', 'Asturian', 'Asturianu', TRUE, 'google', TRUE),
('lb', 'Luxembourgish', 'Lëtzebuergesch', TRUE, 'google', TRUE),
('rm', 'Romansh', 'Rumantsch', TRUE, 'google', TRUE),
('fur', 'Friulian', 'Furlan', TRUE, 'google', TRUE),
('lld', 'Ladin', 'Ladin', TRUE, 'google', TRUE),
('lij', 'Ligurian', 'Ligure', TRUE, 'google', TRUE),
('lmo', 'Lombard', 'Lombard', TRUE, 'google', TRUE),
('vec', 'Venetian', 'Vèneto', TRUE, 'google', TRUE),
('scn', 'Sicilian', 'Sicilianu', TRUE, 'google', TRUE),
('ro', 'Romanian', 'Română', TRUE, 'google', TRUE),
('mo', 'Moldovan', 'Moldovenească', TRUE, 'google', TRUE),
('hr', 'Croatian', 'Hrvatski', TRUE, 'google', TRUE),
('sr', 'Serbian', 'Српски', TRUE, 'google', TRUE),
('sl', 'Slovenian', 'Slovenščina', TRUE, 'google', TRUE),
('sk', 'Slovak', 'Slovenčina', TRUE, 'google', TRUE),
('cs', 'Czech', 'Čeština', TRUE, 'google', TRUE),
('bg', 'Bulgarian', 'Български', TRUE, 'google', TRUE),
('mk', 'Macedonian', 'Македонски', TRUE, 'google', TRUE),
('sq', 'Albanian', 'Shqip', TRUE, 'google', TRUE),
('hy', 'Armenian', 'Հայերեն', TRUE, 'google', TRUE),
('ka', 'Georgian', 'ქართული', TRUE, 'google', TRUE),
('he', 'Hebrew', 'עברית', TRUE, 'openai', TRUE),
('yi', 'Yiddish', 'ייִדיש', TRUE, 'google', TRUE),
('fa', 'Persian', 'فارسی', TRUE, 'openai', TRUE),
('ps', 'Pashto', 'پښتو', TRUE, 'google', TRUE),
('ur', 'Urdu', 'اردو', TRUE, 'openai', TRUE),
('bn', 'Bengali', 'বাংলা', TRUE, 'openai', TRUE),
('as', 'Assamese', 'অসমীয়া', TRUE, 'google', TRUE),
('or', 'Odia', 'ଓଡ଼ିଆ', TRUE, 'google', TRUE),
('pa', 'Punjabi', 'ਪੰਜਾਬੀ', TRUE, 'google', TRUE),
('gu', 'Gujarati', 'ગુજરાતી', TRUE, 'google', TRUE),
('mr', 'Marathi', 'मराठी', TRUE, 'google', TRUE),
('ne', 'Nepali', 'नेपाली', TRUE, 'google', TRUE),
('si', 'Sinhala', 'සිංහල', TRUE, 'google', TRUE),
('ta', 'Tamil', 'தமிழ்', TRUE, 'openai', TRUE),
('te', 'Telugu', 'తెలుగు', TRUE, 'google', TRUE),
('ml', 'Malayalam', 'മലയാളം', TRUE, 'google', TRUE),
('kn', 'Kannada', 'ಕನ್ನಡ', TRUE, 'google', TRUE),
('my', 'Myanmar', 'မြန်မာ', TRUE, 'google', TRUE),
('km', 'Khmer', 'ខ្មែរ', TRUE, 'google', TRUE),
('lo', 'Lao', 'ລາວ', TRUE, 'google', TRUE)
ON CONFLICT (id) DO NOTHING;

-- Insert common localization templates
INSERT INTO localization_templates (template_key, language, content, variables) VALUES
('welcome_message', 'en', 'Welcome to AITBC!', []),
('welcome_message', 'zh', '欢迎使用AITBC！', []),
('welcome_message', 'es', '¡Bienvenido a AITBC!', []),
('welcome_message', 'fr', 'Bienvenue sur AITBC!', []),
('welcome_message', 'de', 'Willkommen bei AITBC!', []),
('welcome_message', 'ja', 'AITBCへようこそ！', []),
('welcome_message', 'ko', 'AITBC에 오신 것을 환영합니다!', []),
('welcome_message', 'ru', 'Добро пожаловать в AITBC!', []),
('welcome_message', 'ar', 'مرحبا بك في AITBC!', []),
('welcome_message', 'hi', 'AITBC में आपका स्वागत है!', []),

('marketplace_title', 'en', 'AI Power Marketplace', []),
('marketplace_title', 'zh', 'AI算力市场', []),
('marketplace_title', 'es', 'Mercado de Poder de IA', []),
('marketplace_title', 'fr', 'Marché de la Puissance IA', []),
('marketplace_title', 'de', 'KI-Leistungsmarktplatz', []),
('marketplace_title', 'ja', 'AIパワーマーケット', []),
('marketplace_title', 'ko', 'AI 파워 마켓플레이스', []),
('marketplace_title', 'ru', 'Рынок мощностей ИИ', []),
('marketplace_title', 'ar', 'سوق قوة الذكاء الاصطناعي', []),
('marketplace_title', 'hi', 'AI पावर मार्केटप्लेस', []),

('agent_status_online', 'en', 'Agent is online and ready', []),
('agent_status_online', 'zh', '智能体在线并准备就绪', []),
('agent_status_online', 'es', 'El agente está en línea y listo', []),
('agent_status_online', 'fr', ''L'agent est en ligne et prêt', []),
('agent_status_online', 'de', 'Agent ist online und bereit', []),
('agent_status_online', 'ja', 'エージェントがオンラインで準備完了', []),
('agent_status_online', 'ko', '에이전트가 온라인 상태이며 준비됨', []),
('agent_status_online', 'ru', 'Агент в сети и готов', []),
('agent_status_online', 'ar', 'العميل متصل وجاهز', []),
('agent_status_online', 'hi', 'एजेंट ऑनलाइन और तैयार है', []),

('transaction_success', 'en', 'Transaction completed successfully', []),
('transaction_success', 'zh', '交易成功完成', []),
('transaction_success', 'es', 'Transacción completada exitosamente', []),
('transaction_success', 'fr', 'Transaction terminée avec succès', []),
('transaction_success', 'de', 'Transaktion erfolgreich abgeschlossen', []),
('transaction_success', 'ja', '取引が正常に完了しました', []),
('transaction_success', 'ko', '거래가 성공적으로 완료되었습니다', []),
('transaction_success', 'ru', 'Транзакция успешно завершена', []),
('transaction_success', 'ar', 'تمت المعاملة بنجاح', []),
('transaction_success', 'hi', 'लेन-देन सफलतापूर्वक पूर्ण हुई', [])
ON CONFLICT (template_key, language) DO NOTHING;

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_translation_cache_expires ON translation_cache(expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_agent_messages_created_at ON agent_messages(created_at);
CREATE INDEX IF NOT EXISTS idx_marketplace_listings_created_at ON marketplace_listings(created_at);

-- Create function to update translation statistics
CREATE OR REPLACE FUNCTION update_translation_stats()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO translation_statistics (
        date, source_language, target_language, provider,
        total_translations, successful_translations, failed_translations,
        avg_confidence, avg_processing_time_ms
    ) VALUES (
        CURRENT_DATE, 
        COALESCE(NEW.source_language, 'unknown'),
        COALESCE(NEW.target_language, 'unknown'),
        COALESCE(NEW.provider, 'unknown'),
        1, 1, 0,
        COALESCE(NEW.confidence, 0),
        COALESCE(NEW.processing_time_ms, 0)
    )
    ON CONFLICT (date, source_language, target_language, provider)
    DO UPDATE SET
        total_translations = translation_statistics.total_translations + 1,
        successful_translations = translation_statistics.successful_translations + 1,
        avg_confidence = (translation_statistics.avg_confidence * translation_statistics.successful_translations + COALESCE(NEW.confidence, 0)) / (translation_statistics.successful_translations + 1),
        avg_processing_time_ms = (translation_statistics.avg_processing_time_ms * translation_statistics.successful_translations + COALESCE(NEW.processing_time_ms, 0)) / (translation_statistics.successful_translations + 1),
        updated_at = NOW();
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for automatic statistics updates
DROP TRIGGER IF EXISTS trigger_update_translation_stats ON translation_cache;
CREATE TRIGGER trigger_update_translation_stats
    AFTER INSERT ON translation_cache
    FOR EACH ROW
    EXECUTE FUNCTION update_translation_stats();

-- Create function to clean up expired cache entries
CREATE OR REPLACE FUNCTION cleanup_expired_cache()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM translation_cache 
    WHERE expires_at IS NOT NULL AND expires_at < NOW();
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Create view for translation analytics
CREATE OR REPLACE VIEW translation_analytics AS
SELECT 
    DATE(created_at) as date,
    source_language,
    target_language,
    provider,
    COUNT(*) as total_translations,
    AVG(confidence) as avg_confidence,
    AVG(processing_time_ms) as avg_processing_time_ms,
    COUNT(CASE WHEN confidence > 0.8 THEN 1 END) as high_confidence_count,
    COUNT(CASE WHEN confidence < 0.5 THEN 1 END) as low_confidence_count
FROM translation_cache
GROUP BY DATE(created_at), source_language, target_language, provider
ORDER BY date DESC;

-- Create view for cache performance metrics
CREATE OR REPLACE VIEW cache_performance_metrics AS
SELECT 
    (SELECT COUNT(*) FROM translation_cache) as total_entries,
    (SELECT COUNT(*) FROM translation_cache WHERE created_at > NOW() - INTERVAL '24 hours') as entries_last_24h,
    (SELECT AVG(access_count) FROM translation_cache) as avg_access_count,
    (SELECT COUNT(*) FROM translation_cache WHERE access_count > 10) as popular_entries,
    (SELECT COUNT(*) FROM translation_cache WHERE expires_at < NOW()) as expired_entries,
    (SELECT AVG(confidence) FROM translation_cache) as avg_confidence,
    (SELECT AVG(processing_time_ms) FROM translation_cache) as avg_processing_time;

-- Grant permissions (adjust as needed for your setup)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO aitbc_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO aitbc_app;

-- Add comments for documentation
COMMENT ON TABLE translation_cache IS 'Cache for translation results to improve performance';
COMMENT ON TABLE supported_languages IS 'Registry of supported languages for translation and detection';
COMMENT ON TABLE marketplace_listings_i18n IS 'Multi-language versions of marketplace listings';
COMMENT ON TABLE agent_message_translations IS 'Translations of agent communications';
COMMENT ON TABLE translation_quality_logs IS 'Quality assessment logs for translations';
COMMENT ON TABLE user_language_preferences IS 'User language preferences and settings';
COMMENT ON TABLE translation_statistics IS 'Daily translation usage statistics';
COMMENT ON TABLE localization_templates IS 'Template strings for UI localization';
COMMENT ON TABLE translation_api_logs IS 'API usage logs for monitoring and analytics';

-- Create partition for large tables (optional for high-volume deployments)
-- This would be implemented based on actual usage patterns
-- CREATE TABLE translation_cache_y2024m01 PARTITION OF translation_cache
-- FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
