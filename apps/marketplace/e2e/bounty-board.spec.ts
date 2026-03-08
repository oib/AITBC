import { test, expect } from '@playwright/test';

test.describe('Bounty Board', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should display bounty board page correctly', async ({ page }) => {
    // Navigate to bounty board
    await page.click('text=Bounty Board');
    
    // Check page title and header
    await expect(page.locator('h1')).toContainText('Bounty Board');
    await expect(page.locator('text=Developer Ecosystem')).toBeVisible();
    
    // Check navigation is active
    await expect(page.locator('button:has-text("Bounty Board")')).toHaveClass(/variant=default/);
  });

  test('should display bounty statistics cards', async ({ page }) => {
    await page.click('text=Bounty Board');
    
    // Check stats cards are present
    await expect(page.locator('text=Active Bounties')).toBeVisible();
    await expect(page.locator('text=Total Value')).toBeVisible();
    await expect(page.locator('text=Completed Today')).toBeVisible();
    await expect(page.locator('text=My Earnings')).toBeVisible();
  });

  test('should display bounty filters', async ({ page }) => {
    await page.click('text=Bounty Board');
    
    // Check filter elements
    await expect(page.locator('input[placeholder*="Search"]')).toBeVisible();
    await expect(page.locator('button:has-text("Filter")')).toBeVisible();
    
    // Check status filter dropdown
    await page.click('button:has-text("Status")');
    await expect(page.locator('text=Active')).toBeVisible();
    await expect(page.locator('text=Completed')).toBeVisible();
    await expect(page.locator('text=Expired')).toBeVisible();
  });

  test('should display bounty list', async ({ page }) => {
    await page.click('text=Bounty Board');
    
    // Wait for bounties to load
    await page.waitForSelector('[data-testid="bounty-list"]', { timeout: 10000 });
    
    // Check bounty items
    const bountyItems = page.locator('[data-testid="bounty-item"]');
    const count = await bountyItems.count();
    
    if (count > 0) {
      // Check first bounty has required elements
      const firstBounty = bountyItems.first();
      await expect(firstBounty.locator('[data-testid="bounty-title"]')).toBeVisible();
      await expect(firstBounty.locator('[data-testid="bounty-reward"]')).toBeVisible();
      await expect(firstBounty.locator('[data-testid="bounty-status"]')).toBeVisible();
      await expect(firstBounty.locator('[data-testid="bounty-deadline"]')).toBeVisible();
    }
  });

  test('should filter bounties by status', async ({ page }) => {
    await page.click('text=Bounty Board');
    
    // Wait for bounties to load
    await page.waitForSelector('[data-testid="bounty-list"]', { timeout: 10000 });
    
    // Get initial count
    const initialBounties = page.locator('[data-testid="bounty-item"]');
    const initialCount = await initialBounties.count();
    
    if (initialCount > 0) {
      // Filter by active status
      await page.click('button:has-text("Status")');
      await page.click('text=Active');
      
      // Wait for filter to apply
      await page.waitForTimeout(1000);
      
      // Check filtered results
      const filteredBounties = page.locator('[data-testid="bounty-item"]');
      const filteredCount = await filteredBounties.count();
      
      // Should have same or fewer bounties
      expect(filteredCount).toBeLessThanOrEqual(initialCount);
    }
  });

  test('should search bounties', async ({ page }) => {
    await page.click('text=Bounty Board');
    
    // Wait for bounties to load
    await page.waitForSelector('[data-testid="bounty-list"]', { timeout: 10000 });
    
    // Get initial count
    const initialBounties = page.locator('[data-testid="bounty-item"]');
    const initialCount = await initialBounties.count();
    
    if (initialCount > 0) {
      // Search for specific term
      await page.fill('input[placeholder*="Search"]', 'test');
      
      // Wait for search to apply
      await page.waitForTimeout(1000);
      
      // Check search results
      const searchResults = page.locator('[data-testid="bounty-item"]');
      const searchCount = await searchResults.count();
      
      // Should have same or fewer bounties
      expect(searchCount).toBeLessThanOrEqual(initialCount);
    }
  });

  test('should display bounty details modal', async ({ page }) => {
    await page.click('text=Bounty Board');
    
    // Wait for bounties to load
    await page.waitForSelector('[data-testid="bounty-list"]', { timeout: 10000 });
    
    const bountyItems = page.locator('[data-testid="bounty-item"]');
    const count = await bountyItems.count();
    
    if (count > 0) {
      // Click on first bounty
      await bountyItems.first().click();
      
      // Check modal appears
      await expect(page.locator('[data-testid="bounty-details-modal"]')).toBeVisible();
      await expect(page.locator('text=Bounty Details')).toBeVisible();
      
      // Check modal content
      await expect(page.locator('[data-testid="bounty-description"]')).toBeVisible();
      await expect(page.locator('[data-testid="bounty-requirements"]')).toBeVisible();
      await expect(page.locator('button:has-text("Submit Solution")')).toBeVisible();
      
      // Close modal
      await page.click('button:has-text("Close")');
      await expect(page.locator('[data-testid="bounty-details-modal"]')).not.toBeVisible();
    }
  });

  test('should handle wallet connection', async ({ page }) => {
    await page.click('text=Bounty Board');
    
    // Check wallet connection button
    await expect(page.locator('button:has-text("Connect Wallet")')).toBeVisible();
    
    // Click connect wallet
    await page.click('button:has-text("Connect Wallet")');
    
    // Check wallet modal appears
    await expect(page.locator('[data-testid="wallet-modal"]')).toBeVisible();
    await expect(page.locator('text=Connect Wallet')).toBeVisible();
    
    // Close wallet modal
    await page.keyboard.press('Escape');
    await expect(page.locator('[data-testid="wallet-modal"]')).not.toBeVisible();
  });

  test('should display bounty creation form', async ({ page }) => {
    await page.click('text=Bounty Board');
    
    // Check create bounty button
    await expect(page.locator('button:has-text("Create Bounty")')).toBeVisible();
    
    // Click create bounty
    await page.click('button:has-text("Create Bounty")');
    
    // Check form appears
    await expect(page.locator('[data-testid="create-bounty-form"]')).toBeVisible();
    await expect(page.locator('text=Create New Bounty')).toBeVisible();
    
    // Check form fields
    await expect(page.locator('input[name="title"]')).toBeVisible();
    await expect(page.locator('textarea[name="description"]')).toBeVisible();
    await expect(page.locator('input[name="reward"]')).toBeVisible();
    await expect(page.locator('select[name="tier"]')).toBeVisible();
    await expect(page.locator('select[name="difficulty"]')).toBeVisible();
    
    // Check form buttons
    await expect(page.locator('button:has-text("Create Bounty")')).toBeVisible();
    await expect(page.locator('button:has-text("Cancel")')).toBeVisible();
  });

  test('should validate bounty creation form', async ({ page }) => {
    await page.click('text=Bounty Board');
    await page.click('button:has-text("Create Bounty")');
    
    // Try to submit empty form
    await page.click('button:has-text("Create Bounty")');
    
    // Check validation errors
    await expect(page.locator('text=Title is required')).toBeVisible();
    await expect(page.locator('text=Description is required')).toBeVisible();
    await expect(page.locator('text=Reward amount is required')).toBeVisible();
  });

  test('should handle pagination', async ({ page }) => {
    await page.click('text=Bounty Board');
    
    // Wait for bounties to load
    await page.waitForSelector('[data-testid="bounty-list"]', { timeout: 10000 });
    
    // Check pagination controls
    const pagination = page.locator('[data-testid="pagination"]');
    const isVisible = await pagination.isVisible();
    
    if (isVisible) {
      // Check page buttons
      await expect(page.locator('button:has-text("Previous")')).toBeVisible();
      await expect(page.locator('button:has-text("Next")')).toBeVisible();
      
      // Check page numbers
      const pageNumbers = page.locator('[data-testid="page-number"]');
      const pageCount = await pageNumbers.count();
      
      if (pageCount > 1) {
        // Click next page
        await page.click('button:has-text("Next")');
        
        // Wait for page to load
        await page.waitForTimeout(1000);
        
        // Check URL or content changed
        const currentUrl = page.url();
        expect(currentUrl).toContain('page=');
      }
    }
  });

  test('should be responsive on mobile', async ({ page }) => {
    // Set mobile viewport
    await page.setViewportSize({ width: 375, height: 667 });
    
    await page.click('text=Bounty Board');
    
    // Check mobile layout
    await expect(page.locator('h1')).toContainText('Bounty Board');
    
    // Check mobile navigation
    await expect(page.locator('button:has-text("☰")')).toBeVisible();
    
    // Open mobile menu
    await page.click('button:has-text("☰")');
    await expect(page.locator('text=Staking')).toBeVisible();
    await expect(page.locator('text=Leaderboard')).toBeVisible();
    await expect(page.locator('text=Ecosystem')).toBeVisible();
    
    // Close mobile menu
    await page.click('button:has-text("☰")');
  });

  test('should handle loading states', async ({ page }) => {
    await page.click('text=Bounty Board');
    
    // Check loading skeleton
    await expect(page.locator('[data-testid="loading-skeleton"]')).toBeVisible();
    
    // Wait for content to load
    await page.waitForSelector('[data-testid="bounty-list"]', { timeout: 10000 });
    
    // Check loading skeleton is gone
    await expect(page.locator('[data-testid="loading-skeleton"]')).not.toBeVisible();
  });

  test('should handle error states', async ({ page }) => {
    // Mock API error
    await page.route('**/api/v1/bounties*', route => {
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Internal server error' })
      });
    });
    
    await page.click('text=Bounty Board');
    
    // Check error message
    await expect(page.locator('[data-testid="error-message"]')).toBeVisible();
    await expect(page.locator('text=Failed to load bounties')).toBeVisible();
    
    // Check retry button
    await expect(page.locator('button:has-text("Retry")')).toBeVisible();
  });
});
