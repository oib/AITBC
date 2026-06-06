// Add this function to index.real.html to update price ticker with real data

async function updatePriceTicker() {
    try {
        // Get recent trades to calculate price statistics
        const response = await fetch(`${EXCHANGE_API_BASE}/api/trades/recent?limit=100`);
        if (!response.ok) return;
        
        const trades = await response.json();
        
        if (trades.length === 0) {
            console.log('No trades to calculate price from');
            return;
        }
        
        // Calculate 24h volume (sum of all trades in last 24h)
        const now = new Date();
        const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);
        
        const recentTrades = trades.filter(trade => 
            new Date(trade.created_at) > yesterday
        );
        
        const totalVolume = recentTrades.reduce((sum, trade) => sum + trade.amount, 0);
        const totalBTC = recentTrades.reduce((sum, trade) => sum + trade.total, 0);
        
        // Calculate current price (price of last trade)
        const currentPrice = trades[0].price;
        
        // Calculate 24h high/low
        const prices = recentTrades.map(t => t.price);
        const high24h = Math.max(...prices);
        const low24h = Math.min(...prices);
        
        // Calculate price change (compare with price 24h ago)
        const price24hAgo = trades[trades.length - 1]?.price || currentPrice;
        const priceChange = ((currentPrice - price24hAgo) / price24hAgo) * 100;
        
        // Update UI
        document.getElementById('currentPrice').textContent = `${currentPrice.toFixed(6)} BTC`;
        document.getElementById('volume24h').textContent = `${totalVolume.toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g, ",")} AITBC`;
        document.getElementById('volume24h').nextElementSibling.textContent = `≈ ${totalBTC.toFixed(5)} BTC`;
        document.getElementById('highLow').textContent = `${high24h.toFixed(6)} / ${low24h.toFixed(6)}`;
        
        // Update price change with color
        const changeElement = document.getElementById('priceChange');
        changeElement.textContent = `${priceChange >= 0 ? '+' : ''}${priceChange.toFixed(2)}%`;
        changeElement.className = `text-sm ${priceChange >= 0 ? 'text-green-600' : 'text-red-600'}`;
        
    } catch (error) {
        console.error('Failed to update price ticker:', error);
    }
}

// Call this function in the DOMContentLoaded event
// Add to existing initialization:
// updatePriceTicker();
// setInterval(updatePriceTicker, 30000); // Update every 30 seconds
