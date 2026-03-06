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
  Shield, 
  TrendingUp, 
  Globe, 
  Users, 
  Award, 
  Lock, 
  Unlock, 
  RefreshCw, 
  Download, 
  Upload, 
  Eye, 
  EyeOff, 
  CheckCircle, 
  XCircle, 
  AlertCircle, 
  Star, 
  Zap, 
  Network, 
  BarChart3, 
  Activity, 
  Clock, 
  Calendar, 
  Link, 
  Copy, 
  Settings, 
  Info, 
  ArrowUpRight, 
  ArrowDownRight, 
  Minus, 
  Plus,
  Share2
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { useWallet } from '@/hooks/use-wallet';

interface ReputationData {
  totalScore: number;
  taskCount: number;
  successCount: number;
  failureCount: number;
  lastUpdated: string;
  syncTimestamp: string;
  isActive: boolean;
}

interface ChainReputation {
  chainId: number;
  reputationScore: number;
  syncBlock: number;
  syncTimestamp: string;
  verified: boolean;
}

interface ReputationStake {
  staker: string;
  amount: number;
  lockPeriod: number;
  startTime: string;
  endTime: string;
  active: boolean;
}

interface ReputationDelegation {
  delegator: string;
  delegate: string;
  amount: number;
  startTime: string;
  active: boolean;
}

interface CrossChainStats {
  totalAgents: number;
  activeChains: number;
  averageReputation: number;
  totalStaked: number;
  syncSuccessRate: number;
  lastSyncTime: string;
}

const CrossChainReputation: React.FC = () => {
  const { toast } = useToast();
  const { isConnected, address } = useWallet();
  
  const [activeTab, setActiveTab] = useState('overview');
  const [loading, setLoading] = useState(true);
  const [reputationData, setReputationData] = useState<ReputationData | null>(null);
  const [chainReputations, setChainReputations] = useState<ChainReputation[]>([]);
  const [stakes, setStakes] = useState<ReputationStake[]>([]);
  const [delegations, setDelegations] = useState<ReputationDelegation[]>([]);
  const [stats, setStats] = useState<CrossChainStats | null>(null);
  
  // Form states
  const [syncForm, setSyncForm] = useState({
    targetChainId: '',
    amount: 0
  });
  
  const [stakeForm, setStakeForm] = useState({
    amount: 0,
    lockPeriod: 30
  });
  
  const [delegateForm, setDelegateForm] = useState({
    delegate: '',
    amount: 0
  });
  
  // Mock data for demonstration
  const mockReputationData: ReputationData = {
    totalScore: 8500,
    taskCount: 125,
    successCount: 118,
    failureCount: 7,
    lastUpdated: '2024-02-27T18:00:00Z',
    syncTimestamp: '2024-02-27T17:30:00Z',
    isActive: true
  };
  
  const mockChainReputations: ChainReputation[] = [
    {
      chainId: 1,
      reputationScore: 8500,
      syncBlock: 18500000,
      syncTimestamp: '2024-02-27T17:30:00Z',
      verified: true
    },
    {
      chainId: 137,
      reputationScore: 8450,
      syncBlock: 42000000,
      syncTimestamp: '2024-02-27T17:25:00Z',
      verified: true
    },
    {
      chainId: 56,
      reputationScore: 8480,
      syncBlock: 28000000,
      syncTimestamp: '2024-02-27T17:20:00Z',
      verified: true
    }
  ];
  
  const mockStakes: ReputationStake[] = [
    {
      staker: address || '0x1234...5678',
      amount: 1000,
      lockPeriod: 30,
      startTime: '2024-02-01T00:00:00Z',
      endTime: '2024-03-03T00:00:00Z',
      active: true
    }
  ];
  
  const mockDelegations: ReputationDelegation[] = [
    {
      delegator: address || '0x1234...5678',
      delegate: '0x8765...4321',
      amount: 500,
      startTime: '2024-02-15T00:00:00Z',
      active: true
    }
  ];
  
  const mockStats: CrossChainStats = {
    totalAgents: 1250,
    activeChains: 8,
    averageReputation: 7200,
    totalStaked: 2500000,
    syncSuccessRate: 98.5,
    lastSyncTime: '2024-02-27T18:00:00Z'
  };
  
  useEffect(() => {
    // Load mock data
    setTimeout(() => {
      setReputationData(mockReputationData);
      setChainReputations(mockChainReputations);
      setStakes(mockStakes);
      setDelegations(mockDelegations);
      setStats(mockStats);
      setLoading(false);
    }, 1000);
  }, [address]);
  
  const handleSyncReputation = async () => {
    if (!isConnected) {
      toast({
        title: "Wallet Not Connected",
        description: "Please connect your wallet to sync reputation",
        variant: "destructive"
      });
      return;
    }
    
    if (!syncForm.targetChainId || syncForm.amount <= 0) {
      toast({
        title: "Invalid Input",
        description: "Please enter valid chain ID and amount",
        variant: "destructive"
      });
      return;
    }
    
    try {
      toast({
        title: "Syncing Reputation",
        description: "Initiating cross-chain reputation sync...",
        variant: "default"
      });
      
      // Simulate sync process
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      const newChainReputation: ChainReputation = {
        chainId: parseInt(syncForm.targetChainId),
        reputationScore: reputationData?.totalScore || 0,
        syncBlock: Math.floor(Math.random() * 1000000),
        syncTimestamp: new Date().toISOString(),
        verified: true
      };
      
      setChainReputations([...chainReputations, newChainReputation]);
      
      // Reset form
      setSyncForm({ targetChainId: '', amount: 0 });
      
      toast({
        title: "Reputation Synced",
        description: `Reputation successfully synced to chain ${syncForm.targetChainId}`,
        variant: "default"
      });
    } catch (error) {
      toast({
        title: "Sync Failed",
        description: "There was an error syncing your reputation",
        variant: "destructive"
      });
    }
  };
  
  const handleStakeReputation = async () => {
    if (!isConnected) {
      toast({
        title: "Wallet Not Connected",
        description: "Please connect your wallet to stake reputation",
        variant: "destructive"
      });
      return;
    }
    
    if (stakeForm.amount <= 0 || stakeForm.lockPeriod <= 0) {
      toast({
        title: "Invalid Input",
        description: "Please enter valid amount and lock period",
        variant: "destructive"
      });
      return;
    }
    
    try {
      toast({
        title: "Staking Reputation",
        description: "Staking your reputation tokens...",
        variant: "default"
      });
      
      // Simulate staking process
      await new Promise(resolve => setTimeout(resolve, 1500));
      
      const newStake: ReputationStake = {
        staker: address || '0x1234...5678',
        amount: stakeForm.amount,
        lockPeriod: stakeForm.lockPeriod,
        startTime: new Date().toISOString(),
        endTime: new Date(Date.now() + stakeForm.lockPeriod * 24 * 60 * 60 * 1000).toISOString(),
        active: true
      };
      
      setStakes([...stakes, newStake]);
      
      // Reset form
      setStakeForm({ amount: 0, lockPeriod: 30 });
      
      toast({
        title: "Reputation Staked",
        description: `Successfully staked ${stakeForm.amount} reputation tokens`,
        variant: "default"
      });
    } catch (error) {
      toast({
        title: "Staking Failed",
        description: "There was an error staking your reputation",
        variant: "destructive"
      });
    }
  };
  
  const handleDelegateReputation = async () => {
    if (!isConnected) {
      toast({
        title: "Wallet Not Connected",
        description: "Please connect your wallet to delegate reputation",
        variant: "destructive"
      });
      return;
    }
    
    if (!delegateForm.delegate || delegateForm.amount <= 0) {
      toast({
        title: "Invalid Input",
        description: "Please enter valid delegate address and amount",
        variant: "destructive"
      });
      return;
    }
    
    try {
      toast({
        title: "Delegating Reputation",
        description: "Delegating your reputation tokens...",
        variant: "default"
      });
      
      // Simulate delegation process
      await new Promise(resolve => setTimeout(resolve, 1500));
      
      const newDelegation: ReputationDelegation = {
        delegator: address || '0x1234...5678',
        delegate: delegateForm.delegate,
        amount: delegateForm.amount,
        startTime: new Date().toISOString(),
        active: true
      };
      
      setDelegations([...delegations, newDelegation]);
      
      // Reset form
      setDelegateForm({ delegate: '', amount: 0 });
      
      toast({
        title: "Reputation Delegated",
        description: `Successfully delegated ${delegateForm.amount} reputation tokens`,
        variant: "default"
      });
    } catch (error) {
      toast({
        title: "Delegation Failed",
        description: "There was an error delegating your reputation",
        variant: "destructive"
      });
    }
  };
  
  const getChainName = (chainId: number) => {
    const chains: { [key: number]: string } = {
      1: 'Ethereum',
      137: 'Polygon',
      56: 'BSC',
      43114: 'Avalanche',
      42161: 'Arbitrum',
      10: 'Optimism',
      250: 'Fantom',
      128: 'Huobi ECO'
    };
    return chains[chainId] || `Chain ${chainId}`;
  };
  
  const getReputationColor = (score: number) => {
    if (score >= 9000) return 'bg-purple-500';
    if (score >= 7500) return 'bg-blue-500';
    if (score >= 6000) return 'bg-green-500';
    if (score >= 4000) return 'bg-yellow-500';
    return 'bg-red-500';
  };
  
  const renderStars = (score: number) => {
    const rating = Math.min(5, Math.floor(score / 2000));
    return Array.from({ length: 5 }, (_, i) => (
      <Star
        key={i}
        className={`w-4 h-4 ${i < rating ? 'text-yellow-400 fill-current' : 'text-gray-300'}`}
      />
    ));
  };
  
  if (loading) {
    return (
      <div className="container mx-auto p-6 space-y-6">
        <div className="text-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
          <p className="mt-2 text-muted-foreground">Loading cross-chain reputation data...</p>
        </div>
      </div>
    );
  }
  
  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Cross-Chain Reputation</h1>
          <p className="text-muted-foreground mt-2">
            Manage and sync your reputation across multiple blockchain networks
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <Badge variant="outline" className="flex items-center space-x-1">
            <Shield className="w-4 h-4" />
            <span>Reputation Score: {reputationData?.totalScore || 0}</span>
          </Badge>
          <Badge variant="outline" className="flex items-center space-x-1">
            <Globe className="w-4 h-4" />
            <span>{chainReputations.length} Chains</span>
          </Badge>
          <Badge variant="outline" className="flex items-center space-x-1">
            <Users className="w-4 h-4" />
            <span>{stats?.totalAgents || 0} Agents</span>
          </Badge>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-5">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="chains">Chain Reputations</TabsTrigger>
          <TabsTrigger value="staking">Staking</TabsTrigger>
          <TabsTrigger value="delegation">Delegation</TabsTrigger>
          <TabsTrigger value="analytics">Analytics</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
          {/* Reputation Overview */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Shield className="w-5 h-5" />
                <span>Reputation Overview</span>
              </CardTitle>
              <CardDescription>
                Your current reputation status and performance metrics
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="text-center">
                  <div className="text-2xl font-bold">{reputationData?.totalScore || 0}</div>
                  <p className="text-sm text-muted-foreground">Total Score</p>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold">{reputationData?.taskCount || 0}</div>
                  <p className="text-sm text-muted-foreground">Total Tasks</p>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold">{reputationData?.successCount || 0}</div>
                  <p className="text-sm text-muted-foreground">Successful</p>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold">{reputationData?.failureCount || 0}</div>
                  <p className="text-sm text-muted-foreground">Failed</p>
                </div>
              </div>
              
              <Separator />
              
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">Success Rate</span>
                  <span className="text-sm">
                    {reputationData ? Math.round((reputationData.successCount / reputationData.taskCount) * 100) : 0}%
                  </span>
                </div>
                <Progress value={reputationData ? (reputationData.successCount / reputationData.taskCount) * 100 : 0} />
              </div>
              
              <div className="flex items-center space-x-2">
                {renderStars(reputationData?.totalScore || 0)}
                <span className="text-sm text-muted-foreground">Reputation Rating</span>
              </div>
            </CardContent>
          </Card>

          {/* Quick Actions */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <RefreshCw className="w-5 h-5" />
                  <span>Sync Reputation</span>
                </CardTitle>
                <CardDescription>
                  Sync your reputation to another blockchain
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Target Chain</label>
                  <Select value={syncForm.targetChainId} onValueChange={(value) => setSyncForm({ ...syncForm, targetChainId: value })}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select chain" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="137">Polygon</SelectItem>
                      <SelectItem value="56">BSC</SelectItem>
                      <SelectItem value="43114">Avalanche</SelectItem>
                      <SelectItem value="42161">Arbitrum</SelectItem>
                      <SelectItem value="10">Optimism</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <Button onClick={handleSyncReputation} className="w-full">
                  <Upload className="w-4 h-4 mr-2" />
                  Sync Now
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <Lock className="w-5 h-5" />
                  <span>Stake Reputation</span>
                </CardTitle>
                <CardDescription>
                  Stake your reputation tokens to earn rewards
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Amount</label>
                  <Input
                    type="number"
                    placeholder="0"
                    value={stakeForm.amount || ''}
                    onChange={(e) => setStakeForm({ ...stakeForm, amount: parseFloat(e.target.value) || 0 })}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Lock Period (days)</label>
                  <Input
                    type="number"
                    placeholder="30"
                    value={stakeForm.lockPeriod || ''}
                    onChange={(e) => setStakeForm({ ...stakeForm, lockPeriod: parseInt(e.target.value) || 30 })}
                  />
                </div>
                <Button onClick={handleStakeReputation} className="w-full">
                  <Lock className="w-4 h-4 mr-2" />
                  Stake Now
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <Users className="w-5 h-5" />
                  <span>Delegate Reputation</span>
                </CardTitle>
                <CardDescription>
                  Delegate your reputation to another agent
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Delegate Address</label>
                  <Input
                    placeholder="0x..."
                    value={delegateForm.delegate || ''}
                    onChange={(e) => setDelegateForm({ ...delegateForm, delegate: e.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Amount</label>
                  <Input
                    type="number"
                    placeholder="0"
                    value={delegateForm.amount || ''}
                    onChange={(e) => setDelegateForm({ ...delegateForm, amount: parseFloat(e.target.value) || 0 })}
                  />
                </div>
                <Button onClick={handleDelegateReputation} className="w-full">
                  <Users className="w-4 h-4 mr-2" />
                  Delegate Now
                </Button>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="chains" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Globe className="w-5 h-5" />
                <span>Chain Reputations</span>
              </CardTitle>
              <CardDescription>
                Your reputation scores across different blockchain networks
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {chainReputations.map((chain, index) => (
                  <div key={index} className="p-4 border rounded-lg">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center space-x-2">
                        <div className={`w-3 h-3 rounded-full ${getReputationColor(chain.reputationScore)}`}></div>
                        <span className="font-semibold">{getChainName(chain.chainId)}</span>
                        <Badge variant="outline">Chain {chain.chainId}</Badge>
                        {chain.verified && (
                          <Badge variant="default" className="flex items-center space-x-1">
                            <CheckCircle className="w-3 h-3" />
                            <span>Verified</span>
                          </Badge>
                        )}
                      </div>
                      <div className="flex items-center space-x-2">
                        <span className="font-semibold">{chain.reputationScore}</span>
                        {renderStars(chain.reputationScore)}
                      </div>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                      <div>
                        <span className="text-muted-foreground">Sync Block:</span>
                        <p className="font-medium">{chain.syncBlock.toLocaleString()}</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Sync Time:</span>
                        <p className="font-medium">{new Date(chain.syncTimestamp).toLocaleString()}</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Status:</span>
                        <p className="font-medium text-green-600">Active</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Actions:</span>
                        <div className="flex space-x-2 mt-1">
                          <Button variant="outline" size="sm">
                            <RefreshCw className="w-3 h-3 mr-1" />
                            Sync
                          </Button>
                          <Button variant="outline" size="sm">
                            <Eye className="w-3 h-3 mr-1" />
                            Details
                          </Button>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="staking" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Lock className="w-5 h-5" />
                <span>Reputation Staking</span>
              </CardTitle>
              <CardDescription>
                Stake your reputation tokens to earn rewards and boost your influence
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {stakes.map((stake, index) => (
                  <div key={index} className="p-4 border rounded-lg">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center space-x-2">
                        <div className={`w-3 h-3 rounded-full ${stake.active ? 'bg-green-500' : 'bg-gray-400'}`}></div>
                        <span className="font-semibold">Stake #{index + 1}</span>
                        <Badge variant={stake.active ? "default" : "secondary"}>
                          {stake.active ? "Active" : "Completed"}
                        </Badge>
                      </div>
                      <div className="flex items-center space-x-2">
                        <span className="font-semibold">{stake.amount} Tokens</span>
                        <span className="text-sm text-muted-foreground">
                          ({stake.lockPeriod} days)
                        </span>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                      <div>
                        <span className="text-muted-foreground">Start Time:</span>
                        <p className="font-medium">{new Date(stake.startTime).toLocaleString()}</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">End Time:</span>
                        <p className="font-medium">{new Date(stake.endTime).toLocaleString()}</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Status:</span>
                        <p className="font-medium text-green-600">
                          {stake.active ? "Locked" : "Unlocked"}
                        </p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Actions:</span>
                        <div className="flex space-x-2 mt-1">
                          {stake.active && (
                            <Button variant="outline" size="sm">
                              <Unlock className="w-3 h-3 mr-1" />
                              Unstake
                            </Button>
                          )}
                          <Button variant="outline" size="sm">
                            <BarChart3 className="w-3 h-3 mr-1" />
                            Rewards
                          </Button>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="delegation" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Users className="w-5 h-5" />
                <span>Reputation Delegation</span>
              </CardTitle>
              <CardDescription>
                Delegate your reputation to other agents and earn shared rewards
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {delegations.map((delegation, index) => (
                  <div key={index} className="p-4 border rounded-lg">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center space-x-2">
                        <div className={`w-3 h-3 rounded-full ${delegation.active ? 'bg-green-500' : 'bg-gray-400'}`}></div>
                        <span className="font-semibold">Delegation #{index + 1}</span>
                        <Badge variant={delegation.active ? "default" : "secondary"}>
                          {delegation.active ? "Active" : "Completed"}
                        </Badge>
                      </div>
                      <div className="flex items-center space-x-2">
                        <span className="font-semibold">{delegation.amount} Tokens</span>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                      <div>
                        <span className="text-muted-foreground">Delegate:</span>
                        <p className="font-medium font-mono">{delegation.delegate}</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Delegator:</span>
                        <p className="font-medium font-mono">{delegation.delegator}</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Start Time:</span>
                        <p className="font-medium">{new Date(delegation.startTime).toLocaleString()}</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Actions:</span>
                        <div className="flex space-x-2 mt-1">
                          {delegation.active && (
                            <Button variant="outline" size="sm">
                              <XCircle className="w-3 h-3 mr-1" />
                              Revoke
                            </Button>
                          )}
                          <Button variant="outline" size="sm">
                            <BarChart3 className="w-3 h-3 mr-1" />
                            Rewards
                          </Button>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="analytics" className="space-y-6">
          {/* Key Metrics Overview */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <Users className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Total Agents</span>
                </div>
                <div className="text-2xl font-bold">{stats?.totalAgents.toLocaleString()}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Active across all chains
                </p>
                <div className="flex items-center space-x-1 mt-2">
                  <ArrowUpRight className="w-3 h-3 text-green-500" />
                  <span className="text-xs text-green-500">+12.5%</span>
                  <span className="text-xs text-muted-foreground">vs last month</span>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <Globe className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Active Chains</span>
                </div>
                <div className="text-2xl font-bold">{stats?.activeChains}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Supported networks
                </p>
                <div className="flex items-center space-x-1 mt-2">
                  <Plus className="w-3 h-3 text-blue-500" />
                  <span className="text-xs text-blue-500">+2 new</span>
                  <span className="text-xs text-muted-foreground">this quarter</span>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <Star className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Avg Reputation</span>
                </div>
                <div className="text-2xl font-bold">{stats?.averageReputation.toLocaleString()}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Network average
                </p>
                <div className="flex items-center space-x-1 mt-2">
                  <ArrowUpRight className="w-3 h-3 text-green-500" />
                  <span className="text-xs text-green-500">+8.3%</span>
                  <span className="text-xs text-muted-foreground">vs last month</span>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <Lock className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Total Staked</span>
                </div>
                <div className="text-2xl font-bold">{stats?.totalStaked.toLocaleString()}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Reputation tokens
                </p>
                <div className="flex items-center space-x-1 mt-2">
                  <ArrowUpRight className="w-3 h-3 text-green-500" />
                  <span className="text-xs text-green-500">+23.7%</span>
                  <span className="text-xs text-muted-foreground">vs last month</span>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Reputation Trends Chart */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <TrendingUp className="w-5 h-5" />
                <span>Reputation Trends</span>
              </CardTitle>
              <CardDescription>
                Your reputation score trends across different chains over time
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {/* Mock Chart Data */}
                <div className="h-64 bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg flex items-center justify-center">
                  <div className="text-center">
                    <BarChart3 className="w-12 h-12 text-muted-foreground mx-auto mb-2" />
                    <p className="text-sm text-muted-foreground">Reputation Score Trends</p>
                    <p className="text-xs text-muted-foreground">Last 30 days performance</p>
                  </div>
                </div>
                
                {/* Chain Performance Summary */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {chainReputations.slice(0, 3).map((chain, index) => (
                    <div key={index} className="p-3 border rounded-lg">
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-medium text-sm">{getChainName(chain.chainId)}</span>
                        <Badge variant="outline" className="text-xs">
                          Rank #{index + 1}
                        </Badge>
                      </div>
                      <div className="flex items-center space-x-2">
                        <div className="flex-1">
                          <div className="text-lg font-bold">{chain.reputationScore}</div>
                          <div className="text-xs text-muted-foreground">Current Score</div>
                        </div>
                        <div className="text-right">
                          <div className="text-sm font-medium text-green-600">+{Math.floor(Math.random() * 200) + 50}</div>
                          <div className="text-xs text-muted-foreground">30d change</div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Detailed Analytics */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Reputation Distribution */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <BarChart3 className="w-5 h-5" />
                  <span>Reputation Distribution</span>
                </CardTitle>
                <CardDescription>
                  Distribution of reputation scores across all agents
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">Elite (9000+)</span>
                      <span className="text-sm text-muted-foreground">15%</span>
                    </div>
                    <Progress value={15} className="h-2" />
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">Excellent (7500-8999)</span>
                      <span className="text-sm text-muted-foreground">35%</span>
                    </div>
                    <Progress value={35} className="h-2" />
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">Good (6000-7499)</span>
                      <span className="text-sm text-muted-foreground">30%</span>
                    </div>
                    <Progress value={30} className="h-2" />
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">Average (4000-5999)</span>
                      <span className="text-sm text-muted-foreground">15%</span>
                    </div>
                    <Progress value={15} className="h-2" />
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">Below Average (&lt;4000)</span>
                      <span className="text-sm text-muted-foreground">5%</span>
                    </div>
                    <Progress value={5} className="h-2" />
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Chain Activity */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <Activity className="w-5 h-5" />
                  <span>Chain Activity</span>
                </CardTitle>
                <CardDescription>
                  Recent activity and sync status across all chains
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {chainReputations.map((chain, index) => (
                    <div key={index} className="flex items-center space-x-3 p-2 rounded-lg hover:bg-muted/50">
                      <div className={`w-2 h-2 rounded-full ${chain.verified ? 'bg-green-500' : 'bg-yellow-500'}`}></div>
                      <div className="flex-1">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-medium">{getChainName(chain.chainId)}</span>
                          <span className="text-xs text-muted-foreground">
                            {new Date(chain.syncTimestamp).toLocaleTimeString()}
                          </span>
                        </div>
                        <div className="flex items-center space-x-2 mt-1">
                          <span className="text-xs text-muted-foreground">
                            Block: {chain.syncBlock.toLocaleString()}
                          </span>
                          <span className="text-xs text-muted-foreground">•</span>
                          <span className="text-xs text-muted-foreground">
                            Score: {chain.reputationScore}
                          </span>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className={`text-xs font-medium ${chain.verified ? 'text-green-600' : 'text-yellow-600'}`}>
                          {chain.verified ? 'Verified' : 'Pending'}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {Math.floor(Math.random() * 60) + 1} min ago
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Performance Metrics */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Zap className="w-5 h-5" />
                <span>Performance Metrics</span>
              </CardTitle>
              <CardDescription>
                Detailed performance metrics and analytics for your reputation
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <div className="text-center">
                  <div className="text-2xl font-bold text-green-600">94.2%</div>
                  <p className="text-sm text-muted-foreground">Success Rate</p>
                  <div className="flex items-center justify-center space-x-1 mt-1">
                    <ArrowUpRight className="w-3 h-3 text-green-500" />
                    <span className="text-xs text-green-500">+2.1%</span>
                  </div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-blue-600">2.3s</div>
                  <p className="text-sm text-muted-foreground">Avg Sync Time</p>
                  <div className="flex items-center justify-center space-x-1 mt-1">
                    <ArrowDownRight className="w-3 h-3 text-green-500" />
                    <span className="text-xs text-green-500">-0.5s</span>
                  </div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-purple-600">156</div>
                  <p className="text-sm text-muted-foreground">Total Tasks</p>
                  <div className="flex items-center justify-center space-x-1 mt-1">
                    <ArrowUpRight className="w-3 h-3 text-green-500" />
                    <span className="text-xs text-green-500">+23</span>
                  </div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-orange-600">4.8</div>
                  <p className="text-sm text-muted-foreground">Avg Rating</p>
                  <div className="flex items-center justify-center space-x-1 mt-1">
                    <Minus className="w-3 h-3 text-gray-500" />
                    <span className="text-xs text-gray-500">0.0</span>
                  </div>
                </div>
              </div>
              
              <Separator className="my-6" />
              
              {/* Recent Activity Timeline */}
              <div className="space-y-4">
                <h4 className="text-sm font-medium">Recent Activity</h4>
                <div className="space-y-3">
                  <div className="flex items-center space-x-3 p-2 rounded-lg bg-muted/20">
                    <div className="w-2 h-2 rounded-full bg-green-500"></div>
                    <div className="flex-1">
                      <div className="text-sm font-medium">Reputation Sync Completed</div>
                      <div className="text-xs text-muted-foreground">Polygon chain - 2 minutes ago</div>
                    </div>
                    <CheckCircle className="w-4 h-4 text-green-500" />
                  </div>
                  <div className="flex items-center space-x-3 p-2 rounded-lg bg-muted/20">
                    <div className="w-2 h-2 rounded-full bg-blue-500"></div>
                    <div className="flex-1">
                      <div className="text-sm font-medium">New Stake Received</div>
                      <div className="text-xs text-muted-foreground">500 tokens from 0x1234...5678 - 15 minutes ago</div>
                    </div>
                    <Lock className="w-4 h-4 text-blue-500" />
                  </div>
                  <div className="flex items-center space-x-3 p-2 rounded-lg bg-muted/20">
                    <div className="w-2 h-2 rounded-full bg-purple-500"></div>
                    <div className="flex-1">
                      <div className="text-sm font-medium">Delegation Created</div>
                      <div className="text-xs text-muted-foreground">200 tokens to 0x8765...4321 - 1 hour ago</div>
                    </div>
                    <Users className="w-4 h-4 text-purple-500" />
                  </div>
                  <div className="flex items-center space-x-3 p-2 rounded-lg bg-muted/20">
                    <div className="w-2 h-2 rounded-full bg-orange-500"></div>
                    <div className="flex-1">
                      <div className="text-sm font-medium">Task Completed Successfully</div>
                      <div className="text-xs text-muted-foreground">Data analysis task - 2 hours ago</div>
                    </div>
                    <CheckCircle className="w-4 h-4 text-orange-500" />
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Export and Sharing */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Download className="w-5 h-5" />
                <span>Export & Sharing</span>
              </CardTitle>
              <CardDescription>
                Export your reputation data and share your achievements
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <Button variant="outline" className="flex items-center space-x-2">
                  <Download className="w-4 h-4" />
                  <span>Export PDF</span>
                </Button>
                <Button variant="outline" className="flex items-center space-x-2">
                  <Copy className="w-4 h-4" />
                  <span>Copy Link</span>
                </Button>
                <Button variant="outline" className="flex items-center space-x-2">
                  <Share2 className="w-4 h-4" />
                  <span>Share Profile</span>
                </Button>
                <Button variant="outline" className="flex items-center space-x-2">
                  <Award className="w-4 h-4" />
                  <span>Generate Badge</span>
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default CrossChainReputation;
