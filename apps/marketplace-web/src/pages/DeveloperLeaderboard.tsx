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
  Trophy,
  Medal,
  Award,
  TrendingUp,
  Users,
  Target,
  Zap,
  Shield,
  Star,
  Crown,
  Gem,
  Flame,
  Rocket,
  Calendar,
  Filter,
  Download,
  RefreshCw
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { formatDistanceToNow } from 'date-fns';

interface LeaderboardEntry {
  address: string;
  rank: number;
  total_earned: number;
  submissions: number;
  avg_accuracy: number;
  success_rate: number;
  bounties_completed: number;
  tier: 'bronze' | 'silver' | 'gold' | 'platinum' | 'diamond';
  reputation_score: number;
  last_active: string;
  streak_days: number;
  weekly_growth: number;
  monthly_growth: number;
}

interface TopPerformer {
  address: string;
  rank: number;
  metric: string;
  value: number;
  change: number;
  badge?: string;
}

interface CategoryStats {
  category: string;
  total_earnings: number;
  participant_count: number;
  avg_earnings: number;
  top_performer: string;
  growth_rate: number;
}

const DeveloperLeaderboard: React.FC = () => {
  const { toast } = useToast();
  
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
  const [topPerformers, setTopPerformers] = useState<TopPerformer[]>([]);
  const [categoryStats, setCategoryStats] = useState<CategoryStats[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('earnings');
  const [period, setPeriod] = useState('weekly');
  const [category, setCategory] = useState('all');
  const [metric, setMetric] = useState('total_earned');
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());

  // Load leaderboard data on component mount
  useEffect(() => {
    loadLeaderboard();
    loadTopPerformers();
    loadCategoryStats();
  }, [period, category, metric]);

  const loadLeaderboard = async () => {
    try {
      setLoading(true);
      const response = await fetch(`/api/v1/bounties/leaderboard?period=${period}&limit=100`);
      
      if (response.ok) {
        const data = await response.json();
        setLeaderboard(data);
        setLastUpdated(new Date());
      } else {
        throw new Error('Failed to load leaderboard');
      }
    } catch (error) {
      console.error('Error loading leaderboard:', error);
      toast({
        title: 'Error',
        description: 'Failed to load leaderboard data',
        variant: 'destructive'
      });
    } finally {
      setLoading(false);
    }
  };

  const loadTopPerformers = async () => {
    try {
      const response = await fetch(`/api/v1/ecosystem/top-performers?category=${category}&period=${period}&limit=10`);
      
      if (response.ok) {
        const data = await response.json();
        setTopPerformers(data.performers);
      }
    } catch (error) {
      console.error('Error loading top performers:', error);
    }
  };

  const loadCategoryStats = async () => {
    try {
      const response = await fetch(`/api/v1/ecosystem/category-stats?period=${period}`);
      
      if (response.ok) {
        const data = await response.json();
        setCategoryStats(data.categories);
      }
    } catch (error) {
      console.error('Error loading category stats:', error);
    }
  };

  const getRankIcon = (rank: number) => {
    if (rank === 1) return <Crown className="h-5 w-5 text-yellow-500" />;
    if (rank === 2) return <Medal className="h-5 w-5 text-gray-400" />;
    if (rank === 3) return <Award className="h-5 w-5 text-amber-600" />;
    return <span className="text-sm font-bold text-muted-foreground">#{rank}</span>;
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

  const getGrowthIcon = (growth: number) => {
    if (growth > 0) return <TrendingUp className="h-4 w-4 text-green-600" />;
    if (growth < 0) return <TrendingUp className="h-4 w-4 text-red-600 rotate-180" />;
    return <div className="h-4 w-4" />;
  };

  const getGrowthColor = (growth: number) => {
    if (growth > 0) return 'text-green-600';
    if (growth < 0) return 'text-red-600';
    return 'text-gray-600';
  };

  const exportLeaderboard = async () => {
    try {
      const response = await fetch(`/api/v1/ecosystem/export?format=csv&period=${period}`);
      
      if (response.ok) {
        const data = await response.json();
        // Create download link
        const link = document.createElement('a');
        link.href = data.url;
        link.download = `leaderboard_${period}.csv`;
        link.click();
        
        toast({
          title: 'Export Started',
          description: 'Leaderboard data is being downloaded',
        });
      }
    } catch (error) {
      console.error('Error exporting leaderboard:', error);
      toast({
        title: 'Error',
        description: 'Failed to export leaderboard',
        variant: 'destructive'
      });
    }
  };

  const refreshData = () => {
    loadLeaderboard();
    loadTopPerformers();
    loadCategoryStats();
  };

  if (loading && leaderboard.length === 0) {
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
          <h1 className="text-3xl font-bold">Developer Leaderboard</h1>
          <p className="text-muted-foreground">
            Top performers in the AITBC developer ecosystem
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={refreshData}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          <Button variant="outline" onClick={exportLeaderboard}>
            <Download className="h-4 w-4 mr-2" />
            Export
          </Button>
        </div>
      </div>

      {/* Top 3 Performers */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {leaderboard.slice(0, 3).map((performer, index) => (
          <Card key={performer.address} className="relative overflow-hidden">
            <div className={`absolute inset-0 bg-gradient-to-br ${
              index === 0 ? 'from-yellow-100 to-amber-100' :
              index === 1 ? 'from-gray-100 to-slate-100' :
              'from-amber-100 to-orange-100'
            } opacity-10`}></div>
            
            <CardHeader className="relative">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  {getRankIcon(performer.rank)}
                  <div>
                    <CardTitle className="text-lg">
                      {performer.address.slice(0, 8)}...{performer.address.slice(-6)}
                    </CardTitle>
                    <Badge className={getTierColor(performer.tier)}>
                      {performer.tier.charAt(0).toUpperCase() + performer.tier.slice(1)}
                    </Badge>
                  </div>
                </div>
              </div>
            </CardHeader>

            <CardContent className="relative space-y-4">
              <div className="text-center">
                <p className="text-3xl font-bold text-blue-600">
                  {performer.total_earned.toLocaleString()}
                </p>
                <p className="text-sm text-muted-foreground">AITBC Earned</p>
              </div>

              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-muted-foreground">Submissions</p>
                  <p className="font-medium">{performer.submissions}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Success Rate</p>
                  <p className="font-medium">{performer.success_rate.toFixed(1)}%</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Avg Accuracy</p>
                  <p className="font-medium">{performer.avg_accuracy.toFixed(1)}%</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Streak</p>
                  <p className="font-medium flex items-center gap-1">
                    <Flame className="h-3 w-3 text-orange-500" />
                    {performer.streak_days} days
                  </p>
                </div>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Weekly Growth</span>
                <div className={`flex items-center gap-1 ${getGrowthColor(performer.weekly_growth)}`}>
                  {getGrowthIcon(performer.weekly_growth)}
                  <span className="font-medium">
                    {performer.weekly_growth > 0 ? '+' : ''}{performer.weekly_growth.toFixed(1)}%
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-4 items-center">
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

        <Select value={category} onValueChange={setCategory}>
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Categories</SelectItem>
            <SelectItem value="developers">Developers</SelectItem>
            <SelectItem value="agents">Agents</SelectItem>
            <SelectItem value="stakers">Stakers</SelectItem>
          </SelectContent>
        </Select>

        <Select value={metric} onValueChange={setMetric}>
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="total_earned">Total Earned</SelectItem>
            <SelectItem value="submissions">Submissions</SelectItem>
            <SelectItem value="success_rate">Success Rate</SelectItem>
            <SelectItem value="avg_accuracy">Accuracy</SelectItem>
          </SelectContent>
        </Select>

        <div className="text-sm text-muted-foreground">
          Last updated: {formatDistanceToNow(lastUpdated, { addSuffix: true })}
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="earnings">Earnings</TabsTrigger>
          <TabsTrigger value="performance">Performance</TabsTrigger>
          <TabsTrigger value="categories">Categories</TabsTrigger>
          <TabsTrigger value="trends">Trends</TabsTrigger>
        </TabsList>

        {/* Earnings Tab */}
        <TabsContent value="earnings" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Trophy className="h-5 w-5" />
                Earnings Leaderboard
              </CardTitle>
              <CardDescription>
                Top developers by total AITBC earnings
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
                    <TableHead>Submissions</TableHead>
                    <TableHead>Success Rate</TableHead>
                    <TableHead>Accuracy</TableHead>
                    <TableHead>Growth</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {leaderboard.map((entry) => (
                    <TableRow key={entry.address}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {getRankIcon(entry.rank)}
                        </div>
                      </TableCell>
                      <TableCell className="font-mono">
                        {entry.address.slice(0, 8)}...{entry.address.slice(-6)}
                      </TableCell>
                      <TableCell>
                        <Badge className={getTierColor(entry.tier)}>
                          {entry.tier.charAt(0).toUpperCase() + entry.tier.slice(1)}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-bold text-blue-600">
                        {entry.total_earned.toLocaleString()} AITBC
                      </TableCell>
                      <TableCell>{entry.submissions}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Progress value={entry.success_rate} className="w-16 h-2" />
                          <span className="text-sm">{entry.success_rate.toFixed(1)}%</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Target className="h-4 w-4 text-green-600" />
                          <span>{entry.avg_accuracy.toFixed(1)}%</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className={`flex items-center gap-1 ${getGrowthColor(entry.weekly_growth)}`}>
                          {getGrowthIcon(entry.weekly_growth)}
                          <span className="text-sm">
                            {entry.weekly_growth > 0 ? '+' : ''}{entry.weekly_growth.toFixed(1)}%
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

        {/* Performance Tab */}
        <TabsContent value="performance" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Target className="h-5 w-5" />
                  Top Accuracy
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {leaderboard
                    .sort((a, b) => b.avg_accuracy - a.avg_accuracy)
                    .slice(0, 5)
                    .map((entry, index) => (
                      <div key={entry.address} className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <span className="text-sm font-bold">#{index + 1}</span>
                          <span className="font-mono text-sm">
                            {entry.address.slice(0, 8)}...{entry.address.slice(-6)}
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <Progress value={entry.avg_accuracy} className="w-20 h-2" />
                          <span className="text-sm font-medium">{entry.avg_accuracy.toFixed(1)}%</span>
                        </div>
                      </div>
                    ))}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Rocket className="h-5 w-5" />
                  Fastest Growth
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {leaderboard
                    .sort((a, b) => b.weekly_growth - a.weekly_growth)
                    .slice(0, 5)
                    .map((entry, index) => (
                      <div key={entry.address} className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <span className="text-sm font-bold">#{index + 1}</span>
                          <span className="font-mono text-sm">
                            {entry.address.slice(0, 8)}...{entry.address.slice(-6)}
                          </span>
                        </div>
                        <div className={`flex items-center gap-1 ${getGrowthColor(entry.weekly_growth)}`}>
                          {getGrowthIcon(entry.weekly_growth)}
                          <span className="text-sm font-medium">
                            {entry.weekly_growth > 0 ? '+' : ''}{entry.weekly_growth.toFixed(1)}%
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
                  <Flame className="h-5 w-5" />
                  Longest Streaks
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {leaderboard
                    .sort((a, b) => b.streak_days - a.streak_days)
                    .slice(0, 5)
                    .map((entry, index) => (
                      <div key={entry.address} className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <span className="text-sm font-bold">#{index + 1}</span>
                          <span className="font-mono text-sm">
                            {entry.address.slice(0, 8)}...{entry.address.slice(-6)}
                          </span>
                        </div>
                        <div className="flex items-center gap-1">
                          <Flame className="h-4 w-4 text-orange-500" />
                          <span className="text-sm font-medium">{entry.streak_days} days</span>
                        </div>
                      </div>
                    ))}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Shield className="h-5 w-5" />
                  Reputation Leaders
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {leaderboard
                    .sort((a, b) => b.reputation_score - a.reputation_score)
                    .slice(0, 5)
                    .map((entry, index) => (
                      <div key={entry.address} className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <span className="text-sm font-bold">#{index + 1}</span>
                          <span className="font-mono text-sm">
                            {entry.address.slice(0, 8)}...{entry.address.slice(-6)}
                          </span>
                          <Badge className={getTierColor(entry.tier)}>
                            {entry.tier.charAt(0).toUpperCase() + entry.tier.slice(1)}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-1">
                          <Star className="h-4 w-4 text-yellow-500" />
                          <span className="text-sm font-medium">{entry.reputation_score.toFixed(1)}</span>
                        </div>
                      </div>
                    ))}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Categories Tab */}
        <TabsContent value="categories" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {categoryStats.map((category) => (
              <Card key={category.category}>
                <CardHeader>
                  <CardTitle className="capitalize">{category.category}</CardTitle>
                  <CardDescription>
                    {category.participant_count} participants
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="text-center">
                    <p className="text-2xl font-bold text-blue-600">
                      {category.total_earnings.toLocaleString()}
                    </p>
                    <p className="text-sm text-muted-foreground">Total Earnings</p>
                  </div>
                  
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Average Earnings</span>
                      <span className="font-medium">{category.avg_earnings.toLocaleString()} AITBC</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Growth Rate</span>
                      <span className={`font-medium ${getGrowthColor(category.growth_rate)}`}>
                        {category.growth_rate > 0 ? '+' : ''}{category.growth_rate.toFixed(1)}%
                      </span>
                    </div>
                  </div>
                  
                  <div className="pt-2 border-t">
                    <p className="text-xs text-muted-foreground mb-1">Top Performer</p>
                    <p className="font-mono text-sm">
                      {category.top_performer.slice(0, 8)}...{category.top_performer.slice(-6)}
                    </p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        {/* Trends Tab */}
        <TabsContent value="trends" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <TrendingUp className="h-5 w-5" />
                  Weekly Trends
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">Total Participants</span>
                    <span className="font-bold">{leaderboard.length}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">Average Earnings</span>
                    <span className="font-bold">
                      {leaderboard.length > 0 
                        ? (leaderboard.reduce((sum, e) => sum + e.total_earned, 0) / leaderboard.length).toLocaleString()
                        : '0'
                      } AITBC
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">Success Rate</span>
                    <span className="font-bold">
                      {leaderboard.length > 0 
                        ? (leaderboard.reduce((sum, e) => sum + e.success_rate, 0) / leaderboard.length).toFixed(1)
                        : '0'
                      }%
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">Average Accuracy</span>
                    <span className="font-bold">
                      {leaderboard.length > 0 
                        ? (leaderboard.reduce((sum, e) => sum + e.avg_accuracy, 0) / leaderboard.length).toFixed(1)
                        : '0'
                      }%
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Users className="h-5 w-5" />
                  Participant Distribution
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {['bronze', 'silver', 'gold', 'platinum', 'diamond'].map((tier) => {
                    const count = leaderboard.filter(e => e.tier === tier).length;
                    const percentage = leaderboard.length > 0 ? (count / leaderboard.length) * 100 : 0;
                    
                    return (
                      <div key={tier} className="space-y-2">
                        <div className="flex justify-between text-sm">
                          <span className="capitalize">{tier}</span>
                          <span className="font-medium">{count} ({percentage.toFixed(1)}%)</span>
                        </div>
                        <Progress value={percentage} className="h-2" />
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default DeveloperLeaderboard;
