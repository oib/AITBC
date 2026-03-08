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
  Layers, 
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
  GitBranch,
  Box,
  ArrowRight,
  ArrowDown,
  MoreHorizontal
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { useWallet } from '@/hooks/use-wallet';

interface SubTask {
  subTaskId: string;
  parentTaskId: string;
  name: string;
  description: string;
  status: 'pending' | 'assigned' | 'in_progress' | 'completed' | 'failed' | 'cancelled';
  assignedAgent?: string;
  dependencies: string[];
  outputs: string[];
  inputs: string[];
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
  errorMessage?: string;
  retryCount: number;
  maxRetries: number;
  requirements: {
    taskType: string;
    estimatedDuration: number;
    gpuTier: string;
    memoryRequirement: number;
    computeIntensity: number;
    dataSize: number;
    priority: number;
    maxCost?: number;
  };
}

interface TaskDecomposition {
  originalTaskId: string;
  subTasks: SubTask[];
  dependencyGraph: Record<string, string[]>;
  executionPlan: string[][];
  estimatedTotalDuration: number;
  estimatedTotalCost: number;
  confidenceScore: number;
  decompositionStrategy: string;
  createdAt: string;
}

interface TaskAggregation {
  aggregationId: string;
  parentTaskId: string;
  aggregationType: string;
  inputSubTasks: string[];
  outputFormat: string;
  aggregationFunction: string;
  createdAt: string;
}

const TaskDecomposition: React.FC = () => {
  const { toast } = useToast();
  const { isConnected, address } = useWallet();
  
  const [decompositions, setDecompositions] = useState<TaskDecomposition[]>([]);
  const [selectedDecomposition, setSelectedDecomposition] = useState<TaskDecomposition | null>(null);
  const [aggregations, setAggregations] = useState<TaskAggregation[]>([]);
  const [activeTab, setActiveTab] = useState('overview');
  const [loading, setLoading] = useState(true);
  const [decomposing, setDecomposing] = useState(false);
  
  // Form states
  const [taskDescription, setTaskDescription] = useState('');
  const [taskType, setTaskType] = useState('mixed_modal');
  const [estimatedDuration, setEstimatedDuration] = useState('2');
  const [gpuTier, setGpuTier] = useState('mid_range_gpu');
  const [memoryRequirement, setMemoryRequirement] = useState('8');
  const [dataSize, setDataSize] = useState('1000');
  const [priority, setPriority] = useState('5');
  const [maxCost, setMaxCost] = useState('0.5');
  const [strategy, setStrategy] = useState('adaptive');
  const [maxSubtasks, setMaxSubtasks] = useState('10');
  
  // Mock data for demonstration
  const mockDecompositions: TaskDecomposition[] = [
    {
      originalTaskId: 'task_001',
      subTasks: [
        {
          subTaskId: 'subtask_001',
          parentTaskId: 'task_001',
          name: 'Data Preprocessing',
          description: 'Clean and preprocess input data',
          status: 'completed',
          assignedAgent: 'agent_001',
          dependencies: [],
          outputs: ['cleaned_data'],
          inputs: ['raw_data'],
          createdAt: '2024-01-26T14:00:00Z',
          startedAt: '2024-01-26T14:00:00Z',
          completedAt: '2024-01-26T14:30:00Z',
          retryCount: 0,
          maxRetries: 3,
          requirements: {
            taskType: 'data_analysis',
            estimatedDuration: 0.5,
            gpuTier: 'mid_range_gpu',
            memoryRequirement: 4,
            computeIntensity: 0.3,
            dataSize: 500,
            priority: 5,
            maxCost: 0.05
          }
        },
        {
          subTaskId: 'subtask_002',
          parentTaskId: 'task_001',
          name: 'Feature Extraction',
          description: 'Extract features from processed data',
          status: 'in_progress',
          assignedAgent: 'agent_002',
          dependencies: ['subtask_001'],
          outputs: ['features'],
          inputs: ['cleaned_data'],
          createdAt: '2024-01-26T14:30:00Z',
          startedAt: '2024-01-26T14:35:00Z',
          retryCount: 0,
          maxRetries: 3,
          requirements: {
            taskType: 'model_inference',
            estimatedDuration: 1.5,
            gpuTier: 'high_end_gpu',
            memoryRequirement: 8,
            computeIntensity: 0.8,
            dataSize: 300,
            priority: 7,
            maxCost: 0.15
          }
        },
        {
          subTaskId: 'subtask_003',
          parentTaskId: 'task_001',
          name: 'Result Aggregation',
          description: 'Aggregate and format results',
          status: 'pending',
          dependencies: ['subtask_002'],
          outputs: ['final_results'],
          inputs: ['features'],
          createdAt: '2024-01-26T14:30:00Z',
          retryCount: 0,
          maxRetries: 3,
          requirements: {
            taskType: 'data_analysis',
            estimatedDuration: 0.3,
            gpuTier: 'cpu_only',
            memoryRequirement: 2,
            computeIntensity: 0.2,
            dataSize: 100,
            priority: 3,
            maxCost: 0.02
          }
        }
      ],
      dependencyGraph: {
        'subtask_001': [],
        'subtask_002': ['subtask_001'],
        'subtask_003': ['subtask_002']
      },
      executionPlan: [
        ['subtask_001'],
        ['subtask_002'],
        ['subtask_003']
      ],
      estimatedTotalDuration: 2.3,
      estimatedTotalCost: 0.22,
      confidenceScore: 0.88,
      decompositionStrategy: 'sequential',
      createdAt: '2024-01-26T13:45:00Z'
    },
    {
      originalTaskId: 'task_002',
      subTasks: [
        {
          subTaskId: 'subtask_004',
          parentTaskId: 'task_002',
          name: 'Image Processing',
          description: 'Process input images',
          status: 'completed',
          assignedAgent: 'agent_003',
          dependencies: [],
          outputs: ['processed_images'],
          inputs: ['raw_images'],
          createdAt: '2024-01-26T12:00:00Z',
          startedAt: '2024-01-26T12:05:00Z',
          completedAt: '2024-01-26T13:05:00Z',
          retryCount: 0,
          maxRetries: 3,
          requirements: {
            taskType: 'image_processing',
            estimatedDuration: 1.0,
            gpuTier: 'high_end_gpu',
            memoryRequirement: 6,
            computeIntensity: 0.7,
            dataSize: 800,
            priority: 8,
            maxCost: 0.10
          }
        },
        {
          subTaskId: 'subtask_005',
          parentTaskId: 'task_002',
          name: 'Text Analysis',
          description: 'Analyze text content',
          status: 'completed',
          assignedAgent: 'agent_001',
          dependencies: [],
          outputs: ['text_features'],
          inputs: ['raw_text'],
          createdAt: '2024-01-26T12:00:00Z',
          startedAt: '2024-01-26T12:00:00Z',
          completedAt: '2024-01-26T12:45:00Z',
          retryCount: 0,
          maxRetries: 3,
          requirements: {
            taskType: 'text_processing',
            estimatedDuration: 0.75,
            gpuTier: 'mid_range_gpu',
            memoryRequirement: 4,
            computeIntensity: 0.4,
            dataSize: 200,
            priority: 6,
            maxCost: 0.04
          }
        },
        {
          subTaskId: 'subtask_006',
          parentTaskId: 'task_002',
          name: 'Multi-Modal Fusion',
          description: 'Combine image and text features',
          status: 'in_progress',
          assignedAgent: 'agent_004',
          dependencies: ['subtask_004', 'subtask_005'],
          outputs: ['fused_features'],
          inputs: ['processed_images', 'text_features'],
          createdAt: '2024-01-26T13:05:00Z',
          startedAt: '2024-01-26T13:10:00Z',
          retryCount: 0,
          maxRetries: 3,
          requirements: {
            taskType: 'mixed_modal',
            estimatedDuration: 1.5,
            gpuTier: 'premium_gpu',
            memoryRequirement: 12,
            computeIntensity: 0.9,
            dataSize: 1000,
            priority: 9,
            maxCost: 0.20
          }
        }
      ],
      dependencyGraph: {
        'subtask_004': [],
        'subtask_005': [],
        'subtask_006': ['subtask_004', 'subtask_005']
      },
      executionPlan: [
        ['subtask_004', 'subtask_005'],
        ['subtask_006']
      ],
      estimatedTotalDuration: 2.5,
      estimatedTotalCost: 0.34,
      confidenceScore: 0.92,
      decompositionStrategy: 'parallel',
      createdAt: '2024-01-26T11:50:00Z'
    }
  ];

  const mockAggregations: TaskAggregation[] = [
    {
      aggregationId: 'agg_001',
      parentTaskId: 'task_001',
      aggregationType: 'concat',
      inputSubTasks: ['subtask_001', 'subtask_002', 'subtask_003'],
      outputFormat: 'json',
      aggregationFunction: 'concatenate_results_json',
      createdAt: '2024-01-26T13:45:00Z'
    },
    {
      aggregationId: 'agg_002',
      parentTaskId: 'task_002',
      aggregationType: 'merge',
      inputSubTasks: ['subtask_004', 'subtask_005', 'subtask_006'],
      outputFormat: 'array',
      aggregationFunction: 'merge_results_array',
      createdAt: '2024-01-26T11:50:00Z'
    }
  ];

  useEffect(() => {
    // Load mock data
    setTimeout(() => {
      setDecompositions(mockDecompositions);
      setAggregations(mockAggregations);
      if (mockDecompositions.length > 0) {
        setSelectedDecomposition(mockDecompositions[0]);
      }
      setLoading(false);
    }, 1000);
  }, []);

  const handleDecomposeTask = async () => {
    if (!isConnected) {
      toast({
        title: "Wallet Not Connected",
        description: "Please connect your wallet to decompose tasks",
        variant: "destructive"
      });
      return;
    }

    if (!taskDescription || !taskType || !estimatedDuration) {
      toast({
        title: "Missing Information",
        description: "Please fill in all required task details",
        variant: "destructive"
      });
      return;
    }

    try {
      setDecomposing(true);
      
      toast({
        title: "Decomposing Task",
        description: "Analyzing task and creating sub-tasks...",
        variant: "default"
      });

      // Simulate decomposition
      await new Promise(resolve => setTimeout(resolve, 3000));

      // Create new decomposition
      const newDecomposition: TaskDecomposition = {
        originalTaskId: `task_${Date.now()}`,
        subTasks: [
          {
            subTaskId: `subtask_${Date.now()}_1`,
            parentTaskId: `task_${Date.now()}`,
            name: 'Initial Processing',
            description: 'Process initial task requirements',
            status: 'pending',
            dependencies: [],
            outputs: ['processed_data'],
            inputs: ['raw_input'],
            createdAt: new Date().toISOString(),
            retryCount: 0,
            maxRetries: 3,
            requirements: {
              taskType: taskType,
              estimatedDuration: parseFloat(estimatedDuration) * 0.3,
              gpuTier: gpuTier,
              memoryRequirement: parseInt(memoryRequirement) * 0.5,
              computeIntensity: 0.5,
              dataSize: parseInt(dataSize) * 0.3,
              priority: parseInt(priority),
              maxCost: parseFloat(maxCost) * 0.3
            }
          },
          {
            subTaskId: `subtask_${Date.now()}_2`,
            parentTaskId: `task_${Date.now()}`,
            name: 'Main Computation',
            description: 'Execute main task computation',
            status: 'pending',
            dependencies: [`subtask_${Date.now()}_1`],
            outputs: ['computed_results'],
            inputs: ['processed_data'],
            createdAt: new Date().toISOString(),
            retryCount: 0,
            maxRetries: 3,
            requirements: {
              taskType: taskType,
              estimatedDuration: parseFloat(estimatedDuration) * 0.6,
              gpuTier: gpuTier,
              memoryRequirement: parseInt(memoryRequirement),
              computeIntensity: 0.8,
              dataSize: parseInt(dataSize) * 0.6,
              priority: parseInt(priority),
              maxCost: parseFloat(maxCost) * 0.6
            }
          },
          {
            subTaskId: `subtask_${Date.now()}_3`,
            parentTaskId: `task_${Date.now()}`,
            name: 'Result Processing',
            description: 'Process and format results',
            status: 'pending',
            dependencies: [`subtask_${Date.now()}_2`],
            outputs: ['final_results'],
            inputs: ['computed_results'],
            createdAt: new Date().toISOString(),
            retryCount: 0,
            maxRetries: 3,
            requirements: {
              taskType: taskType,
              estimatedDuration: parseFloat(estimatedDuration) * 0.1,
              gpuTier: 'cpu_only',
              memoryRequirement: parseInt(memoryRequirement) * 0.3,
              computeIntensity: 0.2,
              dataSize: parseInt(dataSize) * 0.1,
              priority: parseInt(priority),
              maxCost: parseFloat(maxCost) * 0.1
            }
          }
        ],
        dependencyGraph: {
          [`subtask_${Date.now()}_1`]: [],
          [`subtask_${Date.now()}_2`]: [`subtask_${Date.now()}_1`],
          [`subtask_${Date.now()}_3`]: [`subtask_${Date.now()}_2`]
        },
        executionPlan: [
          [`subtask_${Date.now()}_1`],
          [`subtask_${Date.now()}_2`],
          [`subtask_${Date.now()}_3`]
        ],
        estimatedTotalDuration: parseFloat(estimatedDuration),
        estimatedTotalCost: parseFloat(maxCost),
        confidenceScore: 0.85,
        decompositionStrategy: strategy,
        createdAt: new Date().toISOString()
      };

      setDecompositions([newDecomposition, ...decompositions]);
      setSelectedDecomposition(newDecomposition);
      setActiveTab('decompositions');
      
      // Reset form
      setTaskDescription('');
      setTaskType('mixed_modal');
      setEstimatedDuration('2');
      setGpuTier('mid_range_gpu');
      setMemoryRequirement('8');
      setDataSize('1000');
      setPriority('5');
      setMaxCost('0.5');
      setStrategy('adaptive');
      setMaxSubtasks('10');
      
      toast({
        title: "Task Decomposed",
        description: `Task decomposed into ${newDecomposition.subTasks.length} sub-tasks`,
        variant: "default"
      });
    } catch (error) {
      toast({
        title: "Decomposition Failed",
        description: "There was an error decomposing the task",
        variant: "destructive"
      });
    } finally {
      setDecomposing(false);
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

  const getOverallProgress = (decomposition: TaskDecomposition) => {
    const completedCount = decomposition.subTasks.filter(st => st.status === 'completed').length;
    return (completedCount / decomposition.subTasks.length) * 100;
  };

  const renderExecutionPlan = (plan: string[][]) => {
    return (
      <div className="space-y-4">
        {plan.map((stage, stageIndex) => (
          <div key={stageIndex} className="flex items-center space-x-4">
            <div className="flex flex-col items-center">
              <div className="w-8 h-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-sm font-medium">
                {stageIndex + 1}
              </div>
              {stageIndex < plan.length - 1 && (
                <ArrowDown className="w-4 h-4 text-muted-foreground" />
              )}
            </div>
            <div className="flex-1">
              <div className="flex flex-wrap gap-2">
                {stage.map((subTaskId) => {
                  const subTask = selectedDecomposition?.subTasks.find(st => st.subTaskId === subTaskId);
                  return (
                    <Badge key={subTaskId} variant="outline" className="flex items-center space-x-1">
                      <div className={`w-2 h-2 rounded-full ${getStatusColor(subTask?.status || 'pending')}`}></div>
                      <span>{subTask?.name || subTaskId}</span>
                    </Badge>
                  );
                })}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {stage.length > 1 ? 'Parallel execution' : 'Sequential execution'}
              </p>
            </div>
          </div>
        ))}
      </div>
    );
  };

  if (loading) {
    return (
      <div className="container mx-auto p-6 space-y-6">
        <div className="text-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
          <p className="mt-2 text-muted-foreground">Loading task decomposition system...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Task Decomposition</h1>
          <p className="text-muted-foreground mt-2">
            Intelligent task splitting and sub-task management system
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <Badge variant="outline" className="flex items-center space-x-1">
            <Layers className="w-4 h-4" />
            <span>{decompositions.length} Decompositions</span>
          </Badge>
          <Badge variant="outline" className="flex items-center space-x-1">
            <GitBranch className="w-4 h-4" />
            <span>{aggregations.length} Aggregations</span>
          </Badge>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="decompositions">Decompositions</TabsTrigger>
          <TabsTrigger value="decompose">Decompose Task</TabsTrigger>
          <TabsTrigger value="aggregations">Aggregations</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
          {/* System Statistics */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <Layers className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Total Decompositions</span>
                </div>
                <div className="text-2xl font-bold">{decompositions.length}</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <Box className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Total Sub-tasks</span>
                </div>
                <div className="text-2xl font-bold">
                  {decompositions.reduce((sum, d) => sum + d.subTasks.length, 0)}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <Timer className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Avg Duration</span>
                </div>
                <div className="text-2xl font-bold">
                  {(decompositions.reduce((sum, d) => sum + d.estimatedTotalDuration, 0) / decompositions.length || 0).toFixed(1)}h
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <DollarSign className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Avg Cost</span>
                </div>
                <div className="text-2xl font-bold">
                  {(decompositions.reduce((sum, d) => sum + d.estimatedTotalCost, 0) / decompositions.length || 0).toFixed(3)} AITBC
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Recent Decompositions */}
          <Card>
            <CardHeader>
              <CardTitle>Recent Task Decompositions</CardTitle>
              <CardDescription>
                Latest task decomposition activities
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {decompositions.slice(0, 3).map((decomposition) => (
                  <div key={decomposition.originalTaskId} className="flex items-center justify-between p-4 border rounded-lg">
                    <div className="flex items-center space-x-4">
                      <div className="flex flex-col items-center">
                        <div className="w-8 h-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-sm font-medium">
                          {decomposition.subTasks.length}
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">sub-tasks</p>
                      </div>
                      <div>
                        <p className="font-medium">{decomposition.originalTaskId}</p>
                        <p className="text-sm text-muted-foreground">
                          {decomposition.decompositionStrategy} • {decomposition.estimatedTotalDuration.toFixed(1)}h • {decomposition.estimatedTotalCost.toFixed(3)} AITBC
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="flex items-center space-x-2">
                        <Progress value={getOverallProgress(decomposition)} className="w-16 h-2" />
                        <span className="text-sm font-medium">{getOverallProgress(decomposition).toFixed(0)}%</span>
                      </div>
                      <p className="text-xs text-muted-foreground mt-1">
                        {new Date(decomposition.createdAt).toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="decompositions" className="space-y-6">
          {/* Decomposition Selection */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Decompositions List */}
            <Card>
              <CardHeader>
                <CardTitle>Task Decompositions</CardTitle>
                <CardDescription>
                  Available task decompositions
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {decompositions.map((decomposition) => (
                    <div
                      key={decomposition.originalTaskId}
                      className={`p-4 border rounded-lg cursor-pointer transition-colors ${
                        selectedDecomposition?.originalTaskId === decomposition.originalTaskId
                          ? 'border-primary bg-primary/5'
                          : 'border-border hover:bg-muted/50'
                      }`}
                      onClick={() => setSelectedDecomposition(decomposition)}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <h4 className="font-semibold">{decomposition.originalTaskId}</h4>
                        <div className="flex items-center space-x-2">
                          <Badge variant="outline" className="text-xs">
                            {decomposition.decompositionStrategy}
                          </Badge>
                          <Badge variant="outline" className="text-xs">
                            {(decomposition.confidenceScore * 100).toFixed(0)}% confidence
                          </Badge>
                        </div>
                      </div>
                      <div className="space-y-1 text-sm">
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Sub-tasks:</span>
                          <span className="font-medium">{decomposition.subTasks.length}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Duration:</span>
                          <span className="font-medium">{decomposition.estimatedTotalDuration.toFixed(1)}h</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Cost:</span>
                          <span className="font-medium">{decomposition.estimatedTotalCost.toFixed(3)} AITBC</span>
                        </div>
                      </div>
                      <div className="mt-2">
                        <div className="flex items-center space-x-2">
                          <Progress value={getOverallProgress(decomposition)} className="flex-1 h-2" />
                          <span className="text-xs font-medium">{getOverallProgress(decomposition).toFixed(0)}%</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Decomposition Details */}
            {selectedDecomposition && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2">
                    <GitBranch className="w-5 h-5" />
                    <span>{selectedDecomposition.originalTaskId}</span>
                  </CardTitle>
                  <CardDescription>
                    Detailed task decomposition information
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  {/* Overview */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-sm text-muted-foreground">Strategy</p>
                      <p className="text-lg font-bold capitalize">{selectedDecomposition.decompositionStrategy}</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Confidence</p>
                      <p className="text-lg font-bold">{(selectedDecomposition.confidenceScore * 100).toFixed(1)}%</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Total Duration</p>
                      <p className="text-lg font-bold">{selectedDecomposition.estimatedTotalDuration.toFixed(1)}h</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Total Cost</p>
                      <p className="text-lg font-bold">{selectedDecomposition.estimatedTotalCost.toFixed(3)} AITBC</p>
                    </div>
                  </div>

                  {/* Execution Plan */}
                  <div>
                    <h4 className="font-semibold mb-3">Execution Plan</h4>
                    {renderExecutionPlan(selectedDecomposition.executionPlan)}
                  </div>

                  {/* Sub-tasks */}
                  <div>
                    <h4 className="font-semibold mb-3">Sub-tasks</h4>
                    <div className="space-y-3">
                      {selectedDecomposition.subTasks.map((subTask) => (
                        <div key={subTask.subTaskId} className="p-3 border rounded-lg">
                          <div className="flex items-center justify-between mb-2">
                            <h5 className="font-medium">{subTask.name}</h5>
                            <div className={`w-2 h-2 rounded-full ${getStatusColor(subTask.status)}`}></div>
                          </div>
                          <p className="text-sm text-muted-foreground mb-2">{subTask.description}</p>
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
                </CardContent>
              </Card>
            )}
          </div>
        </TabsContent>

        <TabsContent value="decompose" className="space-y-6">
          {/* Task Decomposition Form */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <GitBranch className="w-5 h-5" />
                <span>Decompose New Task</span>
              </CardTitle>
              <CardDescription>
                Create a new task decomposition with intelligent sub-task splitting
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Task Description</label>
                  <textarea
                    className="w-full p-2 border rounded-lg"
                    rows={3}
                    placeholder="Describe the task to be decomposed..."
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
                        <SelectItem value="io_bound">IO Bound</SelectItem>
                        <SelectItem value="mixed_modal">Mixed Modal</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  
                  <div className="space-y-2">
                    <label className="text-sm font-medium">Decomposition Strategy</label>
                    <Select value={strategy} onValueChange={setStrategy}>
                      <SelectTrigger>
                        <SelectValue placeholder="Select strategy" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="sequential">Sequential</SelectItem>
                        <SelectItem value="parallel">Parallel</SelectItem>
                        <SelectItem value="hierarchical">Hierarchical</SelectItem>
                        <SelectItem value="pipeline">Pipeline</SelectItem>
                        <SelectItem value="adaptive">Adaptive</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                
                <div className="space-y-2">
                  <label className="text-sm font-medium">Estimated Duration (hours)</label>
                  <Input
                    type="number"
                    placeholder="Enter estimated duration"
                    value={estimatedDuration}
                    onChange={(e) => setEstimatedDuration(e.target.value)}
                  />
                </div>
                
                <div className="space-y-2">
                  <label className="text-sm font-medium">GPU Tier</label>
                  <Select value={gpuTier} onValueChange={setGpuTier}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select GPU tier" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="cpu_only">CPU Only</SelectItem>
                      <SelectItem value="low_end_gpu">Low-end GPU</SelectItem>
                      <SelectItem value="mid_range_gpu">Mid-range GPU</SelectItem>
                      <SelectItem value="high_end_gpu">High-end GPU</SelectItem>
                      <SelectItem value="premium_gpu">Premium GPU</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                
                <div className="space-y-2">
                  <label className="text-sm font-medium">Memory Requirement (GB)</label>
                  <Input
                    type="number"
                    placeholder="Enter memory requirement"
                    value={memoryRequirement}
                    onChange={(e) => setMemoryRequirement(e.target.value)}
                  />
                </div>
                
                <div className="space-y-2">
                  <label className="text-sm font-medium">Data Size (MB)</label>
                  <Input
                    type="number"
                    placeholder="Enter data size"
                    value={dataSize}
                    onChange={(e) => setDataSize(e.target.value)}
                  />
                </div>
                
                <div className="space-y-2">
                  <label className="text-sm font-medium">Priority (1-10)</label>
                  <Input
                    type="number"
                    min="1"
                    max="10"
                    placeholder="Enter priority"
                    value={priority}
                    onChange={(e) => setPriority(e.target.value)}
                  />
                </div>
                
                <div className="space-y-2">
                  <label className="text-sm font-medium">Maximum Cost (AITBC)</label>
                  <Input
                    type="number"
                    placeholder="Enter maximum cost"
                    value={maxCost}
                    onChange={(e) => setMaxCost(e.target.value)}
                  />
                </div>
                
                <div className="space-y-2">
                  <label className="text-sm font-medium">Maximum Sub-tasks</label>
                  <Input
                    type="number"
                    placeholder="Enter maximum sub-tasks"
                    value={maxSubtasks}
                    onChange={(e) => setMaxSubtasks(e.target.value)}
                  />
                </div>
              </div>
              
              <Button 
                onClick={handleDecomposeTask} 
                className="w-full" 
                disabled={decomposing}
              >
                {decomposing ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                    Decomposing...
                  </>
                ) : (
                  <>
                    <GitBranch className="w-4 h-4 mr-2" />
                    Decompose Task
                  </>
                )}
              </Button>
            </CardContent>
          </Card>

          {/* Strategy Information */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Settings className="w-5 h-5" />
                <span>Decomposition Strategies</span>
              </CardTitle>
              <CardDescription>
                Available task decomposition strategies
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                <div className="p-4 border rounded-lg">
                  <h4 className="font-semibold mb-2">Sequential</h4>
                  <p className="text-sm text-muted-foreground">
                    Tasks are executed one after another in a linear sequence
                  </p>
                </div>
                <div className="p-4 border rounded-lg">
                  <h4 className="font-semibold mb-2">Parallel</h4>
                  <p className="text-sm text-muted-foreground">
                    Tasks are executed simultaneously when possible
                  </p>
                </div>
                <div className="p-4 border rounded-lg">
                  <h4 className="font-semibold mb-2">Hierarchical</h4>
                  <p className="text-sm text-muted-foreground">
                    Tasks are organized in a hierarchical structure
                  </p>
                </div>
                <div className="p-4 border rounded-lg">
                  <h4 className="font-semibold mb-2">Pipeline</h4>
                  <p className="text-sm text-muted-foreground">
                    Tasks flow through predefined processing stages
                  </p>
                </div>
                <div className="p-4 border rounded-lg">
                  <h4 className="font-semibold mb-2">Adaptive</h4>
                  <p className="text-sm text-muted-foreground">
                    Strategy is selected based on task characteristics
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="aggregations" className="space-y-6">
          {/* Aggregation List */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Layers className="w-5 h-5" />
                <span>Task Aggregations</span>
              </CardTitle>
              <CardDescription>
                Result aggregation configurations for completed sub-tasks
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {aggregations.map((aggregation) => (
                  <div key={aggregation.aggregationId} className="p-4 border rounded-lg">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="font-semibold">{aggregation.aggregationId}</h4>
                      <Badge variant="outline">{aggregation.aggregationType}</Badge>
                    </div>
                    <div className="space-y-2 text-sm">
                      <div>
                        <span className="text-muted-foreground">Parent Task:</span>
                        <p className="font-medium">{aggregation.parentTaskId}</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Input Sub-tasks:</span>
                        <p className="font-medium">{aggregation.inputSubTasks.join(', ')}</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Output Format:</span>
                        <p className="font-medium">{aggregation.outputFormat}</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Function:</span>
                        <p className="font-medium">{aggregation.aggregationFunction}</p>
                      </div>
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

export default TaskDecomposition;
