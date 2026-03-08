import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Progress } from '@/components/ui/progress';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  TrendingUp,
  TrendingDown,
  Users,
  DollarSign,
  Activity,
  PieChart,
  BarChart3,
  Zap,
  Shield,
  Target,
  Coins,
  Calendar,
  Download,
  RefreshCw,
  Globe,
  Cpu,
  Database,
  Network,
  Award,
  Star,
  AlertTriangle,
  CheckCircle,
  Info
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { formatDistanceToNow } from 'date-fns';

interface EcosystemOverview {
  total_developers: number;
  total_agents: number;
  total_stakers: number;
  total_bounties: number;
  active_bounties: number;
  completed_bounties: number;
  total_value_locked: number;
  total_rewards_distributed: number;
  daily_volume: number;
  weekly_growth: number;
  monthly_growth: number;
  ecosystem_health_score: number;
  last_updated: string;
}

interface DeveloperEarnings {
  address: string;
  total_earned: number;
  bounties_completed: number;
  success_rate: number;
  tier: string;
  weekly_earnings: number;
  monthly_earnings: number;
  rank: number;
  growth_rate: number;
}

interface AgentUtilization {
  agent_address: string;
  total_submissions: number;
  success_rate: number;
  average_accuracy: number;
  total_earnings: number;
  utilization_rate: number;
  current_tier: string;
  performance_score: number;
  last_active: string;
}

interface TreasuryAllocation {
  category: string;
  amount: number;
  percentage: number;
  description: string;
  trend: 'up' | 'down' | 'stable';
  monthly_change: number;
}

interface StakingMetrics {
  total_staked: number;
  total_stakers: number;
  average_stake_amount: number;
  total_rewards_distributed: number;
  average_apy: number;
  staking_participation_rate: number;
  top_stakers: Array<{
    address: string;
    amount: number;
    rewards: number;
  }>;
  pool_distribution: Array<{
    agent_address: string;
    total_staked: number;
    staker_count: number;
    apy: number;
  }>;
}

interface BountyAnalytics {
  total_bounties: number;
  active_bounties: number;
  completed_bounties: number;
  average_completion_time: number;
  success_rate: number;
  total_value: number;
  category_distribution: Array<{
    category: string;
    count: number;
    value: number;
  }>;
  difficulty_distribution: Array<{
    difficulty: string;
    count: number;
    success_rate: number;
  }>;
  completion_trends: Array<{
    date: string;
    completed: number;
    value: number;
  }>;
}

const EcosystemDashboard: React.FC = () => {
  const { toast } = useToast();
  
  const [overview, setOverview] = useState<EcosystemOverview | null>(null);
  const [developerEarnings, setDeveloperEarnings] = useState<DeveloperEarnings[]>([]);
  const [agentUtilization, setAgentUtilization] = useState<AgentUtilization[]>([]);
  const [treasuryAllocation, setTreasuryAllocation] = useState<TreasuryAllocation[]>([]);
  const [stakingMetrics, setStakingMetrics] = useState<StakingMetrics | null>(null);
  const [bountyAnalytics, setBountyAnalytics] = useState<BountyAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');
  const [period, setPeriod] = useState('weekly');
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());

  // Load ecosystem data on component mount
  useEffect(() => {
    loadEcosystemData();
  }, [period]);

  const loadEcosystemData = async () => {
    try {
      setLoading(true);
      
      // Load overview
      const overviewResponse = await fetch('/api/v1/ecosystem/overview');
      if (overviewResponse.ok) {
        const overviewData = await overviewResponse.json();
        setOverview(overviewData);
      }

      // Load developer earnings
      const earningsResponse = await fetch(`/api/v1/ecosystem/developer-earnings?period=${period}&limit=50`);
      if (earningsResponse.ok) {
        const earningsData = await earningsResponse.json();
        setDeveloperEarnings(earningsData);
      }

      // Load agent utilization
      const utilizationResponse = await fetch(`/api/v1/ecosystem/agent-utilization?period=${period}&limit=50`);
      if (utilizationResponse.ok) {
        const utilizationData = await utilizationResponse.json();
        setAgentUtilization(utilizationData);
      }

      // Load treasury allocation
      const treasuryResponse = await fetch('/api/v1/ecosystem/treasury-allocation');
      if (treasuryResponse.ok) {
        const treasuryData = await treasuryResponse.json();
        setTreasuryAllocation(treasuryData);
      }

      // Load staking metrics
      const stakingResponse = await fetch('/api/v1/ecosystem/staking-metrics');
      if (stakingResponse.ok) {
        const stakingData = await stakingResponse.json();
        setStakingMetrics(stakingData);
      }

      // Load bounty analytics
      const bountyResponse = await fetch('/api/v1/ecosystem/bounty-analytics');
      if (bountyResponse.ok) {
        const bountyData = await bountyResponse.json();
        setBountyAnalytics(bountyData);
      }

      setLastUpdated(new Date());
    } catch (error) {
      console.error('Error loading ecosystem data:', error);
      toast({
        title: 'Error',
        description: 'Failed to load ecosystem data',
        variant: 'destructive'
      });
    } finally {
      setLoading(false);
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

  const getHealthColor = (score: number) => {
    if (score >= 80) return 'text-green-600';
    if (score >= 60) return 'text-yellow-600';
    return 'text-red-600';
  };

  const getHealthIcon = (score: number) => {
    if (score >= 80) return <CheckCircle className="h-5 w-5 text-green-600" />;
    if (score >= 60) return <AlertTriangle className="h-5 w-5 text-yellow-600" />;
    return <AlertTriangle className="h-5 w-5 text-red-600" />;
  };

  const getTrendIcon = (trend: string) => {
    if (trend === 'up') return <TrendingUp className="h-4 w-4 text-green-600" />;
    if (trend === 'down') return <TrendingDown className="h-4 w-4 text-red-600" />;
    return <div className="h-4 w-4" />;
  };

  const exportData = async (dataType: string) => {
    try {
      const response = await fetch(`/api/v1/ecosystem/export?format=csv&type=${dataType}`);
      
      if (response.ok) {
        const data = await response.json();
        // Create download link
        const link = document.createElement('a');
        link.href = data.url;
        link.download = `${dataType}_export_${period}.csv`;
        link.click();
        
        toast({
          title: 'Export Started',
          description: `${dataType} data is being downloaded`,
        });
      }
    } catch (error) {
      console.error('Error exporting data:', error);
      toast({
        title: 'Error',
        description: 'Failed to export data',
        variant: 'destructive'
      });
    }
  };

  const refreshData = () => {
    loadEcosystemData();
  };

  if (loading && !overview) {
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
          <h1 className="text-3xl font-bold">Ecosystem Dashboard</h1>
          <p className="text-muted-foreground">
            Comprehensive overview of the AITBC ecosystem health and performance
          </p>
        </div>
        <div className="flex gap-2">
          <Select value={period} onValueChange={setPeriod}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="daily">Daily</SelectItem>
              <SelectItem value="weekly">Weekly</SelectItem>
              <SelectItem value="monthly">Monthly</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" onClick={refreshData}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          <Button variant="outline" onClick={() => exportData('ecosystem')}>
            <Download className="h-4 w-4 mr-2" />
            Export
          </Button>
        </div>
      </div>

      {/* Ecosystem Health Score */}
      {overview && (
        <Card className="bg-gradient-to-r from-blue-50 to-purple-50">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                {getHealthIcon(overview.ecosystem_health_score)}
                <div>
                  <CardTitle className="text-2xl">Ecosystem Health</CardTitle>
                  <CardDescription>
                    Overall system health and performance indicator
                  </CardDescription>
                </div>
              </div>
              <div className="text-right">
                <p className={`text-4xl font-bold ${getHealthColor(overview.ecosystem_health_score)}`}>
                  {overview.ecosystem_health_score}
                </p>
                <p className="text-sm text-muted-foreground">Health Score</p>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="text-center">
                <p className="text-2xl font-bold text-blue-600">{overview.total_developers.toLocaleString()}</p>
                <p className="text-sm text-muted-foreground">Developers</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-green-600">{overview.total_agents.toLocaleString()}</p>
                <p className="text-sm text-muted-foreground">AI Agents</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-purple-600">{overview.total_stakers.toLocaleString()}</p>
                <p className="text-sm text-muted-foreground">Stakers</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-orange-600">{overview.total_bounties.toLocaleString()}</p>
                <p className="text-sm text-muted-foreground">Bounties</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Key Metrics */}
      {overview && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Total Value Locked</p>
                  <p className="text-2xl font-bold">{overview.total_value_locked.toLocaleString()}</p>
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
                  <p className="text-sm font-medium text-muted-foreground">Rewards Distributed</p>
                  <p className="text-2xl font-bold">{overview.total_rewards_distributed.toLocaleString()}</p>
                  <p className="text-xs text-muted-foreground">AITBC</p>
                </div>
                <Award className="h-8 w-8 text-green-600" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Daily Volume</p>
                  <p className="text-2xl font-bold">{overview.daily_volume.toLocaleString()}</p>
                  <p className="text-xs text-muted-foreground">AITBC</p>
                </div>
                <Activity className="h-8 w-8 text-purple-600" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Active Bounties</p>
                  <p className="text-2xl font-bold">{overview.active_bounties.toLocaleString()}</p>
                  <p className="text-xs text-muted-foreground">Open</p>
                </div>
                <Target className="h-8 w-8 text-orange-600" />
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="developers">Developers</TabsTrigger>
          <TabsTrigger value="agents">Agents</TabsTrigger>
          <TabsTrigger value="treasury">Treasury</TabsTrigger>
          <TabsTrigger value="staking">Staking</TabsTrigger>
          <TabsTrigger value="bounties">Bounties</TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <TrendingUp className="h-5 w-5" />
                  Growth Metrics
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex justify-between items-center">
                  <span className="text-sm text-muted-foreground">Weekly Growth</span>
                  <div className={`flex items-center gap-1 ${overview?.weekly_growth && overview.weekly_growth > 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {overview?.weekly_growth && overview.weekly_growth > 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                    <span className="font-medium">
                      {overview?.weekly_growth ? (overview.weekly_growth > 0 ? '+' : '') : ''}{overview?.weekly_growth?.toFixed(1) || '0.0'}%
                    </span>
                  </div>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm text-muted-foreground">Monthly Growth</span>
                  <div className={`flex items-center gap-1 ${overview?.monthly_growth && overview.monthly_growth > 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {overview?.monthly_growth && overview.monthly_growth > 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                    <span className="font-medium">
                      {overview?.monthly_growth ? (overview.monthly_growth > 0 ? '+' : '') : ''}{overview?.monthly_growth?.toFixed(1) || '0.0'}%
                    </span>
                  </div>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm text-muted-foreground">Completion Rate</span>
                  <span className="font-medium">
                    {overview ? ((overview.completed_bounties / overview.total_bounties) * 100).toFixed(1) : '0.0'}%
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm text-muted-foreground">Participation Rate</span>
                  <span className="font-medium">
                    {overview ? ((overview.total_stakers / (overview.total_developers + overview.total_agents)) * 100).toFixed(1) : '0.0'}%
                  </span>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <PieChart className="h-5 w-5" />
                  Ecosystem Distribution
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Developers</span>
                      <span className="font-medium">{overview?.total_developers.toLocaleString()}</span>
                    </div>
                    <Progress value={overview ? (overview.total_developers / (overview.total_developers + overview.total_agents + overview.total_stakers)) * 100 : 0} className="h-2" />
                  </div>
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">AI Agents</span>
                      <span className="font-medium">{overview?.total_agents.toLocaleString()}</span>
                    </div>
                    <Progress value={overview ? (overview.total_agents / (overview.total_developers + overview.total_agents + overview.total_stakers)) * 100 : 0} className="h-2" />
                  </div>
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Stakers</span>
                      <span className="font-medium">{overview?.total_stakers.toLocaleString()}</span>
                    </div>
                    <Progress value={overview ? (overview.total_stakers / (overview.total_developers + overview.total_agents + overview.total_stakers)) * 100 : 0} className="h-2" />
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Developers Tab */}
        <TabsContent value="developers" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5" />
                Top Developer Earnings
              </CardTitle>
              <CardDescription>
                Highest earning developers in the ecosystem
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Rank</TableHead>
                    <TableHead>Developer</TableHead>
                    <TableHead>Tier</TableHead>
                    <TableHead>Total Earned</TableHead>
                    <TableHead>Bounties</TableHead>
                    <TableHead>Success Rate</TableHead>
                    <TableHead>Growth</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {developerEarnings.slice(0, 10).map((developer) => (
                    <TableRow key={developer.address}>
                      <TableCell className="font-bold">#{developer.rank}</TableCell>
                      <TableCell className="font-mono">
                        {developer.address.slice(0, 8)}...{developer.address.slice(-6)}
                      </TableCell>
                      <TableCell>
                        <Badge className={getTierColor(developer.tier)}>
                          {developer.tier.charAt(0).toUpperCase() + developer.tier.slice(1)}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-bold text-blue-600">
                        {developer.total_earned.toLocaleString()} AITBC
                      </TableCell>
                      <TableCell>{developer.bounties_completed}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Progress value={developer.success_rate} className="w-16 h-2" />
                          <span className="text-sm">{developer.success_rate.toFixed(1)}%</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className={`flex items-center gap-1 ${developer.growth_rate > 0 ? 'text-green-600' : 'text-red-600'}`}>
                          {developer.growth_rate > 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                          <span className="text-sm">
                            {developer.growth_rate > 0 ? '+' : ''}{developer.growth_rate.toFixed(1)}%
                          </span>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Agents Tab */}
        <TabsContent value="agents" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Cpu className="h-5 w-5" />
                AI Agent Utilization
              </CardTitle>
              <CardDescription>
                Performance metrics for AI agents in the ecosystem
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Agent</TableHead>
                    <TableHead>Tier</TableHead>
                    <TableHead>Submissions</TableHead>
                    <TableHead>Success Rate</TableHead>
                    <TableHead>Accuracy</TableHead>
                    <TableHead>Utilization</TableHead>
                    <TableHead>Earnings</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {agentUtilization.slice(0, 10).map((agent) => (
                    <TableRow key={agent.agent_address}>
                      <TableCell className="font-mono">
                        {agent.agent_address.slice(0, 8)}...{agent.agent_address.slice(-6)}
                      </TableCell>
                      <TableCell>
                        <Badge className={getTierColor(agent.current_tier)}>
                          {agent.current_tier.charAt(0).toUpperCase() + agent.current_tier.slice(1)}
                        </Badge>
                      </TableCell>
                      <TableCell>{agent.total_submissions}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Progress value={agent.success_rate} className="w-16 h-2" />
                          <span className="text-sm">{agent.success_rate.toFixed(1)}%</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Target className="h-4 w-4 text-green-600" />
                          <span>{agent.average_accuracy.toFixed(1)}%</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Progress value={agent.utilization_rate} className="w-16 h-2" />
                          <span className="text-sm">{agent.utilization_rate.toFixed(1)}%</span>
                        </div>
                      </TableCell>
                      <TableCell className="font-bold text-green-600">
                        {agent.total_earnings.toLocaleString()} AITBC
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Treasury Tab */}
        <TabsContent value="treasury" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Database className="h-5 w-5" />
                  Treasury Allocation
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {treasuryAllocation.map((allocation) => (
                    <div key={allocation.category} className="space-y-2">
                      <div className="flex justify-between items-center">
                        <div className="flex items-center gap-2">
                          {getTrendIcon(allocation.trend)}
                          <span className="font-medium">{allocation.category}</span>
                        </div>
                        <div className="text-right">
                          <p className="font-bold">{allocation.amount.toLocaleString()} AITBC</p>
                          <p className="text-sm text-muted-foreground">{allocation.percentage.toFixed(1)}%</p>
                        </div>
                      </div>
                      <Progress value={allocation.percentage} className="h-2" />
                      <p className="text-xs text-muted-foreground">{allocation.description}</p>
                      <div className="flex justify-between text-xs">
                        <span className="text-muted-foreground">Monthly Change</span>
                        <span className={allocation.monthly_change > 0 ? 'text-green-600' : 'text-red-600'}>
                          {allocation.monthly_change > 0 ? '+' : ''}{allocation.monthly_change.toFixed(1)}%
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <DollarSign className="h-5 w-5" />
                  Treasury Metrics
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex justify-between items-center">
                  <span className="text-sm text-muted-foreground">Total Treasury</span>
                  <span className="font-bold">
                    {treasuryAllocation.reduce((sum, a) => sum + a.amount, 0).toLocaleString()} AITBC
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm text-muted-foreground">Monthly Revenue</span>
                  <span className="font-bold text-green-600">
                    +{treasuryAllocation.reduce((sum, a) => sum + a.monthly_change, 0).toFixed(1)}%
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm text-muted-foreground">Burn Rate</span>
                  <span className="font-bold text-orange-600">2.3% monthly</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm text-muted-foreground">Runway</span>
                  <span className="font-bold">18 months</span>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Staking Tab */}
        <TabsContent value="staking" className="space-y-4">
          {stakingMetrics && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Shield className="h-5 w-5" />
                    Staking Overview
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">Total Staked</span>
                    <span className="font-bold">{stakingMetrics.total_staked.toLocaleString()} AITBC</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">Total Stakers</span>
                    <span className="font-bold">{stakingMetrics.total_stakers.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">Average Stake</span>
                    <span className="font-bold">{stakingMetrics.average_stake_amount.toLocaleString()} AITBC</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">Average APY</span>
                    <span className="font-bold text-green-600">{stakingMetrics.average_apy.toFixed(1)}%</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">Participation Rate</span>
                    <div className="flex items-center gap-2">
                      <Progress value={stakingMetrics.staking_participation_rate} className="w-16 h-2" />
                      <span className="text-sm">{stakingMetrics.staking_participation_rate.toFixed(1)}%</span>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Star className="h-5 w-5" />
                    Top Stakers
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {stakingMetrics.top_stakers.slice(0, 5).map((staker, index) => (
                      <div key={staker.address} className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <span className="text-sm font-bold">#{index + 1}</span>
                          <span className="font-mono text-sm">
                            {staker.address.slice(0, 8)}...{staker.address.slice(-6)}
                          </span>
                        </div>
                        <div className="text-right">
                          <p className="text-sm font-medium">{staker.amount.toLocaleString()} AITBC</p>
                          <p className="text-xs text-green-600">{staker.rewards.toLocaleString()} rewards</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>

        {/* Bounties Tab */}
        <TabsContent value="bounties" className="space-y-4">
          {bountyAnalytics && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Target className="h-5 w-5" />
                    Bounty Analytics
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">Total Bounties</span>
                    <span className="font-bold">{bountyAnalytics.total_bounties.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">Active Bounties</span>
                    <span className="font-bold text-blue-600">{bountyAnalytics.active_bounties.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">Completed Bounties</span>
                    <span className="font-bold text-green-600">{bountyAnalytics.completed_bounties.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">Success Rate</span>
                    <div className="flex items-center gap-2">
                      <Progress value={bountyAnalytics.success_rate} className="w-16 h-2" />
                      <span className="text-sm">{bountyAnalytics.success_rate.toFixed(1)}%</span>
                    </div>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">Avg Completion Time</span>
                    <span className="font-bold">{bountyAnalytics.average_completion_time.toFixed(1)} days</span>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <BarChart3 className="h-5 w-5" />
                    Category Distribution
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {bountyAnalytics.category_distribution.map((category) => (
                      <div key={category.category} className="space-y-2">
                        <div className="flex justify-between text-sm">
                          <span className="font-medium">{category.category}</span>
                          <span className="text-muted-foreground">{category.count} bounties</span>
                        </div>
                        <Progress value={(category.count / bountyAnalytics.total_bounties) * 100} className="h-2" />
                        <p className="text-xs text-muted-foreground">
                          {category.value.toLocaleString()} AITBC total value
                        </p>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Footer */}
      <div className="text-center text-sm text-muted-foreground">
        <p>Last updated: {formatDistanceToNow(lastUpdated, { addSuffix: true })}</p>
        <p>AITBC Ecosystem Dashboard - Real-time metrics and analytics</p>
      </div>
    </div>
  );
};

export default EcosystemDashboard;
