import { createApp } from 'https://unpkg.com/vue@3/dist/vue.esm-browser.js'

const API_BASE = '/api/v1'

const app = createApp({
  data() {
    return {
      loading: true,
      chainInfo: {
        height: 0,
        hash: '',
        timestamp: null,
        tx_count: 0
      },
      latestBlocks: [],
      stats: {
        totalBlocks: 0,
        totalTransactions: 0,
        avgBlockTime: 2.0,
        hashRate: '0 H/s'
      },
      error: null
    }
  },
  
  async mounted() {
    await this.loadChainData()
    setInterval(this.loadChainData, 5000)
  },
  
  methods: {
    async loadChainData() {
      try {
        this.error = null
        
        // Load chain head
        const headResponse = await fetch(`${API_BASE}/chain/head`)
        if (headResponse.ok) {
          this.chainInfo = await headResponse.json()
        }
        
        // Load latest blocks
        const blocksResponse = await fetch(`${API_BASE}/chain/blocks?limit=10`)
        if (blocksResponse.ok) {
          this.latestBlocks = await blocksResponse.json()
        }
        
        // Calculate stats
        this.stats.totalBlocks = this.chainInfo.height || 0
        this.stats.totalTransactions = this.latestBlocks.reduce((sum, block) => sum + (block.tx_count || 0), 0)
        
        this.loading = false
      } catch (error) {
        console.error('Failed to load chain data:', error)
        this.error = 'Failed to connect to blockchain node'
        this.loading = false
      }
    },
    
    formatHash(hash) {
      if (!hash) return '-'
      return hash.substring(0, 10) + '...' + hash.substring(hash.length - 8)
    },
    
    formatTime(timestamp) {
      if (!timestamp) return '-'
      return new Date(timestamp * 1000).toLocaleString()
    },
    
    formatNumber(num) {
      if (!num) return '0'
      return num.toLocaleString()
    },
    
    getBlockType(block) {
      if (!block) return 'unknown'
      return block.tx_count > 0 ? 'with-tx' : 'empty'
    }
  },
  
  template: `
    <div class="app">
      <!-- Header -->
      <header class="header">
        <div class="container">
          <div class="header-content">
            <div class="logo">
              <svg class="logo-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M12 2L2 7L12 12L22 7L12 2Z"></path>
                <path d="M2 17L12 22L22 17"></path>
                <path d="M2 12L12 17L22 12"></path>
              </svg>
              <h1>AITBC Explorer</h1>
            </div>
            <div class="header-stats">
              <div class="stat">
                <span class="stat-label">Height</span>
                <span class="stat-value">{{ formatNumber(chainInfo.height) }}</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      <!-- Main Content -->
      <main class="main">
        <div class="container">
          <!-- Loading State -->
          <div v-if="loading" class="loading">
            <div class="spinner"></div>
            <p>Loading blockchain data...</p>
          </div>
          
          <!-- Error State -->
          <div v-else-if="error" class="error">
            <svg class="error-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
            <p>{{ error }}</p>
            <button @click="loadChainData" class="retry-btn">Retry</button>
          </div>
          
          <!-- Chain Overview -->
          <div v-else class="overview">
            <div class="cards">
              <div class="card">
                <div class="card-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"></path>
                  </svg>
                </div>
                <div class="card-content">
                  <h3>Current Height</h3>
                  <p class="card-value">{{ formatNumber(chainInfo.height) }}</p>
                </div>
              </div>
              
              <div class="card">
                <div class="card-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
                  </svg>
                </div>
                <div class="card-content">
                  <h3>Latest Block</h3>
                  <p class="card-value hash">{{ formatHash(chainInfo.hash) }}</p>
                </div>
              </div>
              
              <div class="card">
                <div class="card-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path>
                  </svg>
                </div>
                <div class="card-content">
                  <h3>Total Transactions</h3>
                  <p class="card-value">{{ formatNumber(stats.totalTransactions) }}</p>
                </div>
              </div>
            </div>
          </div>
          
          <!-- Latest Blocks -->
          <div v-if="!loading && !error" class="blocks-section">
            <h2>Latest Blocks</h2>
            <div class="blocks-list">
              <div v-for="block in latestBlocks" :key="block.height" 
                   class="block-item" :class="getBlockType(block)">
                <div class="block-height">
                  <span class="height">{{ formatNumber(block.height) }}</span>
                  <span v-if="block.tx_count > 0" class="tx-badge">{{ block.tx_count }} tx</span>
                </div>
                <div class="block-details">
                  <div class="block-hash">
                    <span class="label">Hash:</span>
                    <span class="value">{{ formatHash(block.hash) }}</span>
                  </div>
                  <div class="block-time">
                    <span class="label">Time:</span>
                    <span class="value">{{ formatTime(block.timestamp) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  `
})

app.mount('#app')
