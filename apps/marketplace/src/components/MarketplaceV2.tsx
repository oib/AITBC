import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Alert, AlertDescription, AlertTitle } from './ui/alert';
import { Progress } from './ui/progress';
import { Separator } from './ui/separator';
import { 
  Store, 
  TrendingUp, 
  Users, 
  Package, 
  Star, 
  Heart, 
  Share2, 
  Download, 
  Upload, 
  Search, 
  Filter, 
  Plus, 
  Edit, 
  Trash2, 
  Eye, 
  EyeOff, 
  Copy, 
  MoreHorizontal, 
  Clock, 
  Calendar, 
  DollarSign, 
  CreditCard, 
  Wallet, 
  Shield, 
  Lock, 
  Unlock, 
  CheckCircle, 
  XCircle, 
  AlertCircle, 
  Info, 
  BarChart3, 
  Activity, 
  Zap, 
  Rocket, 
  Target, 
  Award, 
  Crown, 
  Gem, 
  Sparkles, 
  Settings, 
  Play, 
  Pause, 
  RefreshCw, 
  ArrowRight, 
  ArrowUp, 
  ArrowDown, 
  ChevronRight, 
  ChevronDown, 
  ShoppingBag, 
  ShoppingCart, 
  Tag, 
  Hash, 
  AtSign,
  User,
  Building,
  Globe,
  Network,
  Database,
  Cloud,
  Cpu,
  HardDrive,
  MemoryStick,
  Wifi,
  Battery,
  Gauge,
  LineChart,
  PieChart,
  FileText,
  Folder,
  FolderOpen,
  Bell,
  Volume2,
  VolumeX,
  MessageSquare,
  ThumbsUp,
  ThumbsDown,
  Bookmark,
  BookmarkCheck,
  Link2,
  Unlink,
  ZapOff,
  Power,
  PowerOff,
  Settings2,
  Sliders,
  ToggleLeft,
  ToggleRight,
  Key,
  EyeOff as EyeHidden,
  Copy as CopyIcon,
  Share as ShareIcon,
  Brain
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { useWallet } from '@/hooks/use-wallet';

interface MarketplaceService {
  id: string;
  name: string;
  description: string;
  type: 'capability' | 'service' | 'subscription' | 'model' | 'compute' | 'data';
  category: string;
  provider: {
    address: string;
    name: string;
    reputation: number;
    avatar?: string;
    verified: boolean;
  };
  pricing: {
    type: 'fixed' | 'subscription' | 'usage_based' | 'auction';
    amount: number;
    currency: string;
    period?: string;
    unit?: string;
    discount?: number;
  };
  capabilities: Array<{
    name: string;
    description: string;
    performance: number;
    reliability: number;
  }>;
  metrics: {
    rating: number;
    reviews: number;
    usage: number;
    revenue: number;
    subscribers?: number;
  };
  availability: {
    status: 'available' | 'busy' | 'offline' | 'maintenance';
    uptime: number;
    responseTime: number;
    lastUpdated: string;
  };
  requirements: {
    minReputation: number;
    supportedChains: string[];
    prerequisites: string[];
  };
  metadata: {
    tags: string[];
    createdAt: string;
    updatedAt: string;
    version: string;
    documentation?: string;
  };
}

interface MarketplaceStats {
  totalServices: number;
  activeProviders: number;
  totalRevenue: number;
  averageRating: number;
  totalTransactions: number;
  activeSubscriptions: number;
  servicesByType: Record<string, number>;
  servicesByCategory: Record<string, number>;
  topProviders: Array<{
    name: string;
    revenue: number;
    services: number;
    rating: number;
  }>;
  monthlyActivity: Array<{
    month: string;
    services: number;
    revenue: number;
    transactions: number;
    users: number;
  }>;
}

const MarketplaceV2: React.FC = () => {
  const { toast } = useToast();
  const { isConnected, address } = useWallet();
  
  const [activeTab, setActiveTab] = useState('marketplace');
  const [loading, setLoading] = useState(true);
  const [services, setServices] = useState<MarketplaceService[]>([]);
  const [selectedService, setSelectedService] = useState<MarketplaceService | null>(null);
  const [stats, setStats] = useState<MarketplaceStats | null>(null);
  
  // Form states
  const [newServiceName, setNewServiceName] = useState('');
  const [newServiceType, setNewServiceType] = useState('capability');
  const [newServiceCategory, setNewServiceCategory] = useState('ai');
  const [newServiceDescription, setNewServiceDescription] = useState('');
  const [newServicePrice, setNewServicePrice] = useState('');
  const [newServicePricingType, setNewServicePricingType] = useState('fixed');
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState('all');
  const [filterCategory, setFilterCategory] = useState('all');
  const [sortBy, setSortBy] = useState('rating');
  
  // Mock data
  const mockServices: MarketplaceService[] = [
    {
      id: 'service_001',
      name: 'Quantum Trading Algorithm',
      description: 'Advanced reinforcement learning algorithm for cryptocurrency trading with 95% accuracy',
      type: 'capability',
      category: 'trading',
      provider: {
        address: '0x8765...4321',
        name: 'QuantumTrader Pro',
        reputation: 9200,
        avatar: '🤖',
        verified: true
      },
      pricing: {
        type: 'subscription',
        amount: 500,
        currency: 'USDT',
        period: 'monthly',
        discount: 10
      },
      capabilities: [
        { name: 'Market Analysis', description: 'Real-time market analysis', performance: 95, reliability: 98 },
        { name: 'Risk Management', description: 'Advanced risk assessment', performance: 92, reliability: 96 },
        { name: 'Order Execution', description: 'Automated order execution', performance: 94, reliability: 99 }
      ],
      metrics: {
        rating: 4.8,
        reviews: 234,
        usage: 1520,
        revenue: 125000,
        subscribers: 89
      },
      availability: {
        status: 'available',
        uptime: 99.8,
        responseTime: 45,
        lastUpdated: '2024-02-27T10:15:00Z'
      },
      requirements: {
        minReputation: 1000,
        supportedChains: ['ethereum', 'polygon', 'bnb'],
        prerequisites: ['Wallet connected', 'Minimum 1000 USDT']
      },
      metadata: {
        tags: ['trading', 'ai', 'reinforcement-learning', 'crypto'],
        createdAt: '2024-02-01T00:00:00Z',
        updatedAt: '2024-02-27T10:15:00Z',
        version: '2.1.0',
        documentation: 'https://docs.quantumtrader.ai'
      }
    },
    {
      id: 'service_002',
      name: 'Medical Image Analysis AI',
      description: 'Deep learning model for medical image analysis and diagnosis assistance',
      type: 'model',
      category: 'healthcare',
      provider: {
        address: '0x5432...6789',
        name: 'MedAI Solutions',
        reputation: 8900,
        avatar: '🏥',
        verified: true
      },
      pricing: {
        type: 'usage_based',
        amount: 0.05,
        currency: 'USDT',
        unit: 'image'
      },
      capabilities: [
        { name: 'Image Classification', description: 'Medical image classification', performance: 94, reliability: 97 },
        { name: 'Anomaly Detection', description: 'Detect anomalies in medical images', performance: 91, reliability: 95 }
      ],
      metrics: {
        rating: 4.6,
        reviews: 156,
        usage: 890,
        revenue: 45600
      },
      availability: {
        status: 'available',
        uptime: 99.5,
        responseTime: 120,
        lastUpdated: '2024-02-27T09:30:00Z'
      },
      requirements: {
        minReputation: 500,
        supportedChains: ['ethereum', 'polygon'],
        prerequisites: ['HIPAA compliance', 'Medical license verification']
      },
      metadata: {
        tags: ['healthcare', 'ai', 'medical', 'diagnosis'],
        createdAt: '2024-02-10T00:00:00Z',
        updatedAt: '2024-02-27T09:30:00Z',
        version: '1.3.0'
      }
    },
    {
      id: 'service_003',
      name: 'GPU Compute Power',
      description: 'High-performance GPU computing for AI training and inference',
      type: 'compute',
      category: 'infrastructure',
      provider: {
        address: '0x9876...5432',
        name: 'CloudCompute Pro',
        reputation: 8700,
        avatar: '☁️',
        verified: true
      },
      pricing: {
        type: 'usage_based',
        amount: 0.50,
        currency: 'USDT',
        unit: 'hour'
      },
      capabilities: [
        { name: 'GPU Processing', description: 'NVIDIA A100 GPU access', performance: 98, reliability: 99 },
        { name: 'High Memory', description: '80GB VRAM available', performance: 96, reliability: 98 }
      ],
      metrics: {
        rating: 4.7,
        reviews: 412,
        usage: 2340,
        revenue: 289000
      },
      availability: {
        status: 'available',
        uptime: 99.9,
        responseTime: 5,
        lastUpdated: '2024-02-27T11:00:00Z'
      },
      requirements: {
        minReputation: 100,
        supportedChains: ['ethereum', 'polygon', 'bnb', 'arbitrum'],
        prerequisites: ['None']
      },
      metadata: {
        tags: ['compute', 'gpu', 'infrastructure', 'ai'],
        createdAt: '2024-01-15T00:00:00Z',
        updatedAt: '2024-02-27T11:00:00Z',
        version: '3.0.0'
      }
    }
  ];
  
  const mockStats: MarketplaceStats = {
    totalServices: 156,
    activeProviders: 42,
    totalRevenue: 2847500,
    averageRating: 4.5,
    totalTransactions: 12450,
    activeSubscriptions: 892,
    servicesByType: {
      capability: 45,
      service: 38,
      subscription: 29,
      model: 22,
      compute: 15,
      data: 7
    },
    servicesByCategory: {
      ai: 68,
      trading: 32,
      healthcare: 18,
      infrastructure: 15,
      data: 12,
      other: 11
    },
    topProviders: [
      { name: 'QuantumTrader Pro', revenue: 125000, services: 3, rating: 4.8 },
      { name: 'CloudCompute Pro', revenue: 289000, services: 5, rating: 4.7 },
      { name: 'MedAI Solutions', revenue: 45600, services: 2, rating: 4.6 }
    ],
    monthlyActivity: [
      { month: 'Jan', services: 12, revenue: 450000, transactions: 2100, users: 340 },
      { month: 'Feb', services: 18, revenue: 680000, transactions: 3200, users: 520 },
      { month: 'Mar', services: 24, revenue: 890000, transactions: 4100, users: 680 },
      { month: 'Apr', services: 28, revenue: 827500, transactions: 3050, users: 590 }
    ]
  };
  
  useEffect(() => {
    setTimeout(() => {
      setServices(mockServices);
      setStats(mockStats);
      setLoading(false);
    }, 1000);
  }, [address]);
  
  const handlePurchaseService = async (serviceId: string) => {
    if (!isConnected) {
      toast({
        title: "Wallet Not Connected",
        description: "Please connect your wallet to purchase services",
        variant: "destructive"
      });
      return;
    }
    
    try {
      toast({
        title: "Processing Purchase",
        description: "Initiating service purchase...",
        variant: "default"
      });
      
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      toast({
        title: "Purchase Successful",
        description: "Service has been added to your account",
        variant: "default"
      });
    } catch (error) {
      toast({
        title: "Purchase Failed",
        description: "There was an error processing your purchase",
        variant: "destructive"
      });
    }
  };
  
  const handleSubscribeService = async (serviceId: string) => {
    if (!isConnected) {
      toast({
        title: "Wallet Not Connected",
        description: "Please connect your wallet to subscribe",
        variant: "destructive"
      });
      return;
    }
    
    try {
      toast({
        title: "Processing Subscription",
        description: "Setting up your subscription...",
        variant: "default"
      });
      
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      toast({
        title: "Subscription Active",
        description: "You are now subscribed to this service",
        variant: "default"
      });
    } catch (error) {
      toast({
        title: "Subscription Failed",
        description: "There was an error setting up your subscription",
        variant: "destructive"
      });
    }
  };
  
  const handleListService = async () => {
    if (!isConnected) {
      toast({
        title: "Wallet Not Connected",
        description: "Please connect your wallet to list services",
        variant: "destructive"
      });
      return;
    }
    
    if (!newServiceName.trim() || !newServiceDescription.trim() || !newServicePrice) {
      toast({
        title: "Invalid Input",
        description: "Please fill in all required fields",
        variant: "destructive"
      });
      return;
    }
    
    try {
      toast({
        title: "Listing Service",
        description: "Publishing your service to the marketplace...",
        variant: "default"
      });
      
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      const newService: MarketplaceService = {
        id: `service_${Date.now()}`,
        name: newServiceName,
        description: newServiceDescription,
        type: newServiceType as any,
        category: newServiceCategory,
        provider: {
          address: address || '0x1234...5678',
          name: 'You',
          reputation: 8500,
          verified: false
        },
        pricing: {
          type: newServicePricingType as any,
          amount: parseFloat(newServicePrice),
          currency: 'USDT',
          period: newServicePricingType === 'subscription' ? 'monthly' : undefined,
          unit: newServicePricingType === 'usage_based' ? 'unit' : undefined
        },
        capabilities: [],
        metrics: {
          rating: 0,
          reviews: 0,
          usage: 0,
          revenue: 0
        },
        availability: {
          status: 'available',
          uptime: 0,
          responseTime: 0,
          lastUpdated: new Date().toISOString()
        },
        requirements: {
          minReputation: 0,
          supportedChains: ['ethereum'],
          prerequisites: []
        },
        metadata: {
          tags: [],
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          version: '1.0.0'
        }
      };
      
      setServices([newService, ...services]);
      
      // Reset form
      setNewServiceName('');
      setNewServiceType('capability');
      setNewServiceCategory('ai');
      setNewServiceDescription('');
      setNewServicePrice('');
      setNewServicePricingType('fixed');
      
      toast({
        title: "Service Listed",
        description: "Your service is now live on the marketplace",
        variant: "default"
      });
    } catch (error) {
      toast({
        title: "Listing Failed",
        description: "There was an error listing your service",
        variant: "destructive"
      });
    }
  };
  
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'available': return 'bg-green-500';
      case 'busy': return 'bg-yellow-500';
      case 'offline': return 'bg-red-500';
      case 'maintenance': return 'bg-orange-500';
      default: return 'bg-gray-400';
    }
  };
  
  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'capability': return <Zap className="w-4 h-4" />;
      case 'service': return <Package className="w-4 h-4" />;
      case 'subscription': return <Crown className="w-4 h-4" />;
      case 'model': return <Brain className="w-4 h-4" />;
      case 'compute': return <Cpu className="w-4 h-4" />;
      case 'data': return <Database className="w-4 h-4" />;
      default: return <Package className="w-4 h-4" />;
    }
  };
  
  const getRatingColor = (rating: number) => {
    if (rating >= 4.5) return 'text-green-600';
    if (rating >= 4.0) return 'text-blue-600';
    if (rating >= 3.5) return 'text-yellow-600';
    return 'text-red-600';
  };
  
  const sortedServices = [...services].sort((a, b) => {
    switch (sortBy) {
      case 'rating':
        return b.metrics.rating - a.metrics.rating;
      case 'revenue':
        return b.metrics.revenue - a.metrics.revenue;
      case 'usage':
        return b.metrics.usage - a.metrics.usage;
      case 'price_low':
        return a.pricing.amount - b.pricing.amount;
      case 'price_high':
        return b.pricing.amount - a.pricing.amount;
      case 'name':
        return a.name.localeCompare(b.name);
      default:
        return 0;
    }
  });
  
  const filteredServices = sortedServices.filter(service => {
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      return service.name.toLowerCase().includes(query) || 
             service.description.toLowerCase().includes(query) ||
             service.provider.name.toLowerCase().includes(query);
    }
    if (filterType !== 'all') return service.type === filterType;
    if (filterCategory !== 'all') return service.category === filterCategory;
    return true;
  });
  
  if (loading) {
    return (
      <div className="container mx-auto p-6 space-y-6">
        <div className="text-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
          <p className="mt-2 text-muted-foreground">Loading Agent Marketplace 2.0...</p>
        </div>
      </div>
    );
  }
  
  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Agent Marketplace 2.0</h1>
          <p className="text-muted-foreground mt-2">
            Advanced agent capability trading and service subscriptions
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <Badge variant="outline" className="flex items-center space-x-1">
            <Store className="w-4 h-4" />
            <span>{stats?.totalServices} Services</span>
          </Badge>
          <Badge variant="outline" className="flex items-center space-x-1">
            <Users className="w-4 h-4" />
            <span>{stats?.activeProviders} Providers</span>
          </Badge>
          <Badge variant="outline" className="flex items-center space-x-1">
            <Star className="w-4 h-4" />
            <span>{stats?.averageRating} Avg Rating</span>
          </Badge>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="marketplace">Marketplace</TabsTrigger>
          <TabsTrigger value="subscriptions">Subscriptions</TabsTrigger>
          <TabsTrigger value="list">List Service</TabsTrigger>
          <TabsTrigger value="analytics">Analytics</TabsTrigger>
        </TabsList>

        <TabsContent value="marketplace" className="space-y-6">
          {/* Search and Filters */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Search className="w-5 h-5" />
                <span>Search & Filter</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Search</label>
                  <div className="relative">
                    <Search className="absolute left-3 top-3 w-4 h-4 text-muted-foreground" />
                    <Input
                      placeholder="Search services..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="pl-10"
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Type</label>
                  <Select value={filterType} onValueChange={setFilterType}>
                    <SelectTrigger>
                      <SelectValue placeholder="All types" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Types</SelectItem>
                      <SelectItem value="capability">Capability</SelectItem>
                      <SelectItem value="service">Service</SelectItem>
                      <SelectItem value="subscription">Subscription</SelectItem>
                      <SelectItem value="model">Model</SelectItem>
                      <SelectItem value="compute">Compute</SelectItem>
                      <SelectItem value="data">Data</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Category</label>
                  <Select value={filterCategory} onValueChange={setFilterCategory}>
                    <SelectTrigger>
                      <SelectValue placeholder="All categories" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Categories</SelectItem>
                      <SelectItem value="ai">AI</SelectItem>
                      <SelectItem value="trading">Trading</SelectItem>
                      <SelectItem value="healthcare">Healthcare</SelectItem>
                      <SelectItem value="infrastructure">Infrastructure</SelectItem>
                      <SelectItem value="data">Data</SelectItem>
                      <SelectItem value="other">Other</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Sort By</label>
                  <Select value={sortBy} onValueChange={setSortBy}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="rating">Rating</SelectItem>
                      <SelectItem value="revenue">Revenue</SelectItem>
                      <SelectItem value="usage">Usage</SelectItem>
                      <SelectItem value="price_low">Price (Low to High)</SelectItem>
                      <SelectItem value="price_high">Price (High to Low)</SelectItem>
                      <SelectItem value="name">Name</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Actions</label>
                  <div className="flex space-x-2">
                    <Button variant="outline" size="sm">
                      <Filter className="w-4 h-4 mr-2" />
                      More Filters
                    </Button>
                    <Button variant="outline" size="sm">
                      <Download className="w-4 h-4 mr-2" />
                      Export
                    </Button>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Services Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {filteredServices.map((service) => (
              <Card key={service.id} className="hover:shadow-lg transition-shadow">
                <CardHeader>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center space-x-2">
                      {getTypeIcon(service.type)}
                      <Badge variant="outline">{service.type}</Badge>
                      <Badge variant="secondary">{service.category}</Badge>
                      {service.provider.verified && (
                        <Badge variant="default" className="flex items-center space-x-1">
                          <Shield className="w-3 h-3" />
                          <span>Verified</span>
                        </Badge>
                      )}
                      <div className={`w-2 h-2 rounded-full ${getStatusColor(service.availability.status)}`}></div>
                    </div>
                    <Button variant="ghost" size="sm">
                      <MoreHorizontal className="w-4 h-4" />
                    </Button>
                  </div>
                  
                  <CardTitle className="text-lg">{service.name}</CardTitle>
                  <CardDescription className="line-clamp-2">
                    {service.description}
                  </CardDescription>
                </CardHeader>
                
                <CardContent>
                  <div className="space-y-4">
                    {/* Provider Info */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <div className="w-6 h-6 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs font-medium">
                          {service.provider.avatar || service.provider.name.charAt(0).toUpperCase()}
                        </div>
                        <span className="text-sm font-medium">{service.provider.name}</span>
                        <Badge variant="outline" className="text-xs">
                          {service.provider.reputation.toLocaleString()} rep
                        </Badge>
                      </div>
                      <div className="flex items-center space-x-1">
                        <Star className="w-4 h-4 text-yellow-500 fill-current" />
                        <span className={`text-sm font-medium ${getRatingColor(service.metrics.rating)}`}>
                          {service.metrics.rating}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          ({service.metrics.reviews})
                        </span>
                      </div>
                    </div>
                    
                    {/* Pricing */}
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">Pricing</span>
                      <div className="text-right">
                        <div className="text-lg font-bold">
                          ${service.pricing.amount} {service.pricing.currency}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {service.pricing.type === 'subscription' && `per ${service.pricing.period}`}
                          {service.pricing.type === 'usage_based' && `per ${service.pricing.unit}`}
                          {service.pricing.type === 'fixed' && 'one-time'}
                          {service.pricing.type === 'auction' && 'auction'}
                        </div>
                      </div>
                    </div>
                    
                    {/* Metrics */}
                    <div className="grid grid-cols-3 gap-4 text-sm">
                      <div className="text-center">
                        <div className="font-medium">{service.metrics.usage.toLocaleString()}</div>
                        <div className="text-xs text-muted-foreground">Usage</div>
                      </div>
                      <div className="text-center">
                        <div className="font-medium">{service.availability.uptime}%</div>
                        <div className="text-xs text-muted-foreground">Uptime</div>
                      </div>
                      <div className="text-center">
                        <div className="font-medium">{service.availability.responseTime}ms</div>
                        <div className="text-xs text-muted-foreground">Response</div>
                      </div>
                    </div>
                    
                    {/* Tags */}
                    {service.metadata.tags.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {service.metadata.tags.slice(0, 3).map((tag, index) => (
                          <Badge key={index} variant="secondary" className="text-xs">
                            #{tag}
                          </Badge>
                        ))}
                        {service.metadata.tags.length > 3 && (
                          <Badge variant="secondary" className="text-xs">
                            +{service.metadata.tags.length - 3}
                          </Badge>
                        )}
                      </div>
                    )}
                  </div>
                </CardContent>
                
                <CardFooter>
                  <div className="flex space-x-2 w-full">
                    <Button size="sm" className="flex-1">
                      <Eye className="w-4 h-4 mr-2" />
                      View Details
                    </Button>
                    {service.pricing.type === 'subscription' ? (
                      <Button size="sm" className="flex-1" onClick={() => handleSubscribeService(service.id)}>
                        <Crown className="w-4 h-4 mr-2" />
                        Subscribe
                      </Button>
                    ) : (
                      <Button size="sm" className="flex-1" onClick={() => handlePurchaseService(service.id)}>
                        <ShoppingCart className="w-4 h-4 mr-2" />
                        Purchase
                      </Button>
                    )}
                  </div>
                </CardFooter>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="subscriptions" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Crown className="w-5 h-5" />
                <span>Active Subscriptions</span>
              </CardTitle>
              <CardDescription>
                Your active service subscriptions
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {services.filter(s => s.pricing.type === 'subscription').map((service) => (
                  <div key={service.id} className="p-4 border rounded-lg">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center space-x-2">
                        {getTypeIcon(service.type)}
                        <span className="font-semibold">{service.name}</span>
                        <Badge variant="outline">{service.provider.name}</Badge>
                      </div>
                      <div className="flex items-center space-x-2">
                        <Badge variant="default">Active</Badge>
                        <Button variant="ghost" size="sm">
                          <MoreHorizontal className="w-4 h-4" />
                        </Button>
                      </div>
                    </div>
                    
                    <p className="text-sm text-muted-foreground mb-3">{service.description}</p>
                    
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                      <div>
                        <span className="text-muted-foreground">Monthly Cost:</span>
                        <p className="font-medium">${service.pricing.amount} {service.pricing.currency}</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Next Billing:</span>
                        <p className="font-medium">March 27, 2024</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Usage This Month:</span>
                        <p className="font-medium">{Math.floor(service.metrics.usage * 0.3)} times</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Status:</span>
                        <p className="font-medium text-green-600">Active</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="list" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Plus className="w-5 h-5" />
                <span>List New Service</span>
              </CardTitle>
              <CardDescription>
                Offer your services on the Agent Marketplace 2.0
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Service Name</label>
                  <Input
                    placeholder="Enter service name"
                    value={newServiceName}
                    onChange={(e) => setNewServiceName(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Service Type</label>
                  <Select value={newServiceType} onValueChange={setNewServiceType}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="capability">Capability</SelectItem>
                      <SelectItem value="service">Service</SelectItem>
                      <SelectItem value="subscription">Subscription</SelectItem>
                      <SelectItem value="model">Model</SelectItem>
                      <SelectItem value="compute">Compute</SelectItem>
                      <SelectItem value="data">Data</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Category</label>
                  <Select value={newServiceCategory} onValueChange={setNewServiceCategory}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="ai">AI</SelectItem>
                      <SelectItem value="trading">Trading</SelectItem>
                      <SelectItem value="healthcare">Healthcare</SelectItem>
                      <SelectItem value="infrastructure">Infrastructure</SelectItem>
                      <SelectItem value="data">Data</SelectItem>
                      <SelectItem value="other">Other</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Pricing Type</label>
                  <Select value={newServicePricingType} onValueChange={setNewServicePricingType}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="fixed">Fixed Price</SelectItem>
                      <SelectItem value="subscription">Subscription</SelectItem>
                      <SelectItem value="usage_based">Usage Based</SelectItem>
                      <SelectItem value="auction">Auction</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              
              <div className="space-y-2">
                <label className="text-sm font-medium">Description</label>
                <textarea
                  placeholder="Describe your service and its capabilities"
                  value={newServiceDescription}
                  onChange={(e) => setNewServiceDescription(e.target.value)}
                  className="w-full min-h-[100px] p-3 border rounded-md resize-none focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Price</label>
                  <Input
                    type="number"
                    placeholder="0.00"
                    value={newServicePrice}
                    onChange={(e) => setNewServicePrice(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Currency</label>
                  <Select defaultValue="USDT">
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="USDT">USDT</SelectItem>
                      <SelectItem value="USDC">USDC</SelectItem>
                      <SelectItem value="ETH">ETH</SelectItem>
                      <SelectItem value="AITBC">AITBC</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </CardContent>
            <CardFooter>
              <div className="flex space-x-2 w-full">
                <Button variant="outline" className="flex-1">
                  Save as Draft
                </Button>
                <Button onClick={handleListService} className="flex-1">
                  <Plus className="w-4 h-4 mr-2" />
                  List Service
                </Button>
              </div>
            </CardFooter>
          </Card>
        </TabsContent>

        <TabsContent value="analytics" className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <Store className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Total Services</span>
                </div>
                <div className="text-2xl font-bold">{stats?.totalServices}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Listed services
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <Users className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Active Providers</span>
                </div>
                <div className="text-2xl font-bold">{stats?.activeProviders}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Service providers
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <DollarSign className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Total Revenue</span>
                </div>
                <div className="text-2xl font-bold">${stats?.totalRevenue.toLocaleString()}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Marketplace revenue
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <Star className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Average Rating</span>
                </div>
                <div className="text-2xl font-bold">{stats?.averageRating}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Service quality
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Service Type Distribution */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <PieChart className="w-5 h-5" />
                <span>Services by Type</span>
              </CardTitle>
              <CardDescription>
                Distribution of services by type
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {Object.entries(stats?.servicesByType || {}).map(([type, count]) => (
                  <div key={type} className="space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        {getTypeIcon(type)}
                        <span className="text-sm font-medium capitalize">{type}</span>
                      </div>
                      <span className="text-sm text-muted-foreground">{count} services</span>
                    </div>
                    <Progress 
                      value={(count / stats!.totalServices) * 100} 
                      className="h-2" 
                    />
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Top Providers */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Award className="w-5 h-5" />
                <span>Top Providers</span>
              </CardTitle>
              <CardDescription>
                Highest performing service providers
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {stats?.topProviders.map((provider, index) => (
                  <div key={index} className="flex items-center justify-between p-3 border rounded-lg">
                    <div className="flex items-center space-x-3">
                      <div className="w-8 h-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-sm font-medium">
                        {index + 1}
                      </div>
                      <div>
                        <div className="font-medium">{provider.name}</div>
                        <div className="text-sm text-muted-foreground">
                          {provider.services} services • {provider.rating}★ rating
                        </div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-medium">${provider.revenue.toLocaleString()}</div>
                      <div className="text-sm text-muted-foreground">revenue</div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default MarketplaceV2;
