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
  Brain, 
  Zap, 
  Target, 
  Settings, 
  Play, 
  Pause, 
  RefreshCw, 
  Search, 
  Filter, 
  Plus, 
  Eye, 
  MoreHorizontal, 
  Clock, 
  Calendar, 
  Users, 
  Network, 
  Shield, 
  CheckCircle, 
  AlertCircle, 
  BarChart3, 
  Activity, 
  TrendingUp, 
  Award, 
  Star, 
  GitBranch, 
  Layers, 
  Cpu, 
  Battery, 
  Gauge, 
  LineChart, 
  PieChart, 
  ArrowRight, 
  ArrowUp, 
  ArrowDown, 
  ChevronRight, 
  ChevronDown, 
  Lightbulb, 
  Rocket, 
  BrainCircuit, 
  Sparkles, 
  ZapOff, 
  Power, 
  PowerOff, 
  Settings2, 
  Sliders, 
  ToggleLeft, 
  ToggleRight, 
  Lock, 
  Unlock, 
  Key, 
  EyeOff, 
  Volume2, 
  VolumeX, 
  Wifi, 
  WifiOff, 
  Database, 
  HardDrive, 
  MemoryStick, 
  Cloud, 
  Download, 
  Upload, 
  Copy, 
  Share2, 
  Trash2, 
  Edit, 
  Save, 
  FileText, 
  Folder, 
  FolderOpen, 
  Tag, 
  Hash, 
  AtSign
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { useWallet } from '@/hooks/use-wallet';

interface AutonomousAgent {
  id: string;
  name: string;
  type: 'trading' | 'research' | 'development' | 'analysis' | 'creative';
  status: 'active' | 'paused' | 'learning' | 'optimizing' | 'offline';
  autonomy: number; // 0-100
  performance: number; // 0-100
  efficiency: number; // 0-100
  goals: Array<{
    id: string;
    title: string;
    description: string;
    priority: 'low' | 'medium' | 'high' | 'critical';
    progress: number;
    status: 'pending' | 'in_progress' | 'completed' | 'failed';
    deadline?: string;
    createdAt: string;
    updatedAt: string;
  }>;
  capabilities: Array<{
    name: string;
    enabled: boolean;
    performance: number;
    lastUsed: string;
  }>;
  resources: {
    cpu: number;
    memory: number;
    storage: number;
    network: number;
    cost: number;
  };
  learning: {
    models: number;
    accuracy: number;
    trainingTime: number;
    lastUpdate: string;
  };
  metadata: {
    description: string;
    creator: string;
    createdAt: string;
    updatedAt: string;
    tags: string[];
  };
}

interface AutonomyStats {
  totalAgents: number;
  activeAgents: number;
  averageAutonomy: number;
  averagePerformance: number;
  totalGoals: number;
  completedGoals: number;
  successRate: number;
  totalCost: number;
  costSavings: number;
  agentsByType: Record<string, number>;
  performanceMetrics: {
    autonomy: number;
    performance: number;
    efficiency: number;
    reliability: number;
  };
  monthlyActivity: Array<{
    month: string;
    agents: number;
    goals: number;
    autonomy: number;
    performance: number;
  }>;
}

const AgentAutonomy: React.FC = () => {
  const { toast } = useToast();
  const { isConnected, address } = useWallet();
  
  const [activeTab, setActiveTab] = useState('agents');
  const [loading, setLoading] = useState(true);
  const [agents, setAgents] = useState<AutonomousAgent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<AutonomousAgent | null>(null);
  const [stats, setStats] = useState<AutonomyStats | null>(null);
  
  // Form states
  const [newAgentName, setNewAgentName] = useState('');
  const [newAgentType, setNewAgentType] = useState('trading');
  const [newAgentDescription, setNewAgentDescription] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');
  
  // Mock data
  const mockAgents: AutonomousAgent[] = [
    {
      id: 'agent_001',
      name: 'QuantumTrader Pro',
      type: 'trading',
      status: 'active',
      autonomy: 92,
      performance: 87,
      efficiency: 94,
      goals: [
        {
          id: 'goal_001',
          title: 'Maximize Trading Profits',
          description: 'Achieve 15% monthly return through automated trading',
          priority: 'high',
          progress: 78,
          status: 'in_progress',
          deadline: '2024-03-31T23:59:59Z',
          createdAt: '2024-02-01T00:00:00Z',
          updatedAt: '2024-02-27T10:15:00Z'
        },
        {
          id: 'goal_002',
          title: 'Risk Management',
          description: 'Maintain maximum drawdown below 5%',
          priority: 'critical',
          progress: 95,
          status: 'in_progress',
          deadline: '2024-02-28T23:59:59Z',
          createdAt: '2024-02-01T00:00:00Z',
          updatedAt: '2024-02-27T10:15:00Z'
        }
      ],
      capabilities: [
        { name: 'Market Analysis', enabled: true, performance: 89, lastUsed: '2024-02-27T09:30:00Z' },
        { name: 'Risk Assessment', enabled: true, performance: 94, lastUsed: '2024-02-27T09:45:00Z' },
        { name: 'Order Execution', enabled: true, performance: 92, lastUsed: '2024-02-27T10:00:00Z' }
      ],
      resources: {
        cpu: 75,
        memory: 68,
        storage: 45,
        network: 25,
        cost: 125.50
      },
      learning: {
        models: 3,
        accuracy: 87.5,
        trainingTime: 156,
        lastUpdate: '2024-02-27T08:00:00Z'
      },
      metadata: {
        description: 'Autonomous trading agent with advanced risk management',
        creator: address || '0x1234...5678',
        createdAt: '2024-02-01T00:00:00Z',
        updatedAt: '2024-02-27T10:15:00Z',
        tags: ['trading', 'autonomous', 'risk-management', 'profit-maximization']
      }
    },
    {
      id: 'agent_002',
      name: 'ResearchBot Alpha',
      type: 'research',
      status: 'learning',
      autonomy: 78,
      performance: 82,
      efficiency: 85,
      goals: [
        {
          id: 'goal_003',
          title: 'Data Collection',
          description: 'Collect and analyze 10GB of research data',
          priority: 'medium',
          progress: 65,
          status: 'in_progress',
          createdAt: '2024-02-15T00:00:00Z',
          updatedAt: '2024-02-27T14:30:00Z'
        }
      ],
      capabilities: [
        { name: 'Data Mining', enabled: true, performance: 85, lastUsed: '2024-02-27T14:00:00Z' },
        { name: 'Pattern Recognition', enabled: true, performance: 79, lastUsed: '2024-02-27T14:15:00Z' }
      ],
      resources: {
        cpu: 82,
        memory: 74,
        storage: 89,
        network: 67,
        cost: 89.25
      },
      learning: {
        models: 5,
        accuracy: 82.3,
        trainingTime: 234,
        lastUpdate: '2024-02-27T13:45:00Z'
      },
      metadata: {
        description: 'Research agent focused on data analysis and pattern discovery',
        creator: '0x8765...4321',
        createdAt: '2024-02-15T00:00:00Z',
        updatedAt: '2024-02-27T14:30:00Z',
        tags: ['research', 'data-analysis', 'pattern-recognition']
      }
    }
  ];
  
  const mockStats: AutonomyStats = {
    totalAgents: 8,
    activeAgents: 5,
    averageAutonomy: 85.2,
    averagePerformance: 83.7,
    totalGoals: 24,
    completedGoals: 18,
    successRate: 75.0,
    totalCost: 892.75,
    costSavings: 234.50,
    agentsByType: {
      trading: 3,
      research: 2,
      development: 1,
      analysis: 1,
      creative: 1
    },
    performanceMetrics: {
      autonomy: 85.2,
      performance: 83.7,
      efficiency: 87.9,
      reliability: 91.2
    },
    monthlyActivity: [
      { month: 'Jan', agents: 2, goals: 6, autonomy: 78.5, performance: 81.2 },
      { month: 'Feb', agents: 5, goals: 12, autonomy: 85.2, performance: 83.7 },
      { month: 'Mar', agents: 6, goals: 15, autonomy: 87.9, performance: 86.4 },
      { month: 'Apr', agents: 8, goals: 18, autonomy: 90.1, performance: 88.9 }
    ]
  };
  
  useEffect(() => {
    setTimeout(() => {
      setAgents(mockAgents);
      setStats(mockStats);
      setLoading(false);
    }, 1000);
  }, [address]);
  
  const handleCreateAgent = async () => {
    if (!isConnected) {
      toast({
        title: "Wallet Not Connected",
        description: "Please connect your wallet to create an agent",
        variant: "destructive"
      });
      return;
    }
    
    try {
      toast({
        title: "Creating Agent",
        description: "Setting up your autonomous agent...",
        variant: "default"
      });
      
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      const newAgent: AutonomousAgent = {
        id: `agent_${Date.now()}`,
        name: newAgentName,
        type: newAgentType as any,
        status: 'offline',
        autonomy: 0,
        performance: 0,
        efficiency: 0,
        goals: [],
        capabilities: [],
        resources: { cpu: 0, memory: 0, storage: 0, network: 0, cost: 0 },
        learning: { models: 0, accuracy: 0, trainingTime: 0, lastUpdate: '' },
        metadata: {
          description: newAgentDescription,
          creator: address || '0x1234...5678',
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          tags: []
        }
      };
      
      setAgents([newAgent, ...agents]);
      setNewAgentName('');
      setNewAgentType('trading');
      setNewAgentDescription('');
      
      toast({
        title: "Agent Created",
        description: "Your autonomous agent has been created successfully",
        variant: "default"
      });
    } catch (error) {
      toast({
        title: "Creation Failed",
        description: "There was an error creating your agent",
        variant: "destructive"
      });
    }
  };
  
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return 'bg-green-500';
      case 'learning': return 'bg-blue-500';
      case 'optimizing': return 'bg-purple-500';
      case 'paused': return 'bg-yellow-500';
      case 'offline': return 'bg-gray-500';
      default: return 'bg-gray-400';
    }
  };
  
  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'trading': return <TrendingUp className="w-4 h-4" />;
      case 'research': return <Brain className="w-4 h-4" />;
      case 'development': return <GitBranch className="w-4 h-4" />;
      case 'analysis': return <BarChart3 className="w-4 h-4" />;
      case 'creative': return <Sparkles className="w-4 h-4" />;
      default: return <Brain className="w-4 h-4" />;
    }
  };
  
  const getAutonomyColor = (value: number) => {
    if (value >= 80) return 'text-green-600';
    if (value >= 60) return 'text-blue-600';
    if (value >= 40) return 'text-yellow-600';
    return 'text-red-600';
  };
  
  const filteredAgents = agents.filter(agent => {
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      return agent.name.toLowerCase().includes(query) || 
             agent.metadata.description.toLowerCase().includes(query);
    }
    if (filterType !== 'all') return agent.type === filterType;
    if (filterStatus !== 'all') return agent.status === filterStatus;
    return true;
  });
  
  if (loading) {
    return (
      <div className="container mx-auto p-6 space-y-6">
        <div className="text-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
          <p className="mt-2 text-muted-foreground">Loading agent autonomy...</p>
        </div>
      </div>
    );
  }
  
  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Agent Autonomy</h1>
          <p className="text-muted-foreground mt-2">
            Self-improving agents with goal-setting and planning capabilities
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <Badge variant="outline" className="flex items-center space-x-1">
            <Brain className="w-4 h-4" />
            <span>{stats?.totalAgents} Agents</span>
          </Badge>
          <Badge variant="outline" className="flex items-center space-x-1">
            <Activity className="w-4 h-4" />
            <span>{stats?.activeAgents} Active</span>
          </Badge>
          <Badge variant="outline" className="flex items-center space-x-1">
            <Target className="w-4 h-4" />
            <span>{stats?.successRate}% Success Rate</span>
          </Badge>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="agents">Agents</TabsTrigger>
          <TabsTrigger value="goals">Goals</TabsTrigger>
          <TabsTrigger value="create">Create Agent</TabsTrigger>
          <TabsTrigger value="analytics">Analytics</TabsTrigger>
        </TabsList>

        <TabsContent value="agents" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Search className="w-5 h-5" />
                <span>Search & Filter</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Search</label>
                  <div className="relative">
                    <Search className="absolute left-3 top-3 w-4 h-4 text-muted-foreground" />
                    <Input
                      placeholder="Search agents..."
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
                      <SelectItem value="trading">Trading</SelectItem>
                      <SelectItem value="research">Research</SelectItem>
                      <SelectItem value="development">Development</SelectItem>
                      <SelectItem value="analysis">Analysis</SelectItem>
                      <SelectItem value="creative">Creative</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Status</label>
                  <Select value={filterStatus} onValueChange={setFilterStatus}>
                    <SelectTrigger>
                      <SelectValue placeholder="All statuses" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Statuses</SelectItem>
                      <SelectItem value="active">Active</SelectItem>
                      <SelectItem value="learning">Learning</SelectItem>
                      <SelectItem value="optimizing">Optimizing</SelectItem>
                      <SelectItem value="paused">Paused</SelectItem>
                      <SelectItem value="offline">Offline</SelectItem>
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

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {filteredAgents.map((agent) => (
              <Card key={agent.id} className="hover:shadow-lg transition-shadow">
                <CardHeader>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center space-x-2">
                      {getTypeIcon(agent.type)}
                      <Badge variant="outline">{agent.type}</Badge>
                      <Badge variant={agent.status === 'active' ? 'default' : 'secondary'}>
                        {agent.status}
                      </Badge>
                      <div className={`w-2 h-2 rounded-full ${getStatusColor(agent.status)}`}></div>
                    </div>
                    <Button variant="ghost" size="sm">
                      <MoreHorizontal className="w-4 h-4" />
                    </Button>
                  </div>
                  
                  <CardTitle className="text-lg">{agent.name}</CardTitle>
                  <CardDescription className="line-clamp-2">
                    {agent.metadata.description}
                  </CardDescription>
                </CardHeader>
                
                <CardContent>
                  <div className="space-y-4">
                    <div className="grid grid-cols-3 gap-4">
                      <div className="text-center">
                        <div className={`text-lg font-bold ${getAutonomyColor(agent.autonomy)}`}>
                          {agent.autonomy}%
                        </div>
                        <div className="text-xs text-muted-foreground">Autonomy</div>
                      </div>
                      <div className="text-center">
                        <div className={`text-lg font-bold ${getAutonomyColor(agent.performance)}`}>
                          {agent.performance}%
                        </div>
                        <div className="text-xs text-muted-foreground">Performance</div>
                      </div>
                      <div className="text-center">
                        <div className={`text-lg font-bold ${getAutonomyColor(agent.efficiency)}`}>
                          {agent.efficiency}%
                        </div>
                        <div className="text-xs text-muted-foreground">Efficiency</div>
                      </div>
                    </div>
                    
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium">Goals Progress</span>
                        <span className="text-sm text-muted-foreground">
                          {agent.goals.filter(g => g.status === 'completed').length}/{agent.goals.length}
                        </span>
                      </div>
                      <Progress 
                        value={(agent.goals.filter(g => g.status === 'completed').length / agent.goals.length) * 100} 
                        className="h-2" 
                      />
                    </div>
                    
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <span className="text-muted-foreground">Learning Models:</span>
                        <p className="font-medium">{agent.learning.models}</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Accuracy:</span>
                        <p className="font-medium">{agent.learning.accuracy}%</p>
                      </div>
                    </div>
                  </div>
                </CardContent>
                
                <CardFooter>
                  <div className="flex space-x-2 w-full">
                    <Button size="sm" className="flex-1">
                      <Eye className="w-4 h-4 mr-2" />
                      View Details
                    </Button>
                    <Button variant="outline" size="sm">
                      <Settings className="w-4 h-4 mr-2" />
                      Configure
                    </Button>
                  </div>
                </CardFooter>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="goals" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Target className="w-5 h-5" />
                <span>Agent Goals</span>
              </CardTitle>
              <CardDescription>
                Goals and objectives for autonomous agents
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {agents.flatMap(agent => 
                  agent.goals.map(goal => (
                    <div key={goal.id} className="p-4 border rounded-lg">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center space-x-2">
                          <div className={`w-3 h-3 rounded-full ${
                            goal.status === 'completed' ? 'bg-green-500' : 
                            goal.status === 'in_progress' ? 'bg-blue-500' : 'bg-gray-500'
                          }`}></div>
                          <span className="font-semibold">{goal.title}</span>
                          <Badge variant="outline">{goal.priority}</Badge>
                          <Badge variant={goal.status === 'completed' ? 'default' : 'secondary'}>
                            {goal.status}
                          </Badge>
                        </div>
                        <div className="flex items-center space-x-2">
                          <span className="text-sm text-muted-foreground">
                            {agent.name}
                          </span>
                          <Button variant="ghost" size="sm">
                            <MoreHorizontal className="w-4 h-4" />
                          </Button>
                        </div>
                      </div>
                      
                      <p className="text-sm text-muted-foreground mb-3">{goal.description}</p>
                      
                      <div className="space-y-2 mb-3">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-medium">Progress</span>
                          <span className="text-sm text-muted-foreground">{goal.progress}%</span>
                        </div>
                        <Progress value={goal.progress} className="h-2" />
                      </div>
                      
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                        <div>
                          <span className="text-muted-foreground">Created:</span>
                          <p className="font-medium">{new Date(goal.createdAt).toLocaleDateString()}</p>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Updated:</span>
                          <p className="font-medium">{new Date(goal.updatedAt).toLocaleDateString()}</p>
                        </div>
                        {goal.deadline && (
                          <div>
                            <span className="text-muted-foreground">Deadline:</span>
                            <p className="font-medium">{new Date(goal.deadline).toLocaleDateString()}</p>
                          </div>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="create" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Plus className="w-5 h-5" />
                <span>Create Autonomous Agent</span>
              </CardTitle>
              <CardDescription>
                Set up a new self-improving autonomous agent
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Agent Name</label>
                  <Input
                    placeholder="Enter agent name"
                    value={newAgentName}
                    onChange={(e) => setNewAgentName(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Agent Type</label>
                  <Select value={newAgentType} onValueChange={setNewAgentType}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="trading">Trading</SelectItem>
                      <SelectItem value="research">Research</SelectItem>
                      <SelectItem value="development">Development</SelectItem>
                      <SelectItem value="analysis">Analysis</SelectItem>
                      <SelectItem value="creative">Creative</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              
              <div className="space-y-2">
                <label className="text-sm font-medium">Description</label>
                <textarea
                  placeholder="Describe your agent's purpose and capabilities"
                  value={newAgentDescription}
                  onChange={(e) => setNewAgentDescription(e.target.value)}
                  className="w-full min-h-[100px] p-3 border rounded-md resize-none focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              
              <div className="space-y-2">
                <label className="text-sm font-medium">Initial Goals</label>
                <div className="space-y-2">
                  <Input placeholder="Goal 1: Primary objective" />
                  <Input placeholder="Goal 2: Secondary objective" />
                  <Input placeholder="Goal 3: Tertiary objective" />
                </div>
              </div>
              
              <div className="space-y-2">
                <label className="text-sm font-medium">Autonomy Level</label>
                <Select defaultValue="medium">
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="low">Low (20-40%)</SelectItem>
                    <SelectItem value="medium">Medium (40-70%)</SelectItem>
                    <SelectItem value="high">High (70-90%)</SelectItem>
                    <SelectItem value="full">Full (90-100%)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
            <CardFooter>
              <div className="flex space-x-2 w-full">
                <Button variant="outline" className="flex-1">
                  Save as Draft
                </Button>
                <Button onClick={handleCreateAgent} className="flex-1">
                  <Plus className="w-4 h-4 mr-2" />
                  Create Agent
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
                  <Brain className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Total Agents</span>
                </div>
                <div className="text-2xl font-bold">{stats?.totalAgents}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Autonomous agents
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <Activity className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Active Agents</span>
                </div>
                <div className="text-2xl font-bold">{stats?.activeAgents}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Currently running
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <Target className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Success Rate</span>
                </div>
                <div className="text-2xl font-bold">{stats?.successRate}%</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Goal completion
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <Gauge className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Avg Autonomy</span>
                </div>
                <div className="text-2xl font-bold">{stats?.averageAutonomy}%</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Self-governance level
                </p>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <PieChart className="w-5 h-5" />
                <span>Agents by Type</span>
              </CardTitle>
              <CardDescription>
                Distribution of autonomous agents by type
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {Object.entries(stats?.agentsByType || {}).map(([type, count]) => (
                  <div key={type} className="space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        {getTypeIcon(type)}
                        <span className="text-sm font-medium capitalize">{type}</span>
                      </div>
                      <span className="text-sm text-muted-foreground">{count} agents</span>
                    </div>
                    <Progress 
                      value={(count / stats!.totalAgents) * 100} 
                      className="h-2" 
                    />
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

export default AgentAutonomy;
