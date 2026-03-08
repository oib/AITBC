const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AITBC Smart Contract Integration", function () {
    let aitbcToken, zkVerifier, groth16Verifier;
    let aiPowerRental, paymentProcessor, performanceVerifier;
    let disputeResolution, escrowService, dynamicPricing;
    let owner, provider, consumer, arbitrator, oracle;
    
    beforeEach(async function () {
        // Get signers
        [owner, provider, consumer, arbitrator, oracle] = await ethers.getSigners();
        
        // Deploy mock contracts for testing
        const MockERC20 = await ethers.getContractFactory("MockERC20");
        aitbcToken = await MockERC20.deploy("AITBC Token", "AITBC", ethers.utils.parseEther("1000000"));
        await aitbcToken.deployed();
        
        const MockZKVerifier = await ethers.getContractFactory("MockZKVerifier");
        zkVerifier = await MockZKVerifier.deploy();
        await zkVerifier.deployed();
        
        const MockGroth16Verifier = await ethers.getContractFactory("MockGroth16Verifier");
        groth16Verifier = await MockGroth16Verifier.deploy();
        await groth16Verifier.deployed();
        
        // Deploy main contracts
        const AIPowerRental = await ethers.getContractFactory("AIPowerRental");
        aiPowerRental = await AIPowerRental.deploy(
            aitbcToken.address,
            zkVerifier.address,
            groth16Verifier.address
        );
        await aiPowerRental.deployed();
        
        const AITBCPaymentProcessor = await ethers.getContractFactory("AITBCPaymentProcessor");
        paymentProcessor = await AITBCPaymentProcessor.deploy(
            aitbcToken.address,
            aiPowerRental.address
        );
        await paymentProcessor.deployed();
        
        const PerformanceVerifier = await ethers.getContractFactory("PerformanceVerifier");
        performanceVerifier = await PerformanceVerifier.deploy(
            zkVerifier.address,
            groth16Verifier.address,
            aiPowerRental.address
        );
        await performanceVerifier.deployed();
        
        const DisputeResolution = await ethers.getContractFactory("DisputeResolution");
        disputeResolution = await DisputeResolution.deploy(
            aiPowerRental.address,
            paymentProcessor.address,
            performanceVerifier.address
        );
        await disputeResolution.deployed();
        
        const EscrowService = await ethers.getContractFactory("EscrowService");
        escrowService = await EscrowService.deploy(
            aitbcToken.address,
            aiPowerRental.address,
            paymentProcessor.address
        );
        await escrowService.deployed();
        
        const DynamicPricing = await ethers.getContractFactory("DynamicPricing");
        dynamicPricing = await DynamicPricing.deploy(
            aiPowerRental.address,
            performanceVerifier.address,
            aitbcToken.address
        );
        await dynamicPricing.deployed();
        
        // Setup authorizations
        await aiPowerRental.authorizeProvider(provider.address);
        await aiPowerRental.authorizeConsumer(consumer.address);
        await paymentProcessor.authorizePayee(provider.address);
        await paymentProcessor.authorizePayer(consumer.address);
        await performanceVerifier.authorizeOracle(oracle.address);
        await disputeResolution.authorizeArbitrator(arbitrator.address);
        await escrowService.authorizeArbiter(arbitrator.address);
        await dynamicPricing.authorizePriceOracle(oracle.address);
        
        // Transfer tokens to consumer for testing
        await aitbcToken.transfer(consumer.address, ethers.utils.parseEther("1000"));
    });

    describe("Contract Deployment", function () {
        it("Should deploy all contracts successfully", async function () {
            expect(await aiPowerRental.deployed()).to.be.true;
            expect(await paymentProcessor.deployed()).to.be.true;
            expect(await performanceVerifier.deployed()).to.be.true;
            expect(await disputeResolution.deployed()).to.be.true;
            expect(await escrowService.deployed()).to.be.true;
            expect(await dynamicPricing.deployed()).to.be.true;
        });

        it("Should have correct contract addresses", async function () {
            expect(await aiPowerRental.aitbcToken()).to.equal(aitbcToken.address);
            expect(await aiPowerRental.zkVerifier()).to.equal(zkVerifier.address);
            expect(await aiPowerRental.groth16Verifier()).to.equal(groth16Verifier.address);
        });
    });

    describe("AI Power Rental Integration", function () {
        it("Should create and manage rental agreements", async function () {
            const duration = 3600; // 1 hour
            const price = ethers.utils.parseEther("0.01");
            const gpuModel = "RTX 4090";
            const computeUnits = 100;
            
            const tx = await aiPowerRental.connect(consumer).createRental(
                provider.address,
                duration,
                price,
                gpuModel,
                computeUnits
            );
            
            const receipt = await tx.wait();
            const event = receipt.events.find(e => e.event === "AgreementCreated");
            expect(event).to.not.be.undefined;
            expect(event.args.provider).to.equal(provider.address);
            expect(event.args.consumer).to.equal(consumer.address);
            expect(event.args.price).to.equal(price);
        });

        it("Should start rental and lock payment", async function () {
            // Create rental first
            const duration = 3600;
            const price = ethers.utils.parseEther("0.01");
            const platformFee = price.mul(250).div(10000); // 2.5%
            const totalAmount = price.add(platformFee);
            
            const createTx = await aiPowerRental.connect(consumer).createRental(
                provider.address,
                duration,
                price,
                "RTX 4090",
                100
            );
            const createReceipt = await createTx.wait();
            const agreementId = createReceipt.events.find(e => e.event === "AgreementCreated").args.agreementId;
            
            // Approve tokens
            await aitbcToken.connect(consumer).approve(aiPowerRental.address, totalAmount);
            
            // Start rental
            const startTx = await aiPowerRental.connect(consumer).startRental(agreementId);
            const startReceipt = await startTx.wait();
            const startEvent = startReceipt.events.find(e => e.event === "AgreementStarted");
            expect(startEvent).to.not.be.undefined;
            
            // Check agreement status
            const agreement = await aiPowerRental.getRentalAgreement(agreementId);
            expect(agreement.status).to.equal(1); // Active
        });
    });

    describe("Payment Processing Integration", function () {
        it("Should create and confirm payments", async function () {
            const amount = ethers.utils.parseEther("0.01");
            const agreementId = ethers.utils.formatBytes32String("test-agreement");
            
            // Approve tokens
            await aitbcToken.connect(consumer).approve(paymentProcessor.address, amount);
            
            // Create payment
            const tx = await paymentProcessor.connect(consumer).createPayment(
                provider.address,
                amount,
                agreementId,
                "Test payment",
                0 // Immediate release
            );
            
            const receipt = await tx.wait();
            const event = receipt.events.find(e => e.event === "PaymentCreated");
            expect(event).to.not.be.undefined;
            expect(event.args.from).to.equal(consumer.address);
            expect(event.args.to).to.equal(provider.address);
            expect(event.args.amount).to.equal(amount);
        });

        it("Should handle escrow payments", async function () {
            const amount = ethers.utils.parseEther("0.01");
            const releaseTime = Math.floor(Date.now() / 1000) + 3600; // 1 hour from now
            
            // Approve tokens
            await aitbcToken.connect(consumer).approve(escrowService.address, amount);
            
            // Create escrow
            const tx = await escrowService.connect(consumer).createEscrow(
                provider.address,
                arbitrator.address,
                amount,
                0, // Standard escrow
                0, // Manual release
                releaseTime,
                "Test escrow"
            );
            
            const receipt = await tx.wait();
            const event = receipt.events.find(e => e.event === "EscrowCreated");
            expect(event).to.not.be.undefined;
            expect(event.args.depositor).to.equal(consumer.address);
            expect(event.args.beneficiary).to.equal(provider.address);
        });
    });

    describe("Performance Verification Integration", function () {
        it("Should submit and verify performance metrics", async function () {
            const agreementId = 1;
            const responseTime = 1000; // 1 second
            const accuracy = 95;
            const availability = 99;
            const computePower = 1000;
            const throughput = 100;
            const memoryUsage = 512;
            const energyEfficiency = 85;
            
            // Create mock ZK proof
            const mockZKProof = "0x" + "0".repeat(64);
            const mockGroth16Proof = "0x" + "0".repeat(64);
            
            // Submit performance
            const tx = await performanceVerifier.connect(provider).submitPerformance(
                agreementId,
                responseTime,
                accuracy,
                availability,
                computePower,
                throughput,
                memoryUsage,
                energyEfficiency,
                mockZKProof,
                mockGroth16Proof
            );
            
            const receipt = await tx.wait();
            const event = receipt.events.find(e => e.event === "PerformanceSubmitted");
            expect(event).to.not.be.undefined;
            expect(event.args.responseTime).to.equal(responseTime);
            expect(event.args.accuracy).to.equal(accuracy);
        });
    });

    describe("Dispute Resolution Integration", function () {
        it("Should file and manage disputes", async function () {
            const agreementId = 1;
            const reason = "Service quality issues";
            
            // File dispute
            const tx = await disputeResolution.connect(consumer).fileDispute(
                agreementId,
                provider.address,
                0, // Performance dispute
                reason,
                ethers.utils.formatBytes32String("evidence")
            );
            
            const receipt = await tx.wait();
            const event = receipt.events.find(e => e.event === "DisputeFiled");
            expect(event).to.not.be.undefined;
            expect(event.args.initiator).to.equal(consumer.address);
            expect(event.args.respondent).to.equal(provider.address);
        });
    });

    describe("Dynamic Pricing Integration", function () {
        it("Should update market data and calculate prices", async function () {
            const totalSupply = 10000;
            const totalDemand = 8000;
            const activeProviders = 50;
            const activeConsumers = 100;
            const totalVolume = ethers.utils.parseEther("100");
            const transactionCount = 1000;
            const averageResponseTime = 2000;
            const averageAccuracy = 96;
            const marketSentiment = 75;
            
            // Update market data
            const tx = await dynamicPricing.connect(oracle).updateMarketData(
                totalSupply,
                totalDemand,
                activeProviders,
                activeConsumers,
                totalVolume,
                transactionCount,
                averageResponseTime,
                averageAccuracy,
                marketSentiment
            );
            
            const receipt = await tx.wait();
            const event = receipt.events.find(e => e.event === "MarketDataUpdated");
            expect(event).to.not.be.undefined;
            expect(event.args.totalSupply).to.equal(totalSupply);
            expect(event.args.totalDemand).to.equal(totalDemand);
            
            // Get market price
            const marketPrice = await dynamicPricing.getMarketPrice(address(0), "");
            expect(marketPrice).to.be.gt(0);
        });
    });

    describe("Cross-Contract Integration", function () {
        it("Should handle complete rental lifecycle", async function () {
            // 1. Create rental agreement
            const duration = 3600;
            const price = ethers.utils.parseEther("0.01");
            const platformFee = price.mul(250).div(10000);
            const totalAmount = price.add(platformFee);
            
            const createTx = await aiPowerRental.connect(consumer).createRental(
                provider.address,
                duration,
                price,
                "RTX 4090",
                100
            );
            const createReceipt = await createTx.wait();
            const agreementId = createReceipt.events.find(e => e.event === "AgreementCreated").args.agreementId;
            
            // 2. Approve and start rental
            await aitbcToken.connect(consumer).approve(aiPowerRental.address, totalAmount);
            await aiPowerRental.connect(consumer).startRental(agreementId);
            
            // 3. Submit performance metrics
            const mockZKProof = "0x" + "0".repeat(64);
            const mockGroth16Proof = "0x" + "0".repeat(64);
            
            await performanceVerifier.connect(provider).submitPerformance(
                agreementId,
                1000, // responseTime
                95,  // accuracy
                99,  // availability
                1000, // computePower
                100,  // throughput
                512,  // memoryUsage
                85,   // energyEfficiency
                mockZKProof,
                mockGroth16Proof
            );
            
            // 4. Complete rental
            await aiPowerRental.connect(provider).completeRental(agreementId);
            
            // 5. Verify final state
            const agreement = await aiPowerRental.getRentalAgreement(agreementId);
            expect(agreement.status).to.equal(2); // Completed
        });
    });

    describe("Security Tests", function () {
        it("Should prevent unauthorized access", async function () {
            // Try to create rental without authorization
            await expect(
                aiPowerRental.connect(arbitrator).createRental(
                    provider.address,
                    3600,
                    ethers.utils.parseEther("0.01"),
                    "RTX 4090",
                    100
                )
            ).to.be.revertedWith("Not authorized consumer");
        });

        it("Should handle emergency pause", async function () {
            // Pause contracts
            await aiPowerRental.pause();
            await paymentProcessor.pause();
            await performanceVerifier.pause();
            await disputeResolution.pause();
            await escrowService.pause();
            await dynamicPricing.pause();
            
            // Try to perform operations while paused
            await expect(
                aiPowerRental.connect(consumer).createRental(
                    provider.address,
                    3600,
                    ethers.utils.parseEther("0.01"),
                    "RTX 4090",
                    100
                )
            ).to.be.revertedWith("Pausable: paused");
            
            // Unpause
            await aiPowerRental.unpause();
            await paymentProcessor.unpause();
            await performanceVerifier.unpause();
            await disputeResolution.unpause();
            await escrowService.unpause();
            await dynamicPricing.unpause();
        });
    });

    describe("Gas Optimization Tests", function () {
        it("Should track gas usage for major operations", async function () {
            // Create rental
            const tx = await aiPowerRental.connect(consumer).createRental(
                provider.address,
                3600,
                ethers.utils.parseEther("0.01"),
                "RTX 4090",
                100
            );
            const receipt = await tx.wait();
            
            console.log(`Gas used for createRental: ${receipt.gasUsed.toString()}`);
            
            // Should be reasonable gas usage
            expect(receipt.gasUsed).to.be.lt(500000); // Less than 500k gas
        });
    });
});

// Mock contracts for testing
const MockERC20Source = `
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockERC20 is ERC20 {
    constructor(string memory name, string memory symbol, uint256 initialSupply) ERC20(name, symbol) {
        _mint(msg.sender, initialSupply);
    }
}
`;

const MockZKVerifierSource = `
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract MockZKVerifier {
    function verifyPerformanceProof(
        uint256,
        uint256,
        uint256,
        uint256,
        uint256,
        bytes memory
    ) external pure returns (bool) {
        return true;
    }
}
`;

const MockGroth16VerifierSource = `
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract MockGroth16Verifier {
    function verifyProof(bytes memory) external pure returns (bool) {
        return true;
    }
}
`;
