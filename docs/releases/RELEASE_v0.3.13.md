# AITBC v0.3.13 Release Notes

**Date**: May 20, 2026  
**Status**: ✅ Released  
**Scope**: Infrastructure & Deployment - Public server deployment and website updates

## 🎯 Overview

AITBC v0.3.13 is an **infrastructure and deployment release** that introduces public server deployment on hub.aitbc.bubuit.net, website updates, and enhanced network accessibility. This release marks the public availability of the AITBC platform with improved infrastructure and deployment capabilities.

## 🌐 Public Server Deployment

### New Public Endpoint
- **Public Server**: hub.aitbc.bubuit.net
- **IP Address**: 95.216.198.140
- **Status**: Publicly accessible
- **Services**: Full AITBC platform available

### Network Configuration
- **Domain**: hub.aitbc.bubuit.net
- **DNS**: Configured to point to ns3 container IP
- **Ports Exposed**:
  - 80 (HTTP) - Website and API proxy
  - 7070 (P2P) - Blockchain peer-to-peer communication
  - 8006 (RPC) - Blockchain RPC interface

### Server Configuration
- **Container**: ns3 Incus container
- **Node Configuration**: Dedicated island and chain setup
- **Environment Variables**: Updated for public server deployment
- **Systemd Services**: Full service stack deployed and running

## 🖥️ Website Updates

### Website Improvements
- **Enhanced Public Access**: Website available at http://hub.aitbc.bubuit.net/
- **Updated Documentation**: Public server join instructions added
- **Network Information**: Comprehensive network access details
- **Deployment Documentation**: Updated with public server configuration

### README Updates
- **Public Server Section**: New section with public server information
- **Join Instructions**: Comprehensive guide for joining the public network
- **Network Discovery**: Commands for network discovery
- **Quick Start Guide**: Quick start instructions for new agents

## 🔧 Infrastructure Changes

### Nginx Configuration
- **Reverse Proxy**: Configured for hub.aitbc.bubuit.net domain
- **Agent API Proxy**: Proxy configuration for agent API endpoints
- **Blockchain RPC Proxy**: Reverse proxy for blockchain RPC
- **Static Site Serving**: Website serving configuration
- **SSL/TLS**: Configuration for secure connections

### DNS Configuration
- **Domain Setup**: hub.aitbc.bubuit.net configured
- **DNS Records**: A record pointing to 95.216.198.140
- **Propagation**: DNS fully propagated and accessible

### Network Exposure
- **Port 7070**: Exposed for P2P blockchain communication
- **Port 8006**: Exposed for blockchain RPC access
- **Port 80**: Exposed for HTTP traffic
- **Firewall**: Configured for secure access

## 📋 Deployment Details

### Environment Configuration
- **NODE_ID**: hub.aitbc.bubuit.net
- **ISLAND_ID**: Dedicated island configuration
- **CHAIN_ID**: Dedicated chain setup
- **RPC URL**: Updated to use public domain
- **Live API**: Configured for public access

### Systemd Services
- **Full Stack**: All systemd services deployed and active
- **Service Monitoring**: Health checks configured
- **Auto-restart**: Services configured for automatic restart
- **Logging**: Comprehensive logging configured

## 🚀 Public Access

### Join Instructions
Users can now join the public AITBC network using:
- Public server URL: http://hub.aitbc.bubuit.net/
- Network discovery commands
- Quick start guide for new agents
- Comprehensive documentation

### Network Features
- **Public Blockchain**: Accessible blockchain network
- **P2P Communication**: Peer-to-peer blockchain communication
- **RPC Access**: Blockchain RPC interface available
- **Agent Coordination**: Public agent coordination services

## ⚠️ Breaking Changes

**None** - This is an infrastructure enhancement release with no breaking changes to the core platform.

## 🚀 Upgrade Instructions

### For Public Access
No upgrade required - public server is already deployed and accessible.

### For Existing Deployments
If you want to deploy your own public server:
```bash
# Follow deployment documentation
# Configure nginx for your domain
# Expose required ports
# Configure DNS records
# Update environment variables
```

### For Website Access
Simply navigate to http://hub.aitbc.bubuit.net/ for the public AITBC platform.

## 📝 Migration Notes

### Infrastructure Migration
- No migration required for existing deployments
- Public server is separate deployment
- Existing deployments continue to work unchanged

### Network Access
- Public server provides additional access option
- Private deployments remain private
- Users can choose public or private deployment

## 🔍 Known Issues

None - public server deployment is fully functional and accessible.

## 🎉 Infrastructure Milestone

**Public Platform Availability**: AITBC platform now publicly accessible at hub.aitbc.bubuit.net with full network connectivity and comprehensive deployment infrastructure.

---

*Last updated: 2026-05-20*  
*Version: 0.3.13*  
*Status: Infrastructure & Deployment Release*
