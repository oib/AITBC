# AITBC Blockchain Explorer - Enhanced Version

## Overview

The enhanced AITBC Blockchain Explorer provides comprehensive blockchain exploration capabilities with advanced search, analytics, and export features that match the power of CLI tools while providing an intuitive web interface.

## 🚀 New Features

### 🔍 Advanced Search
- **Multi-criteria filtering**: Search by address, amount range, transaction type, and time range
- **Complex queries**: Combine multiple filters for precise results
- **Search history**: Save and reuse common searches
- **Real-time results**: Instant search with pagination

### 📊 Analytics Dashboard
- **Transaction volume analytics**: Visualize transaction patterns over time
- **Network activity monitoring**: Track blockchain health and performance
- **Validator performance**: Monitor validator statistics and rewards
- **Time period analysis**: 1h, 24h, 7d, 30d views with interactive charts

### 📤 Data Export
- **Multiple formats**: Export to CSV, JSON for analysis
- **Custom date ranges**: Export specific time periods
- **Bulk operations**: Export large datasets efficiently
- **Search result exports**: Export filtered search results

### ⚡ Real-time Updates
- **Live transaction feed**: Monitor transactions as they happen
- **Real-time block updates**: See new blocks immediately
- **Network status monitoring**: Track blockchain health
- **Alert system**: Get notified about important events

## 🛠️ Installation

### Prerequisites
- Python 3.13+
- Node.js (for frontend development)
- Access to AITBC blockchain node

### Setup
```bash
# Clone the repository
git clone https://github.com/aitbc/blockchain-explorer.git
cd blockchain-explorer

# Install dependencies
pip install -r requirements.txt

# Run the explorer
python main.py
```

The explorer will be available at `http://localhost:3001`

## 🔧 Configuration

### Environment Variables
```bash
# Blockchain node URL
export BLOCKCHAIN_RPC_URL="http://localhost:8082"

# External node URL (for backup)
export EXTERNAL_RPC_URL="http://aitbc.keisanki.net:8082"

# Explorer settings
export EXPLORER_HOST="0.0.0.0"
export EXPLORER_PORT="3001"
```

### Configuration File
Create `.env` file:
```env
BLOCKCHAIN_RPC_URL=http://localhost:8082
EXTERNAL_RPC_URL=http://aitbc.keisanki.net:8082
EXPLORER_HOST=0.0.0.0
EXPLORER_PORT=3001
```

## 📚 API Documentation

### Search Endpoints

#### Advanced Transaction Search
```http
GET /api/search/transactions
```

Query Parameters:
- `address` (string): Filter by address
- `amount_min` (float): Minimum amount
- `amount_max` (float): Maximum amount
- `tx_type` (string): Transaction type (transfer, stake, smart_contract)
- `since` (datetime): Start date
- `until` (datetime): End date
- `limit` (int): Results per page (max 1000)
- `offset` (int): Pagination offset

Example:
```bash
curl "http://localhost:3001/api/search/transactions?address=0x123...&amount_min=1.0&limit=50"
```

#### Advanced Block Search
```http
GET /api/search/blocks
```

Query Parameters:
- `validator` (string): Filter by validator address
- `since` (datetime): Start date
- `until` (datetime): End date
- `min_tx` (int): Minimum transaction count
- `limit` (int): Results per page (max 1000)
- `offset` (int): Pagination offset

### Analytics Endpoints

#### Analytics Overview
```http
GET /api/analytics/overview
```

Query Parameters:
- `period` (string): Time period (1h, 24h, 7d, 30d)

Response:
```json
{
  "total_transactions": "1,234",
  "transaction_volume": "5,678.90 AITBC",
  "active_addresses": "89",
  "avg_block_time": "2.1s",
  "volume_data": {
    "labels": ["00:00", "02:00", "04:00"],
    "values": [100, 120, 110]
  },
  "activity_data": {
    "labels": ["00:00", "02:00", "04:00"],
    "values": [50, 60, 55]
  }
}
```

### Export Endpoints

#### Export Search Results
```http
GET /api/export/search
```

Query Parameters:
- `format` (string): Export format (csv, json)
- `type` (string): Data type (transactions, blocks)
- `data` (string): JSON-encoded search results

#### Export Latest Blocks
```http
GET /api/export/blocks
```

Query Parameters:
- `format` (string): Export format (csv, json)

## 🎯 Usage Examples

### Advanced Search
1. **Search by address and amount range**:
   - Enter address in search field
   - Click "Advanced" to expand options
   - Set amount range (min: 1.0, max: 100.0)
   - Click "Search Transactions"

2. **Search blocks by validator**:
   - Expand advanced search
   - Enter validator address
   - Set time range if needed
   - Click "Search Blocks"

### Analytics
1. **View 24-hour analytics**:
   - Select "Last 24 Hours" from dropdown
   - View transaction volume chart
   - Check network activity metrics

2. **Compare time periods**:
   - Switch between 1h, 24h, 7d, 30d views
   - Observe trends and patterns

### Export Data
1. **Export search results**:
   - Perform search
   - Click "Export CSV" or "Export JSON"
   - Download file automatically

2. **Export latest blocks**:
   - Go to latest blocks section
   - Click "Export" button
   - Choose format

## 🔍 CLI vs Web Explorer Feature Comparison

| Feature | CLI | Web Explorer |
|---------|-----|--------------|
| **Basic Search** | ✅ `aitbc blockchain transaction` | ✅ Simple search |
| **Advanced Search** | ✅ `aitbc blockchain search` | ✅ Advanced search form |
| **Address Analytics** | ✅ `aitbc blockchain address` | ✅ Address details |
| **Transaction Volume** | ✅ `aitbc blockchain analytics` | ✅ Volume charts |
| **Data Export** | ✅ `--output csv/json` | ✅ Export buttons |
| **Real-time Monitoring** | ✅ `aitbc blockchain monitor` | ✅ Live updates |
| **Visual Analytics** | ❌ Text only | ✅ Interactive charts |
| **User Interface** | ❌ Command line | ✅ Web interface |
| **Mobile Access** | ❌ Limited | ✅ Responsive |

## 🚀 Performance

### Optimization Features
- **Caching**: Frequently accessed data cached for performance
- **Pagination**: Large result sets paginated to prevent memory issues
- **Async operations**: Non-blocking API calls for better responsiveness
- **Compression**: Gzip compression for API responses

### Performance Metrics
- **Page load time**: < 2 seconds for analytics dashboard
- **Search response**: < 500ms for filtered searches
- **Export generation**: < 30 seconds for 1000+ records
- **Real-time updates**: < 5 second latency

## 🔒 Security

### Security Features
- **Input validation**: All user inputs validated and sanitized
- **Rate limiting**: API endpoints protected from abuse
- **CORS protection**: Cross-origin requests controlled
- **HTTPS support**: SSL/TLS encryption for production

### Security Best Practices
- **No sensitive data exposure**: Private keys never displayed
- **Secure headers**: Security headers implemented
- **Input sanitization**: XSS protection enabled
- **Error handling**: No sensitive information in error messages

## 🐛 Troubleshooting

### Common Issues

#### Explorer not loading
```bash
# Check if port is available
netstat -tulpn | grep 3001

# Check logs
python main.py --log-level debug
```

#### Search not working
```bash
# Test blockchain node connectivity
curl http://localhost:8082/rpc/head

# Check API endpoints
curl http://localhost:3001/health
```

#### Analytics not displaying
```bash
# Check browser console for JavaScript errors
# Verify Chart.js library is loaded
# Test API endpoint:
curl http://localhost:3001/api/analytics/overview
```

### Debug Mode
```bash
# Run with debug logging
python main.py --log-level debug

# Check API responses
curl -v http://localhost:3001/api/search/transactions
```

## 📱 Mobile Support

The enhanced explorer is fully responsive and works on:
- **Desktop browsers**: Chrome, Firefox, Safari, Edge
- **Tablet devices**: iPad, Android tablets
- **Mobile phones**: iOS Safari, Chrome Mobile

Mobile-specific features:
- **Touch-friendly interface**: Optimized for touch interactions
- **Responsive charts**: Charts adapt to screen size
- **Simplified navigation**: Mobile-optimized menu
- **Quick actions**: One-tap export and search

## 🔗 Integration

### API Integration
The explorer provides RESTful APIs for integration with:
- **Custom dashboards**: Build custom analytics dashboards
- **Mobile apps**: Integrate blockchain data into mobile applications
- **Trading bots**: Provide blockchain data for automated trading
- **Research tools**: Power blockchain research platforms

### Webhook Support
Configure webhooks for:
- **New block notifications**: Get notified when new blocks are mined
- **Transaction alerts**: Receive alerts for specific transactions
- **Network events**: Monitor network health and performance

## 🚀 Deployment

### Docker Deployment
```bash
# Build Docker image
docker build -t aitbc-explorer .

# Run container
docker run -p 3001:3001 aitbc-explorer
```

### Production Deployment
```bash
# Install with systemd
sudo cp aitbc-explorer.service /etc/systemd/system/
sudo systemctl enable aitbc-explorer
sudo systemctl start aitbc-explorer

# Configure nginx reverse proxy
sudo cp nginx.conf /etc/nginx/sites-available/aitbc-explorer
sudo ln -s /etc/nginx/sites-available/aitbc-explorer /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### Environment Configuration
```bash
# Production environment
export NODE_ENV=production
export BLOCKCHAIN_RPC_URL=https://mainnet.aitbc.dev
export EXPLORER_PORT=3001
export LOG_LEVEL=info
```

## 📈 Roadmap

### Upcoming Features
- **WebSocket real-time updates**: Live blockchain monitoring
- **Advanced charting**: More sophisticated analytics visualizations
- **Custom dashboards**: User-configurable dashboard layouts
- **Alert system**: Email and webhook notifications
- **Multi-language support**: Internationalization
- **Dark mode**: Dark theme support

### Future Enhancements
- **Mobile app**: Native mobile applications
- **API authentication**: Secure API access with API keys
- **Advanced filtering**: More sophisticated search options
- **Performance analytics**: Detailed performance metrics
- **Social features**: Share and discuss blockchain data

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup
```bash
# Clone repository
git clone https://github.com/aitbc/blockchain-explorer.git
cd blockchain-explorer

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install development dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Start development server
python main.py --reload
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📞 Support

- **Documentation**: [Full documentation](https://docs.aitbc.dev/explorer)
- **Issues**: [GitHub Issues](https://github.com/aitbc/blockchain-explorer/issues)
- **Discord**: [AITBC Discord](https://discord.gg/aitbc)
- **Email**: support@aitbc.dev

---

*Enhanced AITBC Blockchain Explorer - Bringing CLI power to the web interface*
