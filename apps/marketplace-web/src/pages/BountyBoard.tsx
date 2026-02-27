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
import { Separator } from '@/components/ui/separator';
import { Clock, Users, Trophy, Filter, Search, TrendingUp, AlertCircle } from 'lucide-react';
import { useWallet } from '@/hooks/use-wallet';
import { useToast } from '@/hooks/use-toast';
import { formatDistanceToNow } from 'date-fns';

interface Bounty {
  bounty_id: string;
  title: string;
  description: string;
  reward_amount: number;
  creator_id: string;
  tier: 'bronze' | 'silver' | 'gold' | 'platinum';
  status: 'created' | 'active' | 'submitted' | 'verified' | 'completed' | 'expired' | 'disputed';
  performance_criteria: Record<string, any>;
  min_accuracy: number;
  max_response_time?: number;
  deadline: string;
  creation_time: string;
  max_submissions: number;
  submission_count: number;
  requires_zk_proof: boolean;
  tags: string[];
  category?: string;
  difficulty?: string;
  winning_submission_id?: string;
  winner_address?: string;
}

interface BountyFilters {
  status?: string;
  tier?: string;
  category?: string;
  min_reward?: number;
  max_reward?: number;
  tags?: string[];
  requires_zk_proof?: boolean;
}

const BountyBoard: React.FC = () => {
  const { address, isConnected } = useWallet();
  const { toast } = useToast();
  
  const [bounties, setBounties] = useState<Bounty[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [filters, setFilters] = useState<BountyFilters>({});
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [selectedBounty, setSelectedBounty] = useState<Bounty | null>(null);
  const [mySubmissions, setMySubmissions] = useState<string[]>([]);

  // Load bounties on component mount
  useEffect(() => {
    loadBounties();
    if (isConnected) {
      loadMySubmissions();
    }
  }, [isConnected]);

  const loadBounties = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/bounties', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...filters,
          page: 1,
          limit: 50
        })
      });
      
      if (response.ok) {
        const data = await response.json();
        setBounties(data);
      } else {
        throw new Error('Failed to load bounties');
      }
    } catch (error) {
      console.error('Error loading bounties:', error);
      toast({
        title: 'Error',
        description: 'Failed to load bounties',
        variant: 'destructive'
      });
    } finally {
      setLoading(false);
    }
  };

  const loadMySubmissions = async () => {
    try {
      const response = await fetch('/api/v1/bounties/my/submissions', {
        headers: { 'Authorization': `Bearer ${address}` }
      });
      
      if (response.ok) {
        const submissions = await response.json();
        setMySubmissions(submissions.map((s: any) => s.bounty_id));
      }
    } catch (error) {
      console.error('Error loading submissions:', error);
    }
  };

  const handleBountySubmit = async (bountyId: string) => {
    if (!isConnected) {
      toast({
        title: 'Wallet Required',
        description: 'Please connect your wallet to submit to bounties',
        variant: 'destructive'
      });
      return;
    }

    // Navigate to submission page or open modal
    setSelectedBounty(bounties.find(b => b.bounty_id === bountyId) || null);
  };

  const getTierColor = (tier: string) => {
    const colors = {
      bronze: 'bg-orange-100 text-orange-800 border-orange-200',
      silver: 'bg-gray-100 text-gray-800 border-gray-200',
      gold: 'bg-yellow-100 text-yellow-800 border-yellow-200',
      platinum: 'bg-purple-100 text-purple-800 border-purple-200'
    };
    return colors[tier as keyof typeof colors] || colors.bronze;
  };

  const getStatusColor = (status: string) => {
    const colors = {
      created: 'bg-gray-100 text-gray-800',
      active: 'bg-green-100 text-green-800',
      submitted: 'bg-blue-100 text-blue-800',
      verified: 'bg-purple-100 text-purple-800',
      completed: 'bg-emerald-100 text-emerald-800',
      expired: 'bg-red-100 text-red-800',
      disputed: 'bg-orange-100 text-orange-800'
    };
    return colors[status as keyof typeof colors] || colors.created;
  };

  const getTimeRemaining = (deadline: string) => {
    const deadlineDate = new Date(deadline);
    const now = new Date();
    const timeRemaining = deadlineDate.getTime() - now.getTime();
    
    if (timeRemaining <= 0) return 'Expired';
    
    return formatDistanceToNow(deadlineDate, { addSuffix: true });
  };

  const filteredBounties = bounties.filter(bounty => {
    const matchesSearch = bounty.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         bounty.description.toLowerCase().includes(searchQuery.toLowerCase());
    
    const matchesTab = activeTab === 'all' || 
                      (activeTab === 'my-submissions' && mySubmissions.includes(bounty.bounty_id)) ||
                      (activeTab === 'active' && bounty.status === 'active') ||
                      (activeTab === 'completed' && bounty.status === 'completed');

    return matchesSearch && matchesTab;
  });

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
          <h1 className="text-3xl font-bold">Bounty Board</h1>
          <p className="text-muted-foreground">
            Discover and participate in AI agent development challenges
          </p>
        </div>
        {isConnected && (
          <Button onClick={() => setShowCreateModal(true)}>
            Create Bounty
          </Button>
        )}
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-muted-foreground">Active Bounties</p>
                <p className="text-2xl font-bold">{bounties.filter(b => b.status === 'active').length}</p>
              </div>
              <Trophy className="h-8 w-8 text-blue-600" />
            </div>
          </CardContent>
        </Card>
        
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-muted-foreground">Total Rewards</p>
                <p className="text-2xl font-bold">
                  {bounties.reduce((sum, b) => sum + b.reward_amount, 0).toLocaleString()} AITBC
                </p>
              </div>
              <TrendingUp className="h-8 w-8 text-green-600" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-muted-foreground">Completion Rate</p>
                <p className="text-2xl font-bold">
                  {bounties.length > 0 
                    ? Math.round((bounties.filter(b => b.status === 'completed').length / bounties.length) * 100)
                    : 0}%
                </p>
              </div>
              <Users className="h-8 w-8 text-purple-600" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-muted-foreground">My Submissions</p>
                <p className="text-2xl font-bold">{mySubmissions.length}</p>
              </div>
              <AlertCircle className="h-8 w-8 text-orange-600" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Search and Filters */}
      <div className="flex flex-col md:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search bounties..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
        
        <Select value={filters.tier || ''} onValueChange={(value) => setFilters(prev => ({ ...prev, tier: value || undefined }))}>
          <SelectTrigger className="w-32">
            <SelectValue placeholder="Tier" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="">All Tiers</SelectItem>
            <SelectItem value="bronze">Bronze</SelectItem>
            <SelectItem value="silver">Silver</SelectItem>
            <SelectItem value="gold">Gold</SelectItem>
            <SelectItem value="platinum">Platinum</SelectItem>
          </SelectContent>
        </Select>

        <Select value={filters.category || ''} onValueChange={(value) => setFilters(prev => ({ ...prev, category: value || undefined }))}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Category" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="">All Categories</SelectItem>
            <SelectItem value="computer-vision">Computer Vision</SelectItem>
            <SelectItem value="nlp">NLP</SelectItem>
            <SelectItem value="robotics">Robotics</SelectItem>
            <SelectItem value="gaming">Gaming</SelectItem>
            <SelectItem value="finance">Finance</SelectItem>
          </SelectContent>
        </Select>

        <Button variant="outline" onClick={loadBounties}>
          <Filter className="h-4 w-4 mr-2" />
          Apply Filters
        </Button>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="all">All Bounties</TabsTrigger>
          <TabsTrigger value="active">Active</TabsTrigger>
          <TabsTrigger value="completed">Completed</TabsTrigger>
          {isConnected && <TabsTrigger value="my-submissions">My Submissions</TabsTrigger>}
        </TabsList>

        <TabsContent value={activeTab} className="space-y-4">
          {/* Bounty Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredBounties.map((bounty) => (
              <Card key={bounty.bounty_id} className="hover:shadow-lg transition-shadow">
                <CardHeader>
                  <div className="flex justify-between items-start">
                    <div className="space-y-2">
                      <CardTitle className="text-lg line-clamp-2">{bounty.title}</CardTitle>
                      <div className="flex gap-2">
                        <Badge className={getTierColor(bounty.tier)}>
                          {bounty.tier.charAt(0).toUpperCase() + bounty.tier.slice(1)}
                        </Badge>
                        <Badge className={getStatusColor(bounty.status)}>
                          {bounty.status.charAt(0).toUpperCase() + bounty.status.slice(1)}
                        </Badge>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-2xl font-bold text-blue-600">
                        {bounty.reward_amount.toLocaleString()}
                      </p>
                      <p className="text-sm text-muted-foreground">AITBC</p>
                    </div>
                  </div>
                </CardHeader>

                <CardContent className="space-y-4">
                  <CardDescription className="line-clamp-3">
                    {bounty.description}
                  </CardDescription>

                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Min Accuracy</span>
                      <span className="font-medium">{bounty.min_accuracy}%</span>
                    </div>
                    
                    {bounty.max_response_time && (
                      <div className="flex justify-between text-sm">
                        <span className="text-muted-foreground">Max Response Time</span>
                        <span className="font-medium">{bounty.max_response_time}ms</span>
                      </div>
                    )}

                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Submissions</span>
                      <span className="font-medium">{bounty.submission_count}/{bounty.max_submissions}</span>
                    </div>

                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Time Remaining</span>
                      <span className="font-medium">{getTimeRemaining(bounty.deadline)}</span>
                    </div>
                  </div>

                  {/* Progress bar for submissions */}
                  <Progress 
                    value={(bounty.submission_count / bounty.max_submissions) * 100} 
                    className="h-2"
                  />

                  {/* Tags */}
                  {bounty.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {bounty.tags.slice(0, 3).map((tag) => (
                        <Badge key={tag} variant="secondary" className="text-xs">
                          {tag}
                        </Badge>
                      ))}
                      {bounty.tags.length > 3 && (
                        <Badge variant="secondary" className="text-xs">
                          +{bounty.tags.length - 3}
                        </Badge>
                      )}
                    </div>
                  )}

                  {/* ZK Proof indicator */}
                  {bounty.requires_zk_proof && (
                    <div className="flex items-center gap-2 text-sm text-blue-600">
                      <AlertCircle className="h-4 w-4" />
                      <span>ZK-Proof Required</span>
                    </div>
                  )}
                </CardContent>

                <CardFooter className="space-y-2">
                  {bounty.status === 'active' && (
                    <Button 
                      className="w-full" 
                      onClick={() => handleBountySubmit(bounty.bounty_id)}
                      disabled={!isConnected}
                    >
                      {isConnected ? 'Submit Solution' : 'Connect Wallet'}
                    </Button>
                  )}
                  
                  {bounty.status === 'completed' && bounty.winner_address && (
                    <div className="w-full text-center">
                      <p className="text-sm text-muted-foreground">Won by</p>
                      <p className="font-mono text-xs">{bounty.winner_address.slice(0, 8)}...{bounty.winner_address.slice(-6)}</p>
                    </div>
                  )}
                  
                  <Button 
                    variant="outline" 
                    className="w-full"
                    onClick={() => setSelectedBounty(bounty)}
                  >
                    View Details
                  </Button>
                </CardFooter>
              </Card>
            ))}
          </div>

          {filteredBounties.length === 0 && (
            <div className="text-center py-12">
              <Trophy className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-semibold mb-2">No bounties found</h3>
              <p className="text-muted-foreground">
                {searchQuery ? 'Try adjusting your search terms' : 'Check back later for new opportunities'}
              </p>
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Bounty Detail Modal */}
      {selectedBounty && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <Card className="max-w-2xl w-full max-h-[80vh] overflow-y-auto">
            <CardHeader>
              <div className="flex justify-between items-start">
                <div className="space-y-2">
                  <CardTitle className="text-xl">{selectedBounty.title}</CardTitle>
                  <div className="flex gap-2">
                    <Badge className={getTierColor(selectedBounty.tier)}>
                      {selectedBounty.tier.charAt(0).toUpperCase() + selectedBounty.tier.slice(1)}
                    </Badge>
                    <Badge className={getStatusColor(selectedBounty.status)}>
                      {selectedBounty.status.charAt(0).toUpperCase() + selectedBounty.status.slice(1)}
                    </Badge>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-3xl font-bold text-blue-600">
                    {selectedBounty.reward_amount.toLocaleString()}
                  </p>
                  <p className="text-sm text-muted-foreground">AITBC</p>
                </div>
              </div>
            </CardHeader>

            <CardContent className="space-y-6">
              <div>
                <h4 className="font-semibold mb-2">Description</h4>
                <p className="text-muted-foreground">{selectedBounty.description}</p>
              </div>

              <div>
                <h4 className="font-semibold mb-2">Requirements</h4>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-sm text-muted-foreground">Minimum Accuracy</p>
                    <p className="font-medium">{selectedBounty.min_accuracy}%</p>
                  </div>
                  {selectedBounty.max_response_time && (
                    <div>
                      <p className="text-sm text-muted-foreground">Max Response Time</p>
                      <p className="font-medium">{selectedBounty.max_response_time}ms</p>
                    </div>
                  )}
                  <div>
                    <p className="text-sm text-muted-foreground">Submissions</p>
                    <p className="font-medium">{selectedBounty.submission_count}/{selectedBounty.max_submissions}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Deadline</p>
                    <p className="font-medium">{new Date(selectedBounty.deadline).toLocaleDateString()}</p>
                  </div>
                </div>
              </div>

              {selectedBounty.performance_criteria && (
                <div>
                  <h4 className="font-semibold mb-2">Performance Criteria</h4>
                  <pre className="bg-muted p-3 rounded text-sm overflow-x-auto">
                    {JSON.stringify(selectedBounty.performance_criteria, null, 2)}
                  </pre>
                </div>
              )}

              {selectedBounty.tags.length > 0 && (
                <div>
                  <h4 className="font-semibold mb-2">Tags</h4>
                  <div className="flex flex-wrap gap-2">
                    {selectedBounty.tags.map((tag) => (
                      <Badge key={tag} variant="secondary">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>

            <CardFooter className="flex gap-2">
              {selectedBounty.status === 'active' && (
                <Button 
                  className="flex-1"
                  onClick={() => handleBountySubmit(selectedBounty.bounty_id)}
                  disabled={!isConnected}
                >
                  {isConnected ? 'Submit Solution' : 'Connect Wallet'}
                </Button>
              )}
              <Button variant="outline" onClick={() => setSelectedBounty(null)}>
                Close
              </Button>
            </CardFooter>
          </Card>
        </div>
      )}
    </div>
  );
};

export default BountyBoard;
