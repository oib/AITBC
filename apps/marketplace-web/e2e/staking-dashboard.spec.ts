import { test, expect } from '@playwright/test';

test.describe('Staking Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should display staking dashboard page correctly', async ({ page }) => {
    // Navigate to staking dashboard
    await page.click('text=Staking');
    
    // Check page title and header
    await expect(page.locator('h1')).toContainText('Staking Dashboard');
    await expect(page.locator('text=Developer Ecosystem')).toBeVisible();
    
    // Check navigation is active
    await expect(page.locator('button:has-text("Staking")')).toHaveClass(/variant=default/);
  });

  test('should display staking overview cards', async ({ page }) => {
    await page.click('text=Staking');
    
    // Check overview cards are present
    await expect(page.locator('text=Total Staked')).toBeVisible();
    await expect(page.locator('text=My Stakes')).toBeVisible();
    await expect(page.locator('text=Available Rewards')).toBeVisible();
    await expect(page.locator('text=Average APY')).toBeVisible();
  });

  test('should display staking tabs', async ({ page }) => {
    await page.click('text=Staking');
    
    // Check tab navigation
    await expect(page.locator('button:has-text("My Stakes")')).toBeVisible();
    await expect(page.locator('button:has-text("Available Agents")')).toBeVisible();
    await expect(page.locator('button:has-text("Staking Pools")')).toBeVisible();
    await expect(page.locator('button:has-text("Rewards")')).toBeVisible();
  });

  test('should display my stakes tab', async ({ page }) => {
    await page.click('text=Staking');
    
    // My Stakes tab should be active by default
    await expect(page.locator('button:has-text("My Stakes")')).toHaveClass(/data-state=active/);
    
    // Check stakes table
    await expect(page.locator('[data-testid="stakes-table"]')).toBeVisible();
    
    // Check table headers
    await expect(page.locator('text=Agent')).toBeVisible();
    await expect(page.locator('text=Amount Staked')).toBeVisible();
    await expect(page.locator('text=APY')).toBeVisible();
    await expect(page.locator('text=Rewards')).toBeVisible();
    await expect(page.locator('text=Actions')).toBeVisible();
  });

  test('should display available agents tab', async ({ page }) => {
    await page.click('text=Staking');
    await page.click('button:has-text("Available Agents")');
    
    // Check agents list
    await expect(page.locator('[data-testid="agents-list"]')).toBeVisible();
    
    // Check agent cards
    const agentCards = page.locator('[data-testid="agent-card"]');
    const count = await agentCards.count();
    
    if (count > 0) {
      // Check first agent card elements
      const firstAgent = agentCards.first();
      await expect(firstAgent.locator('[data-testid="agent-name"]')).toBeVisible();
      await expect(firstAgent.locator('[data-testid="agent-performance"]')).toBeVisible();
      await expect(firstAgent.locator('[data-testid="agent-apy"]')).toBeVisible();
      await expect(firstAgent.locator('button:has-text("Stake")')).toBeVisible();
    }
  });

  test('should display staking pools tab', async ({ page }) => {
    await page.click('text=Staking');
    await page.click('button:has-text("Staking Pools")');
    
    // Check pools table
    await expect(page.locator('[data-testid="pools-table"]')).toBeVisible();
    
    // Check table headers
    await expect(page.locator('text=Agent Address')).toBeVisible();
    await expect(page.locator('text=Total Staked')).toBeVisible();
    await expect(page.locator('text=Stakers')).toBeVisible();
    await expect(page.locator('text=APY')).toBeVisible();
    await expect(page.locator('text=Utilization')).toBeVisible();
  });

  test('should display rewards tab', async ({ page }) => {
    await page.click('text=Staking');
    await page.click('button:has-text("Rewards")');
    
    // Check rewards section
    await expect(page.locator('[data-testid="rewards-section"]')).toBeVisible();
    
    // Check rewards summary
    await expect(page.locator('text=Total Earned')).toBeVisible();
    await expect(page.locator('text=Pending Rewards')).toBeVisible();
    await expect(page.locator('text=Claim History')).toBeVisible();
    
    // Check claim button
    await expect(page.locator('button:has-text("Claim Rewards")')).toBeVisible();
  });

  test('should handle staking modal', async ({ page }) => {
    await page.click('text=Staking');
    await page.click('button:has-text("Available Agents")');
    
    // Wait for agents to load
    await page.waitForSelector('[data-testid="agents-list"]', { timeout: 10000 });
    
    const agentCards = page.locator('[data-testid="agent-card"]');
    const count = await agentCards.count();
    
    if (count > 0) {
      // Click stake button on first agent
      await agentCards.first().locator('button:has-text("Stake")').click();
      
      // Check staking modal appears
      await expect(page.locator('[data-testid="staking-modal"]')).toBeVisible();
      await expect(page.locator('text=Stake Tokens')).toBeVisible();
      
      // Check modal content
      await expect(page.locator('input[name="amount"]')).toBeVisible();
      await expect(page.locator('text=Available Balance')).toBeVisible();
      await expect(page.locator('text=Estimated APY')).toBeVisible();
      
      // Check modal buttons
      await expect(page.locator('button:has-text("Confirm Stake")')).toBeVisible();
      await expect(page.locator('button:has-text("Cancel")')).toBeVisible();
      
      // Close modal
      await page.click('button:has-text("Cancel")');
      await expect(page.locator('[data-testid="staking-modal"]')).not.toBeVisible();
    }
  });

  test('should validate staking amount', async ({ page }) => {
    await page.click('text=Staking');
    await page.click('button:has-text("Available Agents")');
    
    await page.waitForSelector('[data-testid="agents-list"]', { timeout: 10000 });
    
    const agentCards = page.locator('[data-testid="agent-card"]');
    const count = await agentCards.count();
    
    if (count > 0) {
      await agentCards.first().locator('button:has-text("Stake")').click();
      
      // Try to stake without amount
      await page.click('button:has-text("Confirm Stake")');
      
      // Check validation error
      await expect(page.locator('text=Amount is required')).toBeVisible();
      
      // Try to stake invalid amount
      await page.fill('input[name="amount"]', '0');
      await page.click('button:has-text("Confirm Stake")');
      
      // Check validation error
      await expect(page.locator('text=Amount must be greater than 0')).toBeVisible();
      
      // Try to stake more than available
      await page.fill('input[name="amount"]', '999999999');
      await page.click('button:has-text("Confirm Stake")');
      
      // Check validation error
      await expect(page.locator('text=Insufficient balance')).toBeVisible();
    }
  });

  test('should handle unstaking', async ({ page }) => {
    await page.click('text=Staking');
    
    // Wait for stakes to load
    await page.waitForSelector('[data-testid="stakes-table"]', { timeout: 10000 });
    
    const stakeRows = page.locator('[data-testid="stake-row"]');
    const count = await stakeRows.count();
    
    if (count > 0) {
      // Click unstake button on first stake
      await stakeRows.first().locator('button:has-text("Unstake")').click();
      
      // Check unstaking modal appears
      await expect(page.locator('[data-testid="unstaking-modal"]')).toBeVisible();
      await expect(page.locator('text=Unstake Tokens')).toBeVisible();
      
      // Check modal content
      await expect(page.locator('text=Staked Amount')).toBeVisible();
      await expect(page.locator('text=Unstaking Period')).toBeVisible();
      await expect(page.locator('text=Early Unstaking Penalty')).toBeVisible();
      
      // Check modal buttons
      await expect(page.locator('button:has-text("Confirm Unstake")')).toBeVisible();
      await expect(page.locator('button:has-text("Cancel")')).toBeVisible();
      
      // Close modal
      await page.click('button:has-text("Cancel")');
      await expect(page.locator('[data-testid="unstaking-modal"]')).not.toBeVisible();
    }
  });

  test('should display agent performance metrics', async ({ page }) => {
    await page.click('text=Staking');
    await page.click('button:has-text("Available Agents")');
    
    await page.waitForSelector('[data-testid="agents-list"]', { timeout: 10000 });
    
    const agentCards = page.locator('[data-testid="agent-card"]');
    const count = await agentCards.count();
    
    if (count > 0) {
      const firstAgent = agentCards.first();
      
      // Check performance metrics
      await expect(firstAgent.locator('[data-testid="success-rate"]')).toBeVisible();
      await expect(firstAgent.locator('[data-testid="total-tasks"]')).toBeVisible();
      await expect(firstAgent.locator('[data-testid="average-accuracy"]')).toBeVisible();
      await expect(firstAgent.locator('[data-testid="reliability-score"]')).toBeVisible();
    }
  });

  test('should handle rewards claiming', async ({ page }) => {
    await page.click('text=Staking');
    await page.click('button:has-text("Rewards")');
    
    // Wait for rewards to load
    await page.waitForSelector('[data-testid="rewards-section"]', { timeout: 10000 });
    
    // Check if there are claimable rewards
    const claimButton = page.locator('button:has-text("Claim Rewards")');
    const isDisabled = await claimButton.isDisabled();
    
    if (!isDisabled) {
      // Click claim rewards
      await claimButton.click();
      
      // Check confirmation modal
      await expect(page.locator('[data-testid="claim-modal"]')).toBeVisible();
      await expect(page.locator('text=Claim Rewards')).toBeVisible();
      
      // Check claim details
      await expect(page.locator('text=Total Rewards')).toBeVisible();
      await expect(page.locator('text=Gas Fee')).toBeVisible();
      await expect(page.locator('text=Net Amount')).toBeVisible();
      
      // Confirm claim
      await page.click('button:has-text("Confirm Claim")');
      
      // Check success message
      await expect(page.locator('[data-testid="success-message"]')).toBeVisible();
      await expect(page.locator('text=Rewards claimed successfully')).toBeVisible();
    }
  });

  test('should display staking statistics', async ({ page }) => {
    await page.click('text=Staking');
    
    // Check statistics section
    await expect(page.locator('[data-testid="staking-stats"]')).toBeVisible();
    
    // Check stat items
    await expect(page.locator('text=Total Value Locked')).toBeVisible();
    await expect(page.locator('text=Number of Stakers')).toBeVisible();
    await expect(page.locator('text=Average Stake Amount')).toBeVisible();
    await expect(page.locator('text=Total Rewards Distributed')).toBeVisible();
  });

  test('should handle wallet connection for staking', async ({ page }) => {
    await page.click('text=Staking');
    
    // Check wallet connection button
    await expect(page.locator('button:has-text("Connect Wallet")')).toBeVisible();
    
    // Try to stake without wallet connection
    await page.click('button:has-text("Available Agents")');
    
    await page.waitForSelector('[data-testid="agents-list"]', { timeout: 10000 });
    
    const agentCards = page.locator('[data-testid="agent-card"]');
    const count = await agentCards.count();
    
    if (count > 0) {
      await agentCards.first().locator('button:has-text("Stake")').click();
      
      // Should show wallet connection required
      await expect(page.locator('text=Connect wallet to stake')).toBeVisible();
      await expect(page.locator('button:has-text("Connect Wallet")')).toBeVisible();
    }
  });

  test('should be responsive on mobile', async ({ page }) => {
    // Set mobile viewport
    await page.setViewportSize({ width: 375, height: 667 });
    
    await page.click('text=Staking');
    
    // Check mobile layout
    await expect(page.locator('h1')).toContainText('Staking Dashboard');
    
    // Check mobile navigation
    await expect(page.locator('button:has-text("☰")')).toBeVisible();
    
    // Check mobile tabs
    await expect(page.locator('button:has-text("My Stakes")')).toBeVisible();
    await expect(page.locator('button:has-text("Agents")')).toBeVisible();
    await expect(page.locator('button:has-text("Pools")')).toBeVisible();
    await expect(page.locator('button:has-text("Rewards")')).toBeVisible();
    
    // Check mobile table layout
    await expect(page.locator('[data-testid="mobile-stakes-table"]')).toBeVisible();
  });

  test('should handle loading states', async ({ page }) => {
    await page.click('text=Staking');
    
    // Check loading skeleton
    await expect(page.locator('[data-testid="loading-skeleton"]')).toBeVisible();
    
    // Wait for content to load
    await page.waitForSelector('[data-testid="stakes-table"]', { timeout: 10000 });
    
    // Check loading skeleton is gone
    await expect(page.locator('[data-testid="loading-skeleton"]')).not.toBeVisible();
  });

  test('should handle error states', async ({ page }) => {
    // Mock API error
    await page.route('**/api/v1/staking/**', route => {
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Internal server error' })
      });
    });
    
    await page.click('text=Staking');
    
    // Check error message
    await expect(page.locator('[data-testid="error-message"]')).toBeVisible();
    await expect(page.locator('text=Failed to load staking data')).toBeVisible();
    
    // Check retry button
    await expect(page.locator('button:has-text("Retry")')).toBeVisible();
  });
});
