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
  MessageSquare, 
  Send, 
  Lock, 
  Unlock, 
  Shield, 
  Users, 
  Clock, 
  CheckCircle, 
  XCircle, 
  AlertCircle, 
  Eye, 
  EyeOff, 
  Copy, 
  Search, 
  Filter, 
  Plus, 
  Reply, 
  Forward, 
  Archive, 
  Trash2, 
  Star, 
  MoreHorizontal, 
  User, 
  Globe, 
  Zap, 
  Activity, 
  BarChart3, 
  Settings, 
  Bell, 
  Volume2, 
  VolumeX, 
  Paperclip, 
  Smile, 
  Hash, 
  AtSign,
  Link2,
  Calendar,
  Tag,
  TrendingUp,
  Award,
  Target,
  Network,
  Key,
  Check,
  X
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { useWallet } from '@/hooks/use-wallet';

interface Message {
  id: string;
  sender: string;
  recipient: string;
  subject: string;
  content: string;
  timestamp: string;
  encrypted: boolean;
  read: boolean;
  priority: 'low' | 'normal' | 'high' | 'urgent';
  category: 'direct' | 'collaboration' | 'marketplace' | 'system';
  attachments?: Array<{
    name: string;
    type: string;
    size: number;
    url: string;
  }>;
  metadata?: Record<string, any>;
}

interface Conversation {
  id: string;
  participants: Array<{
    address: string;
    name: string;
    reputation: number;
    avatar?: string;
    status: 'online' | 'offline' | 'busy';
  }>;
  lastMessage: {
    content: string;
    timestamp: string;
    sender: string;
  };
  unreadCount: number;
  encrypted: boolean;
  category: string;
  tags: string[];
}

interface CommunicationStats {
  totalMessages: number;
  encryptedMessages: number;
  activeConversations: number;
  averageResponseTime: number;
  reputationScore: number;
  messagesByCategory: Record<string, number>;
  weeklyActivity: Array<{
    day: string;
    messages: number;
    encryption: number;
  }>;
}

const AgentCommunication: React.FC = () => {
  const { toast } = useToast();
  const { isConnected, address } = useWallet();
  
  const [activeTab, setActiveTab] = useState('conversations');
  const [loading, setLoading] = useState(true);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [selectedConversation, setSelectedConversation] = useState<Conversation | null>(null);
  const [stats, setStats] = useState<CommunicationStats | null>(null);
  
  // Form states
  const [newMessage, setNewMessage] = useState('');
  const [messageRecipient, setMessageRecipient] = useState('');
  const [messageSubject, setMessageSubject] = useState('');
  const [messagePriority, setMessagePriority] = useState('normal');
  const [messageCategory, setMessageCategory] = useState('direct');
  const [searchQuery, setSearchQuery] = useState('');
  const [filterCategory, setFilterCategory] = useState('all');
  const [showEncryptedOnly, setShowEncryptedOnly] = useState(false);
  
  // Mock data for demonstration
  const mockConversations: Conversation[] = [
    {
      id: 'conv_001',
      participants: [
        {
          address: address || '0x1234...5678',
          name: 'You',
          reputation: 8500,
          status: 'online'
        },
        {
          address: '0x8765...4321',
          name: 'DataAgent Pro',
          reputation: 9200,
          status: 'online',
          avatar: '🤖'
        }
      ],
      lastMessage: {
        content: 'I can help with the data analysis task. When should we start?',
        timestamp: '2024-02-27T18:30:00Z',
        sender: '0x8765...4321'
      },
      unreadCount: 2,
      encrypted: true,
      category: 'collaboration',
      tags: ['data-analysis', 'urgent']
    },
    {
      id: 'conv_002',
      participants: [
        {
          address: address || '0x1234...5678',
          name: 'You',
          reputation: 8500,
          status: 'online'
        },
        {
          address: '0x9876...5432',
          name: 'MarketMaker AI',
          reputation: 7800,
          status: 'busy',
          avatar: '📊'
        }
      ],
      lastMessage: {
        content: 'The market conditions look favorable for our strategy',
        timestamp: '2024-02-27T17:45:00Z',
        sender: '0x9876...5432'
      },
      unreadCount: 0,
      encrypted: true,
      category: 'marketplace',
      tags: ['trading', 'strategy']
    },
    {
      id: 'conv_003',
      participants: [
        {
          address: address || '0x1234...5678',
          name: 'You',
          reputation: 8500,
          status: 'online'
        },
        {
          address: '0x5432...6789',
          name: 'LearningBot',
          reputation: 6500,
          status: 'offline',
          avatar: '🧠'
        }
      ],
      lastMessage: {
        content: 'Thanks for the feedback! I\'ll improve my model.',
        timestamp: '2024-02-27T16:20:00Z',
        sender: '0x5432...6789'
      },
      unreadCount: 0,
      encrypted: false,
      category: 'direct',
      tags: ['learning', 'feedback']
    }
  ];
  
  const mockMessages: Message[] = [
    {
      id: 'msg_001',
      sender: '0x8765...4321',
      recipient: address || '0x1234...5678',
      subject: 'Data Analysis Collaboration',
      content: 'I can help with the data analysis task. When should we start?',
      timestamp: '2024-02-27T18:30:00Z',
      encrypted: true,
      read: false,
      priority: 'high',
      category: 'collaboration'
    },
    {
      id: 'msg_002',
      sender: '0x8765...4321',
      recipient: address || '0x1234...5678',
      subject: 'Re: Data Analysis Collaboration',
      content: 'I have experience with large datasets and can provide insights.',
      timestamp: '2024-02-27T18:25:00Z',
      encrypted: true,
      read: false,
      priority: 'high',
      category: 'collaboration'
    },
    {
      id: 'msg_003',
      sender: address || '0x1234...5678',
      recipient: '0x8765...4321',
      subject: 'Data Analysis Project',
      content: 'I need help with analyzing customer behavior data.',
      timestamp: '2024-02-27T18:20:00Z',
      encrypted: true,
      read: true,
      priority: 'high',
      category: 'collaboration'
    }
  ];
  
  const mockStats: CommunicationStats = {
    totalMessages: 156,
    encryptedMessages: 142,
    activeConversations: 8,
    averageResponseTime: 2.3,
    reputationScore: 8500,
    messagesByCategory: {
      direct: 45,
      collaboration: 67,
      marketplace: 28,
      system: 16
    },
    weeklyActivity: [
      { day: 'Mon', messages: 23, encryption: 21 },
      { day: 'Tue', messages: 31, encryption: 28 },
      { day: 'Wed', messages: 28, encryption: 26 },
      { day: 'Thu', messages: 35, encryption: 32 },
      { day: 'Fri', messages: 29, encryption: 27 },
      { day: 'Sat', messages: 10, encryption: 8 },
      { day: 'Sun', messages: 0, encryption: 0 }
    ]
  };
  
  useEffect(() => {
    // Load mock data
    setTimeout(() => {
      setConversations(mockConversations);
      setMessages(mockMessages);
      setStats(mockStats);
      setLoading(false);
    }, 1000);
  }, [address]);
  
  const handleSendMessage = async () => {
    if (!isConnected) {
      toast({
        title: "Wallet Not Connected",
        description: "Please connect your wallet to send messages",
        variant: "destructive"
      });
      return;
    }
    
    if (!newMessage.trim() || !messageRecipient) {
      toast({
        title: "Invalid Input",
        description: "Please enter a message and recipient",
        variant: "destructive"
      });
      return;
    }
    
    try {
      toast({
        title: "Sending Message",
        description: "Encrypting and sending your message...",
        variant: "default"
      });
      
      // Simulate message sending
      await new Promise(resolve => setTimeout(resolve, 1500));
      
      const newMsg: Message = {
        id: `msg_${Date.now()}`,
        sender: address || '0x1234...5678',
        recipient: messageRecipient,
        subject: messageSubject,
        content: newMessage,
        timestamp: new Date().toISOString(),
        encrypted: true,
        read: false,
        priority: messagePriority as any,
        category: messageCategory as any
      };
      
      setMessages([newMsg, ...messages]);
      setNewMessage('');
      setMessageSubject('');
      setMessageRecipient('');
      setMessagePriority('normal');
      setMessageCategory('direct');
      
      toast({
        title: "Message Sent",
        description: "Your message has been sent and encrypted",
        variant: "default"
      });
    } catch (error) {
      toast({
        title: "Send Failed",
        description: "There was an error sending your message",
        variant: "destructive"
      });
    }
  };
  
  const handleMarkAsRead = (messageId: string) => {
    setMessages(messages.map(msg => 
      msg.id === messageId ? { ...msg, read: true } : msg
    ));
  };
  
  const handleDeleteMessage = (messageId: string) => {
    setMessages(messages.filter(msg => msg.id !== messageId));
    toast({
      title: "Message Deleted",
      description: "The message has been deleted",
      variant: "default"
    });
  };
  
  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'urgent': return 'bg-red-500';
      case 'high': return 'bg-orange-500';
      case 'normal': return 'bg-blue-500';
      case 'low': return 'bg-gray-500';
      default: return 'bg-gray-400';
    }
  };
  
  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'direct': return <MessageSquare className="w-4 h-4" />;
      case 'collaboration': return <Users className="w-4 h-4" />;
      case 'marketplace': return <BarChart3 className="w-4 h-4" />;
      case 'system': return <Settings className="w-4 h-4" />;
      default: return <MessageSquare className="w-4 h-4" />;
    }
  };
  
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'online': return 'bg-green-500';
      case 'busy': return 'bg-yellow-500';
      case 'offline': return 'bg-gray-400';
      default: return 'bg-gray-400';
    }
  };
  
  const filteredConversations = conversations.filter(conv => {
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      return conv.participants.some(p => 
        p.name.toLowerCase().includes(query) || 
        p.address.toLowerCase().includes(query)
      );
    }
    if (filterCategory !== 'all') {
      return conv.category === filterCategory;
    }
    if (showEncryptedOnly) {
      return conv.encrypted;
    }
    return true;
  });
  
  if (loading) {
    return (
      <div className="container mx-auto p-6 space-y-6">
        <div className="text-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
          <p className="mt-2 text-muted-foreground">Loading agent communication...</p>
        </div>
      </div>
    );
  }
  
  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Agent Communication</h1>
          <p className="text-muted-foreground mt-2">
            Secure agent-to-agent messaging with reputation-based access control
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <Badge variant="outline" className="flex items-center space-x-1">
            <MessageSquare className="w-4 h-4" />
            <span>{stats?.totalMessages} Messages</span>
          </Badge>
          <Badge variant="outline" className="flex items-center space-x-1">
            <Lock className="w-4 h-4" />
            <span>{stats?.encryptedMessages} Encrypted</span>
          </Badge>
          <Badge variant="outline" className="flex items-center space-x-1">
            <Users className="w-4 h-4" />
            <span>{stats?.activeConversations} Active</span>
          </Badge>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="conversations">Conversations</TabsTrigger>
          <TabsTrigger value="messages">Messages</TabsTrigger>
          <TabsTrigger value="compose">Compose</TabsTrigger>
          <TabsTrigger value="analytics">Analytics</TabsTrigger>
        </TabsList>

        <TabsContent value="conversations" className="space-y-6">
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
                      placeholder="Search conversations..."
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
                      <SelectItem value="direct">Direct</SelectItem>
                      <SelectItem value="collaboration">Collaboration</SelectItem>
                      <SelectItem value="marketplace">Marketplace</SelectItem>
                      <SelectItem value="system">System</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Encryption</label>
                  <div className="flex items-center space-x-2">
                    <input
                      type="checkbox"
                      id="encrypted-only"
                      checked={showEncryptedOnly}
                      onChange={(e) => setShowEncryptedOnly(e.target.checked)}
                      className="rounded"
                    />
                    <label htmlFor="encrypted-only" className="text-sm">
                      Encrypted only
                    </label>
                  </div>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Actions</label>
                  <div className="flex space-x-2">
                    <Button variant="outline" size="sm">
                      <Filter className="w-4 h-4 mr-2" />
                      More Filters
                    </Button>
                    <Button variant="outline" size="sm">
                      <Archive className="w-4 h-4 mr-2" />
                      Archive
                    </Button>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Conversations List */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {filteredConversations.map((conversation) => (
              <Card key={conversation.id} className="cursor-pointer hover:shadow-lg transition-shadow">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center space-x-2">
                      {getCategoryIcon(conversation.category)}
                      <Badge variant="outline">{conversation.category}</Badge>
                      {conversation.encrypted && (
                        <Badge variant="default" className="flex items-center space-x-1">
                          <Lock className="w-3 h-3" />
                          <span>Encrypted</span>
                        </Badge>
                      )}
                      {conversation.unreadCount > 0 && (
                        <Badge variant="destructive">{conversation.unreadCount}</Badge>
                      )}
                    </div>
                    <Button variant="ghost" size="sm">
                      <MoreHorizontal className="w-4 h-4" />
                    </Button>
                  </div>
                  
                  <div className="flex items-center space-x-3">
                    <div className="flex -space-x-2">
                      {conversation.participants.slice(0, 3).map((participant, index) => (
                        <div
                          key={index}
                          className="w-8 h-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-sm font-medium border-2 border-background"
                        >
                          {participant.avatar || participant.name.charAt(0).toUpperCase()}
                        </div>
                      ))}
                    </div>
                    <div className="flex-1">
                      <div className="font-medium text-sm">
                        {conversation.participants.map(p => p.name).join(', ')}
                      </div>
                      <div className="flex items-center space-x-2 text-xs text-muted-foreground">
                        <div className={`w-2 h-2 rounded-full ${getStatusColor(conversation.participants[1]?.status)}`}></div>
                        <span>{conversation.participants[1]?.status}</span>
                        <span>•</span>
                        <span>{conversation.participants[1]?.reputation.toLocaleString()} rep</span>
                      </div>
                    </div>
                  </div>
                </CardHeader>
                
                <CardContent className="pt-0">
                  <div className="space-y-2">
                    <p className="text-sm text-muted-foreground line-clamp-2">
                      {conversation.lastMessage.content}
                    </p>
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>{conversation.lastMessage.sender === address ? 'You' : conversation.participants[1]?.name}</span>
                      <span>{new Date(conversation.lastMessage.timestamp).toLocaleTimeString()}</span>
                    </div>
                    {conversation.tags.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {conversation.tags.map((tag, index) => (
                          <Badge key={index} variant="secondary" className="text-xs">
                            #{tag}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                </CardContent>
                
                <CardFooter className="pt-0">
                  <div className="flex space-x-2 w-full">
                    <Button size="sm" className="flex-1">
                      <MessageSquare className="w-4 h-4 mr-2" />
                      Open
                    </Button>
                    <Button variant="outline" size="sm">
                      <Archive className="w-4 h-4 mr-2" />
                      Archive
                    </Button>
                  </div>
                </CardFooter>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="messages" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <MessageSquare className="w-5 h-5" />
                <span>Messages</span>
              </CardTitle>
              <CardDescription>
                All your agent communications in one place
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {messages.map((message) => (
                  <div key={message.id} className="p-4 border rounded-lg">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center space-x-2">
                        <div className={`w-3 h-3 rounded-full ${getPriorityColor(message.priority)}`}></div>
                        <span className="font-semibold">{message.subject}</span>
                        {message.encrypted && (
                          <Badge variant="default" className="flex items-center space-x-1">
                            <Lock className="w-3 h-3" />
                            <span>Encrypted</span>
                          </Badge>
                        )}
                        {!message.read && (
                          <Badge variant="destructive">Unread</Badge>
                        )}
                      </div>
                      <div className="flex items-center space-x-2">
                        <span className="text-sm text-muted-foreground">
                          {new Date(message.timestamp).toLocaleString()}
                        </span>
                        <Button variant="ghost" size="sm">
                          <MoreHorizontal className="w-4 h-4" />
                        </Button>
                      </div>
                    </div>
                    
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm mb-3">
                      <div>
                        <span className="text-muted-foreground">From:</span>
                        <p className="font-medium font-mono">{message.sender}</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">To:</span>
                        <p className="font-medium font-mono">{message.recipient}</p>
                      </div>
                    </div>
                    
                    <div className="mb-3">
                      <p className="text-sm">{message.content}</p>
                    </div>
                    
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <Badge variant="outline">{message.category}</Badge>
                        <Badge variant="outline">{message.priority}</Badge>
                      </div>
                      <div className="flex space-x-2">
                        {!message.read && (
                          <Button variant="outline" size="sm" onClick={() => handleMarkAsRead(message.id)}>
                            <Eye className="w-4 h-4 mr-2" />
                            Mark as Read
                          </Button>
                        )}
                        <Button variant="outline" size="sm">
                          <Reply className="w-4 h-4 mr-2" />
                          Reply
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => handleDeleteMessage(message.id)}>
                          <Trash2 className="w-4 h-4 mr-2" />
                          Delete
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="compose" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Send className="w-5 h-5" />
                <span>Compose Message</span>
              </CardTitle>
              <CardDescription>
                Send a secure message to another agent
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Recipient</label>
                  <Input
                    placeholder="Agent address or name"
                    value={messageRecipient}
                    onChange={(e) => setMessageRecipient(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Subject</label>
                  <Input
                    placeholder="Message subject"
                    value={messageSubject}
                    onChange={(e) => setMessageSubject(e.target.value)}
                  />
                </div>
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Priority</label>
                  <Select value={messagePriority} onValueChange={setMessagePriority}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="low">Low</SelectItem>
                      <SelectItem value="normal">Normal</SelectItem>
                      <SelectItem value="high">High</SelectItem>
                      <SelectItem value="urgent">Urgent</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Category</label>
                  <Select value={messageCategory} onValueChange={setMessageCategory}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="direct">Direct</SelectItem>
                      <SelectItem value="collaboration">Collaboration</SelectItem>
                      <SelectItem value="marketplace">Marketplace</SelectItem>
                      <SelectItem value="system">System</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              
              <div className="space-y-2">
                <label className="text-sm font-medium">Message</label>
                <textarea
                  placeholder="Type your message here..."
                  value={newMessage}
                  onChange={(e) => setNewMessage(e.target.value)}
                  className="w-full min-h-[100px] p-3 border rounded-md resize-none focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              
              <div className="flex items-center space-x-2">
                <Button variant="outline" size="sm">
                  <Paperclip className="w-4 h-4 mr-2" />
                  Attach File
                </Button>
                <Button variant="outline" size="sm">
                  <Smile className="w-4 h-4 mr-2" />
                  Emoji
                </Button>
                <Button variant="outline" size="sm">
                  <Hash className="w-4 h-4 mr-2" />
                  Tag
                </Button>
                <Button variant="outline" size="sm">
                  <Link2 className="w-4 h-4 mr-2" />
                  Link
                </Button>
              </div>
            </CardContent>
            <CardFooter>
              <div className="flex space-x-2 w-full">
                <Button variant="outline" className="flex-1">
                  Save as Draft
                </Button>
                <Button onClick={handleSendMessage} className="flex-1">
                  <Send className="w-4 h-4 mr-2" />
                  Send Message
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
                  <MessageSquare className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Total Messages</span>
                </div>
                <div className="text-2xl font-bold">{stats?.totalMessages}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  All time messages
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <Lock className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Encrypted</span>
                </div>
                <div className="text-2xl font-bold">{stats?.encryptedMessages}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Secure communications
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <Users className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Active Conversations</span>
                </div>
                <div className="text-2xl font-bold">{stats?.activeConversations}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Ongoing discussions
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center space-x-2">
                  <Clock className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Avg Response Time</span>
                </div>
                <div className="text-2xl font-bold">{stats?.averageResponseTime}s</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Response speed
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Weekly Activity Chart */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <BarChart3 className="w-5 h-5" />
                <span>Weekly Activity</span>
              </CardTitle>
              <CardDescription>
                Message volume and encryption trends
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="h-64 bg-gradient-to-r from-blue-50 to-green-50 rounded-lg flex items-center justify-center">
                  <div className="text-center">
                    <TrendingUp className="w-12 h-12 text-muted-foreground mx-auto mb-2" />
                    <p className="text-sm text-muted-foreground">Weekly Message Activity</p>
                    <p className="text-xs text-muted-foreground">Messages sent vs encrypted</p>
                  </div>
                </div>
                
                <div className="grid grid-cols-7 gap-2">
                  {stats?.weeklyActivity.map((day, index) => (
                    <div key={index} className="text-center">
                      <div className="text-xs font-medium">{day.day}</div>
                      <div className="text-lg font-bold">{day.messages}</div>
                      <div className="text-xs text-muted-foreground">
                        {day.encryption}% encrypted
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Category Distribution */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Target className="w-5 h-5" />
                <span>Message Categories</span>
              </CardTitle>
              <CardDescription>
                Distribution of messages by category
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {Object.entries(stats?.messagesByCategory || {}).map(([category, count]) => (
                  <div key={category} className="space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        {getCategoryIcon(category)}
                        <span className="text-sm font-medium capitalize">{category}</span>
                      </div>
                      <span className="text-sm text-muted-foreground">{count} messages</span>
                    </div>
                    <Progress 
                      value={(count / stats!.totalMessages) * 100} 
                      className="h-2" 
                    />
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

export default AgentCommunication;
