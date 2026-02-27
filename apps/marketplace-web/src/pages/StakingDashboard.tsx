import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Progress } from '@/components/ui/progress';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Separator } from '@/components/ui/separator';
import {
  TrendingUp,
  TrendingDown,
  Wallet,
  Clock,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Calculator,
  Shield,
  Zap,
  Star,
  Info,
  ArrowUpRight,
  ArrowDownRight,
  Coins,
  BarChart3,
  PieChart,
  Activity
} from 'lucide-react';
import { useWallet } from '@/hooks/use-wallet';
import { useToast } from '@/hooks/use-toast';
import { formatDistanceToNow, format } from 'date-fns';

interface Stake {
  stake_id: string;
  staker_address: string;
  agent_wallet: string;
  amount: number;
  lock_period: number;
  start_time: string;
  end_time: string;
  status: 'active' | 'unbonding' | 'completed' | 'slashed';
  accumulated_rewards: number;
  last_reward_time: string;
  current_apy: number;
  agent_tier: 'bronze' | 'silver' | 'gold' | 'platinum' | 'diamond';
  performance_multiplier: number;
  auto_compound: boolean;
  unbonding_time?: string;
  early_unbond_penalty: number;
  lock_bonus_multiplier: number;
}

interface AgentMetrics {
  agent_wallet: string;
  total_staked: number;
  staker_count: number;
  total_rewards_distributed: number;
  average_accuracy: number;
  total_submissions: number;
  successful_submissions: number;
  success_rate: number;
  current_tier: 'bronze' | 'silver' | 'gold' | 'platinum' | 'diamond';
  tier_score: number;
  reputation_score: number;
  last_update_time: string;
  average_response_time?: number;
  energy_efficiency_score?: number;
}

interface StakingPool {
  agent_wallet: string;
  total_staked: number;
  total_rewards: number;
  pool_apy: number;
  staker_count: number;
  active_stakers: string[];
  last_distribution_time: string;
  min_stake_amount: number;
  max_stake_amount: number;
  auto_compound_enabled: boolean;
  pool_performance_score: number;
  volatility_score: number;
}

const StakingDashboard: React.FC = () => {
  const { address, isConnected } = useWallet();
  const { toast } = useToast();
  
  const [stakes, setStakes] = useState<Stake[]>([]);
  const [supportedAgents, setSupportedAgents] = useState<AgentMetrics[]>([]);
  const [stakingPools, setStakingPools] = useState<StakingPool[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('my-stakes');
  const [showCreateStakeModal, setShowCreateStakeModal] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<AgentMetrics | null>(null);
  const [stakeForm, setStakeForm] = useState({
    agent_wallet: '',
    amount: '',
    lock_period: '30',
    auto_compound: false
  });
  const [totalRewards, setTotalRewards] = useState(0);
  const [totalStaked, setTotalStaked] = useState(0);

  // Load data on component mount
  useEffect(() => {
    if (isConnected) {
      loadMyStakes();
      loadMyRewards();
    }
    loadSupportedAgents();
    loadStakingPools();
  }, [isConnected]);

  const loadMyStakes = async () => {
    try {
      const response = await fetch('/api/v1/staking/my-positions', {
        headers: { 'Authorization': `Bearer ${address}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setStakes(data);
        
        // Calculate total staked
        const total = data.reduce((sum: number, stake: Stake) => sum + stake.amount, 0);
        setTotalStaked(total);
      }
    } catch (error) {
      console.error('Error loading stakes:', error);
    }
  };

  const loadMyRewards = async () => {
    try {
      const response = await fetch('/api/v1/staking/my-rewards?period=monthly', {
        headers: { 'Authorization': `Bearer ${address}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setTotalRewards(data.total_rewards);
      }
    } catch (error) {
      console.error('Error loading rewards:', error);
    }
  };

  const loadSupportedAgents = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/staking/agents/supported?limit=50');
      
      if (response.ok) {
        const data = await response.json();
        setSupportedAgents(data.agents);
      }
    } catch (error) {
      console.error('Error loading agents:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadStakingPools = async () => {
    try {
      const response = await fetch('/api/v1/staking/pools');
      
      if (response.ok) {
        const data = await response.json();
        setStakingPools(data);
      }
    } catch (error) {
      console.error('Error loading pools:', error);
    }
  };

  const handleCreateStake = async () => {
    if (!isConnected) {
      toast({
        title: 'Wallet Required',
        description: 'Please connect your wallet to create stakes',
        variant: 'destructive'
      });
      return;
    }

    try {
      const response = await fetch('/api/v1/stake', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${address}`
        },
        body: JSON.stringify(stakeForm)
      });

      if (response.ok) {
        const newStake = await response.json();
        setStakes(prev => [newStake, ...prev]);
        setShowCreateStakeModal(false);
        setStakeForm({ agent_wallet: '', amount: '', lock_period: '30', auto_compound: false });
        
        toast({
          title: 'Stake Created',
          description: `Successfully staked ${stakeForm.amount} AITBC`,
        });
        
        // Reload data
        loadMyStakes();
        loadStakingPools();
      } else {
        throw new Error('Failed to create stake');
      }
    } catch (error) {
      console.error('Error creating stake:', error);
      toast({
        title: 'Error',
        description: 'Failed to create stake',
        variant: 'destructive'
      });
    }
  };

  const handleUnbondStake = async (stakeId: string) => {
    try {
      const response = await fetch(`/api/v1/stake/${stakeId}/unbond`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${address}` }
      });

      if (response.ok) {
        toast({
          title: 'Unbonding Initiated',
          description: 'Your stake is now in the unbonding period',
        });
        
        // Reload stakes
        loadMyStakes();
      } else {
        throw new Error('Failed to unbond stake');
      }
    } catch (error) {
      console.error('Error unbonding stake:', error);
      toast({
        title: 'Error',
        description: 'Failed to unbond stake',
        variant: 'destructive'
      });
    }
  };

  const handleCompleteUnbonding = async (stakeId: string) => {
    try {
      const response = await fetch(`/api/v1/stake/${stakeId}/complete`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${address}` }
      });

      if (response.ok) {
        const result = await response.json();
        toast({
          title: 'Unbonding Completed',
          description: `Received ${result.total_amount + result.total_rewards} AITBC`,
        });
        
        // Reload stakes and rewards
        loadMyStakes();
        loadMyRewards();
      } else {
        throw new Error('Failed to complete unbonding');
      }
    } catch (error) {
      console.error('Error completing unbonding:', error);
      toast({
        title: 'Error',
        description: 'Failed to complete unbonding',
        variant: 'destructive'
      });
    }
  };

  const getTierColor = (tier: string) => {
    const colors = {
      bronze: 'bg-orange-100 text-orange-800 border-orange-200',
      silver: 'bg-gray-100 text-gray-800 border-gray-200',
      gold: 'bg-yellow-100 text-yellow-800 border-yellow-200',
      platinum: 'bg-purple-100 text-purple-800 border-purple-200',
      diamond: 'bg-blue-100 text-blue-800 border-blue-200'
    };
    return colors[tier as keyof typeof colors] || colors.bronze;
  };

  const getStatusColor = (status: string) => {
    const colors = {
      active: 'bg-green-100 text-green-800',
      unbonding: 'bg-yellow-100 text-yellow-800',
      completed: 'bg-blue-100 text-blue-800',
      slashed: 'bg-red-100 text-red-800'
    };
    return colors[status as keyof typeof colors] || colors.active;
  };

  const getTimeRemaining = (endTime: string) => {
    const endDate = new Date(endTime);
    const now = new Date();
    const timeRemaining = endDate.getTime() - now.getTime();
    
    if (timeRemaining <= 0) return 'Expired';
    
    return formatDistanceToNow(endDate, { addSuffix: true });
  };

  const calculateAPY = (agent: AgentMetrics, lockPeriod: number) => {
    const baseAPY = 5.0;
    const tierMultipliers = {
      bronze: 1.0,
      silver: 1.2,
      gold: 1.5,
      platinum: 2.0,
      diamond: 3.0
    };
    
    const lockMultipliers = {
      30: 1.1,
      90: 1.25,
      180: 1.5,
      365: 2.0
    };
    
    const tierMultiplier = tierMultipliers[agent.current_tier as keyof typeof tierMultipliers];
    const lockMultiplier = lockMultipliers[lockPeriod as keyof typeof lockMultipliers] || 1.0;
    
    const apy = baseAPY * tierMultiplier * lockMultiplier;
    return Math.min(apy, 20.0); // Cap at 20%
  };

  const getRiskLevel = (agent: AgentMetrics) => {
    if (agent.success_rate >= 90 && agent.average_accuracy >= 90) return 'low';
    if (agent.success_rate >= 70 && agent.average_accuracy >= 70) return 'medium';
    return 'high';
  };

  const getRiskColor = (risk: string) => {
    const colors = {
      low: 'text-green-600',
      medium: 'text-yellow-600',
      high: 'text-red-600'
    };
    return colors[risk as keyof typeof colors] || colors.medium;
  };

  if (loading) {
    return (
      <div className="container mx-auto py-8">
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto py-8 space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold">Staking Dashboard</h1>
          <p className="text-muted-foreground">
            Stake AITBC tokens on AI agents and earn rewards based on performance
          </p>
        </div>
        {isConnected && (
          <Button onClick={() => setShowCreateStakeModal(true)}>
            Create Stake
          </Button>
        )}
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-muted-foreground">Total Staked</p>
                <p className="text-2xl font-bold">{totalStaked.toLocaleString()}</p>
                <p className="text-xs text-muted-foreground">AITBC</p>
              </div>
              <Coins className="h-8 w-8 text-blue-600" />
            </div>
          </CardContent>
        </Card>
        
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-muted-foreground">Total Rewards</p>
                <p className="text-2xl font-bold">{totalRewards.toLocaleString()}</p>
                <p className="text-xs text-muted-foreground">AITBC</p>
              </div>
              <TrendingUp className="h-8 w-8 text-green-600" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-muted-foreground">Active Stakes</p>
                <p className="text-2xl font-bold">{stakes.filter(s => s.status === 'active').length}</p>
                <p className="text-xs text-muted-foreground">Positions</p>
              </div>
              <Shield className="h-8 w-8 text-purple-600" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-muted-foreground">Average APY</p>
                <p className="text-2xl font-bold">
                  {stakes.length > 0 
                    ? (stakes.reduce((sum, s) => sum + s.current_apy, 0) / stakes.length).toFixed(1)
                    : '0.0'
                  }%
                </p>
                <p className="text-xs text-muted-foreground">Annual Yield</p>
              </div>
              <BarChart3 className="h-8 w-8 text-orange-600" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="my-stakes">My Stakes</TabsTrigger>
          <TabsTrigger value="agents">Available Agents</TabsTrigger>
          <TabsTrigger value="pools">Staking Pools</TabsTrigger>
          {isConnected && <TabsTrigger value="rewards">Rewards</TabsTrigger>}
        </TabsList>

        {/* My Stakes Tab */}
        <TabsContent value="my-stakes" className="space-y-4">
          {!isConnected ? (
            <Alert>
              <Wallet className="h-4 w-4" />
              <AlertDescription>
                Connect your wallet to view your staking positions
              </AlertDescription>
            </Alert>
          ) : stakes.length === 0 ? (
            <div className="text-center py-12">
              <Shield className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-semibold mb-2">No Stakes Found</h3>
              <p className="text-muted-foreground mb-4">
                Start staking on AI agents to earn rewards
              </p>
              <Button onClick={() => setShowCreateStakeModal(true)}>
                Create Your First Stake
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              {stakes.map((stake) => (
                <Card key={stake.stake_id}>
                  <CardHeader>
                    <div className="flex justify-between items-start">
                      <div className="space-y-2">
                        <CardTitle className="text-lg">
                          {stake.agent_wallet.slice(0, 8)}...{stake.agent_wallet.slice(-6)}
                        </CardTitle>
                        <div className="flex gap-2">
                          <Badge className={getTierColor(stake.agent_tier)}>
                            {stake.agent_tier.charAt(0).toUpperCase() + stake.agent_tier.slice(1)}
                          </Badge>
                          <Badge className={getStatusColor(stake.status)}>
                            {stake.status.charAt(0).toUpperCase() + stake.status.slice(1)}
                          </Badge>
                          {stake.auto_compound && (
                            <Badge variant="secondary">
                              <Zap className="h-3 w-3 mr-1" />
                              Auto-Compound
                            </Badge>
                          )}
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-2xl font-bold text-blue-600">
                          {stake.amount.toLocaleString()}
                        </p>
                        <p className="text-sm text-muted-foreground">AITBC</p>
                        <p className="text-sm font-medium text-green-600">
                          {stake.current_apy.toFixed(1)}% APY
                        </p>
                      </div>
                    </div>
                  </CardHeader>

                  <CardContent className="space-y-4">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      <div>
                        <p className="text-sm text-muted-foreground">Lock Period</p>
                        <p className="font-medium">{stake.lock_period} days</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Time Remaining</p>
                        <p className="font-medium">{getTimeRemaining(stake.end_time)}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Accumulated Rewards</p>
                        <p className="font-medium text-green-600">
                          {stake.accumulated_rewards.toFixed(2)} AITBC
                        </p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Performance Multiplier</p>
                        <p className="font-medium">{stake.performance_multiplier}x</p>
                      </div>
                    </div>

                    {/* Progress bar for lock period */}
                    <div>
                      <div className="flex justify-between text-sm mb-1">
                        <span className="text-muted-foreground">Lock Progress</span>
                        <span className="font-medium">
                          {Math.max(0, 100 - ((new Date(stake.end_time).getTime() - Date.now()) / (stake.lock_period * 24 * 60 * 60 * 1000) * 100)).toFixed(1)}%
                        </span>
                      </div>
                      <Progress 
                        value={Math.max(0, 100 - ((new Date(stake.end_time).getTime() - Date.now()) / (stake.lock_period * 24 * 60 * 60 * 1000) * 100))} 
                        className="h-2"
                      />
                    </div>
                  </CardContent>

                  <CardFooter className="flex gap-2">
                    {stake.status === 'active' && new Date(stake.end_time) <= new Date() && (
                      <Button 
                        variant="outline" 
                        onClick={() => handleUnbondStake(stake.stake_id)}
                      >
                        <Clock className="h-4 w-4 mr-2" />
                        Initiate Unbonding
                      </Button>
                    )}
                    
                    {stake.status === 'unbonding' && (
                      <Button 
                        onClick={() => handleCompleteUnbonding(stake.stake_id)}
                      >
                        <CheckCircle className="h-4 w-4 mr-2" />
                        Complete Unbonding
                      </Button>
                    )}
                    
                    <Button variant="outline" size="sm">
                      View Details
                    </Button>
                  </CardFooter>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* Available Agents Tab */}
        <TabsContent value="agents" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {supportedAgents.map((agent) => (
              <Card key={agent.agent_wallet} className="hover:shadow-lg transition-shadow">
                <CardHeader>
                  <div className="flex justify-between items-start">
                    <div className="space-y-2">
                      <CardTitle className="text-lg">
                        {agent.agent_wallet.slice(0, 8)}...{agent.agent_wallet.slice(-6)}
                      </CardTitle>
                      <div className="flex gap-2">
                        <Badge className={getTierColor(agent.current_tier)}>
                          {agent.current_tier.charAt(0).toUpperCase() + agent.current_tier.slice(1)}
                        </Badge>
                        <Badge className={getRiskColor(getRiskLevel(agent))}>
                          {getRiskLevel(agent).toUpperCase()} RISK
                        </Badge>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-2xl font-bold text-blue-600">
                        {calculateAPY(agent, 30).toFixed(1)}%
                      </p>
                      <p className="text-sm text-muted-foreground">APY</p>
                    </div>
                  </div>
                </CardHeader>

                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-sm text-muted-foreground">Total Staked</p>
                      <p className="font-medium">{agent.total_staked.toLocaleString()}</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Stakers</p>
                      <p className="font-medium">{agent.staker_count}</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Accuracy</p>
                      <p className="font-medium">{agent.average_accuracy.toFixed(1)}%</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Success Rate</p>
                      <p className="font-medium">{agent.success_rate.toFixed(1)}%</p>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Total Submissions</span>
                      <span className="font-medium">{agent.total_submissions}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Rewards Distributed</span>
                      <span className="font-medium text-green-600">
                        {agent.total_rewards_distributed.toLocaleString()} AITBC
                      </span>
                    </div>
                  </div>

                  {/* Performance indicators */}
                  <div className="flex items-center gap-2 text-sm">
                    <Activity className="h-4 w-4 text-blue-600" />
                    <span>Performance Score: {agent.tier_score.toFixed(1)}</span>
                  </div>
                </CardContent>

                <CardFooter>
                  <Button 
                    className="w-full"
                    onClick={() => {
                      setSelectedAgent(agent);
                      setStakeForm(prev => ({ ...prev, agent_wallet: agent.agent_wallet }));
                      setShowCreateStakeModal(true);
                    }}
                    disabled={!isConnected}
                  >
                    {isConnected ? 'Stake on Agent' : 'Connect Wallet'}
                  </Button>
                </CardFooter>
              </Card>
            ))}
          </div>
        </TabsContent>

        {/* Staking Pools Tab */}
        <TabsContent value="pools" className="space-y-4">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Agent</TableHead>
                <TableHead>Total Staked</TableHead>
                <TableHead>Pool APY</TableHead>
                <TableHead>Stakers</TableHead>
                <TableHead>Total Rewards</TableHead>
                <TableHead>Performance</TableHead>
                <TableHead>Volatility</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {stakingPools.map((pool) => (
                <TableRow key={pool.agent_wallet}>
                  <TableCell className="font-mono">
                    {pool.agent_wallet.slice(0, 8)}...{pool.agent_wallet.slice(-6)}
                  </TableCell>
                  <TableCell>{pool.total_staked.toLocaleString()} AITBC</TableCell>
                  <TableCell>
                    <span className="text-green-600 font-medium">{pool.pool_apy.toFixed(1)}%</span>
                  </TableCell>
                  <TableCell>{pool.staker_count}</TableCell>
                  <TableCell className="text-green-600">
                    {pool.total_rewards.toLocaleString()} AITBC
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Progress value={pool.pool_performance_score} className="w-16 h-2" />
                      <span className="text-sm">{pool.pool_performance_score.toFixed(0)}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant={pool.volatility_score < 30 ? 'secondary' : pool.volatility_score < 70 ? 'default' : 'destructive'}>
                      {pool.volatility_score < 30 ? 'Low' : pool.volatility_score < 70 ? 'Medium' : 'High'}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TabsContent>

        {/* Rewards Tab */}
        <TabsContent value="rewards" className="space-y-4">
          {!isConnected ? (
            <Alert>
              <Wallet className="h-4 w-4" />
              <AlertDescription>
                Connect your wallet to view your rewards
              </AlertDescription>
            </Alert>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Coins className="h-5 w-5" />
                    Reward Summary
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Total Earned</span>
                      <span className="font-bold text-green-600">
                        {totalRewards.toLocaleString()} AITBC
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Pending Rewards</span>
                      <span className="font-bold">
                        {stakes.reduce((sum, s) => sum + s.accumulated_rewards, 0).toLocaleString()} AITBC
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Average APY</span>
                      <span className="font-bold">
                        {stakes.length > 0 
                          ? (stakes.reduce((sum, s) => sum + s.current_apy, 0) / stakes.length).toFixed(1)
                          : '0.0'
                        }%
                      </span>
                    </div>
                  </div>
                  
                  <Separator />
                  
                  <Button className="w-full">
                    Claim All Rewards
                  </Button>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <PieChart className="h-5 w-5" />
                    Reward History
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-center py-8 text-muted-foreground">
                    <Info className="h-8 w-8 mx-auto mb-2" />
                    <p>Reward history will be available soon</p>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Create Stake Modal */}
      {showCreateStakeModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <Card className="max-w-md w-full">
            <CardHeader>
              <CardTitle>Create New Stake</CardTitle>
              <CardDescription>
                Stake AITBC tokens on an AI agent to earn rewards
              </CardDescription>
            </CardHeader>

            <CardContent className="space-y-4">
              <div>
                <label className="text-sm font-medium">Agent</label>
                <Select 
                  value={stakeForm.agent_wallet} 
                  onValueChange={(value) => setStakeForm(prev => ({ ...prev, agent_wallet: value }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select an agent" />
                  </SelectTrigger>
                  <SelectContent>
                    {supportedAgents.map((agent) => (
                      <SelectItem key={agent.agent_wallet} value={agent.agent_wallet}>
                        <div className="flex items-center justify-between w-full">
                          <span>{agent.agent_wallet.slice(0, 8)}...{agent.agent_wallet.slice(-6)}</span>
                          <span className="text-green-600">{calculateAPY(agent, parseInt(stakeForm.lock_period)).toFixed(1)}% APY</span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <label className="text-sm font-medium">Amount (AITBC)</label>
                <Input
                  type="number"
                  placeholder="100.0"
                  value={stakeForm.amount}
                  onChange={(e) => setStakeForm(prev => ({ ...prev, amount: e.target.value }))}
                  min="100"
                  max="100000"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Min: 100 AITBC, Max: 100,000 AITBC
                </p>
              </div>

              <div>
                <label className="text-sm font-medium">Lock Period</label>
                <Select 
                  value={stakeForm.lock_period} 
                  onValueChange={(value) => setStakeForm(prev => ({ ...prev, lock_period: value }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="30">30 days (1.1x multiplier)</SelectItem>
                    <SelectItem value="90">90 days (1.25x multiplier)</SelectItem>
                    <SelectItem value="180">180 days (1.5x multiplier)</SelectItem>
                    <SelectItem value="365">365 days (2.0x multiplier)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {selectedAgent && (
                <div className="bg-muted p-3 rounded">
                  <h4 className="font-medium mb-2">Estimated Returns</h4>
                  <div className="space-y-1 text-sm">
                    <div className="flex justify-between">
                      <span>Base APY:</span>
                      <span>5.0%</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Tier Multiplier:</span>
                      <span>{selectedAgent.current_tier} tier</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Lock Multiplier:</span>
                      <span>{stakeForm.lock_period === '30' ? '1.1x' : stakeForm.lock_period === '90' ? '1.25x' : stakeForm.lock_period === '180' ? '1.5x' : '2.0x'}</span>
                    </div>
                    <div className="flex justify-between font-bold">
                      <span>Estimated APY:</span>
                      <span className="text-green-600">
                        {calculateAPY(selectedAgent, parseInt(stakeForm.lock_period)).toFixed(1)}%
                      </span>
                    </div>
                  </div>
                </div>
              )}

              <div className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  id="auto-compound"
                  checked={stakeForm.auto_compound}
                  onChange={(e) => setStakeForm(prev => ({ ...prev, auto_compound: e.target.checked }))}
                />
                <label htmlFor="auto-compound" className="text-sm">
                  Enable auto-compounding
                </label>
              </div>
            </CardContent>

            <CardFooter className="flex gap-2">
              <Button 
                className="flex-1"
                onClick={handleCreateStake}
                disabled={!stakeForm.agent_wallet || !stakeForm.amount || parseFloat(stakeForm.amount) < 100}
              >
                Create Stake
              </Button>
              <Button variant="outline" onClick={() => setShowCreateStakeModal(false)}>
                Cancel
              </Button>
            </CardFooter>
          </Card>
        </div>
      )}
    </div>
  );
};

export default StakingDashboard;
