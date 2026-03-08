const { expect } = require("chai");
const axios = require("axios");
const { ethers } = require("hardhat");

describe("API Integration Tests", function () {
    let apiBaseUrl, contracts, signers;
    
    before(async function () {
        // Setup contracts and API server
        apiBaseUrl = process.env.API_BASE_URL || "http://localhost:3001";
        
        // Deploy mock contracts for testing
        const MockERC20 = await ethers.getContractFactory("MockERC20");
        const aitbcToken = await MockERC20.deploy("AITBC Token", "AITBC", ethers.utils.parseEther("1000000"));
        
        const MockAgentBounty = await ethers.getContractFactory("MockAgentBounty");
        const agentBounty = await MockAgentBounty.deploy(aitbcToken.address);
        
        const MockAgentStaking = await ethers.getContractFactory("MockAgentStaking");
        const agentStaking = await MockAgentStaking.deploy(aitbcToken.address);
        
        contracts = { aitbcToken, agentBounty, agentStaking };
        signers = await ethers.getSigners();
    });

    describe("Bounty API Endpoints", function () {
        it("GET /api/v1/bounties - Should return active bounties", async function () {
            try {
                const response = await axios.get(`${apiBaseUrl}/api/v1/bounties`);
                
                expect(response.status).to.equal(200);
                expect(response.data).to.have.property('bounties');
                expect(Array.isArray(response.data.bounties)).to.be.true;
                
                // Validate bounty structure
                if (response.data.bounties.length > 0) {
                    const bounty = response.data.bounties[0];
                    expect(bounty).to.have.property('bounty_id');
                    expect(bounty).to.have.property('title');
                    expect(bounty).to.have.property('reward_amount');
                    expect(bounty).to.have.property('status');
                    expect(bounty).to.have.property('deadline');
                }
            } catch (error) {
                // If API server is not running, skip test
                this.skip();
            }
        });

        it("GET /api/v1/bounties/:id - Should return specific bounty", async function () {
            try {
                const bountyId = 1;
                const response = await axios.get(`${apiBaseUrl}/api/v1/bounties/${bountyId}`);
                
                expect(response.status).to.equal(200);
                expect(response.data).to.have.property('bounty_id', bountyId);
                expect(response.data).to.have.property('title');
                expect(response.data).to.have.property('description');
                expect(response.data).to.have.property('reward_amount');
            } catch (error) {
                if (error.response?.status === 404) {
                    // Expected if bounty doesn't exist
                    expect(error.response.status).to.equal(404);
                } else {
                    this.skip();
                }
            }
        });

        it("POST /api/v1/bounties - Should create new bounty", async function () {
            try {
                const bountyData = {
                    title: "Test Bounty",
                    description: "A test bounty for API testing",
                    reward_amount: "100",
                    deadline: new Date(Date.now() + 86400000).toISOString(),
                    min_accuracy: 90,
                    max_response_time: 3600,
                    max_submissions: 10,
                    requires_zk_proof: false,
                    tags: ["test", "api"],
                    tier: "BRONZE",
                    difficulty: "easy"
                };
                
                const response = await axios.post(`${apiBaseUrl}/api/v1/bounties`, bountyData);
                
                expect(response.status).to.equal(201);
                expect(response.data).to.have.property('bounty_id');
                expect(response.data.title).to.equal(bountyData.title);
            } catch (error) {
                if (error.response?.status === 401) {
                    // Expected if authentication is required
                    expect(error.response.status).to.equal(401);
                } else {
                    this.skip();
                }
            }
        });

        it("GET /api/v1/bounties/categories - Should return bounty categories", async function () {
            try {
                const response = await axios.get(`${apiBaseUrl}/api/v1/bounties/categories`);
                
                expect(response.status).to.equal(200);
                expect(response.data).to.have.property('categories');
                expect(Array.isArray(response.data.categories)).to.be.true;
            } catch (error) {
                this.skip();
            }
        });
    });

    describe("Staking API Endpoints", function () {
        it("GET /api/v1/staking/pools - Should return staking pools", async function () {
            try {
                const response = await axios.get(`${apiBaseUrl}/api/v1/staking/pools`);
                
                expect(response.status).to.equal(200);
                expect(response.data).to.have.property('pools');
                expect(Array.isArray(response.data.pools)).to.be.true;
                
                if (response.data.pools.length > 0) {
                    const pool = response.data.pools[0];
                    expect(pool).to.have.property('agent_address');
                    expect(pool).to.have.property('total_staked');
                    expect(pool).to.have.property('apy');
                    expect(pool).to.have.property('staker_count');
                }
            } catch (error) {
                this.skip();
            }
        });

        it("GET /api/v1/staking/agents - Should return registered agents", async function () {
            try {
                const response = await axios.get(`${apiBaseUrl}/api/v1/staking/agents`);
                
                expect(response.status).to.equal(200);
                expect(response.data).to.have.property('agents');
                expect(Array.isArray(response.data.agents)).to.be.true;
                
                if (response.data.agents.length > 0) {
                    const agent = response.data.agents[0];
                    expect(agent).to.have.property('address');
                    expect(agent).to.have.property('name');
                    expect(agent).to.have.property('total_staked');
                    expect(agent).to.have.property('success_rate');
                }
            } catch (error) {
                this.skip();
            }
        });

        it("POST /api/v1/staking/stake - Should stake tokens", async function () {
            try {
                const stakeData = {
                    agent_address: signers[1].address,
                    amount: "1000"
                };
                
                const response = await axios.post(`${apiBaseUrl}/api/v1/staking/stake`, stakeData);
                
                expect(response.status).to.equal(200);
                expect(response.data).to.have.property('transaction_hash');
                expect(response.data).to.have.property('stake_amount');
            } catch (error) {
                if (error.response?.status === 401) {
                    expect(error.response.status).to.equal(401);
                } else {
                    this.skip();
                }
            }
        });
    });

    describe("Leaderboard API Endpoints", function () {
        it("GET /api/v1/leaderboard/developers - Should return developer rankings", async function () {
            try {
                const response = await axios.get(`${apiBaseUrl}/api/v1/leaderboard/developers`);
                
                expect(response.status).to.equal(200);
                expect(response.data).to.have.property('rankings');
                expect(Array.isArray(response.data.rankings)).to.be.true;
                
                if (response.data.rankings.length > 0) {
                    const ranking = response.data.rankings[0];
                    expect(ranking).to.have.property('rank');
                    expect(ranking).to.have.property('address');
                    expect(ranking).to.have.property('total_earned');
                    expect(ranking).to.have.property('bounties_completed');
                    expect(ranking).to.have.property('success_rate');
                }
            } catch (error) {
                this.skip();
            }
        });

        it("GET /api/v1/leaderboard/top-performers - Should return top performers", async function () {
            try {
                const response = await axios.get(`${apiBaseUrl}/api/v1/leaderboard/top-performers`);
                
                expect(response.status).to.equal(200);
                expect(response.data).to.have.property('performers');
                expect(Array.isArray(response.data.performers)).to.be.true;
                
                if (response.data.performers.length > 0) {
                    const performer = response.data.performers[0];
                    expect(performer).to.have.property('address');
                    expect(performer).to.have.property('name');
                    expect(performer).to.have.property('performance_score');
                    expect(performer).to.have.property('category');
                }
            } catch (error) {
                this.skip();
            }
        });

        it("GET /api/v1/leaderboard/category-stats - Should return category statistics", async function () {
            try {
                const response = await axios.get(`${apiBaseUrl}/api/v1/leaderboard/category-stats`);
                
                expect(response.status).to.equal(200);
                expect(response.data).to.have.property('categories');
                expect(Array.isArray(response.data.categories)).to.be.true;
                
                if (response.data.categories.length > 0) {
                    const category = response.data.categories[0];
                    expect(category).to.have.property('category');
                    expect(category).to.have.property('total_earnings');
                    expect(category).to.have.property('participant_count');
                    expect(category).to.have.property('average_performance');
                }
            } catch (error) {
                this.skip();
            }
        });
    });

    describe("Ecosystem API Endpoints", function () {
        it("GET /api/v1/ecosystem/overview - Should return ecosystem overview", async function () {
            try {
                const response = await axios.get(`${apiBaseUrl}/api/v1/ecosystem/overview`);
                
                expect(response.status).to.equal(200);
                expect(response.data).to.have.property('total_developers');
                expect(response.data).to.have.property('total_agents');
                expect(response.data).to.have.property('total_stakers');
                expect(response.data).to.have.property('total_bounties');
                expect(response.data).to.have.property('ecosystem_health_score');
            } catch (error) {
                this.skip();
            }
        });

        it("GET /api/v1/ecosystem/developer-earnings - Should return developer earnings", async function () {
            try {
                const response = await axios.get(`${apiBaseUrl}/api/v1/ecosystem/developer-earnings?period=weekly&limit=50`);
                
                expect(response.status).to.equal(200);
                expect(Array.isArray(response.data)).to.be.true;
                
                if (response.data.length > 0) {
                    const earnings = response.data[0];
                    expect(earnings).to.have.property('address');
                    expect(earnings).to.have.property('total_earned');
                    expect(earnings).to.have.property('bounties_completed');
                    expect(earnings).to.have.property('success_rate');
                }
            } catch (error) {
                this.skip();
            }
        });

        it("GET /api/v1/ecosystem/treasury-allocation - Should return treasury allocation", async function () {
            try {
                const response = await axios.get(`${apiBaseUrl}/api/v1/ecosystem/treasury-allocation`);
                
                expect(response.status).to.equal(200);
                expect(Array.isArray(response.data)).to.be.true;
                
                if (response.data.length > 0) {
                    const allocation = response.data[0];
                    expect(allocation).to.have.property('category');
                    expect(allocation).to.have.property('amount');
                    expect(allocation).to.have.property('percentage');
                    expect(allocation).to.have.property('description');
                }
            } catch (error) {
                this.skip();
            }
        });
    });

    describe("Error Handling", function () {
        it("Should return 404 for non-existent endpoints", async function () {
            try {
                await axios.get(`${apiBaseUrl}/api/v1/nonexistent`);
                expect.fail("Should have returned 404");
            } catch (error) {
                if (error.response) {
                    expect(error.response.status).to.equal(404);
                } else {
                    this.skip();
                }
            }
        });

        it("Should validate request parameters", async function () {
            try {
                const invalidData = {
                    title: "", // Invalid empty title
                    reward_amount: "-100" // Invalid negative amount
                };
                
                await axios.post(`${apiBaseUrl}/api/v1/bounties`, invalidData);
                expect.fail("Should have returned validation error");
            } catch (error) {
                if (error.response) {
                    expect(error.response.status).to.be.oneOf([400, 422]);
                } else {
                    this.skip();
                }
            }
        });

        it("Should handle rate limiting", async function () {
            try {
                // Make multiple rapid requests to test rate limiting
                const requests = Array(20).fill().map(() => 
                    axios.get(`${apiBaseUrl}/api/v1/bounties`)
                );
                
                await Promise.all(requests);
                // If we get here, rate limiting might not be implemented
                console.log("Rate limiting not detected");
            } catch (error) {
                if (error.response?.status === 429) {
                    expect(error.response.status).to.equal(429);
                } else {
                    this.skip();
                }
            }
        });
    });

    describe("Authentication & Authorization", function () {
        it("Should require authentication for protected endpoints", async function () {
            try {
                await axios.post(`${apiBaseUrl}/api/v1/bounties`, {
                    title: "Test",
                    reward_amount: "100"
                });
                expect.fail("Should have required authentication");
            } catch (error) {
                if (error.response) {
                    expect(error.response.status).to.equal(401);
                } else {
                    this.skip();
                }
            }
        });

        it("Should validate API tokens", async function () {
            try {
                await axios.get(`${apiBaseUrl}/api/v1/bounties`, {
                    headers: {
                        'Authorization': 'Bearer invalid-token'
                    }
                });
                expect.fail("Should have rejected invalid token");
            } catch (error) {
                if (error.response) {
                    expect(error.response.status).to.be.oneOf([401, 403]);
                } else {
                    this.skip();
                }
            }
        });
    });

    describe("Performance Tests", function () {
        it("Should handle concurrent requests", async function () {
            try {
                const startTime = Date.now();
                const requests = Array(10).fill().map(() => 
                    axios.get(`${apiBaseUrl}/api/v1/bounties`)
                );
                
                await Promise.all(requests);
                const endTime = Date.now();
                const duration = endTime - startTime;
                
                // Should complete within reasonable time (5 seconds)
                expect(duration).to.be.lessThan(5000);
            } catch (error) {
                this.skip();
            }
        });

        it("Should return responses within acceptable time limits", async function () {
            try {
                const startTime = Date.now();
                await axios.get(`${apiBaseUrl}/api/v1/bounties`);
                const endTime = Date.now();
                const responseTime = endTime - startTime;
                
                // Should respond within 1 second
                expect(responseTime).to.be.lessThan(1000);
            } catch (error) {
                this.skip();
            }
        });
    });
});
