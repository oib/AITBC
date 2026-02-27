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
  Wallet, 
  Send, 
  Settings, 
  Clock, 
  TrendingUp, 
  AlertTriangle,
  CheckCircle,
  ArrowUpRight,
  ArrowDownLeft,
  DollarSign,
  Shield,
  Activity
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { useWallet } from '@/hooks/use-wallet';

interface WalletInfo {
  agentId: string;
  owner: string;
  balance: string;
  totalAllowance: string;
  spentAmount: string;
  spendingLimit: string;
  transactionCount: number;
  createdAt: string;
  lastActivity: string;
  isActive: boolean;
  microTransactionEnabled: boolean;
}

interface Transaction {
  id: string;
  agent: string;
  recipient: string;
  amount: string;
  purpose: string;
  timestamp: string;
  isMicroTransaction: boolean;
  status: 'pending' | 'completed' | 'failed';
}

interface WalletStats {
  balance: string;
  totalAllowance: string;
  spentAmount: string;
  remainingAllowance: string;
  transactionCount: number;
  utilizationRate: number;
}

const AgentWallet: React.FC = () => {
  const { toast } = useToast();
  const { isConnected, address } = useWallet();
  
  const [wallets, setWallets] = useState<WalletInfo[]>([]);
  const [selectedWallet, setSelectedWallet] = useState<WalletInfo | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [walletStats, setWalletStats] = useState<WalletStats | null>(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [loading, setLoading] = useState(true);
  
  // Form states
  const [allowanceAmount, setAllowanceAmount] = useState('');
  const [spendingLimit, setSpendingLimit] = useState('');
  const [recipient, setRecipient] = useState('');
  const [amount, setAmount] = useState('');
  const [purpose, setPurpose] = useState('');
  const [selectedAgent, setSelectedAgent] = useState('');
  
  // Mock data for demonstration
  const mockWallets: WalletInfo[] = [
    {
      agentId: 'agent_001',
      owner: '0x1234...5678',
      balance: '850.50',
      totalAllowance: '1000.00',
      spentAmount: '149.50',
      spendingLimit: '500.00',
      transactionCount: 23,
      createdAt: '2024-01-15T10:30:00Z',
      lastActivity: '2024-01-25T14:20:00Z',
      isActive: true,
      microTransactionEnabled: true
    },
    {
      agentId: 'agent_002',
      owner: '0xabcd...efgh',
      balance: '1200.75',
      totalAllowance: '2000.00',
      spentAmount: '799.25',
      spendingLimit: '1000.00',
      transactionCount: 45,
      createdAt: '2024-01-18T09:15:00Z',
      lastActivity: '2024-01-26T16:45:00Z',
      isActive: true,
      microTransactionEnabled: true
    },
    {
      agentId: 'agent_003',
      owner: '0x5678...9abc',
      balance: '450.25',
      totalAllowance: '500.00',
      spentAmount: '49.75',
      spendingLimit: '250.00',
      transactionCount: 12,
      createdAt: '2024-01-20T11:45:00Z',
      lastActivity: '2024-01-24T13:30:00Z',
      isActive: true,
      microTransactionEnabled: false
    }
  ];

  const mockTransactions: Transaction[] = [
    {
      id: 'tx_001',
      agent: 'agent_001',
      recipient: 'provider_gpu_001',
      amount: '0.05',
      purpose: 'GPU rental - text processing',
      timestamp: '2024-01-25T14:20:00Z',
      isMicroTransaction: true,
      status: 'completed'
    },
    {
      id: 'tx_002',
      agent: 'agent_002',
      recipient: 'provider_gpu_002',
      amount: '0.15',
      purpose: 'GPU rental - image processing',
      timestamp: '2024-01-26T16:45:00Z',
      isMicroTransaction: true,
      status: 'completed'
    },
    {
      id: 'tx_003',
      agent: 'agent_001',
      recipient: 'data_provider_001',
      amount: '2.50',
      purpose: 'Dataset purchase',
      timestamp: '2024-01-24T10:15:00Z',
      isMicroTransaction: false,
      status: 'completed'
    }
  ];

  useEffect(() => {
    // Load mock data
    setTimeout(() => {
      setWallets(mockWallets);
      setTransactions(mockTransactions);
      if (mockWallets.length > 0) {
        setSelectedWallet(mockWallets[0]);
        updateWalletStats(mockWallets[0]);
      }
      setLoading(false);
    }, 1000);
  }, []);

  const updateWalletStats = (wallet: WalletInfo) => {
    const stats: WalletStats = {
      balance: wallet.balance,
      totalAllowance: wallet.totalAllowance,
      spentAmount: wallet.spentAmount,
      remainingAllowance: (parseFloat(wallet.totalAllowance) - parseFloat(wallet.spentAmount)).toFixed(2),
      transactionCount: wallet.transactionCount,
      utilizationRate: (parseFloat(wallet.spentAmount) / parseFloat(wallet.totalAllowance)) * 100
    };
    setWalletStats(stats);
  };

  const handleGrantAllowance = async () => {
    if (!isConnected || !selectedWallet || !allowanceAmount) {
      toast({
        title: "Missing Information",
        description: "Please connect wallet and fill in all fields",
        variant: "destructive"
      });
      return;
    }

    try {
      // Simulate allowance grant
      toast({
        title: "Granting Allowance",
        description: `Granting ${allowanceAmount} AITBC to ${selectedWallet.agentId}`,
        variant: "default"
      });

      // Update wallet state
      const updatedWallet = {
        ...selectedWallet,
        totalAllowance: (parseFloat(selectedWallet.totalAllowance) + parseFloat(allowanceAmount)).toFixed(2),
        balance: (parseFloat(selectedWallet.balance) + parseFloat(allowanceAmount)).toFixed(2)
      };
      
      setSelectedWallet(updatedWallet);
      setWallets(wallets.map(w => w.agentId === updatedWallet.agentId ? updatedWallet : w));
      updateWalletStats(updatedWallet);
      
      setAllowanceAmount('');
      
      toast({
        title: "Allowance Granted",
        description: `Successfully granted ${allowanceAmount} AITBC to ${selectedWallet.agentId}`,
        variant: "default"
      });
    } catch (error) {
      toast({
        title: "Grant Failed",
        description: "There was an error granting the allowance",
        variant: "destructive"
      });
    }
  };

  const handleUpdateSpendingLimit = async () => {
    if (!isConnected || !selectedWallet || !spendingLimit) {
      toast({
        title: "Missing Information",
        description: "Please connect wallet and fill in all fields",
        variant: "destructive"
      });
      return;
    }

    try {
      // Simulate spending limit update
      toast({
        title: "Updating Spending Limit",
        description: `Updating spending limit to ${spendingLimit} AITBC`,
        variant: "default"
      });

      // Update wallet state
      const updatedWallet = {
        ...selectedWallet,
        spendingLimit: spendingLimit
      };
      
      setSelectedWallet(updatedWallet);
      setWallets(wallets.map(w => w.agentId === updatedWallet.agentId ? updatedWallet : w));
      
      setSpendingLimit('');
      
      toast({
        title: "Spending Limit Updated",
        description: `Successfully updated spending limit to ${spendingLimit} AITBC`,
        variant: "default"
      });
    } catch (error) {
      toast({
        title: "Update Failed",
        description: "There was an error updating the spending limit",
        variant: "destructive"
      });
    }
  };

  const handleExecuteTransaction = async () => {
    if (!isConnected || !selectedWallet || !recipient || !amount || !purpose) {
      toast({
        title: "Missing Information",
        description: "Please fill in all transaction fields",
        variant: "destructive"
      });
      return;
    }

    try {
      // Simulate transaction execution
      toast({
        title: "Executing Transaction",
        description: `Sending ${amount} AITBC to ${recipient}`,
        variant: "default"
      });

      // Create new transaction
      const newTransaction: Transaction = {
        id: `tx_${Date.now()}`,
        agent: selectedWallet.agentId,
        recipient: recipient,
        amount: amount,
        purpose: purpose,
        timestamp: new Date().toISOString(),
        isMicroTransaction: parseFloat(amount) < 0.001,
        status: 'completed'
      };

      // Update wallet state
      const updatedWallet = {
        ...selectedWallet,
        balance: (parseFloat(selectedWallet.balance) - parseFloat(amount)).toFixed(2),
        spentAmount: (parseFloat(selectedWallet.spentAmount) + parseFloat(amount)).toFixed(2),
        transactionCount: selectedWallet.transactionCount + 1,
        lastActivity: new Date().toISOString()
      };
      
      setSelectedWallet(updatedWallet);
      setWallets(wallets.map(w => w.agentId === updatedWallet.agentId ? updatedWallet : w));
      setTransactions([newTransaction, ...transactions]);
      updateWalletStats(updatedWallet);
      
      // Clear form
      setRecipient('');
      setAmount('');
      setPurpose('');
      
      toast({
        title: "Transaction Completed",
        description: `Successfully sent ${amount} AITBC to ${recipient}`,
        variant: "default"
      });
    } catch (error) {
      toast({
        title: "Transaction Failed",
        description: "There was an error executing the transaction",
        variant: "destructive"
      });
    }
  };

  const handleToggleMicroTransactions = async () => {
    if (!isConnected || !selectedWallet) return;

    try {
      const updatedWallet = {
        ...selectedWallet,
        microTransactionEnabled: !selectedWallet.microTransactionEnabled
      };
      
      setSelectedWallet(updatedWallet);
      setWallets(wallets.map(w => w.agentId === updatedWallet.agentId ? updatedWallet : w));
      
      toast({
        title: "Settings Updated",
        description: `Micro-transactions ${updatedWallet.microTransactionEnabled ? 'enabled' : 'disabled'}`,
        variant: "default"
      });
    } catch (error) {
      toast({
        title: "Update Failed",
        description: "There was an error updating the settings",
        variant: "destructive"
      });
    }
  };

  if (loading) {
    return (
      <div className="container mx-auto p-6 space-y-6">
        <div className="text-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
          <p className="mt-2 text-muted-foreground">Loading agent wallets...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Agent Wallet Management</h1>
          <p className="text-muted-foreground mt-2">
            Manage and monitor autonomous agent wallets with micro-transaction support
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <Badge variant="outline" className="flex items-center space-x-1">
            <Wallet className="w-4 h-4" />
            <span>{wallets.length} Active Wallets</span>
          </Badge>
          <Badge variant="outline" className="flex items-center space-x-1">
            <Activity className="w-4 h-4" />
            <span>{transactions.length} Transactions</span>
          </Badge>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Wallet Selection */}
        <div className="lg:col-span-1">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Wallet className="w-5 h-5" />
                <span>Agent Wallets</span>
              </CardTitle>
              <CardDescription>
                Select an agent wallet to manage
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {wallets.map((wallet) => (
                <div
                  key={wallet.agentId}
                  className={`p-4 border rounded-lg cursor-pointer transition-colors ${
                    selectedWallet?.agentId === wallet.agentId
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:bg-muted/50'
                  }`}
                  onClick={() => {
                    setSelectedWallet(wallet);
                    updateWalletStats(wallet);
                  }}
                >
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="font-semibold">{wallet.agentId}</h4>
                    <Badge variant={wallet.isActive ? "default" : "secondary"}>
                      {wallet.isActive ? "Active" : "Inactive"}
                    </Badge>
                  </div>
                  <div className="space-y-1 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Balance:</span>
                      <span className="font-medium">{wallet.balance} AITBC</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Spent:</span>
                      <span className="font-medium">{wallet.spentAmount} AITBC</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Transactions:</span>
                      <span className="font-medium">{wallet.transactionCount}</span>
                    </div>
                  </div>
                  <div className="flex items-center space-x-2 mt-2">
                    {wallet.microTransactionEnabled && (
                      <Badge variant="secondary" className="text-xs">
                        <DollarSign className="w-3 h-3 mr-1" />
                        Micro-transactions
                      </Badge>
                    )}
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>

        {/* Wallet Details */}
        <div className="lg:col-span-2">
          {selectedWallet ? (
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsList className="grid w-full grid-cols-4">
                <TabsTrigger value="overview">Overview</TabsTrigger>
                <TabsTrigger value="transactions">Transactions</TabsTrigger>
                <TabsTrigger value="manage">Manage</TabsTrigger>
                <TabsTrigger value="settings">Settings</TabsTrigger>
              </TabsList>

              <TabsContent value="overview" className="space-y-6">
                {/* Wallet Stats */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  <Card>
                    <CardContent className="pt-6">
                      <div className="flex items-center space-x-2">
                        <DollarSign className="w-4 h-4 text-muted-foreground" />
                        <span className="text-sm font-medium">Balance</span>
                      </div>
                      <div className="text-2xl font-bold">{walletStats?.balance} AITBC</div>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-6">
                      <div className="flex items-center space-x-2">
                        <TrendingUp className="w-4 h-4 text-muted-foreground" />
                        <span className="text-sm font-medium">Total Allowance</span>
                      </div>
                      <div className="text-2xl font-bold">{walletStats?.totalAllowance} AITBC</div>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-6">
                      <div className="flex items-center space-x-2">
                        <ArrowUpRight className="w-4 h-4 text-muted-foreground" />
                        <span className="text-sm font-medium">Spent</span>
                      </div>
                      <div className="text-2xl font-bold">{walletStats?.spentAmount} AITBC</div>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-6">
                      <div className="flex items-center space-x-2">
                        <Activity className="w-4 h-4 text-muted-foreground" />
                        <span className="text-sm font-medium">Transactions</span>
                      </div>
                      <div className="text-2xl font-bold">{walletStats?.transactionCount}</div>
                    </CardContent>
                  </Card>
                </div>

                {/* Utilization */}
                <Card>
                  <CardHeader>
                    <CardTitle>Allowance Utilization</CardTitle>
                    <CardDescription>
                      Current spending vs. total allowance
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <span>Spent: {walletStats?.spentAmount} AITBC</span>
                        <span>Remaining: {walletStats?.remainingAllowance} AITBC</span>
                      </div>
                      <Progress value={walletStats?.utilizationRate || 0} className="w-full" />
                      <div className="text-center text-sm text-muted-foreground">
                        {walletStats?.utilizationRate?.toFixed(1)}% utilized
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* Recent Activity */}
                <Card>
                  <CardHeader>
                    <CardTitle>Recent Activity</CardTitle>
                    <CardDescription>
                      Latest transactions and wallet events
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-4">
                      {transactions.slice(0, 5).map((tx) => (
                        <div key={tx.id} className="flex items-center justify-between p-3 border rounded-lg">
                          <div className="flex items-center space-x-3">
                            <div className={`w-2 h-2 rounded-full ${
                              tx.status === 'completed' ? 'bg-green-500' :
                              tx.status === 'pending' ? 'bg-yellow-500' : 'bg-red-500'
                            }`}></div>
                            <div>
                              <p className="font-medium">{tx.purpose}</p>
                              <p className="text-sm text-muted-foreground">
                                To: {tx.recipient.slice(0, 8)}...{tx.recipient.slice(-6)}
                              </p>
                            </div>
                          </div>
                          <div className="text-right">
                            <p className="font-medium">{tx.amount} AITBC</p>
                            <p className="text-xs text-muted-foreground">
                              {new Date(tx.timestamp).toLocaleDateString()}
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="transactions" className="space-y-6">
                <Card>
                  <CardHeader>
                    <CardTitle>Transaction History</CardTitle>
                    <CardDescription>
                      All transactions for this agent wallet
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-4">
                      {transactions.map((tx) => (
                        <div key={tx.id} className="flex items-center justify-between p-4 border rounded-lg">
                          <div className="flex items-center space-x-4">
                            <div className={`w-3 h-3 rounded-full ${
                              tx.status === 'completed' ? 'bg-green-500' :
                              tx.status === 'pending' ? 'bg-yellow-500' : 'bg-red-500'
                            }`}></div>
                            <div>
                              <p className="font-medium">{tx.purpose}</p>
                              <p className="text-sm text-muted-foreground">
                                {tx.isMicroTransaction ? 'Micro-transaction' : 'Standard transaction'}
                              </p>
                              <p className="text-xs text-muted-foreground">
                                To: {tx.recipient}
                              </p>
                            </div>
                          </div>
                          <div className="text-right">
                            <p className="font-medium">{tx.amount} AITBC</p>
                            <p className="text-sm text-muted-foreground">
                              {new Date(tx.timestamp).toLocaleString()}
                            </p>
                            <Badge variant={tx.status === 'completed' ? "default" : "secondary"}>
                              {tx.status}
                            </Badge>
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="manage" className="space-y-6">
                {/* Grant Allowance */}
                <Card>
                  <CardHeader>
                    <CardTitle>Grant Allowance</CardTitle>
                    <CardDescription>
                      Add funds to the agent's allowance
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="space-y-2">
                      <label className="text-sm font-medium">Amount (AITBC)</label>
                      <Input
                        type="number"
                        placeholder="Enter amount"
                        value={allowanceAmount}
                        onChange={(e) => setAllowanceAmount(e.target.value)}
                      />
                    </div>
                    <Button onClick={handleGrantAllowance} className="w-full">
                      <ArrowDownLeft className="w-4 h-4 mr-2" />
                      Grant Allowance
                    </Button>
                  </CardContent>
                </Card>

                {/* Execute Transaction */}
                <Card>
                  <CardHeader>
                    <CardTitle>Execute Transaction</CardTitle>
                    <CardDescription>
                      Send funds from agent wallet
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="space-y-2">
                      <label className="text-sm font-medium">Recipient</label>
                      <Input
                        placeholder="Enter recipient address"
                        value={recipient}
                        onChange={(e) => setRecipient(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-medium">Amount (AITBC)</label>
                      <Input
                        type="number"
                        placeholder="Enter amount"
                        value={amount}
                        onChange={(e) => setAmount(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-medium">Purpose</label>
                      <Input
                        placeholder="Enter transaction purpose"
                        value={purpose}
                        onChange={(e) => setPurpose(e.target.value)}
                      />
                    </div>
                    <Button onClick={handleExecuteTransaction} className="w-full">
                      <Send className="w-4 h-4 mr-2" />
                      Execute Transaction
                    </Button>
                  </CardContent>
                </Card>

                {/* Update Spending Limit */}
                <Card>
                  <CardHeader>
                    <CardTitle>Update Spending Limit</CardTitle>
                    <CardDescription>
                      Set maximum spending limit per period
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="space-y-2">
                      <label className="text-sm font-medium">New Limit (AITBC)</label>
                      <Input
                        type="number"
                        placeholder="Enter spending limit"
                        value={spendingLimit}
                        onChange={(e) => setSpendingLimit(e.target.value)}
                      />
                    </div>
                    <Button onClick={handleUpdateSpendingLimit} className="w-full">
                      <Settings className="w-4 h-4 mr-2" />
                      Update Limit
                    </Button>
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="settings" className="space-y-6">
                {/* Wallet Settings */}
                <Card>
                  <CardHeader>
                    <CardTitle>Wallet Settings</CardTitle>
                    <CardDescription>
                      Configure agent wallet behavior
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-medium">Micro-transactions</p>
                        <p className="text-sm text-muted-foreground">
                          Enable transactions below 0.001 AITBC
                        </p>
                      </div>
                      <Button
                        variant={selectedWallet.microTransactionEnabled ? "default" : "outline"}
                        onClick={handleToggleMicroTransactions}
                      >
                        {selectedWallet.microTransactionEnabled ? "Enabled" : "Disabled"}
                      </Button>
                    </div>
                    <Separator />
                    <div className="space-y-2">
                      <p className="font-medium">Wallet Information</p>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                        <div>
                          <span className="text-muted-foreground">Agent ID:</span>
                          <p className="font-mono">{selectedWallet.agentId}</p>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Owner:</span>
                          <p className="font-mono">{selectedWallet.owner.slice(0, 8)}...{selectedWallet.owner.slice(-6)}</p>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Created:</span>
                          <p>{new Date(selectedWallet.createdAt).toLocaleDateString()}</p>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Last Activity:</span>
                          <p>{new Date(selectedWallet.lastActivity).toLocaleDateString()}</p>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* Security */}
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center space-x-2">
                      <Shield className="w-5 h-5" />
                      <span>Security</span>
                    </CardTitle>
                    <CardDescription>
                      Security settings and permissions
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <Alert>
                      <CheckCircle className="h-4 w-4" />
                      <AlertTitle>Wallet Secured</AlertTitle>
                      <AlertDescription>
                        This agent wallet is protected by smart contract security measures and spending limits.
                      </AlertDescription>
                    </Alert>
                  </CardContent>
                </Card>
              </TabsContent>
            </Tabs>
          ) : (
            <Card>
              <CardContent className="pt-6">
                <div className="text-center py-8">
                  <Wallet className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                  <p className="text-muted-foreground">Select an agent wallet to manage</p>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
};

export default AgentWallet;
