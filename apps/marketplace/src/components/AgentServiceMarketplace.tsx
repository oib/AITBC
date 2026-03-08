import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Alert, AlertDescription, AlertTitle } from './ui/alert';
import { Progress } from './ui/progress';
import { 
  Store, 
  Search, 
  Filter, 
  Star, 
  Clock, 
  DollarSign, 
  Users, 
  TrendingUp, 
  Award, 
  Shield, 
  Zap, 
  Target, 
  BarChart3, 
  Calendar, 
  CheckCircle, 
  AlertCircle, 
  XCircle, 
  Plus, 
  Edit, 
  Trash2, 
  Eye, 
  MessageSquare,
  ThumbsUp,
  ThumbsDown,
  Briefcase,
  Building,
  MapPin,
  Globe,
  Lock,
  Unlock,
  Heart,
  Share2,
  Bookmark,
  MoreHorizontal
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { useWallet } from '@/hooks/use-wallet';

interface Service {
  id: string;
  agentId: string;
  serviceType: string;
  name: string;
  description: string;
  metadata: Record<string, any>;
  basePrice: number;
  reputation: number;
  status: string;
  totalEarnings: number;
  completedJobs: number;
  averageRating: number;
  ratingCount: number;
  listedAt: string;
  lastUpdated: string;
  guildId?: string;
  tags: string[];
  capabilities: string[];
  requirements: string[];
  pricingModel: string;
  estimatedDuration: number;
  availability: Record<string, boolean>;
}

interface MarketplaceAnalytics {
  totalServices: number;
  activeServices: number;
  totalRequests: number;
  pendingRequests: number;
  totalVolume: number;
  totalGuilds: number;
  averageServicePrice: number;
  popularCategories: string[];
  topAgents: string[];
  revenueTrends: Record<string, number>;
  growthMetrics: Record<string, number>;
}

const AgentServiceMarketplace: React.FC = () => {
  const { toast } = useToast();
  const { isConnected, address } = useWallet();
  
  const [services, setServices] = useState<Service[]>([]);
  const [analytics, setAnalytics] = useState<MarketplaceAnalytics | null>(null);
  const [activeTab, setActiveTab] = useState('marketplace');
  const [loading, setLoading] = useState(true);
  
  // Search and filter states
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [priceRange, setPriceRange] = useState({ min: 0, max: 1000 });
  const [minRating, setMinRating] = useState(0);
  
  // Mock data for demonstration
  const mockServices: Service[] = [
    {
      id: 'service_001',
      agentId: 'agent_001',
      serviceType: 'data_analysis',
      name: 'Advanced Data Analytics',
      description: 'Comprehensive data analysis with machine learning insights',
      metadata: { expertise: ['ml', 'statistics', 'visualization'] },
      basePrice: 0.05,
      reputation: 850,
      status: 'active',
      totalEarnings: 2.5,
      completedJobs: 50,
      averageRating: 4.7,
      ratingCount: 45,
      listedAt: '2024-01-26T10:00:00Z',
      lastUpdated: '2024-01-26T16:00:00Z',
      guildId: 'guild_001',
      tags: ['machine-learning', 'statistics', 'visualization'],
      capabilities: ['data-processing', 'ml-models', 'insights'],
      requirements: ['data-access', 'clear-objectives'],
      pricingModel: 'fixed',
      estimatedDuration: 2,
      availability: { monday: true, tuesday: true, wednesday: true, thursday: true, friday: true, saturday: false, sunday: false }
    },
    {
      id: 'service_002',
      agentId: 'agent_002',
      serviceType: 'content_creation',
      name: 'AI Content Generation',
      description: 'High-quality content creation for blogs, articles, and marketing',
      metadata: { expertise: ['writing', 'seo', 'marketing'] },
      basePrice: 0.03,
      reputation: 920,
      status: 'active',
      totalEarnings: 1.8,
      completedJobs: 60,
      averageRating: 4.9,
      ratingCount: 58,
      listedAt: '2024-01-25T08:00:00Z',
      lastUpdated: '2024-01-26T14:00:00Z',
      tags: ['writing', 'seo', 'marketing', 'content'],
      capabilities: ['blog-writing', 'article-writing', 'seo-optimization'],
      requirements: ['topic-guidelines', 'target-audience'],
      pricingModel: 'per_task',
      estimatedDuration: 1,
      availability: { monday: true, tuesday: true, wednesday: true, thursday: true, friday: true, saturday: true, sunday: true }
    },
    {
      id: 'service_003',
      agentId: 'agent_003',
      serviceType: 'research',
      name: 'Market Research Analysis',
      description: 'In-depth market research and competitive analysis',
      metadata: { expertise: ['research', 'analysis', 'reporting'] },
      basePrice: 0.08,
      reputation: 780,
      status: 'active',
      totalEarnings: 3.2,
      completedJobs: 40,
      averageRating: 4.5,
      ratingCount: 38,
      listedAt: '2024-01-24T12:00:00Z',
      lastUpdated: '2024-01-26T11:00:00Z',
      tags: ['research', 'analysis', 'reporting', 'market'],
      capabilities: ['market-analysis', 'competitive-intelligence', 'reporting'],
      requirements: ['research-scope', 'industry-focus'],
      pricingModel: 'hourly',
      estimatedDuration: 4,
      availability: { monday: true, tuesday: true, wednesday: true, thursday: true, friday: true, saturday: false, sunday: false }
    }
  ];
  
  const mockAnalytics: MarketplaceAnalytics = {
    totalServices: 150,
    activeServices: 120,
    totalRequests: 450,
    pendingRequests: 25,
    totalVolume: 25.5,
    totalGuilds: 8,
    averageServicePrice: 0.17,
    popularCategories: ['data_analysis', 'content_creation', 'research', 'development'],
    topAgents: ['agent_001', 'agent_002', 'agent_003'],
    revenueTrends: { '2024-01': 5.2, '2024-02': 8.1, '2024-03': 12.2 },
    growthMetrics: { 'service_growth': 0.15, 'request_growth': 0.25, 'guild_growth': 0.10 }
  };
  
  useEffect(() => {
    // Load mock data
    setTimeout(() => {
      setServices(mockServices);
      setAnalytics(mockAnalytics);
      setLoading(false);
    }, 1000);
  }, []);
  
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return 'bg-green-500';
      case 'pending': return 'bg-yellow-500';
      case 'accepted': return 'bg-blue-500';
      case 'completed': return 'bg-green-500';
      case 'cancelled': return 'bg-red-500';
      case 'expired': return 'bg-gray-500';
      default: return 'bg-gray-400';
    }
  };
  
  const renderStars = (rating: number) => {
    return Array.from({ length: 5 }, (_, i) => (
      <Star
        key={i}
        className={`w-4 h-4 ${i < rating ? 'text-yellow-400 fill-current' : 'text-gray-300'}`}
      />
    ));
  };
  
  const filteredServices = services.filter(service => {
    if (selectedCategory !== 'all' && service.serviceType !== selectedCategory) return false;
    if (service.basePrice < priceRange.min || service.basePrice > priceRange.max) return false;
    if (service.averageRating < minRating) return false;
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      return (
        service.name.toLowerCase().includes(query) ||
        service.description.toLowerCase().includes(query) ||
        service.tags.some(tag => tag.toLowerCase().includes(query))
      );
    }
    return true;
  });
  
  if (loading) {
    return (
      <div className="container mx-auto p-6 space-y-6">
        <div className="text-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
          <p className="mt-2 text-muted-foreground">Loading marketplace...</p>
        </div>
      </div>
    );
  }
  
  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">AI Agent Service Marketplace</h1>
          <p className="text-muted-foreground mt-2">
            Discover and monetize specialized AI agent services
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <Badge variant="outline" className="flex items-center space-x-1">
            <Store className="w-4 h-4" />
            <span>{analytics?.totalServices} Services</span>
          </Badge>
          <Badge variant="outline" className="flex items-center space-x-1">
            <Users className="w-4 h-4" />
            <span>{analytics?.totalGuilds} Guilds</span>
          </Badge>
          <Badge variant="outline" className="flex items-center space-x-1">
            <TrendingUp className="w-4 h-4" />
            <span>{analytics?.totalVolume} AITBC Volume</span>
          </Badge>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-5">
          <TabsTrigger value="marketplace">Marketplace</TabsTrigger>
          <TabsTrigger value="analytics">Analytics</TabsTrigger>
        </TabsList>

        <TabsContent value="marketplace" className="space-y-6">
          {/* Search and Filters */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Search className="w-5 h-5" />
                <span>Search Services</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Search</label>
                  <Input
                    placeholder="Search services..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Category</label>
                  <Select value={selectedCategory} onValueChange={setSelectedCategory}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select category" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Categories</SelectItem>
                      <SelectItem value="data_analysis">Data Analysis</SelectItem>
                      <SelectItem value="content_creation">Content Creation</SelectItem>
                      <SelectItem value="research">Research</SelectItem>
                      <SelectItem value="development">Development</SelectItem>
                      <SelectItem value="design">Design</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Price Range</label>
                  <div className="flex items-center space-x-2">
                    <Input
                      type="number"
                      placeholder="Min"
                      value={priceRange.min}
                      onChange={(e) => setPriceRange({ ...priceRange, min: parseFloat(e.target.value) || 0 })}
                    />
                    <span>-</span>
                    <Input
                      type="number"
                      placeholder="Max"
                      value={priceRange.max}
                      onChange={(e) => setPriceRange({ ...priceRange, max: parseFloat(e.target.value) || 1000 })}
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Min Rating</label>
                  <Select value={minRating.toString()} onValueChange={(value) => setMinRating(parseInt(value))}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select rating" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="0">All Ratings</SelectItem>
                      <SelectItem value="3">3+ Stars</SelectItem>
                      <SelectItem value="4">4+ Stars</SelectItem>
                      <SelectItem value="5">5 Stars</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Service Listings */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredServices.map((service) => (
              <Card key={service.id} className="cursor-pointer hover:shadow-lg transition-shadow">
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <CardTitle className="text-lg">{service.name}</CardTitle>
                      <CardDescription className="mt-1">
                        {service.description}
                      </CardDescription>
                    </div>
                    <div className={`w-3 h-3 rounded-full ${getStatusColor(service.status)}`}></div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between">
                    <Badge variant="outline">{service.serviceType.replace('_', ' ')}</Badge>
                    <div className="flex items-center space-x-1">
                      {renderStars(Math.floor(service.averageRating))}
                      <span className="text-sm text-muted-foreground">({service.ratingCount})</span>
                    </div>
                  </div>
                  
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-1">
                      <DollarSign className="w-4 h-4 text-muted-foreground" />
                      <span className="font-semibold">{service.basePrice} AITBC</span>
                    </div>
                    <div className="flex items-center space-x-1">
                      <Shield className="w-4 h-4 text-muted-foreground" />
                      <span className="text-sm">{service.reputation}</span>
                    </div>
                  </div>
                  
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-1">
                      <Briefcase className="w-4 h-4 text-muted-foreground" />
                      <span className="text-sm">{service.completedJobs} jobs</span>
                    </div>
                    <div className="flex items-center space-x-1">
                      <TrendingUp className="w-4 h-4 text-muted-foreground" />
                      <span className="text-sm">{service.totalEarnings} AITBC</span>
                    </div>
                  </div>
                  
                  <div className="flex flex-wrap gap-1">
                    {service.tags.map((tag) => (
                      <Badge key={tag} variant="secondary" className="text-xs">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                </CardContent>
                <CardFooter className="flex space-x-2">
                  <Button
                    variant="outline"
                    size="sm"
                  >
                    <Eye className="w-4 h-4 mr-2" />
                    View
                  </Button>
                  <Button
                    size="sm"
                  >
                    <Plus className="w-4 h-4 mr-2" />
                    Request
                  </Button>
                </CardFooter>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="analytics" className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <Store className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Total Services</span>
                </div>
                <div className="text-2xl font-bold">{analytics?.totalServices}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  {analytics?.activeServices} active
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <Users className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Total Requests</span>
                </div>
                <div className="text-2xl font-bold">{analytics?.totalRequests}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  {analytics?.pendingRequests} pending
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <DollarSign className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Total Volume</span>
                </div>
                <div className="text-2xl font-bold">{analytics?.totalVolume} AITBC</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Avg: {analytics?.averageServicePrice} AITBC
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <Building className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Total Guilds</span>
                </div>
                <div className="text-2xl font-bold">{analytics?.totalGuilds}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Active guilds
                </p>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default AgentServiceMarketplace;
