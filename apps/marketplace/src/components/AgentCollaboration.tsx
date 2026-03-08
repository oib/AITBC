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
  Users, 
  Plus, 
  Settings, 
  Play, 
  Pause, 
  CheckCircle, 
  XCircle, 
  AlertCircle, 
  Clock, 
  Target, 
  Zap, 
  Activity, 
  BarChart3, 
  TrendingUp, 
  Award, 
  Star, 
  MessageSquare, 
  Lock, 
  Unlock, 
  Eye, 
  EyeOff, 
  Copy, 
  Share2, 
  Download, 
  Upload, 
  RefreshCw, 
  Filter, 
  Search, 
  MoreHorizontal, 
  User, 
  Globe, 
  Network, 
  GitBranch, 
  Layers, 
  Boxes, 
  ArrowRight, 
  ArrowLeft, 
  ArrowUp, 
  ArrowDown, 
  Link2, 
  Unlink, 
  Handshake, 
  Briefcase, 
  DollarSign, 
  Timer, 
  Calendar, 
  Tag, 
  Hash, 
  AtSign,
  FileText,
  Folder,
  FolderOpen,
  Database,
  Cloud,
  Shield,
  Key,
  Check,
  X,
  CheckSquare
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { useWallet } from '@/hooks/use-wallet';

interface CollaborationProject {
  id: string;
  name: string;
  description: string;
  status: 'planning' | 'active' | 'paused' | 'completed' | 'cancelled';
  priority: 'low' | 'normal' | 'high' | 'critical';
  category: 'research' | 'development' | 'trading' | 'analysis' | 'creative';
  creator: string;
  participants: Array<{
    address: string;
    name: string;
    role: 'leader' | 'contributor' | 'reviewer' | 'observer';
    reputation: number;
    avatar?: string;
    status: 'online' | 'offline' | 'busy';
    joinedAt: string;
  }>;
  tasks: Array<{
    id: string;
    title: string;
    description: string;
    status: 'todo' | 'in_progress' | 'review' | 'completed' | 'blocked';
    assignee?: string;
    priority: 'low' | 'normal' | 'high' | 'critical';
    estimatedTime: number;
    actualTime?: number;
    dependencies: string[];
    createdAt: string;
    updatedAt: string;
  }>;
  resources: Array<{
    type: 'data' | 'model' | 'compute' | 'storage' | 'funds';
    name: string;
    amount: number;
    unit: string;
    provider: string;
    allocated: boolean;
  }>;
  timeline: {
    startDate: string;
    endDate: string;
    milestones: Array<{
      id: string;
      title: string;
      description: string;
      dueDate: string;
      completed: boolean;
      completedAt?: string;
    }>;
  };
  budget: {
    total: number;
    allocated: number;
    spent: number;
    currency: string;
  };
  metrics: {
    progress: number;
    efficiency: number;
    quality: number;
    collaboration: number;
  };
  createdAt: string;
  updatedAt: string;
}

interface CollaborationStats {
  totalProjects: number;
  activeProjects: number;
  completedProjects: number;
  totalParticipants: number;
  averageTeamSize: number;
  successRate: number;
  averageDuration: number;
  totalBudget: number;
  budgetUtilization: number;
  projectsByCategory: Record<string, number>;
  monthlyActivity: Array<{
    month: string;
    projects: number;
    participants: number;
    budget: number;
  }>;
}

const AgentCollaboration: React.FC = () => {
  const { toast } = useToast();
  const { isConnected, address } = useWallet();
  
  const [activeTab, setActiveTab] = useState('projects');
  const [loading, setLoading] = useState(true);
  const [projects, setProjects] = useState<CollaborationProject[]>([]);
  const [selectedProject, setSelectedProject] = useState<CollaborationProject | null>(null);
  const [stats, setStats] = useState<CollaborationStats | null>(null);
  
  // Form states
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectDescription, setNewProjectDescription] = useState('');
  const [newProjectCategory, setNewProjectCategory] = useState('development');
  const [newProjectPriority, setNewProjectPriority] = useState('normal');
  const [searchQuery, setSearchQuery] = useState('');
  const [filterCategory, setFilterCategory] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');
  
  // Mock data for demonstration
  const mockProjects: CollaborationProject[] = [
    {
      id: 'proj_001',
      name: 'AI-Powered Trading Bot',
      description: 'Develop an autonomous trading bot using advanced machine learning algorithms for cryptocurrency markets',
      status: 'active',
      priority: 'high',
      category: 'trading',
      creator: address || '0x1234...5678',
      participants: [
        {
          address: address || '0x1234...5678',
          name: 'You',
          role: 'leader',
          reputation: 8500,
          avatar: '👤',
          status: 'online',
          joinedAt: '2024-02-20T00:00:00Z'
        },
        {
          address: '0x8765...4321',
          name: 'QuantumTrader',
          role: 'contributor',
          reputation: 9200,
          avatar: '🤖',
          status: 'online',
          joinedAt: '2024-02-20T01:00:00Z'
        },
        {
          address: '0x9876...5432',
          name: 'DataScientist',
          role: 'contributor',
          reputation: 7800,
          avatar: '📊',
          status: 'busy',
          joinedAt: '2024-02-20T02:00:00Z'
        }
      ],
      tasks: [
        {
          id: 'task_001',
          title: 'Design Trading Algorithm',
          description: 'Create the core trading algorithm architecture',
          status: 'completed',
          assignee: '0x8765...4321',
          priority: 'high',
          estimatedTime: 8,
          actualTime: 6,
          dependencies: [],
          createdAt: '2024-02-20T00:00:00Z',
          updatedAt: '2024-02-22T14:30:00Z'
        },
        {
          id: 'task_002',
          title: 'Implement Risk Management',
          description: 'Develop risk assessment and management system',
          status: 'in_progress',
          assignee: '0x9876...5432',
          priority: 'high',
          estimatedTime: 12,
          dependencies: ['task_001'],
          createdAt: '2024-02-21T00:00:00Z',
          updatedAt: '2024-02-27T10:15:00Z'
        },
        {
          id: 'task_003',
          title: 'Backtesting Framework',
          description: 'Create comprehensive backtesting system',
          status: 'todo',
          priority: 'normal',
          estimatedTime: 16,
          dependencies: ['task_001', 'task_002'],
          createdAt: '2024-02-22T00:00:00Z',
          updatedAt: '2024-02-22T00:00:00Z'
        }
      ],
      resources: [
        {
          type: 'compute',
          name: 'GPU Computing Power',
          amount: 100,
          unit: 'hours',
          provider: 'CloudCompute',
          allocated: true
        },
        {
          type: 'data',
          name: 'Market Data Feed',
          amount: 1000,
          unit: 'GB',
          provider: 'DataHub',
          allocated: true
        },
        {
          type: 'funds',
          name: 'Development Budget',
          amount: 5000,
          unit: 'USD',
          provider: 'Project Treasury',
          allocated: false
        }
      ],
      timeline: {
        startDate: '2024-02-20T00:00:00Z',
        endDate: '2024-03-20T00:00:00Z',
        milestones: [
          {
            id: 'milestone_001',
            title: 'Algorithm Design Complete',
            description: 'Core trading algorithm designed and approved',
            dueDate: '2024-02-25T00:00:00Z',
            completed: true,
            completedAt: '2024-02-22T14:30:00Z'
          },
          {
            id: 'milestone_002',
            title: 'Risk Management Implementation',
            description: 'Risk management system fully implemented',
            dueDate: '2024-03-05T00:00:00Z',
            completed: false
          },
          {
            id: 'milestone_003',
            title: 'Beta Testing',
            description: 'Initial beta testing with paper trading',
            dueDate: '2024-03-15T00:00:00Z',
            completed: false
          }
        ]
      },
      budget: {
        total: 10000,
        allocated: 7500,
        spent: 3200,
        currency: 'USD'
      },
      metrics: {
        progress: 45,
        efficiency: 87,
        quality: 92,
        collaboration: 95
      },
      createdAt: '2024-02-20T00:00:00Z',
      updatedAt: '2024-02-27T10:15:00Z'
    },
    {
      id: 'proj_002',
      name: 'Medical Image Analysis',
      description: 'Research project for AI-powered medical image analysis and diagnosis assistance',
      status: 'active',
      priority: 'critical',
      category: 'research',
      creator: '0x5432...6789',
      participants: [
        {
          address: '0x5432...6789',
          name: 'MedAI Researcher',
          role: 'leader',
          reputation: 9500,
          avatar: '🏥',
          status: 'online',
          joinedAt: '2024-02-15T00:00:00Z'
        },
        {
          address: address || '0x1234...5678',
          name: 'You',
          role: 'contributor',
          reputation: 8500,
          avatar: '👤',
          status: 'online',
          joinedAt: '2024-02-16T00:00:00Z'
        }
      ],
      tasks: [
        {
          id: 'task_004',
          title: 'Dataset Preparation',
          description: 'Prepare and preprocess medical imaging dataset',
          status: 'completed',
          assignee: address || '0x1234...5678',
          priority: 'critical',
          estimatedTime: 24,
          actualTime: 20,
          dependencies: [],
          createdAt: '2024-02-16T00:00:00Z',
          updatedAt: '2024-02-24T16:45:00Z'
        }
      ],
      resources: [
        {
          type: 'storage',
          name: 'Medical Data Storage',
          amount: 500,
          unit: 'GB',
          provider: 'SecureStorage',
          allocated: true
        }
      ],
      timeline: {
        startDate: '2024-02-15T00:00:00Z',
        endDate: '2024-04-15T00:00:00Z',
        milestones: [
          {
            id: 'milestone_004',
            title: 'Dataset Ready',
            description: 'Medical imaging dataset prepared and validated',
            dueDate: '2024-02-25T00:00:00Z',
            completed: true,
            completedAt: '2024-02-24T16:45:00Z'
          }
        ]
      },
      budget: {
        total: 15000,
        allocated: 12000,
        spent: 5800,
        currency: 'USD'
      },
      metrics: {
        progress: 25,
        efficiency: 83,
        quality: 88,
        collaboration: 91
      },
      createdAt: '2024-02-15T00:00:00Z',
      updatedAt: '2024-02-24T16:45:00Z'
    }
  ];
  
  const mockStats: CollaborationStats = {
    totalProjects: 12,
    activeProjects: 5,
    completedProjects: 6,
    totalParticipants: 28,
    averageTeamSize: 3.5,
    successRate: 85.7,
    averageDuration: 21,
    totalBudget: 125000,
    budgetUtilization: 73.4,
    projectsByCategory: {
      research: 3,
      development: 4,
      trading: 2,
      analysis: 2,
      creative: 1
    },
    monthlyActivity: [
      { month: 'Jan', projects: 2, participants: 8, budget: 15000 },
      { month: 'Feb', projects: 5, participants: 18, budget: 35000 },
      { month: 'Mar', projects: 3, participants: 12, budget: 25000 },
      { month: 'Apr', projects: 2, participants: 10, budget: 20000 }
    ]
  };
  
  useEffect(() => {
    // Load mock data
    setTimeout(() => {
      setProjects(mockProjects);
      setStats(mockStats);
      setLoading(false);
    }, 1000);
  }, [address]);
  
  const handleCreateProject = async () => {
    if (!isConnected) {
      toast({
        title: "Wallet Not Connected",
        description: "Please connect your wallet to create a project",
        variant: "destructive"
      });
      return;
    }
    
    if (!newProjectName.trim() || !newProjectDescription.trim()) {
      toast({
        title: "Invalid Input",
        description: "Please enter project name and description",
        variant: "destructive"
      });
      return;
    }
    
    try {
      toast({
        title: "Creating Project",
        description: "Setting up your collaboration project...",
        variant: "default"
      });
      
      // Simulate project creation
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      const newProject: CollaborationProject = {
        id: `proj_${Date.now()}`,
        name: newProjectName,
        description: newProjectDescription,
        status: 'planning',
        priority: newProjectPriority as any,
        category: newProjectCategory as any,
        creator: address || '0x1234...5678',
        participants: [
          {
            address: address || '0x1234...5678',
            name: 'You',
            role: 'leader',
            reputation: 8500,
            avatar: '👤',
            status: 'online',
            joinedAt: new Date().toISOString()
          }
        ],
        tasks: [],
        resources: [],
        timeline: {
          startDate: new Date().toISOString(),
          endDate: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
          milestones: []
        },
        budget: {
          total: 0,
          allocated: 0,
          spent: 0,
          currency: 'USD'
        },
        metrics: {
          progress: 0,
          efficiency: 100,
          quality: 100,
          collaboration: 100
        },
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      };
      
      setProjects([newProject, ...projects]);
      
      // Reset form
      setNewProjectName('');
      setNewProjectDescription('');
      setNewProjectCategory('development');
      setNewProjectPriority('normal');
      
      toast({
        title: "Project Created",
        description: "Your collaboration project has been created successfully",
        variant: "default"
      });
    } catch (error) {
      toast({
        title: "Creation Failed",
        description: "There was an error creating your project",
        variant: "destructive"
      });
    }
  };
  
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return 'bg-green-500';
      case 'planning': return 'bg-blue-500';
      case 'paused': return 'bg-yellow-500';
      case 'completed': return 'bg-purple-500';
      case 'cancelled': return 'bg-red-500';
      default: return 'bg-gray-400';
    }
  };
  
  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'critical': return 'bg-red-500';
      case 'high': return 'bg-orange-500';
      case 'normal': return 'bg-blue-500';
      case 'low': return 'bg-gray-500';
      default: return 'bg-gray-400';
    }
  };
  
  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'research': return <Database className="w-4 h-4" />;
      case 'development': return <GitBranch className="w-4 h-4" />;
      case 'trading': return <BarChart3 className="w-4 h-4" />;
      case 'analysis': return <Target className="w-4 h-4" />;
      case 'creative': return <Star className="w-4 h-4" />;
      default: return <Folder className="w-4 h-4" />;
    }
  };
  
  const getRoleIcon = (role: string) => {
    switch (role) {
      case 'leader': return <Award className="w-4 h-4" />;
      case 'contributor': return <Users className="w-4 h-4" />;
      case 'reviewer': return <Eye className="w-4 h-4" />;
      case 'observer': return <EyeOff className="w-4 h-4" />;
      default: return <User className="w-4 h-4" />;
    }
  };
  
  const filteredProjects = projects.filter(project => {
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      return project.name.toLowerCase().includes(query) || 
             project.description.toLowerCase().includes(query);
    }
    if (filterCategory !== 'all') {
      return project.category === filterCategory;
    }
    if (filterStatus !== 'all') {
      return project.status === filterStatus;
    }
    return true;
  });
  
  if (loading) {
    return (
      <div className="container mx-auto p-6 space-y-6">
        <div className="text-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
          <p className="mt-2 text-muted-foreground">Loading agent collaboration...</p>
        </div>
      </div>
    );
  }
  
  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Agent Collaboration</h1>
          <p className="text-muted-foreground mt-2">
            Joint task execution and collaborative project management
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <Badge variant="outline" className="flex items-center space-x-1">
            <Users className="w-4 h-4" />
            <span>{stats?.totalProjects} Projects</span>
          </Badge>
          <Badge variant="outline" className="flex items-center space-x-1">
            <Activity className="w-4 h-4" />
            <span>{stats?.activeProjects} Active</span>
          </Badge>
          <Badge variant="outline" className="flex items-center space-x-1">
            <Handshake className="w-4 h-4" />
            <span>{stats?.totalParticipants} Participants</span>
          </Badge>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="projects">Projects</TabsTrigger>
          <TabsTrigger value="tasks">Tasks</TabsTrigger>
          <TabsTrigger value="create">Create</TabsTrigger>
          <TabsTrigger value="analytics">Analytics</TabsTrigger>
        </TabsList>

        <TabsContent value="projects" className="space-y-6">
          {/* Search and Filters */}
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
                      placeholder="Search projects..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="pl-10"
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Category</label>
                  <Select value={filterCategory} onValueChange={setFilterCategory}>
                    <SelectTrigger>
                      <SelectValue placeholder="All categories" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Categories</SelectItem>
                      <SelectItem value="research">Research</SelectItem>
                      <SelectItem value="development">Development</SelectItem>
                      <SelectItem value="trading">Trading</SelectItem>
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
                      <SelectItem value="planning">Planning</SelectItem>
                      <SelectItem value="active">Active</SelectItem>
                      <SelectItem value="paused">Paused</SelectItem>
                      <SelectItem value="completed">Completed</SelectItem>
                      <SelectItem value="cancelled">Cancelled</SelectItem>
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

          {/* Projects Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {filteredProjects.map((project) => (
              <Card key={project.id} className="hover:shadow-lg transition-shadow">
                <CardHeader>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center space-x-2">
                      {getCategoryIcon(project.category)}
                      <Badge variant="outline">{project.category}</Badge>
                      <Badge variant={project.status === 'active' ? 'default' : 'secondary'}>
                        {project.status}
                      </Badge>
                      <div className={`w-2 h-2 rounded-full ${getPriorityColor(project.priority)}`}></div>
                    </div>
                    <Button variant="ghost" size="sm">
                      <MoreHorizontal className="w-4 h-4" />
                    </Button>
                  </div>
                  
                  <CardTitle className="text-lg">{project.name}</CardTitle>
                  <CardDescription className="line-clamp-2">
                    {project.description}
                  </CardDescription>
                </CardHeader>
                
                <CardContent>
                  <div className="space-y-4">
                    {/* Participants */}
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">Team</span>
                      <div className="flex -space-x-2">
                        {project.participants.slice(0, 4).map((participant, index) => (
                          <div
                            key={index}
                            className="w-6 h-6 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs font-medium border-2 border-background"
                            title={participant.name}
                          >
                            {participant.avatar || participant.name.charAt(0).toUpperCase()}
                          </div>
                        ))}
                        {project.participants.length > 4 && (
                          <div className="w-6 h-6 rounded-full bg-muted text-muted-foreground flex items-center justify-center text-xs font-medium border-2 border-background">
                            +{project.participants.length - 4}
                          </div>
                        )}
                      </div>
                    </div>
                    
                    {/* Progress */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium">Progress</span>
                        <span className="text-sm text-muted-foreground">{project.metrics.progress}%</span>
                      </div>
                      <Progress value={project.metrics.progress} className="h-2" />
                    </div>
                    
                    {/* Budget */}
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">Budget</span>
                      <span className="text-sm text-muted-foreground">
                        ${project.budget.spent.toLocaleString()} / ${project.budget.total.toLocaleString()}
                      </span>
                    </div>
                    
                    {/* Timeline */}
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">Timeline</span>
                      <span className="text-sm text-muted-foreground">
                        {new Date(project.timeline.startDate).toLocaleDateString()} - {new Date(project.timeline.endDate).toLocaleDateString()}
                      </span>
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
                      <Users className="w-4 h-4 mr-2" />
                      Join
                    </Button>
                  </div>
                </CardFooter>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="tasks" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <CheckSquare className="w-5 h-5" />
                <span>Task Overview</span>
              </CardTitle>
              <CardDescription>
                All tasks across your collaborative projects
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {projects.flatMap(project => 
                  project.tasks.map(task => (
                    <div key={task.id} className="p-4 border rounded-lg">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center space-x-2">
                          <div className={`w-3 h-3 rounded-full ${getPriorityColor(task.priority)}`}></div>
                          <span className="font-semibold">{task.title}</span>
                          <Badge variant="outline">{task.status}</Badge>
                        </div>
                        <div className="flex items-center space-x-2">
                          <span className="text-sm text-muted-foreground">
                            {project.name}
                          </span>
                          <Button variant="ghost" size="sm">
                            <MoreHorizontal className="w-4 h-4" />
                          </Button>
                        </div>
                      </div>
                      
                      <p className="text-sm text-muted-foreground mb-3">{task.description}</p>
                      
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                        <div>
                          <span className="text-muted-foreground">Assignee:</span>
                          <p className="font-medium">
                            {task.assignee ? project.participants.find(p => p.address === task.assignee)?.name : 'Unassigned'}
                          </p>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Time:</span>
                          <p className="font-medium">
                            {task.actualTime ? `${task.actualTime}h (est: ${task.estimatedTime}h)` : `${task.estimatedTime}h estimated`}
                          </p>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Created:</span>
                          <p className="font-medium">{new Date(task.createdAt).toLocaleDateString()}</p>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Updated:</span>
                          <p className="font-medium">{new Date(task.updatedAt).toLocaleDateString()}</p>
                        </div>
                      </div>
                      
                      {task.dependencies.length > 0 && (
                        <div className="mt-3">
                          <span className="text-sm font-medium">Dependencies:</span>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {task.dependencies.map(depId => {
                              const depTask = project.tasks.find(t => t.id === depId);
                              return depTask ? (
                                <Badge key={depId} variant="secondary" className="text-xs">
                                  {depTask.title}
                                </Badge>
                              ) : null;
                            })}
                          </div>
                        </div>
                      )}
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
                <span>Create New Project</span>
              </CardTitle>
              <CardDescription>
                Start a new collaborative project with other agents
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Project Name</label>
                  <Input
                    placeholder="Enter project name"
                    value={newProjectName}
                    onChange={(e) => setNewProjectName(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Category</label>
                  <Select value={newProjectCategory} onValueChange={setNewProjectCategory}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="research">Research</SelectItem>
                      <SelectItem value="development">Development</SelectItem>
                      <SelectItem value="trading">Trading</SelectItem>
                      <SelectItem value="analysis">Analysis</SelectItem>
                      <SelectItem value="creative">Creative</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              
              <div className="space-y-2">
                <label className="text-sm font-medium">Description</label>
                <textarea
                  placeholder="Describe your project goals and requirements"
                  value={newProjectDescription}
                  onChange={(e) => setNewProjectDescription(e.target.value)}
                  className="w-full min-h-[100px] p-3 border rounded-md resize-none focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Priority</label>
                  <Select value={newProjectPriority} onValueChange={setNewProjectPriority}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="low">Low</SelectItem>
                      <SelectItem value="normal">Normal</SelectItem>
                      <SelectItem value="high">High</SelectItem>
                      <SelectItem value="critical">Critical</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Initial Team Size</label>
                  <Input
                    type="number"
                    placeholder="Number of participants"
                    defaultValue="3"
                    min="1"
                    max="10"
                  />
                </div>
              </div>
            </CardContent>
            <CardFooter>
              <div className="flex space-x-2 w-full">
                <Button variant="outline" className="flex-1">
                  Save as Draft
                </Button>
                <Button onClick={handleCreateProject} className="flex-1">
                  <Plus className="w-4 h-4 mr-2" />
                  Create Project
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
                  <Users className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Total Projects</span>
                </div>
                <div className="text-2xl font-bold">{stats?.totalProjects}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  All collaborative projects
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <Activity className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Active Projects</span>
                </div>
                <div className="text-2xl font-bold">{stats?.activeProjects}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Currently in progress
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <Handshake className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Total Participants</span>
                </div>
                <div className="text-2xl font-bold">{stats?.totalParticipants}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Active collaborators
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <TrendingUp className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Success Rate</span>
                </div>
                <div className="text-2xl font-bold">{stats?.successRate}%</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Project completion rate
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Category Distribution */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <BarChart3 className="w-5 h-5" />
                <span>Projects by Category</span>
              </CardTitle>
              <CardDescription>
                Distribution of collaborative projects by category
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {Object.entries(stats?.projectsByCategory || {}).map(([category, count]) => (
                  <div key={category} className="space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        {getCategoryIcon(category)}
                        <span className="text-sm font-medium capitalize">{category}</span>
                      </div>
                      <span className="text-sm text-muted-foreground">{count} projects</span>
                    </div>
                    <Progress 
                      value={(count / stats!.totalProjects) * 100} 
                      className="h-2" 
                    />
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Monthly Activity */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Calendar className="w-5 h-5" />
                <span>Monthly Activity</span>
              </CardTitle>
              <CardDescription>
                Project creation and participation trends
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="h-64 bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg flex items-center justify-center">
                <div className="text-center">
                  <TrendingUp className="w-12 h-12 text-muted-foreground mx-auto mb-2" />
                  <p className="text-sm text-muted-foreground">Monthly Activity Trends</p>
                  <p className="text-xs text-muted-foreground">Projects, participants, and budget over time</p>
                </div>
              </div>
              
              <div className="grid grid-cols-4 gap-4 mt-4">
                {stats?.monthlyActivity.map((month, index) => (
                  <div key={index} className="text-center">
                    <div className="text-sm font-medium">{month.month}</div>
                    <div className="text-lg font-bold">{month.projects}</div>
                    <div className="text-xs text-muted-foreground">
                      {month.participants} participants
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

export default AgentCollaboration;
