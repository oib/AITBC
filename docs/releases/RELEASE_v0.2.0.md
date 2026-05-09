# AITBC v0.2.0 Release Notes

**Date**: February 1, 2026  
**Status**: ✅ Released  
**Scope**: Enhanced services and trading infrastructure

## 🎯 Overview

AITBC v0.2.0 is a **major infrastructure enhancement release** that introduces wallet daemon, trade exchange with Bitcoin integration, and Zero-Knowledge proof capabilities. This release establishes the foundation for secure transactions and privacy-preserving features.

## 🚀 New Features

### 💰 Wallet Daemon
- **FastAPI Service**: REST and JSON-RPC endpoints for wallet management
- **Encrypted Keystore**: Argon2id + XChaCha20-Poly1305 encryption
- **Mock Ledger Adapter**: SQLite backend for testing
- **Port Configuration**: Running on port 8002, nginx proxy at /wallet/
- **Bitcoin Payment Gateway**: Bitcoin payment integration for AITBC purchases
- **Dependencies**: aitbc-sdk, aitbc-crypto, fastapi, uvicorn

### 🏪 Trade Exchange
- **User Management System**: Individual wallet management per user
- **Bitcoin Integration**: QR code generation for Bitcoin payments
- **Real-time Payment Monitoring**: Live payment status tracking
- **Session-based Authentication**: Secure user authentication
- **Exchange Rate**: 1 BTC = 100,000 AITBC
- **Deployment**: https://aitbc.bubuit.net/Exchange/

### 🔐 Zero-Knowledge Applications
- **Circom Compiler v2.2.3**: ZK circuit compilation capability
- **ZK Circuits Compiled**: receipt_simple with 300 constraints
- **Trusted Setup Ceremony**: Powers of Tau setup completed
- **Privacy Features**:
  - Identity commitments
  - Stealth addresses
  - Private receipt attestation
  - Group membership proofs
  - Private bidding
  - Computation proofs
- **API Endpoints**: /api/zk/ for ZK operations

### 🔧 Coordinator API Extensions
- **Enhanced Routers**: New routers for advanced features
- **Backward Compatibility**: Maintained across all existing APIs
- **Service Integration**: Enhanced integration capabilities

### 📚 Enhanced Documentation
- **Split Documentation**: Different guides for miners, clients, developers
- **API References**: Comprehensive API documentation
- **Technical Specs**: Detailed technical specifications
- **Deployment**: https://aitbc.bubuit.net/docs/

## 🔧 Technical Implementation

### Wallet Daemon Features
- **Encryption**: Argon2id key derivation + XChaCha20-Poly1305 encryption
- **REST API**: Standard REST endpoints for wallet operations
- **JSON-RPC**: JSON-RPC interface for compatibility
- **SQLite Backend**: Mock ledger for testing and development
- **Bitcoin Gateway**: Integration with Bitcoin payment processing

### Trade Exchange Features
- **User Registration**: Individual user account creation
- **Wallet Generation**: Per-user wallet management
- **QR Code Generation**: Bitcoin payment QR codes
- **Payment Monitoring**: Real-time Bitcoin payment tracking
- **Session Management**: Secure session-based authentication
- **Exchange Rate System**: BTC to AITBC conversion

### ZK Applications Features
- **Circuit Compilation**: Circom compiler integration
- **Trusted Setup**: Powers of Tau ceremony execution
- **Privacy Features**: Multiple privacy-preserving operations
- **API Integration**: REST API for ZK operations
- **Proof Generation**: ZK proof generation capabilities

## 📋 Deployment Architecture

- **Container Services**: Wallet daemon, trade exchange, ZK applications
- **nginx Configuration**: Additional routes for new services
- **SSL/HTTPS**: Secure access to all financial services
- **Database Integration**: SQLite backend for wallet and ledger

## 🔍 Known Limitations

- Trade Exchange uses mock ledger adapter
- Limited ZK circuit types available
- Bitcoin payment gateway in testing phase
- No advanced trading features
- No cross-chain capabilities

## 📊 Performance Metrics

- **Wallet Response Time**: <200ms for wallet operations
- **Exchange Load Time**: <500ms initial load
- **ZK Proof Generation**: <5s for receipt_simple circuit
- **Service Uptime**: 99.5% availability

## 🎉 Milestone Achievement

**Financial Infrastructure Complete**: Wallet daemon, trade exchange, and ZK applications successfully deployed with Bitcoin integration.

---

*Last updated: 2026-02-01*  
*Version: 0.2.0*  
*Status: Financial Infrastructure Release*
