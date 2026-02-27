const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentStaking System", function () {
    let agentStaking, aitbcToken;
    let owner, agent, staker1, staker2;
    
    beforeEach(async function () {
        // Get signers
        [owner, agent, staker1, staker2] = await ethers.getSigners();
        
        // Deploy mock AITBC token
        const MockERC20 = await ethers.getContractFactory("MockERC20");
        aitbcToken = await MockERC20.deploy("AITBC Token", "AITBC", ethers.utils.parseEther("1000000"));
        await aitbcToken.deployed();
        
        // Deploy AgentStaking contract
        const AgentStaking = await ethers.getContractFactory("AgentStaking");
        agentStaking = await AgentStaking.deploy(aitbcToken.address);
        await agentStaking.deployed();
        
        // Transfer tokens to stakers
        await aitbcToken.transfer(staker1.address, ethers.utils.parseEther("10000"));
        await aitbcToken.transfer(staker2.address, ethers.utils.parseEther("10000"));
    });

    describe("Agent Registration", function () {
        it("Should register an agent successfully", async function () {
            const tx = await agentStaking.connect(agent).registerAgent(
                "Test Agent",
                "https://example.com/metadata",
                ["AI", "ML", "NLP"]
            );
            
            const receipt = await tx.wait();
            const event = receipt.events.find(e => e.event === "AgentRegistered");
            
            expect(event.args.agentAddress).to.equal(agent.address);
            expect(event.args.name).to.equal("Test Agent");
            expect(event.args.metadataURI).to.equal("https://example.com/metadata");
        });

        it("Should fail if agent is already registered", async function () {
            await agentStaking.connect(agent).registerAgent(
                "Test Agent",
                "metadata",
                ["AI"]
            );
            
            await expect(
                agentStaking.connect(agent).registerAgent(
                    "Another Agent",
                    "metadata2",
                    ["ML"]
                )
            ).to.be.revertedWith("Agent already registered");
        });

        it("Should update agent metadata", async function () {
            await agentStaking.connect(agent).registerAgent(
                "Test Agent",
                "metadata",
                ["AI"]
            );
            
            await agentStaking.connect(agent).updateAgentMetadata(
                "Updated Agent",
                "https://updated.com/metadata",
                ["AI", "ML", "CV"]
            );
            
            const agentInfo = await agentStaking.getAgentInfo(agent.address);
            expect(agentInfo.name).to.equal("Updated Agent");
            expect(agentInfo.metadataURI).to.equal("https://updated.com/metadata");
        });
    });

    describe("Staking Operations", function () {
        beforeEach(async function () {
            await agentStaking.connect(agent).registerAgent(
                "Test Agent",
                "metadata",
                ["AI"]
            );
        });

        it("Should stake tokens successfully", async function () {
            const stakeAmount = ethers.utils.parseEther("1000");
            
            await aitbcToken.connect(staker1).approve(agentStaking.address, stakeAmount);
            
            const tx = await agentStaking.connect(staker1).stake(agent.address, stakeAmount);
            const receipt = await tx.wait();
            const event = receipt.events.find(e => e.event === "TokensStaked");
            
            expect(event.args.staker).to.equal(staker1.address);
            expect(event.args.agent).to.equal(agent.address);
            expect(event.args.amount).to.equal(stakeAmount);
        });

        it("Should track total staked per agent", async function () {
            const stakeAmount1 = ethers.utils.parseEther("500");
            const stakeAmount2 = ethers.utils.parseEther("300");
            
            await aitbcToken.connect(staker1).approve(agentStaking.address, stakeAmount1);
            await aitbcToken.connect(staker2).approve(agentStaking.address, stakeAmount2);
            
            await agentStaking.connect(staker1).stake(agent.address, stakeAmount1);
            await agentStaking.connect(staker2).stake(agent.address, stakeAmount2);
            
            const agentInfo = await agentStaking.getAgentInfo(agent.address);
            expect(agentInfo.totalStaked).to.equal(stakeAmount1.add(stakeAmount2));
        });

        it("Should unstake tokens successfully", async function () {
            const stakeAmount = ethers.utils.parseEther("1000");
            
            await aitbcToken.connect(staker1).approve(agentStaking.address, stakeAmount);
            await agentStaking.connect(staker1).stake(agent.address, stakeAmount);
            
            // Fast forward past unstaking delay
            await ethers.provider.send("evm_increaseTime", [86400 * 7]); // 7 days
            await ethers.provider.send("evm_mine");
            
            const initialBalance = await aitbcToken.balanceOf(staker1.address);
            
            await agentStaking.connect(staker1).unstake(agent.address, stakeAmount);
            
            const finalBalance = await aitbcToken.balanceOf(staker1.address);
            expect(finalBalance).to.equal(initialBalance.add(stakeAmount));
        });

        it("Should fail to unstake before delay period", async function () {
            const stakeAmount = ethers.utils.parseEther("1000");
            
            await aitbcToken.connect(staker1).approve(agentStaking.address, stakeAmount);
            await agentStaking.connect(staker1).stake(agent.address, stakeAmount);
            
            await expect(
                agentStaking.connect(staker1).unstake(agent.address, stakeAmount)
            ).to.be.revertedWith("Unstaking delay not met");
        });

        it("Should fail to unstake more than staked", async function () {
            const stakeAmount = ethers.utils.parseEther("1000");
            const unstakeAmount = ethers.utils.parseEther("1500");
            
            await aitbcToken.connect(staker1).approve(agentStaking.address, stakeAmount);
            await agentStaking.connect(staker1).stake(agent.address, stakeAmount);
            
            // Fast forward past unstaking delay
            await ethers.provider.send("evm_increaseTime", [86400 * 7]);
            await ethers.provider.send("evm_mine");
            
            await expect(
                agentStaking.connect(staker1).unstake(agent.address, unstakeAmount)
            ).to.be.revertedWith("Insufficient staked amount");
        });
    });

    describe("Reward Distribution", function () {
        beforeEach(async function () {
            await agentStaking.connect(agent).registerAgent(
                "Test Agent",
                "metadata",
                ["AI"]
            );
            
            const stakeAmount = ethers.utils.parseEther("1000");
            await aitbcToken.connect(staker1).approve(agentStaking.address, stakeAmount);
            await agentStaking.connect(staker1).stake(agent.address, stakeAmount);
        });

        it("Should distribute rewards proportionally", async function () {
            const rewardAmount = ethers.utils.parseEther("100");
            
            await aitbcToken.transfer(agentStaking.address, rewardAmount);
            
            const initialBalance = await aitbcToken.balanceOf(staker1.address);
            
            await agentStaking.distributeRewards(agent.address, rewardAmount);
            
            const finalBalance = await aitbcToken.balanceOf(staker1.address);
            expect(finalBalance).to.equal(initialBalance.add(rewardAmount));
        });

        it("Should handle multiple stakers proportionally", async function () {
            // Add second staker
            const stakeAmount2 = ethers.utils.parseEther("500");
            await aitbcToken.connect(staker2).approve(agentStaking.address, stakeAmount2);
            await agentStaking.connect(staker2).stake(agent.address, stakeAmount2);
            
            const rewardAmount = ethers.utils.parseEther("150");
            await aitbcToken.transfer(agentStaking.address, rewardAmount);
            
            const initialBalance1 = await aitbcToken.balanceOf(staker1.address);
            const initialBalance2 = await aitbcToken.balanceOf(staker2.address);
            
            await agentStaking.distributeRewards(agent.address, rewardAmount);
            
            const finalBalance1 = await aitbcToken.balanceOf(staker1.address);
            const finalBalance2 = await aitbcToken.balanceOf(staker2.address);
            
            // Staker1 had 1000 tokens, Staker2 had 500 tokens (2:1 ratio)
            // So rewards should be distributed 100:50
            expect(finalBalance1).to.equal(initialBalance1.add(ethers.utils.parseEther("100")));
            expect(finalBalance2).to.equal(initialBalance2.add(ethers.utils.parseEther("50")));
        });
    });

    describe("Agent Performance Tracking", function () {
        beforeEach(async function () {
            await agentStaking.connect(agent).registerAgent(
                "Test Agent",
                "metadata",
                ["AI"]
            );
        });

        it("Should record successful performance", async function () {
            await agentStaking.recordPerformance(agent.address, true, 95);
            
            const agentInfo = await agentStaking.getAgentInfo(agent.address);
            expect(agentInfo.successfulTasks).to.equal(1);
            expect(agentInfo.totalTasks).to.equal(1);
            expect(agentInfo.successRate).to.equal(10000); // 100% in basis points
        });

        it("Should record failed performance", async function () {
            await agentStaking.recordPerformance(agent.address, false, 60);
            
            const agentInfo = await agentStaking.getAgentInfo(agent.address);
            expect(agentInfo.successfulTasks).to.equal(0);
            expect(agentInfo.totalTasks).to.equal(1);
            expect(agentInfo.successRate).to.equal(0);
        });

        it("Should calculate success rate correctly", async function () {
            // Record multiple performances
            await agentStaking.recordPerformance(agent.address, true, 90);
            await agentStaking.recordPerformance(agent.address, true, 85);
            await agentStaking.recordPerformance(agent.address, false, 70);
            await agentStaking.recordPerformance(agent.address, true, 95);
            
            const agentInfo = await agentStaking.getAgentInfo(agent.address);
            expect(agentInfo.successfulTasks).to.equal(3);
            expect(agentInfo.totalTasks).to.equal(4);
            expect(agentInfo.successRate).to.equal(7500); // 75% in basis points
        });

        it("Should update average accuracy", async function () {
            await agentStaking.recordPerformance(agent.address, true, 90);
            await agentStaking.recordPerformance(agent.address, true, 80);
            await agentStaking.recordPerformance(agent.address, true, 85);
            
            const agentInfo = await agentStaking.getAgentInfo(agent.address);
            expect(agentInfo.averageAccuracy).to.equal(8500); // 85% in basis points
        });
    });

    describe("Slashing Mechanism", function () {
        beforeEach(async function () {
            await agentStaking.connect(agent).registerAgent(
                "Test Agent",
                "metadata",
                ["AI"]
            );
            
            const stakeAmount = ethers.utils.parseEther("1000");
            await aitbcToken.connect(staker1).approve(agentStaking.address, stakeAmount);
            await agentStaking.connect(staker1).stake(agent.address, stakeAmount);
        });

        it("Should slash agent stake for misconduct", async function () {
            const slashAmount = ethers.utils.parseEther("100");
            
            const initialContractBalance = await aitbcToken.balanceOf(agentStaking.address);
            
            await agentStaking.slashStake(agent.address, slashAmount, "Test slash reason");
            
            const finalContractBalance = await aitbcToken.balanceOf(agentStaking.address);
            expect(finalContractBalance).to.equal(initialContractBalance.sub(slashAmount));
        });

        it("Should emit slash event", async function () {
            const slashAmount = ethers.utils.parseEther("100");
            
            const tx = await agentStaking.slashStake(agent.address, slashAmount, "Test reason");
            const receipt = await tx.wait();
            const event = receipt.events.find(e => e.event === "StakeSlashed");
            
            expect(event.args.agent).to.equal(agent.address);
            expect(event.args.amount).to.equal(slashAmount);
            expect(event.args.reason).to.equal("Test reason");
        });

        it("Should fail to slash more than total staked", async function () {
            const totalStaked = await agentStaking.getAgentStakedAmount(agent.address);
            const slashAmount = totalStaked.add(ethers.utils.parseEther("1"));
            
            await expect(
                agentStaking.slashStake(agent.address, slashAmount, "Excessive slash")
            ).to.be.revertedWith("Slash amount exceeds total staked");
        });
    });

    describe("Access Control", function () {
        it("Should only allow owner to set performance recorder", async function () {
            await expect(
                agentStaking.connect(staker1).setPerformanceRecorder(staker2.address)
            ).to.be.revertedWith("Ownable: caller is not the owner");
        });

        it("Should allow owner to set performance recorder", async function () {
            await agentStaking.setPerformanceRecorder(staker2.address);
            expect(await agentStaking.performanceRecorder()).to.equal(staker2.address);
        });

        it("Should only allow performance recorder to record performance", async function () {
            await agentStaking.connect(agent).registerAgent(
                "Test Agent",
                "metadata",
                ["AI"]
            );
            
            await expect(
                agentStaking.connect(staker1).recordPerformance(agent.address, true, 90)
            ).to.be.revertedWith("Not authorized to record performance");
        });
    });
});
