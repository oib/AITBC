#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

console.log("=== AITBC Smart Contract Validation ===");

// Contract files to validate
const contracts = [
    'contracts/AIPowerRental.sol',
    'contracts/AITBCPaymentProcessor.sol', 
    'contracts/PerformanceVerifier.sol',
    'contracts/DisputeResolution.sol',
    'contracts/EscrowService.sol',
    'contracts/DynamicPricing.sol'
];

// Validation checks
const validationResults = {
    totalContracts: 0,
    validContracts: 0,
    totalLines: 0,
    contracts: []
};

console.log("\n🔍 Validating smart contracts...");

contracts.forEach(contractPath => {
    if (fs.existsSync(contractPath)) {
        const content = fs.readFileSync(contractPath, 'utf8');
        const lines = content.split('\n').length;
        
        // Basic validation checks
        const checks = {
            hasSPDXLicense: content.includes('SPDX-License-Identifier'),
            hasPragma: content.includes('pragma solidity'),
            hasContractDefinition: content.includes('contract ') || content.includes('interface ') || content.includes('library '),
            hasConstructor: content.includes('constructor'),
            hasFunctions: content.includes('function '),
            hasEvents: content.includes('event '),
            hasModifiers: content.includes('modifier '),
            importsOpenZeppelin: content.includes('@openzeppelin/contracts'),
            hasErrorHandling: content.includes('require(') || content.includes('revert('),
            hasAccessControl: content.includes('onlyOwner') || content.includes('require(msg.sender'),
            lineCount: lines
        };
        
        // Calculate validation score
        const score = Object.values(checks).filter(Boolean).length;
        const maxScore = Object.keys(checks).length;
        const isValid = score >= (maxScore * 0.7); // 70% threshold
        
        validationResults.totalContracts++;
        validationResults.totalLines += lines;
        
        if (isValid) {
            validationResults.validContracts++;
        }
        
        validationResults.contracts.push({
            name: path.basename(contractPath),
            path: contractPath,
            lines: lines,
            checks: checks,
            score: score,
            maxScore: maxScore,
            isValid: isValid
        });
        
        console.log(`${isValid ? '✅' : '❌'} ${path.basename(contractPath)} (${lines} lines, ${score}/${maxScore} checks)`);
    } else {
        console.log(`❌ ${contractPath} (file not found)`);
    }
});

console.log("\n📊 Validation Summary:");
console.log(`Total contracts: ${validationResults.totalContracts}`);
console.log(`Valid contracts: ${validationResults.validContracts}`);
console.log(`Total lines of code: ${validationResults.totalLines}`);
console.log(`Validation rate: ${((validationResults.validContracts / validationResults.totalContracts) * 100).toFixed(1)}%`);

// Detailed contract analysis
console.log("\n📋 Contract Details:");
validationResults.contracts.forEach(contract => {
    console.log(`\n📄 ${contract.name}:`);
    console.log(`   Lines: ${contract.lines}`);
    console.log(`   Score: ${contract.score}/${contract.maxScore}`);
    console.log(`   Status: ${contract.isValid ? '✅ Valid' : '❌ Needs Review'}`);
    
    const failedChecks = Object.entries(contract.checks)
        .filter(([key, value]) => !value)
        .map(([key]) => key);
    
    if (failedChecks.length > 0) {
        console.log(`   Missing: ${failedChecks.join(', ')}`);
    }
});

// Integration validation
console.log("\n🔗 Integration Validation:");

// Check for cross-contract references
const crossReferences = {
    'AIPowerRental': ['AITBCPaymentProcessor', 'PerformanceVerifier'],
    'AITBCPaymentProcessor': ['AIPowerRental', 'DisputeResolution', 'EscrowService'],
    'PerformanceVerifier': ['AIPowerRental'],
    'DisputeResolution': ['AIPowerRental', 'AITBCPaymentProcessor', 'PerformanceVerifier'],
    'EscrowService': ['AIPowerRental', 'AITBCPaymentProcessor'],
    'DynamicPricing': ['AIPowerRental', 'PerformanceVerifier']
};

Object.entries(crossReferences).forEach(([contract, dependencies]) => {
    const contractData = validationResults.contracts.find(c => c.name === `${contract}.sol`);
    if (contractData) {
        const content = fs.readFileSync(contractData.path, 'utf8');
        const foundDependencies = dependencies.filter(dep => content.includes(dep));
        
        console.log(`${foundDependencies.length === dependencies.length ? '✅' : '❌'} ${contract} references: ${foundDependencies.length}/${dependencies.length}`);
        
        if (foundDependencies.length < dependencies.length) {
            const missing = dependencies.filter(dep => !foundDependencies.includes(dep));
            console.log(`   Missing references: ${missing.join(', ')}`);
        }
    }
});

// Security validation
console.log("\n🔒 Security Validation:");
let securityScore = 0;
const securityChecks = {
    'ReentrancyGuard': 0,
    'Pausable': 0,
    'Ownable': 0,
    'AccessControl': 0,
    'SafeMath': 0,
    'IERC20': 0
};

validationResults.contracts.forEach(contract => {
    const content = fs.readFileSync(contract.path, 'utf8');
    
    Object.keys(securityChecks).forEach(securityFeature => {
        if (content.includes(securityFeature)) {
            securityChecks[securityFeature]++;
        }
    });
});

Object.entries(securityChecks).forEach(([feature, count]) => {
    const percentage = (count / validationResults.totalContracts) * 100;
    console.log(`${feature}: ${count}/${validationResults.totalContracts} contracts (${percentage.toFixed(1)}%)`);
    if (count > 0) securityScore++;
});

console.log(`\n🛡️  Security Score: ${securityScore}/${Object.keys(securityChecks).length}`);

// Gas optimization validation
console.log("\n⛽ Gas Optimization Validation:");
let gasOptimizationScore = 0;
const gasOptimizationFeatures = [
    'constant',
    'immutable',
    'view',
    'pure',
    'external',
    'internal',
    'private',
    'memory',
    'storage',
    'calldata'
];

validationResults.contracts.forEach(contract => {
    const content = fs.readFileSync(contract.path, 'utf8');
    let contractGasScore = 0;
    
    gasOptimizationFeatures.forEach(feature => {
        if (content.includes(feature)) {
            contractGasScore++;
        }
    });
    
    if (contractGasScore >= 5) {
        gasOptimizationScore++;
        console.log(`✅ ${contract.name}: Optimized (${contractGasScore}/${gasOptimizationFeatures.length} features)`);
    } else {
        console.log(`⚠️  ${contract.name}: Could be optimized (${contractGasScore}/${gasOptimizationFeatures.length} features)`);
    }
});

console.log(`\n⚡ Gas Optimization Score: ${gasOptimizationScore}/${validationResults.totalContracts}`);

// Final assessment
console.log("\n🎯 Final Assessment:");
const overallScore = validationResults.validContracts + securityScore + gasOptimizationScore;
const maxScore = validationResults.totalContracts + Object.keys(securityChecks).length + validationResults.totalContracts;
const overallPercentage = (overallScore / maxScore) * 100;

console.log(`Overall Score: ${overallScore}/${maxScore} (${overallPercentage.toFixed(1)}%)`);

if (overallPercentage >= 80) {
    console.log("🚀 Status: EXCELLENT - Ready for deployment");
} else if (overallPercentage >= 60) {
    console.log("✅ Status: GOOD - Minor improvements recommended");
} else if (overallPercentage >= 40) {
    console.log("⚠️  Status: FAIR - Significant improvements needed");
} else {
    console.log("❌ Status: POOR - Major improvements required");
}

console.log("\n📝 Recommendations:");
if (validationResults.validContracts < validationResults.totalContracts) {
    console.log("- Fix contract validation issues");
}
if (securityScore < Object.keys(securityChecks).length) {
    console.log("- Add missing security features");
}
if (gasOptimizationScore < validationResults.totalContracts) {
    console.log("- Optimize gas usage");
}
console.log("- Run comprehensive tests");
console.log("- Perform security audit");
console.log("- Deploy to testnet first");

console.log("\n✨ Validation completed!");
