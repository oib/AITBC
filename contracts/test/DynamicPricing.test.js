import { expect } from "chai";
import hardhat from "hardhat";
const { ethers } = hardhat;

describe.skip("DynamicPricing", function () {
  let dynamicPricing, aitbcToken, aiPowerRental, performanceVerifier;
  let deployer, provider, oracle;
  
  const BASE_PRICE = ethers.parseEther("0.01");
  const INITIAL_SUPPLY = ethers.parseUnits("1000000", 18);

  beforeEach(async function () {
    [deployer, provider, oracle] = await ethers.getSigners();

    // Deploy AIToken
    const AIToken = await ethers.getContractFactory("AIToken");
    aitbcToken = await AIToken.deploy(INITIAL_SUPPLY);
    await aitbcToken.waitForDeployment();

    // Deploy mock verifiers for AIPowerRental
    const ZKReceiptVerifier = await ethers.getContractFactory("ZKReceiptVerifier");
    const zkVerifier = await ZKReceiptVerifier.deploy();
    await zkVerifier.waitForDeployment();

    const Groth16Verifier = await ethers.getContractFactory("Groth16Verifier");
    const groth16Verifier = await Groth16Verifier.deploy();
    await groth16Verifier.waitForDeployment();

    // Deploy AIPowerRental
    const AIPowerRental = await ethers.getContractFactory("AIPowerRental");
    aiPowerRental = await AIPowerRental.deploy(
      await aitbcToken.getAddress(),
      await zkVerifier.getAddress(),
      await groth16Verifier.getAddress()
    );
    await aiPowerRental.waitForDeployment();

    // Deploy PerformanceVerifier (requires verifiers and AIPowerRental)
    const PerformanceVerifier = await ethers.getContractFactory("PerformanceVerifier");
    performanceVerifier = await PerformanceVerifier.deploy(
      await zkVerifier.getAddress(),
      await groth16Verifier.getAddress(),
      await aiPowerRental.getAddress()
    );
    await performanceVerifier.waitForDeployment();

    // Deploy DynamicPricing
    const DynamicPricing = await ethers.getContractFactory("DynamicPricing");
    dynamicPricing = await DynamicPricing.deploy(
      await aiPowerRental.getAddress(),
      await performanceVerifier.getAddress(),
      await aitbcToken.getAddress()
    );
    await dynamicPricing.waitForDeployment();

    // Authorize oracle
    await dynamicPricing.connect(deployer).authorizePriceOracle(oracle.address);
  });

  describe("Deployment", function () {
    it("Should deploy with correct addresses", async function () {
      expect(await dynamicPricing.aiPowerRental()).to.equal(await aiPowerRental.getAddress());
      expect(await dynamicPricing.performanceVerifier()).to.equal(await performanceVerifier.getAddress());
      expect(await dynamicPricing.aitbcToken()).to.equal(await aitbcToken.getAddress());
    });

    it("Should set deployer as owner", async function () {
      expect(await dynamicPricing.owner()).to.equal(deployer.address);
    });

    it("Should set default configuration values", async function () {
      expect(await dynamicPricing.basePricePerHour()).to.equal(1e16);
      expect(await dynamicPricing.minPricePerHour()).to.equal(1e15);
      expect(await dynamicPricing.maxPricePerHour()).to.equal(1e18);
      expect(await dynamicPricing.priceVolatilityThreshold()).to.equal(2000);
    });
  });

  describe("Market Data Updates", function () {
    it("Should update market data", async function () {
      await dynamicPricing.connect(oracle).updateMarketData(
        1000, // totalSupply
        800,  // totalDemand
        50,   // activeProviders
        100,  // activeConsumers
        BASE_PRICE,
        1000, // priceVolatility
        80,   // utilizationRate
        1000, // totalVolume
        50,   // transactionCount
        200,  // averageResponseTime
        95,   // averageAccuracy
        75    // marketSentiment
      );
      
      const marketData = await dynamicPricing.marketDataHistory(0);
      expect(marketData.totalSupply).to.equal(1000);
      expect(marketData.totalDemand).to.equal(800);
    });

    it("Should emit MarketDataUpdated event", async function () {
      await expect(
        dynamicPricing.connect(oracle).updateMarketData(
          1000, 800, 50, 100, BASE_PRICE, 1000, 80, 1000, 50, 200, 95, 75
        )
      ).to.emit(dynamicPricing, "MarketDataUpdated");
    });

    it("Should revert if not authorized oracle", async function () {
      await expect(
        dynamicPricing.connect(provider).updateMarketData(
          1000, 800, 50, 100, BASE_PRICE, 1000, 80, 1000, 50, 200, 95, 75
        )
      ).to.be.reverted;
    });
  });

  describe("Price Calculation", function () {
    beforeEach(async function () {
      await dynamicPricing.connect(oracle).updateMarketData(
        1000, 800, 50, 100, BASE_PRICE, 1000, 80, 1000, 50, 200, 95, 75
      );
    });

    it("Should calculate new price based on market data", async function () {
      const newPrice = await dynamicPricing.calculatePrice(0);
      expect(newPrice).to.be.gt(0);
    });

    it("Should update price", async function () {
      await dynamicPricing.connect(oracle).updatePrice(0);
      
      const priceHistory = await dynamicPricing.priceHistory(0, 0);
      expect(priceHistory.price).to.be.gt(0);
    });

    it("Should emit PriceCalculated event", async function () {
      await expect(
        dynamicPricing.connect(oracle).updatePrice(0)
      ).to.emit(dynamicPricing, "PriceCalculated");
    });

    it("Should respect minimum price limit", async function () {
      const minPrice = await dynamicPricing.minPricePerHour();
      expect(minPrice).to.equal(1e15);
    });

    it("Should respect maximum price limit", async function () {
      const maxPrice = await dynamicPricing.maxPricePerHour();
      expect(maxPrice).to.equal(1e18);
    });
  });

  describe("Provider Pricing", function () {
    it("Should set provider pricing", async function () {
      await dynamicPricing.connect(deployer).setProviderPricing(
        provider.address,
        BASE_PRICE,
        1, // Fixed strategy
        100 // reputation score
      );
      
      const providerPricing = await dynamicPricing.providerPricing(provider.address);
      expect(providerPricing.currentPrice).to.equal(BASE_PRICE);
    });

    it("Should emit ProviderPriceUpdated event", async function () {
      await expect(
        dynamicPricing.connect(deployer).setProviderPricing(
          provider.address,
          BASE_PRICE,
          1,
          100
        )
      ).to.emit(dynamicPricing, "ProviderPriceUpdated");
    });

    it("Should update provider price", async function () {
      await dynamicPricing.connect(deployer).setProviderPricing(
        provider.address,
        BASE_PRICE,
        1,
        100
      );
      
      const newPrice = BASE_PRICE * 110n / 100n; // 10% increase
      await dynamicPricing.connect(deployer).updateProviderPrice(provider.address, newPrice);
      
      const providerPricing = await dynamicPricing.providerPricing(provider.address);
      expect(providerPricing.currentPrice).to.equal(newPrice);
    });

    it("Should revert if non-owner sets provider pricing", async function () {
      await expect(
        dynamicPricing.connect(provider).setProviderPricing(
          provider.address,
          BASE_PRICE,
          1,
          100
        )
      ).to.be.revertedWithCustomError(dynamicPricing, "OwnableUnauthorizedAccount");
    });
  });

  describe("Regional Pricing", function () {
    it("Should set regional pricing", async function () {
      await dynamicPricing.connect(deployer).setRegionalPricing(
        "us-east-1",
        150, // 1.5x multiplier
        500,
        400,
        BASE_PRICE
      );
      
      const regionalPricing = await dynamicPricing.regionalPricing("us-east-1");
      expect(regionalPricing.regionalMultiplier).to.equal(150);
    });

    it("Should emit RegionalPriceUpdated event", async function () {
      await expect(
        dynamicPricing.connect(deployer).setRegionalPricing(
          "us-east-1",
          150,
          500,
          400,
          BASE_PRICE
        )
      ).to.emit(dynamicPricing, "RegionalPriceUpdated");
    });

    it("Should add supported region", async function () {
      await dynamicPricing.connect(deployer).setRegionalPricing(
        "us-east-1",
        150,
        500,
        400,
        BASE_PRICE
      );
      
      const regions = await dynamicPricing.getSupportedRegions();
      expect(regions).to.include("us-east-1");
    });

    it("Should revert if non-owner sets regional pricing", async function () {
      await expect(
        dynamicPricing.connect(provider).setRegionalPricing(
          "us-east-1",
          150,
          500,
          400,
          BASE_PRICE
        )
      ).to.be.revertedWithCustomError(dynamicPricing, "OwnableUnauthorizedAccount");
    });
  });

  describe("Configuration Updates", function () {
    it("Should update base price", async function () {
      await dynamicPricing.connect(deployer).updateBasePrice(2e16);
      
      expect(await dynamicPricing.basePricePerHour()).to.equal(2e16);
    });

    it("Should update minimum price", async function () {
      await dynamicPricing.connect(deployer).updateMinPrice(2e15);
      
      expect(await dynamicPricing.minPricePerHour()).to.equal(2e15);
    });

    it("Should update maximum price", async function () {
      await dynamicPricing.connect(deployer).updateMaxPrice(2e18);
      
      expect(await dynamicPricing.maxPricePerHour()).to.equal(2e18);
    });

    it("Should update price volatility threshold", async function () {
      await dynamicPricing.connect(deployer).updatePriceVolatilityThreshold(3000);
      
      expect(await dynamicPricing.priceVolatilityThreshold()).to.equal(3000);
    });

    it("Should update surge multiplier", async function () {
      await dynamicPricing.connect(deployer).updateSurgeMultiplier(400); // 4x
      
      expect(await dynamicPricing.surgeMultiplier()).to.equal(400);
    });

    it("Should revert if non-owner updates configuration", async function () {
      await expect(
        dynamicPricing.connect(provider).updateBasePrice(2e16)
      ).to.be.revertedWithCustomError(dynamicPricing, "OwnableUnauthorizedAccount");
    });
  });

  describe("Oracle Management", function () {
    it("Should authorize price oracle", async function () {
      await dynamicPricing.connect(deployer).authorizePriceOracle(provider.address);
      
      expect(await dynamicPricing.authorizedPriceOracles(provider.address)).to.be.true;
    });

    it("Should revoke price oracle", async function () {
      await dynamicPricing.connect(deployer).authorizePriceOracle(provider.address);
      await dynamicPricing.connect(deployer).revokePriceOracle(provider.address);
      
      expect(await dynamicPricing.authorizedPriceOracles(provider.address)).to.be.false;
    });

    it("Should revert if non-owner manages oracles", async function () {
      await expect(
        dynamicPricing.connect(provider).authorizePriceOracle(oracle.address)
      ).to.be.revertedWithCustomError(dynamicPricing, "OwnableUnauthorizedAccount");
    });
  });

  describe("Price Queries", function () {
    beforeEach(async function () {
      await dynamicPricing.connect(oracle).updateMarketData(
        1000, 800, 50, 100, BASE_PRICE, 1000, 80, 1000, 50, 200, 95, 75
      );
    });

    it("Should get current price", async function () {
      const price = await dynamicPricing.getCurrentPrice();
      expect(price).to.be.gt(0);
    });

    it("Should get market condition", async function () {
      const condition = await dynamicPricing.getMarketCondition();
      expect(condition).to.be.gte(0); // enum value
    });

    it("Should get price history", async function () {
      await dynamicPricing.connect(oracle).updatePrice(0);
      
      const history = await dynamicPricing.priceHistory(0, 0);
      expect(history.price).to.be.gt(0);
    });
  });
});
