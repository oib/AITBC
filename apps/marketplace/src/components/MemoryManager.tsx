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
  Database, 
  Upload, 
  Download, 
  Search, 
  Filter, 
  Trash2, 
  Clock, 
  HardDrive,
  Brain,
  Zap,
  Shield,
  TrendingUp
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { useWallet } from '@/hooks/use-wallet';

interface MemoryRecord {
  cid: string;
  agentId: string;
  memoryType: string;
  priority: string;
  version: number;
  timestamp: string;
  size: number;
  tags: string[];
  accessCount: number;
  lastAccessed: string;
  expiresAt?: string;
  parentCid?: string;
  verified: boolean;
}

interface MemoryStats {
  totalMemories: number;
  totalSizeBytes: number;
  totalSizeMB: number;
  byType: Record<string, number>;
  byPriority: Record<string, number>;
  totalAccessCount: number;
  averageAccessCount: number;
  agentCount: number;
}

const MemoryManager: React.FC = () => {
  const { toast } = useToast();
  const { isConnected, address } = useWallet();
  
  const [memories, setMemories] = useState<MemoryRecord[]>([]);
  const [filteredMemories, setFilteredMemories] = useState<MemoryRecord[]>([]);
  const [stats, setStats] = useState<MemoryStats | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedType, setSelectedType] = useState('all');
  const [selectedPriority, setSelectedPriority] = useState('all');
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('memories');
  
  // Mock data for demonstration
  const mockMemories: MemoryRecord[] = [
    {
      cid: 'QmAbc123...',
      agentId: 'agent_001',
      memoryType: 'experience',
      priority: 'high',
      version: 3,
      timestamp: '2024-01-15T10:30:00Z',
      size: 2048576,
      tags: ['training', 'nlp', 'conversation'],
      accessCount: 45,
      lastAccessed: '2024-01-20T14:15:00Z',
      verified: true
    },
    {
      cid: 'QmDef456...',
      agentId: 'agent_001',
      memoryType: 'policy_weights',
      priority: 'critical',
      version: 7,
      timestamp: '2024-01-18T09:45:00Z',
      size: 1048576,
      tags: ['model', 'weights', 'reinforcement'],
      accessCount: 128,
      lastAccessed: '2024-01-22T16:30:00Z',
      verified: true
    },
    {
      cid: 'QmGhi789...',
      agentId: 'agent_002',
      memoryType: 'knowledge_graph',
      priority: 'medium',
      version: 1,
      timestamp: '2024-01-20T11:20:00Z',
      size: 5242880,
      tags: ['knowledge', 'graph', 'vision'],
      accessCount: 23,
      lastAccessed: '2024-01-21T13:45:00Z',
      verified: false
    },
    {
      cid: 'QmJkl012...',
      agentId: 'agent_002',
      memoryType: 'training_data',
      priority: 'low',
      version: 2,
      timestamp: '2024-01-22T08:15:00Z',
      size: 10485760,
      tags: ['data', 'images', 'classification'],
      accessCount: 8,
      lastAccessed: '2024-01-22T08:15:00Z',
      expiresAt: '2024-02-22T08:15:00Z',
      verified: true
    }
  ];

  const mockStats: MemoryStats = {
    totalMemories: 4,
    totalSizeBytes: 18874368,
    totalSizeMB: 18.0,
    byType: {
      'experience': 1,
      'policy_weights': 1,
      'knowledge_graph': 1,
      'training_data': 1
    },
    byPriority: {
      'critical': 1,
      'high': 1,
      'medium': 1,
      'low': 1
    },
    totalAccessCount: 204,
    averageAccessCount: 51,
    agentCount: 2
  };

  useEffect(() => {
    // Load mock data
    setTimeout(() => {
      setMemories(mockMemories);
      setFilteredMemories(mockMemories);
      setStats(mockStats);
      setLoading(false);
    }, 1000);
  }, []);

  useEffect(() => {
    filterMemories();
  }, [searchQuery, selectedType, selectedPriority, memories]);

  const filterMemories = () => {
    let filtered = memories.filter(memory => {
      // Search query filter
      if (searchQuery) {
        const query = searchQuery.toLowerCase();
        const matchesSearch = 
          memory.cid.toLowerCase().includes(query) ||
          memory.memoryType.toLowerCase().includes(query) ||
          memory.tags.some(tag => tag.toLowerCase().includes(query)) ||
          memory.agentId.toLowerCase().includes(query);
        if (!matchesSearch) return false;
      }

      // Type filter
      if (selectedType !== 'all' && memory.memoryType !== selectedType) {
        return false;
      }

      // Priority filter
      if (selectedPriority !== 'all' && memory.priority !== selectedPriority) {
        return false;
      }

      return true;
    });

    setFilteredMemories(filtered);
  };

  const handleDownload = async (memory: MemoryRecord) => {
    if (!isConnected) {
      toast({
        title: "Wallet Not Connected",
        description: "Please connect your wallet to download memories",
        variant: "destructive"
      });
      return;
    }

    try {
      // Simulate download process
      toast({
        title: "Download Started",
        description: `Downloading memory ${memory.cid}...`,
        variant: "default"
      });

      // Simulate download completion
      setTimeout(() => {
        toast({
          title: "Download Complete",
          description: `Memory ${memory.cid} downloaded successfully`,
          variant: "default"
        });
      }, 2000);
    } catch (error) {
      toast({
        title: "Download Failed",
        description: "There was an error downloading the memory",
        variant: "destructive"
      });
    }
  };

  const handleDelete = async (memory: MemoryRecord) => {
    if (!isConnected) {
      toast({
        title: "Wallet Not Connected",
        description: "Please connect your wallet to delete memories",
        variant: "destructive"
      });
      return;
    }

    try {
      // Remove from local state
      setMemories(prev => prev.filter(m => m.cid !== memory.cid));
      
      toast({
        title: "Memory Deleted",
        description: `Memory ${memory.cid} has been deleted`,
        variant: "default"
      });
    } catch (error) {
      toast({
        title: "Delete Failed",
        description: "There was an error deleting the memory",
        variant: "destructive"
      });
    }
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'critical': return 'bg-red-500';
      case 'high': return 'bg-orange-500';
      case 'medium': return 'bg-yellow-500';
      case 'low': return 'bg-green-500';
      default: return 'bg-gray-500';
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'experience': return <Brain className="w-4 h-4" />;
      case 'policy_weights': return <Zap className="w-4 h-4" />;
      case 'knowledge_graph': return <Database className="w-4 h-4" />;
      case 'training_data': return <HardDrive className="w-4 h-4" />;
      default: return <Database className="w-4 h-4" />;
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const memoryTypes = Array.from(new Set(memories.map(m => m.memoryType)));
  const priorities = ['critical', 'high', 'medium', 'low'];

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Memory Manager</h1>
          <p className="text-muted-foreground mt-2">
            Manage and monitor your agent's persistent memory storage
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <Badge variant="outline" className="flex items-center space-x-1">
            <Database className="w-4 h-4" />
            <span>{stats?.totalMemories || 0} Memories</span>
          </Badge>
          <Badge variant="outline" className="flex items-center space-x-1">
            <HardDrive className="w-4 h-4" />
            <span>{stats?.totalSizeMB.toFixed(1) || 0} MB</span>
          </Badge>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="memories">Memories</TabsTrigger>
          <TabsTrigger value="statistics">Statistics</TabsTrigger>
          <TabsTrigger value="settings">Settings</TabsTrigger>
        </TabsList>

        <TabsContent value="memories" className="space-y-6">
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
                    placeholder="Search memories by CID, type, tags..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full"
                  />
                </div>
                <Select value={selectedType} onValueChange={setSelectedType}>
                  <SelectTrigger className="w-40">
                    <SelectValue placeholder="Type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Types</SelectItem>
                    {memoryTypes.map(type => (
                      <SelectItem key={type} value={type}>
                        <div className="flex items-center space-x-2">
                          {getTypeIcon(type)}
                          <span>{type.replace('_', ' ')}</span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={selectedPriority} onValueChange={setSelectedPriority}>
                  <SelectTrigger className="w-32">
                    <SelectValue placeholder="Priority" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Priorities</SelectItem>
                    {priorities.map(priority => (
                      <SelectItem key={priority} value={priority}>
                        <div className="flex items-center space-x-2">
                          <div className={`w-2 h-2 rounded-full ${getPriorityColor(priority)}`}></div>
                          <span>{priority.charAt(0).toUpperCase() + priority.slice(1)}</span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          {/* Memory List */}
          {loading ? (
            <div className="text-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
              <p className="mt-2 text-muted-foreground">Loading memories...</p>
            </div>
          ) : filteredMemories.length === 0 ? (
            <Alert>
              <Database className="h-4 w-4" />
              <AlertTitle>No memories found</AlertTitle>
              <AlertDescription>
                Try adjusting your search criteria or filters to find memories.
              </AlertDescription>
            </Alert>
          ) : (
            <div className="space-y-4">
              {filteredMemories.map((memory) => (
                <Card key={memory.cid}>
                  <CardContent className="pt-6">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center space-x-3 mb-2">
                          {getTypeIcon(memory.memoryType)}
                          <h4 className="font-semibold">{memory.cid}</h4>
                          <Badge variant="outline">{memory.memoryType.replace('_', ' ')}</Badge>
                          <div className={`w-2 h-2 rounded-full ${getPriorityColor(memory.priority)}`}></div>
                          <span className="text-sm text-muted-foreground capitalize">
                            {memory.priority} priority
                          </span>
                          {memory.verified && (
                            <Shield className="w-4 h-4 text-green-500" />
                          )}
                        </div>
                        
                        <div className="flex flex-wrap gap-1 mb-3">
                          {memory.tags.map(tag => (
                            <Badge key={tag} variant="secondary" className="text-xs">
                              {tag}
                            </Badge>
                          ))}
                        </div>
                        
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm text-muted-foreground">
                          <div className="flex items-center space-x-1">
                            <HardDrive className="w-4 h-4" />
                            <span>{formatSize(memory.size)}</span>
                          </div>
                          <div className="flex items-center space-x-1">
                            <TrendingUp className="w-4 h-4" />
                            <span>{memory.accessCount} accesses</span>
                          </div>
                          <div className="flex items-center space-x-1">
                            <Clock className="w-4 h-4" />
                            <span>Version {memory.version}</span>
                          </div>
                          <div className="flex items-center space-x-1">
                            <Database className="w-4 h-4" />
                            <span>{memory.agentId}</span>
                          </div>
                        </div>
                        
                        <div className="text-sm text-muted-foreground mt-2">
                          Created: {new Date(memory.timestamp).toLocaleDateString()}
                          {memory.lastAccessed !== memory.timestamp && (
                            <> • Last accessed: {new Date(memory.lastAccessed).toLocaleDateString()}</>
                          )}
                          {memory.expiresAt && (
                            <> • Expires: {new Date(memory.expiresAt).toLocaleDateString()}</>
                          )}
                        </div>
                      </div>
                      
                      <div className="flex items-center space-x-2 ml-4">
                        <Button 
                          variant="outline" 
                          size="sm"
                          onClick={() => handleDownload(memory)}
                          className="flex items-center space-x-1"
                        >
                          <Download className="w-4 h-4" />
                          <span>Download</span>
                        </Button>
                        <Button 
                          variant="outline" 
                          size="sm"
                          onClick={() => handleDelete(memory)}
                          className="flex items-center space-x-1 text-red-600 hover:text-red-700"
                        >
                          <Trash2 className="w-4 h-4" />
                          <span>Delete</span>
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="statistics" className="space-y-6">
          {stats ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2">
                    <Database className="w-5 h-5" />
                    <span>Storage Overview</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex justify-between">
                    <span>Total Memories</span>
                    <span className="font-semibold">{stats.totalMemories}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Total Size</span>
                    <span className="font-semibold">{stats.totalSizeMB.toFixed(1)} MB</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Agent Count</span>
                    <span className="font-semibold">{stats.agentCount}</span>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2">
                    <TrendingUp className="w-5 h-5" />
                    <span>Access Statistics</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex justify-between">
                    <span>Total Accesses</span>
                    <span className="font-semibold">{stats.totalAccessCount}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Average Accesses</span>
                    <span className="font-semibold">{stats.averageAccessCount.toFixed(1)}</span>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Memory Types</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {Object.entries(stats.byType).map(([type, count]) => (
                    <div key={type} className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        {getTypeIcon(type)}
                        <span className="capitalize">{type.replace('_', ' ')}</span>
                      </div>
                      <Badge variant="outline">{count}</Badge>
                    </div>
                  ))}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Priority Distribution</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {Object.entries(stats.byPriority).map(([priority, count]) => (
                    <div key={priority} className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <div className={`w-2 h-2 rounded-full ${getPriorityColor(priority)}`}></div>
                        <span className="capitalize">{priority}</span>
                      </div>
                      <Badge variant="outline">{count}</Badge>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </div>
          ) : (
            <div className="text-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
              <p className="mt-2 text-muted-foreground">Loading statistics...</p>
            </div>
          )}
        </TabsContent>

        <TabsContent value="settings" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Memory Settings</CardTitle>
              <CardDescription>
                Configure memory management settings and preferences
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Alert>
                <AlertTitle>Coming Soon</AlertTitle>
                <AlertDescription>
                  Memory management settings will be available in the next update.
                </AlertDescription>
              </Alert>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default MemoryManager;
