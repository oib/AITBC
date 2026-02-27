const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentBounty System", function () {
    let agentBounty, aitbcToken, performanceVerifier;
    let owner, bountyCreator, agent, arbitrator;
    
    beforeEach(async function () {
        // Get signers
        [owner, bountyCreator, agent, arbitrator] = await ethers.getSigners();
        
        // Deploy mock AITBC token
        const MockERC20 = await ethers.getContractFactory("MockERC20");
        aitbcToken = await MockERC20.deploy("AITBC Token", "AITBC", ethers.utils.parseEther("1000000"));
        await aitbcToken.deployed();
        
        // Deploy mock performance verifier
        const MockPerformanceVerifier = await ethers.getContractFactory("MockPerformanceVerifier");
        performanceVerifier = await MockPerformanceVerifier.deploy();
        await performanceVerifier.deployed();
        
        // Deploy AgentBounty contract
        const AgentBounty = await ethers.getContractFactory("AgentBounty");
        agentBounty = await AgentBounty.deploy(
            aitbcToken.address,
            performanceVerifier.address
        );
        await agentBounty.deployed();
        
        // Transfer tokens to bounty creator and agent
        await aitbcToken.transfer(bountyCreator.address, ethers.utils.parseEther("10000"));
        await aitbcToken.transfer(agent.address, ethers.utils.parseEther("10000"));
    });

    describe("Bounty Creation", function () {
        it("Should create a bounty successfully", async function () {
            const rewardAmount = ethers.utils.parseEther("100");
            const deadline = Math.floor(Date.now() / 1000) + 86400; // 24 hours from now
            
            await aitbcToken.connect(bountyCreator).approve(agentBounty.address, rewardAmount);
            
            const tx = await agentBounty.connect(bountyCreator).createBounty(
                "Test Bounty",
                "A test bounty for AI agents",
                rewardAmount,
                deadline,
                90, // min_accuracy
                3600, // max_response_time
                10, // max_submissions
                false, // requires_zk_proof
                ["test", "ai"],
                "BRONZE",
                "easy"
            );
            
            const receipt = await tx.wait();
            const event = receipt.events.find(e => e.event === "BountyCreated");
            
            expect(event.args.bountyId).to.equal(1);
            expect(event.args.creator).to.equal(bountyCreator.address);
            expect(event.args.rewardAmount).to.equal(rewardAmount);
        });

        it("Should fail if reward amount is zero", async function () {
            const deadline = Math.floor(Date.now() / 1000) + 86400;
            
            await aitbcToken.connect(bountyCreator).approve(agentBounty.address, ethers.utils.parseEther("100"));
            
            await expect(
                agentBounty.connect(bountyCreator).createBounty(
                    "Test Bounty",
                    "Description",
                    0,
                    deadline,
                    90,
                    3600,
                    10,
                    false,
                    ["test"],
                    "BRONZE",
                    "easy"
                )
            ).to.be.revertedWith("Reward amount must be greater than 0");
        });

        it("Should fail if deadline is in the past", async function () {
            const pastDeadline = Math.floor(Date.now() / 1000) - 3600; // 1 hour ago
            
            await aitbcToken.connect(bountyCreator).approve(agentBounty.address, ethers.utils.parseEther("100"));
            
            await expect(
                agentBounty.connect(bountyCreator).createBounty(
                    "Test Bounty",
                    "Description",
                    ethers.utils.parseEther("100"),
                    pastDeadline,
                    90,
                    3600,
                    10,
                    false,
                    ["test"],
                    "BRONZE",
                    "easy"
                )
            ).to.be.revertedWith("Deadline must be in the future");
        });
    });

    describe("Bounty Submission", function () {
        let bountyId;
        
        beforeEach(async function () {
            const rewardAmount = ethers.utils.parseEther("100");
            const deadline = Math.floor(Date.now() / 1000) + 86400;
            
            await aitbcToken.connect(bountyCreator).approve(agentBounty.address, rewardAmount);
            
            const tx = await agentBounty.connect(bountyCreator).createBounty(
                "Test Bounty",
                "Description",
                rewardAmount,
                deadline,
                90,
                3600,
                10,
                false,
                ["test"],
                "BRONZE",
                "easy"
            );
            
            const receipt = await tx.wait();
            bountyId = receipt.events.find(e => e.event === "BountyCreated").args.bountyId;
        });

        it("Should submit a bounty successfully", async function () {
            const submissionData = "test submission data";
            
            const tx = await agentBounty.connect(agent).submitBounty(
                bountyId,
                submissionData,
                []
            );
            
            const receipt = await tx.wait();
            const event = receipt.events.find(e => e.event === "BountySubmitted");
            
            expect(event.args.bountyId).to.equal(bountyId);
            expect(event.args.submitter).to.equal(agent.address);
            expect(event.args.submissionData).to.equal(submissionData);
        });

        it("Should fail if bounty doesn't exist", async function () {
            await expect(
                agentBounty.connect(agent).submitBounty(
                    999,
                    "test data",
                    []
                )
            ).to.be.revertedWith("Bounty does not exist");
        });

        it("Should fail if bounty is expired", async function () {
            // Fast forward time past deadline
            await ethers.provider.send("evm_increaseTime", [86400 * 2]); // 2 days
            await ethers.provider.send("evm_mine");
            
            await expect(
                agentBounty.connect(agent).submitBounty(
                    bountyId,
                    "test data",
                    []
                )
            ).to.be.revertedWith("Bounty has expired");
        });
    });

    describe("Bounty Verification", function () {
        let bountyId, submissionId;
        
        beforeEach(async function () {
            const rewardAmount = ethers.utils.parseEther("100");
            const deadline = Math.floor(Date.now() / 1000) + 86400;
            
            await aitbcToken.connect(bountyCreator).approve(agentBounty.address, rewardAmount);
            
            const tx = await agentBounty.connect(bountyCreator).createBounty(
                "Test Bounty",
                "Description",
                rewardAmount,
                deadline,
                90,
                3600,
                10,
                false,
                ["test"],
                "BRONZE",
                "easy"
            );
            
            const receipt = await tx.wait();
            bountyId = receipt.events.find(e => e.event === "BountyCreated").args.bountyId;
            
            const submitTx = await agentBounty.connect(agent).submitBounty(
                bountyId,
                "test submission data",
                []
            );
            
            const submitReceipt = await submitTx.wait();
            submissionId = submitReceipt.events.find(e => e.event === "BountySubmitted").args.submissionId;
        });

        it("Should verify a bounty successfully", async function () {
            // Mock performance verifier to return true
            await performanceVerifier.setMockResult(true);
            
            const tx = await agentBounty.verifyBounty(submissionId);
            const receipt = await tx.wait();
            const event = receipt.events.find(e => e.event === "BountyVerified");
            
            expect(event.args.submissionId).to.equal(submissionId);
            expect(event.args.success).to.be.true;
        });

        it("Should distribute rewards upon successful verification", async function () {
            // Mock performance verifier to return true
            await performanceVerifier.setMockResult(true);
            
            const initialBalance = await aitbcToken.balanceOf(agent.address);
            
            await agentBounty.verifyBounty(submissionId);
            
            const finalBalance = await aitbcToken.balanceOf(agent.address);
            expect(finalBalance).to.be.gt(initialBalance);
        });

        it("Should handle failed verification", async function () {
            // Mock performance verifier to return false
            await performanceVerifier.setMockResult(false);
            
            const tx = await agentBounty.verifyBounty(submissionId);
            const receipt = await tx.wait();
            const event = receipt.events.find(e => e.event === "BountyVerified");
            
            expect(event.args.success).to.be.false;
        });
    });

    describe("Fee Management", function () {
        it("Should allow owner to update fees", async function () {
            const newCreationFee = 75; // 0.75%
            
            await agentBounty.updateCreationFee(newCreationFee);
            
            expect(await agentBounty.creationFeePercentage()).to.equal(newCreationFee);
        });

        it("Should prevent non-owners from updating fees", async function () {
            await expect(
                agentBounty.connect(bountyCreator).updateCreationFee(75)
            ).to.be.revertedWith("Ownable: caller is not the owner");
        });

        it("Should validate fee ranges", async function () {
            // Test fee too high (over 1000 basis points = 10%)
            await expect(
                agentBounty.updateCreationFee(1001)
            ).to.be.revertedWith("Fee cannot exceed 1000 basis points");
        });
    });

    describe("Pausability", function () {
        it("Should allow owner to pause and unpause", async function () {
            await agentBounty.pause();
            expect(await agentBounty.paused()).to.be.true;
            
            await agentBounty.unpause();
            expect(await agentBounty.paused()).to.be.false;
        });

        it("Should prevent operations when paused", async function () {
            await agentBounty.pause();
            
            const rewardAmount = ethers.utils.parseEther("100");
            const deadline = Math.floor(Date.now() / 1000) + 86400;
            
            await aitbcToken.connect(bountyCreator).approve(agentBounty.address, rewardAmount);
            
            await expect(
                agentBounty.connect(bountyCreator).createBounty(
                    "Test Bounty",
                    "Description",
                    rewardAmount,
                    deadline,
                    90,
                    3600,
                    10,
                    false,
                    ["test"],
                    "BRONZE",
                    "easy"
                )
            ).to.be.revertedWith("Pausable: paused");
        });
    });
});
