# Marketplace Web - AITBC Documentation

Vite/TypeScript marketplace with offer/bid functionality, stats dashboard, and mock/live data toggle. Production UI ready.

<span class="component-status live">● Live</span>

## Overview

The Marketplace Web is the primary interface for clients to submit AI compute jobs and for miners to offer their services. It provides a real-time trading platform with comprehensive job management and analytics.

### Key Features

- Real-time job marketplace with offer/bid functionality
- Interactive statistics dashboard
- Mock/live data toggle for development
- Responsive design for all devices
- WebSocket integration for live updates
- Wallet integration for seamless payments

## Technology Stack

- **Framework**: Vite 4.x
- **Language**: TypeScript 5.x
- **UI**: TailwindCSS + Headless UI
- **State Management**: Zustand
- **Charts**: Chart.js
- **WebSocket**: Native WebSocket API
- **Icons**: Lucide React

## Getting Started

### Prerequisites

- Node.js 18+
- npm or yarn

### Installation

```bash
# Clone the repository
git clone https://gitea.bubuit.net/oib/aitbc.git
cd aitbc/apps/marketplace-web

# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

### Environment Variables

Create `.env.local`:

```env
VITE_API_URL=http://localhost:18000
VITE_WS_URL=ws://localhost:18000/ws
VITE_EXPLORER_URL=http://localhost:3000
VITE_NETWORK=mainnet
```

## Architecture

### Directory Structure

```
marketplace-web/
├── src/
│   ├── components/     # Reusable UI components
│   ├── pages/         # Page components
│   ├── hooks/         # Custom React hooks
│   ├── stores/        # Zustand stores
│   ├── types/         # TypeScript definitions
│   ├── utils/         # Utility functions
│   └── styles/        # Global styles
├── public/            # Static assets
└── dist/             # Build output
```

### Core Components

#### JobCard
Display job information with real-time status updates.

```typescript
interface JobCardProps {
  job: Job;
  onBid?: (jobId: string, amount: number) => void;
  showActions?: boolean;
}
```

#### StatsDashboard
Real-time statistics and charts.

```typescript
interface StatsData {
  totalJobs: number;
  activeMiners: number;
  avgProcessingTime: number;
  totalVolume: number;
}
```

#### OfferPanel
Create and manage job offers.

```typescript
interface OfferForm {
  model: string;
  prompt: string;
  parameters: JobParameters;
  maxPrice: number;
}
```

## Features

### 1. Job Marketplace

Browse and submit AI compute jobs:

- Filter by model type and price
- Sort by deadline or reward
- Real-time status updates
- Bid on available jobs

### 2. Statistics Dashboard

Monitor network activity:

- Total jobs and volume
- Active miners count
- Average processing times
- Historical charts

### 3. Wallet Integration

Connect your AITBC wallet:

- Browser wallet support
- Balance display
- Transaction history
- One-click payments

### 4. Developer Mode

Toggle between mock and live data:

```typescript
const isDevMode = import.meta.env.DEV;
const useMockData = localStorage.getItem('useMockData') === 'true';
```

## API Integration

### WebSocket Events

```typescript
// Connect to WebSocket
const ws = new WebSocket(VITE_WS_URL);

// Listen for job updates
ws.on('job_update', (data: JobUpdate) => {
  updateJobStatus(data.jobId, data.status);
});

// Listen for new bids
ws.on('new_bid', (data: Bid) => {
  addBidToList(data);
});
```

### REST API Calls

```typescript
// Submit job
const submitJob = async (job: JobSubmission) => {
  const response = await fetch(`${VITE_API_URL}/v1/jobs`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Api-Key': apiKey,
    },
    body: JSON.stringify(job),
  });
  return response.json();
};

// Get market stats
const getStats = async () => {
  const response = await fetch(`${VITE_API_URL}/v1/stats`);
  return response.json();
};
```

## State Management

Using Zustand for state management:

```typescript
// stores/marketplace.ts
interface MarketplaceStore {
  jobs: Job[];
  stats: StatsData;
  filters: FilterOptions;
  setJobs: (jobs: Job[]) => void;
  updateJob: (jobId: string, updates: Partial<Job>) => void;
  setFilters: (filters: FilterOptions) => void;
}

export const useMarketplaceStore = create<MarketplaceStore>((set) => ({
  jobs: [],
  stats: initialStats,
  filters: {},
  setJobs: (jobs) => set({ jobs }),
  updateJob: (jobId, updates) =>
    set((state) => ({
      jobs: state.jobs.map((job) =>
        job.id === jobId ? { ...job, ...updates } : job
      ),
    })),
  setFilters: (filters) => set({ filters }),
}));
```

## Styling

### TailwindCSS Configuration

```javascript
// tailwind.config.js
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: '#2563eb',
        secondary: '#1e40af',
      },
    },
  },
  plugins: [],
};
```

### CSS Variables

```css
/* src/styles/globals.css */
:root {
  --color-primary: #2563eb;
  --color-secondary: #1e40af;
  --color-success: #10b981;
  --color-warning: #f59e0b;
  --color-danger: #ef4444;
}
```

## Deployment

### Docker Deployment

```dockerfile
FROM node:18-alpine

WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production

COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=0 /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### Environment Configuration

#### Production

```env
VITE_API_URL=https://aitbc.bubuit.net/api
VITE_WS_URL=wss://aitbc.bubuit.net/ws
VITE_NETWORK=mainnet
```

#### Staging

```env
VITE_API_URL=https://staging.aitbc.bubuit.net/api
VITE_WS_URL=wss://staging.aitbc.bubuit.net/ws
VITE_NETWORK=testnet
```

## Testing

### Unit Tests

```bash
# Run tests
npm run test

# Run with coverage
npm run test:coverage
```

### E2E Tests

```bash
# Install Playwright
npm run install:e2e

# Run E2E tests
npm run test:e2e
```

## Performance Optimization

### Code Splitting

```typescript
// Lazy load components
const StatsDashboard = lazy(() => import('./components/StatsDashboard'));
const JobList = lazy(() => import('./components/JobList'));

// Use with Suspense
<Suspense fallback={<Loading />}>
  <StatsDashboard />
</Suspense>
```

### Image Optimization

```typescript
// Use next-gen formats
const optimizedImage = {
  src: '/api/og?title=Marketplace',
  width: 1200,
  height: 630,
  format: 'avif',
};
```

## Troubleshooting

### Common Issues

1. **WebSocket Connection Failed**
   - Check WS_URL in environment
   - Verify firewall settings
   - Check browser console for errors

2. **Data Not Loading**
   - Toggle mock/live data switch
   - Check API endpoint status
   - Verify API key configuration

3. **Build Errors**
   - Clear node_modules and reinstall
   - Check TypeScript version
   - Verify all imports

### Debug Mode

Enable debug logging:

```typescript
if (import.meta.env.DEV) {
  console.log('Debug info:', debugData);
}
```

## Contributing

1. Fork the repository
2. Create feature branch
3. Make changes
4. Add tests
5. Submit PR

### Code Style

- Use TypeScript strict mode
- Follow ESLint rules
- Use Prettier for formatting
- Write meaningful commit messages

## Security

- Never commit API keys
- Use environment variables for secrets
- Implement rate limiting
- Validate all inputs
- Use HTTPS in production

## Support

- Documentation: [docs.aitbc.bubuit.net](https://docs.aitbc.bubuit.net)
- Discord: [discord.gg/aitbc](https://discord.gg/aitbc)
- Issues: [Gitea Issues](https://gitea.bubuit.net/oib/aitbc/issues)
