import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Alert, AlertDescription, AlertTitle } from './ui/alert';
import { Search, Filter, ShoppingCart, Star, TrendingUp, Clock, CheckCircle, XCircle } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { useWallet } from '@/hooks/use-wallet';

interface KnowledgeGraph {
  graphId: string;
  cid: string;
  creator: string;
  price: number;
  tags: string[];
  qualityScore: number;
  accessCount: number;
  totalRevenue: number;
  royaltyRate: number;
  isActive: boolean;
  createdAt: string;
  description: string;
  metadata: string;
}

interface PurchaseRecord {
  graphId: string;
  buyer: string;
  purchasedAt: string;
  expiresAt: string;
  decryptionKey: string;
  isActive: boolean;
}

const KnowledgeMarketplace: React.FC = () => {
  const { toast } = useToast();
  const { isConnected, address } = useWallet();
  
  const [graphs, setGraphs] = useState<KnowledgeGraph[]>([]);
  const [filteredGraphs, setFilteredGraphs] = useState<KnowledgeGraph[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [priceRange, setPriceRange] = useState({ min: 0, max: 1000 });
  const [sortBy, setSortBy] = useState('quality');
  const [loading, setLoading] = useState(true);
  const [purchasedGraphs, setPurchasedGraphs] = useState<PurchaseRecord[]>([]);
  const [activeTab, setActiveTab] = useState('browse');
  
  // Mock data for demonstration
  const mockGraphs: KnowledgeGraph[] = [
    {
      graphId: 'graph_001',
      cid: 'QmXxx...123',
      creator: '0x1234...5678',
      price: 100,
      tags: ['nlp', 'transformer', 'language'],
      qualityScore: 950,
      accessCount: 156,
      totalRevenue: 15600,
      royaltyRate: 500,
      isActive: true,
      createdAt: '2024-01-15T10:30:00Z',
      description: 'Advanced NLP knowledge graph with transformer architectures',
      metadata: '{"nodes": 1250, "edges": 3400, "domains": ["nlp", "ai"]}'
    },
    {
      graphId: 'graph_002',
      cid: 'QmYyy...456',
      creator: '0xabcd...efgh',
      price: 250,
      tags: ['computer-vision', 'cnn', 'image'],
      qualityScore: 890,
      accessCount: 89,
      totalRevenue: 22250,
      royaltyRate: 300,
      isActive: true,
      createdAt: '2024-01-20T14:15:00Z',
      description: 'Computer vision knowledge graph with CNN architectures',
      metadata: '{"nodes": 890, "edges": 2100, "domains": ["vision", "ml"]}'
    },
    {
      graphId: 'graph_003',
      cid: 'QmZzz...789',
      creator: '0x5678...9abc',
      price: 75,
      tags: ['reinforcement-learning', 'rl', 'gaming'],
      qualityScore: 920,
      accessCount: 234,
      totalRevenue: 17550,
      royaltyRate: 400,
      isActive: true,
      createdAt: '2024-01-25T09:45:00Z',
      description: 'Reinforcement learning knowledge graph for gaming AI',
      metadata: '{"nodes": 670, "edges": 1890, "domains": ["rl", "gaming"]}'
    }
  ];

  useEffect(() => {
    // Load mock data
    setTimeout(() => {
      setGraphs(mockGraphs);
      setFilteredGraphs(mockGraphs);
      setLoading(false);
    }, 1000);
  }, []);

  useEffect(() => {
    filterAndSortGraphs();
  }, [searchQuery, selectedTags, priceRange, sortBy, graphs]);

  const filterAndSortGraphs = () => {
    let filtered = graphs.filter(graph => {
      // Search query filter
      if (searchQuery) {
        const query = searchQuery.toLowerCase();
        const matchesSearch = 
          graph.description.toLowerCase().includes(query) ||
          graph.tags.some(tag => tag.toLowerCase().includes(query)) ||
          graph.creator.toLowerCase().includes(query);
        if (!matchesSearch) return false;
      }

      // Tags filter
      if (selectedTags.length > 0) {
        const hasSelectedTag = selectedTags.some(tag => graph.tags.includes(tag));
        if (!hasSelectedTag) return false;
      }

      // Price range filter
      if (graph.price < priceRange.min || graph.price > priceRange.max) {
        return false;
      }

      return true;
    });

    // Sort
    filtered.sort((a, b) => {
      switch (sortBy) {
        case 'quality':
          return b.qualityScore - a.qualityScore;
        case 'price_low':
          return a.price - b.price;
        case 'price_high':
          return b.price - a.price;
        case 'popularity':
          return b.accessCount - a.accessCount;
        case 'newest':
          return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
        default:
          return 0;
      }
    });

    setFilteredGraphs(filtered);
  };

  const handlePurchase = async (graph: KnowledgeGraph) => {
    if (!isConnected) {
      toast({
        title: "Wallet Not Connected",
        description: "Please connect your wallet to purchase knowledge graphs",
        variant: "destructive"
      });
      return;
    }

    try {
      // Simulate purchase process
      const purchaseRecord: PurchaseRecord = {
        graphId: graph.graphId,
        buyer: address || '',
        purchasedAt: new Date().toISOString(),
        expiresAt: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(), // 30 days
        decryptionKey: `key_${Math.random().toString(36).substr(2, 9)}`,
        isActive: true
      };

      setPurchasedGraphs([...purchasedGraphs, purchaseRecord]);

      toast({
        title: "Purchase Successful!",
        description: `You now have access to "${graph.description}"`,
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

  const hasPurchased = (graphId: string) => {
    return purchasedGraphs.some(record => 
      record.graphId === graphId && 
      record.isActive && 
      new Date(record.expiresAt) > new Date()
    );
  };

  const getQualityColor = (score: number) => {
    if (score >= 900) return 'bg-green-500';
    if (score >= 700) return 'bg-yellow-500';
    return 'bg-red-500';
  };

  const allTags = Array.from(new Set(graphs.flatMap(g => g.tags)));

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Knowledge Graph Marketplace</h1>
          <p className="text-muted-foreground mt-2">
            Discover and purchase high-quality knowledge graphs to enhance your AI agents
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <Badge variant="outline" className="flex items-center space-x-1">
            <Star className="w-4 h-4" />
            <span>{graphs.length} Graphs Available</span>
          </Badge>
          <Badge variant="outline" className="flex items-center space-x-1">
            <TrendingUp className="w-4 h-4" />
            <span>{graphs.reduce((sum, g) => sum + g.accessCount, 0)} Total Accesses</span>
          </Badge>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="browse">Browse Graphs</TabsTrigger>
          <TabsTrigger value="purchased">My Purchases</TabsTrigger>
          <TabsTrigger value="create">Create Graph</TabsTrigger>
        </TabsList>

        <TabsContent value="browse" className="space-y-6">
          {/* Search and Filters */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Search className="w-5 h-5" />
                <span>Search & Filter</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex space-x-4">
                <div className="flex-1">
                  <Input
                    placeholder="Search knowledge graphs..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full"
                  />
                </div>
                <Select value={sortBy} onValueChange={setSortBy}>
                  <SelectTrigger className="w-48">
                    <SelectValue placeholder="Sort by" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="quality">Quality Score</SelectItem>
                    <SelectItem value="price_low">Price: Low to High</SelectItem>
                    <SelectItem value="price_high">Price: High to Low</SelectItem>
                    <SelectItem value="popularity">Most Popular</SelectItem>
                    <SelectItem value="newest">Newest First</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex space-x-4">
                <div className="flex-1">
                  <label className="text-sm font-medium mb-2 block">Price Range (AITBC)</label>
                  <div className="flex space-x-2">
                    <Input
                      type="number"
                      placeholder="Min"
                      value={priceRange.min}
                      onChange={(e) => setPriceRange(prev => ({ ...prev, min: Number(e.target.value) }))}
                      className="w-24"
                    />
                    <Input
                      type="number"
                      placeholder="Max"
                      value={priceRange.max}
                      onChange={(e) => setPriceRange(prev => ({ ...prev, max: Number(e.target.value) }))}
                      className="w-24"
                    />
                  </div>
                </div>
                <div className="flex-1">
                  <label className="text-sm font-medium mb-2 block">Tags</label>
                  <div className="flex flex-wrap gap-2">
                    {allTags.map(tag => (
                      <Badge
                        key={tag}
                        variant={selectedTags.includes(tag) ? "default" : "outline"}
                        className="cursor-pointer"
                        onClick={() => {
                          setSelectedTags(prev => 
                            prev.includes(tag) 
                              ? prev.filter(t => t !== tag)
                              : [...prev, tag]
                          );
                        }}
                      >
                        {tag}
                      </Badge>
                    ))}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Graph Listings */}
          {loading ? (
            <div className="text-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
              <p className="mt-2 text-muted-foreground">Loading knowledge graphs...</p>
            </div>
          ) : filteredGraphs.length === 0 ? (
            <Alert>
              <XCircle className="h-4 w-4" />
              <AlertTitle>No graphs found</AlertTitle>
              <AlertDescription>
                Try adjusting your search criteria or filters to find knowledge graphs.
              </AlertDescription>
            </Alert>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {filteredGraphs.map((graph) => {
                const isPurchased = hasPurchased(graph.graphId);
                return (
                  <Card key={graph.graphId} className="relative">
                    <CardHeader>
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <CardTitle className="text-lg line-clamp-2">
                            {graph.description}
                          </CardTitle>
                          <CardDescription className="mt-1">
                            by {graph.creator.slice(0, 6)}...{graph.creator.slice(-4)}
                          </CardDescription>
                        </div>
                        <div className="flex items-center space-x-1">
                          <div className={`w-2 h-2 rounded-full ${getQualityColor(graph.qualityScore)}`}></div>
                          <span className="text-sm font-medium">{graph.qualityScore}</span>
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="flex flex-wrap gap-1">
                        {graph.tags.map(tag => (
                          <Badge key={tag} variant="secondary" className="text-xs">
                            {tag}
                          </Badge>
                        ))}
                      </div>
                      
                      <div className="grid grid-cols-2 gap-4 text-sm">
                        <div className="flex items-center space-x-1">
                          <ShoppingCart className="w-4 h-4 text-muted-foreground" />
                          <span>{graph.accessCount} accesses</span>
                        </div>
                        <div className="flex items-center space-x-1">
                          <TrendingUp className="w-4 h-4 text-muted-foreground" />
                          <span>{graph.totalRevenue} AITBC</span>
                        </div>
                      </div>

                      <div className="text-sm text-muted-foreground">
                        <div className="flex items-center space-x-1">
                          <Clock className="w-4 h-4" />
                          <span>Created {new Date(graph.createdAt).toLocaleDateString()}</span>
                        </div>
                      </div>
                    </CardContent>
                    <CardFooter className="flex items-center justify-between">
                      <div className="text-lg font-bold">
                        {graph.price} AITBC
                      </div>
                      {isPurchased ? (
                        <Button variant="outline" disabled className="flex items-center space-x-1">
                          <CheckCircle className="w-4 h-4" />
                          <span>Purchased</span>
                        </Button>
                      ) : (
                        <Button 
                          onClick={() => handlePurchase(graph)}
                          className="flex items-center space-x-1"
                        >
                          <ShoppingCart className="w-4 h-4" />
                          <span>Purchase</span>
                        </Button>
                      )}
                    </CardFooter>
                  </Card>
                );
              })}
            </div>
          )}
        </TabsContent>

        <TabsContent value="purchased" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>My Purchased Knowledge Graphs</CardTitle>
              <CardDescription>
                Knowledge graphs you have purchased and can access
              </CardDescription>
            </CardHeader>
            <CardContent>
              {purchasedGraphs.length === 0 ? (
                <div className="text-center py-8">
                  <ShoppingCart className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                  <p className="text-muted-foreground">No purchased knowledge graphs yet</p>
                  <Button 
                    className="mt-4"
                    onClick={() => setActiveTab('browse')}
                  >
                    Browse Marketplace
                  </Button>
                </div>
              ) : (
                <div className="space-y-4">
                  {purchasedGraphs.map((record) => {
                    const graph = graphs.find(g => g.graphId === record.graphId);
                    if (!graph) return null;
                    
                    return (
                      <Card key={record.graphId}>
                        <CardContent className="pt-6">
                          <div className="flex items-center justify-between">
                            <div>
                              <h4 className="font-semibold">{graph.description}</h4>
                              <p className="text-sm text-muted-foreground">
                                Purchased on {new Date(record.purchasedAt).toLocaleDateString()}
                              </p>
                              <p className="text-sm text-muted-foreground">
                                Expires on {new Date(record.expiresAt).toLocaleDateString()}
                              </p>
                            </div>
                            <div className="flex items-center space-x-2">
                              <Badge variant="outline">
                                {record.graphId}
                              </Badge>
                              <Button variant="outline" size="sm">
                                Download
                              </Button>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="create" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Create Knowledge Graph</CardTitle>
              <CardDescription>
                Upload and monetize your knowledge graphs on the marketplace
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Alert>
                <AlertTitle>Coming Soon</AlertTitle>
                <AlertDescription>
                  Knowledge graph creation tools will be available in the next update.
                </AlertDescription>
              </Alert>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default KnowledgeMarketplace;
