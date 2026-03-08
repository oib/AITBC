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
  Play, 
  Pause, 
  Square, 
  Settings, 
  Clock, 
  TrendingUp, 
  Activity, 
  CheckCircle,
  AlertTriangle,
  XCircle,
  RefreshCw,
  Eye,
  Cpu,
  Zap,
  Target,
  BarChart3,
  Timer,
  DollarSign,
  Shield,
  Network,
  Layers
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { useWallet } from '@/hooks/use-wallet';

interface AgentCapability {
  agentId: string;
  supportedTaskTypes: string[];
  gpuTier: string;
  maxConcurrentTasks: number;
  currentLoad: number;
  performanceScore: number;
  costPerHour: number;
  reliabilityScore: number;
  status: 'available' | 'busy' | 'offline' | 'maintenance';
  lastUpdated: string;
}

interface OrchestrationPlan {
  taskId: string;
  subTasks: Array<{
    subTaskId: string;
    name: string;
    status: string;
    assignedAgent?: string;
    requirements: {
      taskType: string;
      estimatedDuration: number;
      gpuTier: string;
      memoryRequirement: number;
      computeIntensity: number;
    };
  }>;
  agentAssignments: Array<{
    subTaskId: string;
    agentId: string;
    status: string;
    assignedAt: string;
    startedAt?: string;
    completedAt?: string;
  }>;
  executionTimeline: Record<string, string>;
  resourceRequirements: Record<string, number>;
  estimatedCost: number;
  confidenceScore: number;
  createdAt: string;
}

interface OrchestrationMetrics {
  orchestratorStatus: string;
  activePlans: number;
  completedPlans: number;
  failedPlans: number;
  registeredAgents: number;
  availableAgents: number;
  metrics: {
    totalTasks: number;
    successfulTasks: number;
    failedTasks: number;
    averageExecutionTime: number;
    averageCost: number;
    agentUtilization: number;
  };
  resourceUtilization: Record<string, number>;
}

const AgentOrchestration: React.FC = () => {
  const { toast } = useToast();
  const { isConnected, address } = useWallet();
  
  const [agents, setAgents] = useState<AgentCapability[]>([]);
  const [orchestrationPlans, setOrchestrationPlans] = useState<OrchestrationPlan[]>([]);
  const [selectedPlan, setSelectedPlan] = useState<OrchestrationPlan | null>(null);
  const [metrics, setMetrics] = useState<OrchestrationMetrics | null>(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [loading, setLoading] = useState(true);
  const [orchestrating, setOrchestrating] = useState(false);
  
  // Form states
  const [taskDescription, setTaskDescription] = useState('');
  const [taskType, setTaskType] = useState('mixed_modal');
  const [priority, setPriority] = useState('medium');
  const [maxBudget, setMaxBudget] = useState('0.5');
  const [deadline, setDeadline] = useState('');
  
  // Mock data for demonstration
  const mockAgents: AgentCapability[] = [
    {
      agentId: 'agent_001',
      supportedTaskTypes: ['text_processing', 'data_analysis'],
      gpuTier: 'mid_range_gpu',
      maxConcurrentTasks: 3,
      currentLoad: 1,
      performanceScore: 0.85,
      costPerHour: 0.05,
      reliabilityScore: 0.92,
      status: 'available',
      lastUpdated: '2024-01-26T16:45:00Z'
    },
    {
      agentId: 'agent_002',
      supportedTaskTypes: ['image_processing', 'model_inference'],
      gpuTier: 'high_end_gpu',
      maxConcurrentTasks: 2,
      currentLoad: 2,
      performanceScore: 0.92,
      costPerHour: 0.09,
      reliabilityScore: 0.88,
      status: 'busy',
      lastUpdated: '2024-01-26T16:50:00Z'
    },
    {
      agentId: 'agent_003',
      supportedTaskTypes: ['compute_intensive', 'model_training'],
      gpuTier: 'premium_gpu',
      maxConcurrentTasks: 1,
      currentLoad: 0,
      performanceScore: 0.96,
      costPerHour: 0.15,
      reliabilityScore: 0.95,
      status: 'available',
      lastUpdated: '2024-01-26T16:40:00Z'
    },
    {
      agentId: 'agent_004',
      supportedTaskTypes: ['audio_processing', 'video_processing'],
      gpuTier: 'high_end_gpu',
      maxConcurrentTasks: 2,
      currentLoad: 0,
      performanceScore: 0.78,
      costPerHour: 0.08,
      reliabilityScore: 0.85,
      status: 'available',
      lastUpdated: '2024-01-26T16:35:00Z'
    },
    {
      agentId: 'agent_005',
      supportedTaskTypes: ['io_bound', 'data_processing'],
      gpuTier: 'cpu_only',
      maxConcurrentTasks: 5,
      currentLoad: 3,
      performanceScore: 0.72,
      costPerHour: 0.02,
      reliabilityScore: 0.90,
      status: 'busy',
      lastUpdated: '2024-01-26T16:55:00Z'
    }
  ];

  const mockPlans: OrchestrationPlan[] = [
    {
      taskId: 'task_001',
      subTasks: [
        {
          subTaskId: 'subtask_001',
          name: 'Data Preprocessing',
          status: 'completed',
          assignedAgent: 'agent_001',
          requirements: {
            taskType: 'data_analysis',
            estimatedDuration: 0.5,
            gpuTier: 'mid_range_gpu',
            memoryRequirement: 4,
            computeIntensity: 0.3
          }
        },
        {
          subTaskId: 'subtask_002',
          name: 'Model Inference',
          status: 'in_progress',
          assignedAgent: 'agent_002',
          requirements: {
            taskType: 'model_inference',
            estimatedDuration: 1.5,
            gpuTier: 'high_end_gpu',
            memoryRequirement: 8,
            computeIntensity: 0.8
          }
        },
        {
          subTaskId: 'subtask_003',
          name: 'Result Aggregation',
          status: 'pending',
          requirements: {
            taskType: 'data_analysis',
            estimatedDuration: 0.3,
            gpuTier: 'cpu_only',
            memoryRequirement: 2,
            computeIntensity: 0.2
          }
        }
      ],
      agentAssignments: [
        {
          subTaskId: 'subtask_001',
          agentId: 'agent_001',
          status: 'completed',
          assignedAt: '2024-01-26T14:00:00Z',
          startedAt: '2024-01-26T14:00:00Z',
          completedAt: '2024-01-26T14:30:00Z'
        },
        {
          subTaskId: 'subtask_002',
          agentId: 'agent_002',
          status: 'in_progress',
          assignedAt: '2024-01-26T14:30:00Z',
          startedAt: '2024-01-26T14:35:00Z'
        }
      ],
      executionTimeline: {
        'subtask_001': '2024-01-26T14:00:00Z',
        'subtask_002': '2024-01-26T14:30:00Z',
        'subtask_003': '2024-01-26T16:00:00Z'
      },
      resourceRequirements: {
        GPU: 2,
        MEMORY: 14
      },
      estimatedCost: 0.21,
      confidenceScore: 0.88,
      createdAt: '2024-01-26T13:45:00Z'
    },
    {
      taskId: 'task_002',
      subTasks: [
        {
          subTaskId: 'subtask_004',
          name: 'Image Processing',
          status: 'completed',
          assignedAgent: 'agent_004',
          requirements: {
            taskType: 'image_processing',
            estimatedDuration: 2.0,
            gpuTier: 'high_end_gpu',
            memoryRequirement: 6,
            computeIntensity: 0.7
          }
        },
        {
          subTaskId: 'subtask_005',
          name: 'Feature Extraction',
          status: 'completed',
          assignedAgent: 'agent_001',
          requirements: {
            taskType: 'data_analysis',
            estimatedDuration: 1.0,
            gpuTier: 'mid_range_gpu',
            memoryRequirement: 4,
            computeIntensity: 0.5
          }
        }
      ],
      agentAssignments: [
        {
          subTaskId: 'subtask_004',
          agentId: 'agent_004',
          status: 'completed',
          assignedAt: '2024-01-26T12:00:00Z',
          startedAt: '2024-01-26T12:05:00Z',
          completedAt: '2024-01-26T14:05:00Z'
        },
        {
          subTaskId: 'subtask_005',
          agentId: 'agent_001',
          status: 'completed',
          assignedAt: '2024-01-26T14:05:00Z',
          startedAt: '2024-01-26T14:10:00Z',
          completedAt: '2024-01-26T15:10:00Z'
        }
      ],
      executionTimeline: {
        'subtask_004': '2024-01-26T12:00:00Z',
        'subtask_005': '2024-01-26T14:05:00Z'
      },
      resourceRequirements: {
        GPU: 2,
        MEMORY: 10
      },
      estimatedCost: 0.17,
      confidenceScore: 0.92,
      createdAt: '2024-01-26T11:50:00Z'
    }
  ];

  const mockMetrics: OrchestrationMetrics = {
    orchestratorStatus: 'monitoring',
    activePlans: 2,
    completedPlans: 15,
    failedPlans: 3,
    registeredAgents: 5,
    availableAgents: 3,
    metrics: {
      totalTasks: 20,
      successfulTasks: 17,
      failedTasks: 3,
      averageExecutionTime: 2.5,
      averageCost: 0.18,
      agentUtilization: 0.65
    },
    resourceUtilization: {
      GPU: 0.75,
      MEMORY: 0.60,
      CPU: 0.45
    }
  };

  useEffect(() => {
    // Load mock data
    setTimeout(() => {
      setAgents(mockAgents);
      setOrchestrationPlans(mockPlans);
      setMetrics(mockMetrics);
      if (mockPlans.length > 0) {
        setSelectedPlan(mockPlans[0]);
      }
      setLoading(false);
    }, 1000);
  }, []);

  const handleOrchestrateTask = async () => {
    if (!isConnected) {
      toast({
        title: "Wallet Not Connected",
        description: "Please connect your wallet to orchestrate tasks",
        variant: "destructive"
      });
      return;
    }

    if (!taskDescription || !taskType || !maxBudget) {
      toast({
        title: "Missing Information",
        description: "Please fill in all task details",
        variant: "destructive"
      });
      return;
    }

    try {
      setOrchestrating(true);
      
      toast({
        title: "Orchestrating Task",
        description: "Decomposing task and assigning agents...",
        variant: "default"
      });

      // Simulate orchestration
      await new Promise(resolve => setTimeout(resolve, 3000));

      // Create new plan
      const newPlan: OrchestrationPlan = {
        taskId: `task_${Date.now()}`,
        subTasks: [
          {
            subTaskId: `subtask_${Date.now()}_1`,
            name: 'Initial Processing',
            status: 'pending',
            requirements: {
              taskType: taskType,
              estimatedDuration: 1.0,
              gpuTier: 'mid_range_gpu',
              memoryRequirement: 4,
              computeIntensity: 0.5
            }
          },
          {
            subTaskId: `subtask_${Date.now()}_2`,
            name: 'Main Computation',
            status: 'pending',
            requirements: {
              taskType: taskType,
              estimatedDuration: 2.0,
              gpuTier: 'high_end_gpu',
              memoryRequirement: 8,
              computeIntensity: 0.8
            }
          }
        ],
        agentAssignments: [],
        executionTimeline: {},
        resourceRequirements: {
          GPU: 2,
          MEMORY: 12
        },
        estimatedCost: parseFloat(maxBudget) * 0.8,
        confidenceScore: 0.85,
        createdAt: new Date().toISOString()
      };

      setOrchestrationPlans([newPlan, ...orchestrationPlans]);
      setSelectedPlan(newPlan);
      setActiveTab('plans');
      
      // Reset form
      setTaskDescription('');
      setTaskType('mixed_modal');
      setPriority('medium');
      setMaxBudget('0.5');
      setDeadline('');
      
      toast({
        title: "Task Orchestrated",
        description: "Task has been decomposed and agents assigned",
        variant: "default"
      });
    } catch (error) {
      toast({
        title: "Orchestration Failed",
        description: "There was an error orchestrating the task",
        variant: "destructive"
      });
    } finally {
      setOrchestrating(false);
    }
  };

  const handleCancelPlan = async (taskId: string) => {
    try {
      toast({
        title: "Cancelling Plan",
        description: "Cancelling orchestration plan...",
        variant: "default"
      });

      // Remove plan
      setOrchestrationPlans(orchestrationPlans.filter(plan => plan.taskId !== taskId));
      
      if (selectedPlan?.taskId === taskId) {
        setSelectedPlan(null);
      }
      
      toast({
        title: "Plan Cancelled",
        description: "Orchestration plan has been cancelled",
        variant: "default"
      });
    } catch (error) {
      toast({
        title: "Cancellation Failed",
        description: "There was an error cancelling the plan",
        variant: "destructive"
      });
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'bg-green-500';
      case 'in_progress': return 'bg-blue-500';
      case 'pending': return 'bg-yellow-500';
      case 'failed': return 'bg-red-500';
      case 'cancelled': return 'bg-gray-500';
      default: return 'bg-gray-400';
    }
  };

  const getAgentStatusColor = (status: string) => {
    switch (status) {
      case 'available': return 'bg-green-500';
      case 'busy': return 'bg-blue-500';
      case 'offline': return 'bg-red-500';
      case 'maintenance': return 'bg-yellow-500';
      default: return 'bg-gray-400';
    }
  };

  const getOverallPlanStatus = (plan: OrchestrationPlan) => {
    const completedCount = plan.subTasks.filter(st => st.status === 'completed').length;
    const failedCount = plan.subTasks.filter(st => st.status === 'failed').length;
    const totalCount = plan.subTasks.length;
    
    if (completedCount === totalCount) return 'completed';
    if (failedCount > 0) return 'failed';
    if (completedCount > 0) return 'in_progress';
    return 'pending';
  };

  if (loading) {
    return (
      <div className="container mx-auto p-6 space-y-6">
        <div className="text-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
          <p className="mt-2 text-muted-foreground">Loading orchestration system...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Agent Orchestration</h1>
          <p className="text-muted-foreground mt-2">
            Multi-agent coordination and task orchestration system
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <Badge variant="outline" className="flex items-center space-x-1">
            <Users className="w-4 h-4" />
            <span>{metrics?.registeredAgents} Agents</span>
          </Badge>
          <Badge variant="outline" className="flex items-center space-x-1">
            <Activity className="w-4 h-4" />
            <span>{metrics?.activePlans} Active Plans</span>
          </Badge>
          <Badge variant="outline" className="flex items-center space-x-1">
            <Network className="w-4 h-4" />
            <span>{metrics?.availableAgents} Available</span>
          </Badge>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-5">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="agents">Agents</TabsTrigger>
          <TabsTrigger value="plans">Plans</TabsTrigger>
          <TabsTrigger value="orchestrate">Orchestrate</TabsTrigger>
          <TabsTrigger value="metrics">Metrics</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
          {/* System Status */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <Users className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Total Agents</span>
                </div>
                <div className="text-2xl font-bold">{metrics?.registeredAgents}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  {metrics?.availableAgents} available
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <Activity className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Active Plans</span>
                </div>
                <div className="text-2xl font-bold">{metrics?.activePlans}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  {metrics?.completedPlans} completed
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <Timer className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Avg Execution</span>
                </div>
                <div className="text-2xl font-bold">{metrics?.metrics.averageExecutionTime}h</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Per task
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <DollarSign className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Avg Cost</span>
                </div>
                <div className="text-2xl font-bold">{metrics?.metrics.averageCost} AITBC</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Per task
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Resource Utilization */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <BarChart3 className="w-5 h-5" />
                <span>Resource Utilization</span>
              </CardTitle>
              <CardDescription>
                Current system resource usage
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {Object.entries(metrics?.resourceUtilization || {}).map(([resource, utilization]) => (
                  <div key={resource}>
                    <p className="text-sm font-medium capitalize">{resource}</p>
                    <div className="flex items-center space-x-2 mt-1">
                      <Progress value={utilization * 100} className="flex-1" />
                      <span className="text-sm font-medium">{(utilization * 100).toFixed(0)}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Recent Plans */}
          <Card>
            <CardHeader>
              <CardTitle>Recent Orchestration Plans</CardTitle>
              <CardDescription>
                Latest task orchestration activities
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {orchestrationPlans.slice(0, 3).map((plan) => (
                  <div key={plan.taskId} className="flex items-center justify-between p-4 border rounded-lg">
                    <div className="flex items-center space-x-4">
                      <div className={`w-3 h-3 rounded-full ${getStatusColor(getOverallPlanStatus(plan))}`}></div>
                      <div>
                        <p className="font-medium">{plan.taskId}</p>
                        <p className="text-sm text-muted-foreground">
                          {plan.subTasks.length} sub-tasks • {plan.estimatedCost} AITBC
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-medium">{getOverallPlanStatus(plan)}</p>
                      <p className="text-xs text-muted-foreground">
                        {new Date(plan.createdAt).toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="agents" className="space-y-6">
          {/* Agent Registry */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {agents.map((agent) => (
              <Card key={agent.agentId}>
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <CardTitle className="text-lg">{agent.agentId}</CardTitle>
                      <CardDescription className="mt-1">
                        {agent.supportedTaskTypes.join(', ')}
                      </CardDescription>
                    </div>
                    <div className={`w-3 h-3 rounded-full ${getAgentStatusColor(agent.status)}`}></div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-muted-foreground">GPU Tier:</span>
                      <p className="font-medium capitalize">{agent.gpuTier.replace('_', ' ')}</p>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Load:</span>
                      <p className="font-medium">{agent.currentLoad}/{agent.maxConcurrentTasks}</p>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Performance:</span>
                      <p className="font-medium">{(agent.performanceScore * 100).toFixed(0)}%</p>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Cost:</span>
                      <p className="font-medium">{agent.costPerHour} AITBC/h</p>
                    </div>
                  </div>
                  
                  <div className="space-y-2">
                    <div className="flex items-center space-x-2">
                      <span className="text-xs text-muted-foreground">Reliability:</span>
                      <Progress value={agent.reliabilityScore * 100} className="flex-1 h-2" />
                      <span className="text-xs font-medium">{(agent.reliabilityScore * 100).toFixed(0)}%</span>
                    </div>
                  </div>
                  
                  <div className="flex items-center justify-between">
                    <Badge variant={agent.status === 'available' ? "default" : "secondary"}>
                      {agent.status}
                    </Badge>
                    <p className="text-xs text-muted-foreground">
                      {new Date(agent.lastUpdated).toLocaleTimeString()}
                    </p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="plans" className="space-y-6">
          {/* Plan Selection */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Plans List */}
            <Card>
              <CardHeader>
                <CardTitle>Orchestration Plans</CardTitle>
                <CardDescription>
                  Active and recent orchestration plans
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {orchestrationPlans.map((plan) => (
                    <div
                      key={plan.taskId}
                      className={`p-4 border rounded-lg cursor-pointer transition-colors ${
                        selectedPlan?.taskId === plan.taskId
                          ? 'border-primary bg-primary/5'
                          : 'border-border hover:bg-muted/50'
                      }`}
                      onClick={() => setSelectedPlan(plan)}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <h4 className="font-semibold">{plan.taskId}</h4>
                        <div className={`w-3 h-3 rounded-full ${getStatusColor(getOverallPlanStatus(plan))}`}></div>
                      </div>
                      <div className="space-y-1 text-sm">
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Sub-tasks:</span>
                          <span className="font-medium">{plan.subTasks.length}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Est. Cost:</span>
                          <span className="font-medium">{plan.estimatedCost} AITBC</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Created:</span>
                          <span className="font-medium">{new Date(plan.createdAt).toLocaleDateString()}</span>
                        </div>
                      </div>
                      <div className="flex items-center space-x-2 mt-2">
                        <Badge variant="outline" className="text-xs">
                          {getOverallPlanStatus(plan)}
                        </Badge>
                        <Badge variant="outline" className="text-xs">
                          {(plan.confidenceScore * 100).toFixed(0)}% confidence
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Plan Details */}
            {selectedPlan && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2">
                    <Layers className="w-5 h-5" />
                    <span>{selectedPlan.taskId}</span>
                  </CardTitle>
                  <CardDescription>
                    Detailed orchestration plan information
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  {/* Plan Overview */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-sm text-muted-foreground">Total Sub-tasks</p>
                      <p className="text-lg font-bold">{selectedPlan.subTasks.length}</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Estimated Cost</p>
                      <p className="text-lg font-bold">{selectedPlan.estimatedCost} AITBC</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Confidence Score</p>
                      <p className="text-lg font-bold">{(selectedPlan.confidenceScore * 100).toFixed(1)}%</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Created</p>
                      <p className="text-lg font-bold">{new Date(selectedPlan.createdAt).toLocaleDateString()}</p>
                    </div>
                  </div>

                  {/* Sub-tasks */}
                  <div>
                    <h4 className="font-semibold mb-3">Sub-tasks</h4>
                    <div className="space-y-3">
                      {selectedPlan.subTasks.map((subTask) => (
                        <div key={subTask.subTaskId} className="p-3 border rounded-lg">
                          <div className="flex items-center justify-between mb-2">
                            <h5 className="font-medium">{subTask.name}</h5>
                            <div className={`w-2 h-2 rounded-full ${getStatusColor(subTask.status)}`}></div>
                          </div>
                          <div className="grid grid-cols-2 gap-2 text-xs">
                            <div>
                              <span className="text-muted-foreground">Type:</span>
                              <p className="font-medium">{subTask.requirements.taskType}</p>
                            </div>
                            <div>
                              <span className="text-muted-foreground">Duration:</span>
                              <p className="font-medium">{subTask.requirements.estimatedDuration}h</p>
                            </div>
                            <div>
                              <span className="text-muted-foreground">GPU:</span>
                              <p className="font-medium capitalize">{subTask.requirements.gpuTier.replace('_', ' ')}</p>
                            </div>
                            <div>
                              <span className="text-muted-foreground">Memory:</span>
                              <p className="font-medium">{subTask.requirements.memoryRequirement}GB</p>
                            </div>
                          </div>
                          {subTask.assignedAgent && (
                            <div className="mt-2">
                              <span className="text-xs text-muted-foreground">Assigned to:</span>
                              <p className="text-sm font-medium">{subTask.assignedAgent}</p>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex space-x-2">
                    <Button variant="outline" size="sm">
                      <Eye className="w-4 h-4 mr-2" />
                      View Details
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => handleCancelPlan(selectedPlan.taskId)}>
                      <XCircle className="w-4 h-4 mr-2" />
                      Cancel Plan
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </TabsContent>

        <TabsContent value="orchestrate" className="space-y-6">
          {/* Task Orchestration Form */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Target className="w-5 h-5" />
                <span>Orchestrate New Task</span>
              </CardTitle>
              <CardDescription>
                Create a new orchestration plan for complex task execution
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Task Description</label>
                  <textarea
                    className="w-full p-2 border rounded-lg"
                    rows={3}
                    placeholder="Describe the task to be orchestrated..."
                    value={taskDescription}
                    onChange={(e) => setTaskDescription(e.target.value)}
                  />
                </div>
                
                <div className="space-y-4">
                  <div className="space-y-2">
                    <label className="text-sm font-medium">Task Type</label>
                    <Select value={taskType} onValueChange={setTaskType}>
                      <SelectTrigger>
                        <SelectValue placeholder="Select task type" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="text_processing">Text Processing</SelectItem>
                        <SelectItem value="image_processing">Image Processing</SelectItem>
                        <SelectItem value="audio_processing">Audio Processing</SelectItem>
                        <SelectItem value="video_processing">Video Processing</SelectItem>
                        <SelectItem value="data_analysis">Data Analysis</SelectItem>
                        <SelectItem value="model_inference">Model Inference</SelectItem>
                        <SelectItem value="model_training">Model Training</SelectItem>
                        <SelectItem value="compute_intensive">Compute Intensive</SelectItem>
                        <SelectItem value="mixed_modal">Mixed Modal</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  
                  <div className="space-y-2">
                    <label className="text-sm font-medium">Priority</label>
                    <Select value={priority} onValueChange={setPriority}>
                      <SelectTrigger>
                        <SelectValue placeholder="Select priority" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="low">Low</SelectItem>
                        <SelectItem value="medium">Medium</SelectItem>
                        <SelectItem value="high">High</SelectItem>
                        <SelectItem value="critical">Critical</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                
                <div className="space-y-2">
                  <label className="text-sm font-medium">Maximum Budget (AITBC)</label>
                  <Input
                    type="number"
                    placeholder="Enter maximum budget"
                    value={maxBudget}
                    onChange={(e) => setMaxBudget(e.target.value)}
                  />
                </div>
                
                <div className="space-y-2">
                  <label className="text-sm font-medium">Deadline (Optional)</label>
                  <Input
                    type="datetime-local"
                    value={deadline}
                    onChange={(e) => setDeadline(e.target.value)}
                  />
                </div>
              </div>
              
              <Button 
                onClick={handleOrchestrateTask} 
                className="w-full" 
                disabled={orchestrating}
              >
                {orchestrating ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                    Orchestrating...
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4 mr-2" />
                    Orchestrate Task
                  </>
                )}
              </Button>
            </CardContent>
          </Card>

          {/* Available Agents */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Users className="w-5 h-5" />
                <span>Available Agents</span>
              </CardTitle>
              <CardDescription>
                Agents ready for task assignment
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {agents.filter(agent => agent.status === 'available').map((agent) => (
                  <div key={agent.agentId} className="p-4 border rounded-lg">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="font-semibold">{agent.agentId}</h4>
                      <div className="w-2 h-2 rounded-full bg-green-500"></div>
                    </div>
                    <div className="space-y-1 text-sm">
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Performance:</span>
                        <span>{(agent.performanceScore * 100).toFixed(0)}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Cost:</span>
                        <span>{agent.costPerHour} AITBC/h</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Load:</span>
                        <span>{agent.currentLoad}/{agent.maxConcurrentTasks}</span>
                      </div>
                    </div>
                    <div className="mt-2">
                      <p className="text-xs text-muted-foreground">Supported:</p>
                      <p className="text-xs">{agent.supportedTaskTypes.slice(0, 2).join(', ')}</p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="metrics" className="space-y-6">
          {/* Performance Metrics */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <CheckCircle className="w-5 h-5 text-green-500" />
                  <span>Success Rate</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold text-green-600">
                  {((metrics?.metrics.successfulTasks || 0) / (metrics?.metrics.totalTasks || 1) * 100).toFixed(1)}%
                </div>
                <p className="text-sm text-muted-foreground mt-1">
                  {metrics?.metrics.successfulTasks} of {metrics?.metrics.totalTasks} tasks successful
                </p>
              </CardContent>
            </Card>
            
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <Timer className="w-5 h-5 text-blue-500" />
                  <span>Avg Execution Time</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold text-blue-600">
                  {metrics?.metrics.averageExecutionTime}h
                </div>
                <p className="text-sm text-muted-foreground mt-1">
                  Per task completion
                </p>
              </CardContent>
            </Card>
            
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <DollarSign className="w-5 h-5 text-purple-500" />
                  <span>Average Cost</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold text-purple-600">
                  {metrics?.metrics.averageCost} AITBC
                </div>
                <p className="text-sm text-muted-foreground mt-1">
                  Per task execution
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Agent Utilization */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Activity className="w-5 h-5" />
                <span>Agent Utilization</span>
              </CardTitle>
              <CardDescription>
                Current agent workload and availability
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span>Overall Utilization</span>
                    <span>{(metrics?.metrics?.agentUtilization ? (metrics.metrics.agentUtilization * 100).toFixed(1) : '0')}%</span>
                  </div>
                  <Progress value={metrics?.metrics?.agentUtilization ? (metrics.metrics.agentUtilization * 100) : 0} className="w-full" />
                </div>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {agents.map((agent) => (
                    <div key={agent.agentId} className="p-3 border rounded-lg">
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-medium">{agent.agentId}</span>
                        <Badge variant={agent.status === 'available' ? "default" : "secondary"}>
                          {agent.status}
                        </Badge>
                      </div>
                      <div>
                        <div className="flex justify-between text-sm mb-1">
                          <span>Load</span>
                          <span>{agent.currentLoad}/{agent.maxConcurrentTasks}</span>
                        </div>
                        <Progress 
                          value={(agent.currentLoad / agent.maxConcurrentTasks) * 100} 
                          className="w-full h-2" 
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* System Health */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Shield className="w-5 h-5" />
                <span>System Health</span>
              </CardTitle>
              <CardDescription>
                Orchestration system status and health indicators
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-4">
                  <div className="flex items-center space-x-2">
                    <div className="w-3 h-3 rounded-full bg-green-500"></div>
                    <span className="font-medium">Orchestrator Status</span>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    System is {metrics?.orchestratorStatus} and operating normally
                  </p>
                </div>
                
                <div className="space-y-4">
                  <div className="flex items-center space-x-2">
                    <div className="w-3 h-3 rounded-full bg-green-500"></div>
                    <span className="font-medium">Agent Network</span>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {metrics?.availableAgents} of {metrics?.registeredAgents} agents available
                  </p>
                </div>
              </div>
              
              <Separator />
              
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-center">
                <div>
                  <p className="text-2xl font-bold text-green-600">{metrics?.completedPlans}</p>
                  <p className="text-sm text-muted-foreground">Completed Plans</p>
                </div>
                <div>
                  <p className="text-2xl font-bold text-blue-600">{metrics?.activePlans}</p>
                  <p className="text-sm text-muted-foreground">Active Plans</p>
                </div>
                <div>
                  <p className="text-2xl font-bold text-red-600">{metrics?.failedPlans}</p>
                  <p className="text-sm text-muted-foreground">Failed Plans</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default AgentOrchestration;
