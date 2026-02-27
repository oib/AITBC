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
  TrendingUp, 
  Brain, 
  Clock, 
  DollarSign, 
  Activity, 
  Zap, 
  Shield, 
  AlertTriangle,
  CheckCircle,
  BarChart3,
  Settings,
  Target,
  Timer,
  Coins
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { useWallet } from '@/hooks/use-wallet';

interface BidStrategy {
  id: string;
  name: string;
  description: string;
  confidenceScore: number;
  successProbability: number;
  expectedWaitTime: number;
  bidPrice: number;
  costEfficiency: number;
  reasoning: string[];
  marketConditions: {
    demandLevel: number;
    priceVolatility: number;
    averagePrice: number;
  };
}

interface MarketAnalysis {
  currentConditions: {
    demandLevel: number;
    priceVolatility: number;
    averageHourlyPrice: number;
    gpuUtilizationRate: number;
  };
  priceTrend: string;
  demandTrend: string;
  volatilityTrend: string;
  futurePrediction: {
    demandLevel: number;
    averageHourlyPrice: number;
  };
  recommendations: string[];
}

interface AgentPreferences {
  preferredStrategy: string;
  riskTolerance: number;
  costSensitivity: number;
  urgencyPreference: number;
  maxWaitTime: number;
  minSuccessProbability: number;
}

const BidStrategy: React.FC = () => {
  const { toast } = useToast();
  const { isConnected, address } = useWallet();
  
  const [strategies, setStrategies] = useState<BidStrategy[]>([]);
  const [selectedStrategy, setSelectedStrategy] = useState<BidStrategy | null>(null);
  const [marketAnalysis, setMarketAnalysis] = useState<MarketAnalysis | null>(null);
  const [agentPreferences, setAgentPreferences] = useState<AgentPreferences>({
    preferredStrategy: 'balanced',
    riskTolerance: 0.5,
    costSensitivity: 0.5,
    urgencyPreference: 0.5,
    maxWaitTime: 3600,
    minSuccessProbability: 0.7
  });
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('strategies');
  
  // Form states
  const [taskUrgency, setTaskUrgency] = useState('medium');
  const [taskDuration, setTaskDuration] = useState('1');
  const [gpuTier, setGpuTier] = useState('mid_range');
  const [maxBudget, setMaxBudget] = useState('0.1');
  const [customStrategy, setCustomStrategy] = useState('');
  
  // Mock data for demonstration
  const mockStrategies: BidStrategy[] = [
    {
      id: 'urgent_bid',
      name: 'Urgent Bid',
      description: 'Aggressive bidding for time-critical tasks',
      confidenceScore: 0.85,
      successProbability: 0.92,
      expectedWaitTime: 120, // seconds
      bidPrice: 0.08,
      costEfficiency: 0.65,
      reasoning: [
        'High market demand increases bid price',
        'Critical urgency requires aggressive bidding',
        'Market conditions require price premium',
        'High risk premium applied due to strategy'
      ],
      marketConditions: {
        demandLevel: 0.75,
        priceVolatility: 0.12,
        averagePrice: 0.05
      }
    },
    {
      id: 'cost_optimized',
      name: 'Cost Optimized',
      description: 'Minimize cost while maintaining reasonable success probability',
      confidenceScore: 0.78,
      successProbability: 0.68,
      expectedWaitTime: 480,
      bidPrice: 0.03,
      costEfficiency: 0.92,
      reasoning: [
        'Low market demand allows for competitive pricing',
        'Cost optimization prioritized over speed',
        'Favorable market conditions enable discount pricing',
        'Budget constraints drive conservative bidding'
      ],
      marketConditions: {
        demandLevel: 0.45,
        priceVolatility: 0.08,
        averagePrice: 0.05
      }
    },
    {
      id: 'balanced',
      name: 'Balanced',
      description: 'Optimal balance between cost and performance',
      confidenceScore: 0.88,
      successProbability: 0.82,
      expectedWaitTime: 240,
      bidPrice: 0.05,
      costEfficiency: 0.78,
      reasoning: [
        'Balanced approach selected based on task requirements',
        'Market conditions support standard pricing',
        'Moderate urgency allows for balanced bidding',
        'Risk premium adjusted for market stability'
      ],
      marketConditions: {
        demandLevel: 0.60,
        priceVolatility: 0.10,
        averagePrice: 0.05
      }
    },
    {
      id: 'aggressive',
      name: 'Aggressive',
      description: 'High-risk, high-reward bidding strategy',
      confidenceScore: 0.72,
      successProbability: 0.88,
      expectedWaitTime: 90,
      bidPrice: 0.10,
      costEfficiency: 0.55,
      reasoning: [
        'High demand detected - consider urgent bidding strategy',
        'Aggressive approach for maximum success probability',
        'Market volatility allows for premium pricing',
        'High risk premium applied due to strategy'
      ],
      marketConditions: {
        demandLevel: 0.85,
        priceVolatility: 0.18,
        averagePrice: 0.05
      }
    },
    {
      id: 'conservative',
      name: 'Conservative',
      description: 'Low-risk bidding with focus on reliability',
      confidenceScore: 0.91,
      successProbability: 0.58,
      expectedWaitTime: 600,
      bidPrice: 0.025,
      costEfficiency: 0.85,
      reasoning: [
        'High volatility - consider conservative bidding',
        'Low risk tolerance drives conservative approach',
        'Market uncertainty requires price caution',
        'Reliability prioritized over speed'
      ],
      marketConditions: {
        demandLevel: 0.35,
        priceVolatility: 0.22,
        averagePrice: 0.05
      }
    }
  ];

  const mockMarketAnalysis: MarketAnalysis = {
    currentConditions: {
      demandLevel: 0.68,
      priceVolatility: 0.12,
      averageHourlyPrice: 0.05,
      gpuUtilizationRate: 0.75
    },
    priceTrend: 'stable',
    demandTrend: 'increasing',
    volatilityTrend: 'stable',
    futurePrediction: {
      demandLevel: 0.72,
      averageHourlyPrice: 0.052
    },
    recommendations: [
      'High demand detected - consider urgent bidding strategy',
      'GPU utilization very high - expect longer wait times',
      'Low prices - good opportunity for cost optimization'
    ]
  };

  useEffect(() => {
    // Load mock data
    setTimeout(() => {
      setStrategies(mockStrategies);
      setMarketAnalysis(mockMarketAnalysis);
      setLoading(false);
    }, 1000);
  }, []);

  const handleCalculateBid = async () => {
    if (!isConnected) {
      toast({
        title: "Wallet Not Connected",
        description: "Please connect your wallet to calculate bids",
        variant: "destructive"
      });
      return;
    }

    if (!taskDuration || !maxBudget) {
      toast({
        title: "Missing Information",
        description: "Please fill in all task details",
        variant: "destructive"
      });
      return;
    }

    try {
      setLoading(true);
      
      // Simulate bid calculation
      toast({
        title: "Calculating Bid Strategy",
        description: "Analyzing market conditions and optimizing bid...",
        variant: "default"
      });

      // Simulate calculation delay
      await new Promise(resolve => setTimeout(resolve, 2000));

      // Select best strategy based on preferences
      const bestStrategy = strategies.find(s => s.id === agentPreferences.preferredStrategy) || 
                           strategies.reduce((best, current) => 
                             current.costEfficiency > best.costEfficiency ? current : best
                           );

      setSelectedStrategy(bestStrategy);
      setActiveTab('strategies');
      
      toast({
        title: "Bid Strategy Calculated",
        description: `Optimal strategy: ${bestStrategy.name}`,
        variant: "default"
      });
    } catch (error) {
      toast({
        title: "Calculation Failed",
        description: "There was an error calculating the bid strategy",
        variant: "destructive"
      });
    } finally {
      setLoading(false);
    }
  };

  const handleUpdatePreferences = async () => {
    if (!isConnected) {
      toast({
        title: "Wallet Not Connected",
        description: "Please connect your wallet to update preferences",
        variant: "destructive"
      });
      return;
    }

    try {
      toast({
        title: "Updating Preferences",
        description: "Saving your agent bidding preferences...",
        variant: "default"
      });

      // Simulate update
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      toast({
        title: "Preferences Updated",
        description: "Your bidding preferences have been saved",
        variant: "default"
      });
    } catch (error) {
      toast({
        title: "Update Failed",
        description: "There was an error updating preferences",
        variant: "destructive"
      });
    }
  };

  const getStrategyColor = (strategy: BidStrategy) => {
    if (strategy.successProbability > 0.8) return 'bg-green-500';
    if (strategy.successProbability > 0.6) return 'bg-yellow-500';
    return 'bg-red-500';
  };

  const getTrendIcon = (trend: string) => {
    switch (trend) {
      case 'increasing': return <TrendingUp className="w-4 h-4 text-green-500" />;
      case 'decreasing': return <TrendingUp className="w-4 h-4 text-red-500 rotate-180" />;
      default: return <Activity className="w-4 h-4 text-blue-500" />;
    }
  };

  if (loading) {
    return (
      <div className="container mx-auto p-6 space-y-6">
        <div className="text-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
          <p className="mt-2 text-muted-foreground">Loading bid strategies...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Bid Strategy Engine</h1>
          <p className="text-muted-foreground mt-2">
            Intelligent bidding algorithms for optimal GPU rental negotiations
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <Badge variant="outline" className="flex items-center space-x-1">
            <Brain className="w-4 h-4" />
            <span>{strategies.length} Strategies</span>
          </Badge>
          <Badge variant="outline" className="flex items-center space-x-1">
            <Activity className="w-4 h-4" />
            <span>Market Active</span>
          </Badge>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="strategies">Strategies</TabsTrigger>
          <TabsTrigger value="market">Market Analysis</TabsTrigger>
          <TabsTrigger value="calculate">Calculate Bid</TabsTrigger>
          <TabsTrigger value="preferences">Preferences</TabsTrigger>
        </TabsList>

        <TabsContent value="strategies" className="space-y-6">
          {/* Selected Strategy Details */}
          {selectedStrategy && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <Target className="w-5 h-5" />
                  <span>Selected Strategy: {selectedStrategy.name}</span>
                </CardTitle>
                <CardDescription>{selectedStrategy.description}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                {/* Strategy Metrics */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  <Card>
                    <CardContent className="pt-6">
                      <div className="flex items-center space-x-2">
                        <DollarSign className="w-4 h-4 text-muted-foreground" />
                        <span className="text-sm font-medium">Bid Price</span>
                      </div>
                      <div className="text-2xl font-bold">{selectedStrategy.bidPrice} AITBC</div>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-6">
                      <div className="flex items-center space-x-2">
                        <CheckCircle className="w-4 h-4 text-muted-foreground" />
                        <span className="text-sm font-medium">Success Rate</span>
                      </div>
                      <div className="text-2xl font-bold">{(selectedStrategy.successProbability * 100).toFixed(1)}%</div>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-6">
                      <div className="flex items-center space-x-2">
                        <Timer className="w-4 h-4 text-muted-foreground" />
                        <span className="text-sm font-medium">Wait Time</span>
                      </div>
                      <div className="text-2xl font-bold">{Math.floor(selectedStrategy.expectedWaitTime / 60)}m</div>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-6">
                      <div className="flex items-center space-x-2">
                        <Coins className="w-4 h-4 text-muted-foreground" />
                        <span className="text-sm font-medium">Efficiency</span>
                      </div>
                      <div className="text-2xl font-bold">{(selectedStrategy.costEfficiency * 100).toFixed(1)}%</div>
                    </CardContent>
                  </Card>
                </div>

                {/* Reasoning */}
                <Card>
                  <CardHeader>
                    <CardTitle>Strategy Reasoning</CardTitle>
                    <CardDescription>
                      Why this strategy was selected
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {selectedStrategy.reasoning.map((reason, index) => (
                        <div key={index} className="flex items-start space-x-2">
                          <div className={`w-2 h-2 rounded-full mt-2 ${getStrategyColor(selectedStrategy)}`}></div>
                          <p className="text-sm">{reason}</p>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>

                {/* Market Conditions */}
                <Card>
                  <CardHeader>
                    <CardTitle>Market Conditions</CardTitle>
                    <CardDescription>
                      Current market analysis
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div>
                        <p className="text-sm text-muted-foreground">Demand Level</p>
                        <div className="flex items-center space-x-2">
                          <Progress value={selectedStrategy.marketConditions.demandLevel * 100} className="flex-1" />
                          <span className="text-sm font-medium">{(selectedStrategy.marketConditions.demandLevel * 100).toFixed(0)}%</span>
                        </div>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Price Volatility</p>
                        <div className="flex items-center space-x-2">
                          <Progress value={selectedStrategy.marketConditions.priceVolatility * 100} className="flex-1" />
                          <span className="text-sm font-medium">{(selectedStrategy.marketConditions.priceVolatility * 100).toFixed(0)}%</span>
                        </div>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Avg Price</p>
                        <p className="text-lg font-bold">{selectedStrategy.marketConditions.averagePrice} AITBC</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </CardContent>
            </Card>
          )}

          {/* All Strategies */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {strategies.map((strategy) => (
              <Card 
                key={strategy.id} 
                className={`cursor-pointer transition-all hover:shadow-lg ${
                  selectedStrategy?.id === strategy.id ? 'ring-2 ring-primary' : ''
                }`}
                onClick={() => setSelectedStrategy(strategy)}
              >
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <CardTitle className="text-lg">{strategy.name}</CardTitle>
                      <CardDescription className="mt-1">{strategy.description}</CardDescription>
                    </div>
                    <div className={`w-3 h-3 rounded-full ${getStrategyColor(strategy)}`}></div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-muted-foreground">Price:</span>
                      <p className="font-medium">{strategy.bidPrice} AITBC</p>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Success:</span>
                      <p className="font-medium">{(strategy.successProbability * 100).toFixed(1)}%</p>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Wait:</span>
                      <p className="font-medium">{Math.floor(strategy.expectedWaitTime / 60)}m</p>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Efficiency:</span>
                      <p className="font-medium">{(strategy.costEfficiency * 100).toFixed(1)}%</p>
                    </div>
                  </div>
                  
                  <div className="flex items-center space-x-2">
                    <div className="flex-1">
                      <div className="flex items-center space-x-1">
                        <span className="text-xs text-muted-foreground">Confidence:</span>
                        <Progress value={strategy.confidenceScore * 100} className="flex-1 h-2" />
                      </div>
                    </div>
                    <span className="text-xs font-medium">{(strategy.confidenceScore * 100).toFixed(0)}%</span>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="market" className="space-y-6">
          {/* Current Market Conditions */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <BarChart3 className="w-5 h-5" />
                <span>Current Market Conditions</span>
              </CardTitle>
              <CardDescription>
                Real-time market analysis and trends
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <div>
                  <p className="text-sm text-muted-foreground">Demand Level</p>
                  <div className="flex items-center space-x-2 mt-1">
                    <Progress value={marketAnalysis!.currentConditions.demandLevel * 100} className="flex-1" />
                    <span className="text-sm font-medium">{(marketAnalysis!.currentConditions.demandLevel * 100).toFixed(0)}%</span>
                  </div>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Price Volatility</p>
                  <div className="flex items-center space-x-2 mt-1">
                    <Progress value={marketAnalysis!.currentConditions.priceVolatility * 100} className="flex-1" />
                    <span className="text-sm font-medium">{(marketAnalysis!.currentConditions.priceVolatility * 100).toFixed(0)}%</span>
                  </div>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Avg Hourly Price</p>
                  <p className="text-lg font-bold mt-1">{marketAnalysis!.currentConditions.averageHourlyPrice} AITBC</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">GPU Utilization</p>
                  <div className="flex items-center space-x-2 mt-1">
                    <Progress value={marketAnalysis!.currentConditions.gpuUtilizationRate * 100} className="flex-1" />
                    <span className="text-sm font-medium">{(marketAnalysis!.currentConditions.gpuUtilizationRate * 100).toFixed(0)}%</span>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Market Trends */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  {getTrendIcon(marketAnalysis!.priceTrend)}
                  <span>Price Trend</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold capitalize">{marketAnalysis!.priceTrend}</p>
                <p className="text-sm text-muted-foreground mt-1">
                  Based on 24-hour analysis
                </p>
              </CardContent>
            </Card>
            
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  {getTrendIcon(marketAnalysis!.demandTrend)}
                  <span>Demand Trend</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold capitalize">{marketAnalysis!.demandTrend}</p>
                <p className="text-sm text-muted-foreground mt-1">
                  Based on recent activity
                </p>
              </CardContent>
            </Card>
            
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  {getTrendIcon(marketAnalysis!.volatilityTrend)}
                  <span>Volatility Trend</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold capitalize">{marketAnalysis!.volatilityTrend}</p>
                <p className="text-sm text-muted-foreground mt-1">
                  Market stability indicator
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Future Prediction */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Zap className="w-5 h-5" />
                <span>24-Hour Prediction</span>
              </CardTitle>
              <CardDescription>
                AI-powered market forecast
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <p className="text-sm text-muted-foreground">Predicted Demand</p>
                  <div className="flex items-center space-x-2 mt-1">
                    <Progress value={marketAnalysis!.futurePrediction.demandLevel * 100} className="flex-1" />
                    <span className="text-sm font-medium">{(marketAnalysis!.futurePrediction.demandLevel * 100).toFixed(0)}%</span>
                  </div>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Predicted Price</p>
                  <p className="text-lg font-bold mt-1">{marketAnalysis!.futurePrediction.averageHourlyPrice} AITBC</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Recommendations */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <AlertTriangle className="w-5 h-5" />
                <span>Market Recommendations</span>
              </CardTitle>
              <CardDescription>
                AI-generated recommendations based on current conditions
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {marketAnalysis!.recommendations.map((recommendation, index) => (
                  <div key={index} className="flex items-start space-x-2">
                    <div className="w-2 h-2 rounded-full bg-blue-500 mt-2"></div>
                    <p className="text-sm">{recommendation}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="calculate" className="space-y-6">
          {/* Task Details */}
          <Card>
            <CardHeader>
              <CardTitle>Task Details</CardTitle>
              <CardDescription>
                Enter task requirements to calculate optimal bid strategy
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Task Urgency</label>
                  <Select value={taskUrgency} onValueChange={setTaskUrgency}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select urgency" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="low">Low</SelectItem>
                      <SelectItem value="medium">Medium</SelectItem>
                      <SelectItem value="high">High</SelectItem>
                      <SelectItem value="critical">Critical</SelectItem>
                    </SelectContent>
                  </Select>
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
                      <SelectItem value="mid_range">Mid-range GPU</SelectItem>
                      <SelectItem value="high_end_gpu">High-end GPU</SelectItem>
                      <SelectItem value="premium_gpu">Premium GPU</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                
                <div className="space-y-2">
                  <label className="text-sm font-medium">Duration (hours)</label>
                  <Input
                    type="number"
                    placeholder="Enter duration"
                    value={taskDuration}
                    onChange={(e) => setTaskDuration(e.target.value)}
                  />
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
              </div>
              
              <Button onClick={handleCalculateBid} className="w-full" disabled={loading}>
                {loading ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                    Calculating...
                  </>
                ) : (
                  <>
                    <Brain className="w-4 h-4 mr-2" />
                    Calculate Optimal Bid
                  </>
                )}
              </Button>
            </CardContent>
          </Card>

          {/* Results */}
          {selectedStrategy && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <CheckCircle className="w-5 h-5 text-green-500" />
                  <span>Optimal Strategy Found</span>
                </CardTitle>
                <CardDescription>
                  Recommended bid strategy for your task
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="flex items-center justify-between p-4 border rounded-lg">
                    <div>
                      <h4 className="font-semibold">{selectedStrategy.name}</h4>
                      <p className="text-sm text-muted-foreground">{selectedStrategy.description}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-2xl font-bold">{selectedStrategy.bidPrice} AITBC</p>
                      <p className="text-sm text-muted-foreground">Bid Price</p>
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="text-center">
                      <p className="text-sm text-muted-foreground">Success Probability</p>
                      <p className="text-lg font-bold">{(selectedStrategy.successProbability * 100).toFixed(1)}%</p>
                    </div>
                    <div className="text-center">
                      <p className="text-sm text-muted-foreground">Expected Wait</p>
                      <p className="text-lg font-bold">{Math.floor(selectedStrategy.expectedWaitTime / 60)}m</p>
                    </div>
                    <div className="text-center">
                      <p className="text-sm text-muted-foreground">Cost Efficiency</p>
                      <p className="text-lg font-bold">{(selectedStrategy.costEfficiency * 100).toFixed(1)}%</p>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="preferences" className="space-y-6">
          {/* Agent Preferences */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Settings className="w-5 h-5" />
                <span>Agent Bidding Preferences</span>
              </CardTitle>
              <CardDescription>
                Configure your agent's bidding behavior and risk tolerance
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-4">
                  <div>
                    <label className="text-sm font-medium">Preferred Strategy</label>
                    <Select value={agentPreferences.preferredStrategy} onValueChange={(value) => 
                      setAgentPreferences(prev => ({ ...prev, preferredStrategy: value }))
                    }>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="urgent_bid">Urgent Bid</SelectItem>
                        <SelectItem value="cost_optimized">Cost Optimized</SelectItem>
                        <SelectItem value="balanced">Balanced</SelectItem>
                        <SelectItem value="aggressive">Aggressive</SelectItem>
                        <SelectItem value="conservative">Conservative</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  
                  <div>
                    <label className="text-sm font-medium">Risk Tolerance</label>
                    <div className="space-y-2">
                      <Input
                        type="range"
                        min="0"
                        max="1"
                        step="0.1"
                        value={agentPreferences.riskTolerance}
                        onChange={(e) => setAgentPreferences(prev => ({ ...prev, riskTolerance: parseFloat(e.target.value) }))}
                      />
                      <div className="flex justify-between text-xs text-muted-foreground">
                        <span>Conservative</span>
                        <span>{(agentPreferences.riskTolerance * 100).toFixed(0)}%</span>
                        <span>Aggressive</span>
                      </div>
                    </div>
                  </div>
                </div>
                
                <div className="space-y-4">
                  <div>
                    <label className="text-sm font-medium">Cost Sensitivity</label>
                    <div className="space-y-2">
                      <Input
                        type="range"
                        min="0"
                        max="1"
                        step="0.1"
                        value={agentPreferences.costSensitivity}
                        onChange={(e) => setAgentPreferences(prev => ({ ...prev, costSensitivity: parseFloat(e.target.value) }))}
                      />
                      <div className="flex justify-between text-xs text-muted-foreground">
                        <span>Performance</span>
                        <span>{(agentPreferences.costSensitivity * 100).toFixed(0)}%</span>
                        <span>Cost</span>
                      </div>
                    </div>
                  </div>
                  
                  <div>
                    <label className="text-sm font-medium">Urgency Preference</label>
                    <div className="space-y-2">
                      <Input
                        type="range"
                        min="0"
                        max="1"
                        step="0.1"
                        value={agentPreferences.urgencyPreference}
                        onChange={(e) => setAgentPreferences(prev => ({ ...prev, urgencyPreference: parseFloat(e.target.value) }))}
                      />
                      <div className="flex justify-between text-xs text-muted-foreground">
                        <span>Relaxed</span>
                        <span>{(agentPreferences.urgencyPreference * 100).toFixed(0)}%</span>
                        <span>Urgent</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="text-sm font-medium">Maximum Wait Time (seconds)</label>
                  <Input
                    type="number"
                    value={agentPreferences.maxWaitTime}
                    onChange={(e) => setAgentPreferences(prev => ({ ...prev, maxWaitTime: parseInt(e.target.value) }))}
                  />
                </div>
                
                <div>
                  <label className="text-sm font-medium">Minimum Success Probability</label>
                  <div className="space-y-2">
                    <Input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={agentPreferences.minSuccessProbability}
                      onChange={(e) => setAgentPreferences(prev => ({ ...prev, minSuccessProbability: parseFloat(e.target.value) }))}
                    />
                    <div className="text-center text-sm text-muted-foreground">
                      {(agentPreferences.minSuccessProbability * 100).toFixed(0)}%
                    </div>
                  </div>
                </div>
              </div>
              
              <Button onClick={handleUpdatePreferences} className="w-full">
                <Settings className="w-4 h-4 mr-2" />
                Save Preferences
              </Button>
            </CardContent>
          </Card>

          {/* Strategy Preview */}
          <Card>
            <CardHeader>
              <CardTitle>Strategy Impact Preview</CardTitle>
              <CardDescription>
                How your preferences affect bidding behavior
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <Alert>
                  <Shield className="h-4 w-4" />
                  <AlertTitle>Risk Management</AlertTitle>
                  <AlertDescription>
                    Your risk tolerance of {(agentPreferences.riskTolerance * 100).toFixed(0)}% will favor 
                    {agentPreferences.riskTolerance > 0.6 ? ' aggressive bidding with higher success rates' : ' conservative bidding with better cost efficiency'}.
                  </AlertDescription>
                </Alert>
                
                <Alert>
                  <DollarSign className="h-4 w-4" />
                  <AlertTitle>Cost Optimization</AlertTitle>
                  <AlertDescription>
                    Cost sensitivity of {(agentPreferences.costSensitivity * 100).toFixed(0)}% will prioritize 
                    {agentPreferences.costSensitivity > 0.6 ? ' lower prices over faster execution' : ' faster execution over cost savings'}.
                  </AlertDescription>
                </Alert>
                
                <Alert>
                  <Timer className="h-4 w-4" />
                  <AlertTitle>Time Efficiency</AlertTitle>
                  <AlertDescription>
                    Urgency preference of {(agentPreferences.urgencyPreference * 100).toFixed(0)}% will focus on 
                    {agentPreferences.urgencyPreference > 0.6 ? ' minimizing wait times' : ' optimizing for cost and success rate'}.
                  </AlertDescription>
                </Alert>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default BidStrategy;
