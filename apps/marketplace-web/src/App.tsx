import React from 'react'
import { BrowserRouter as Router, Routes, Route, Link, Navigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import BountyBoard from '@/pages/BountyBoard'
import StakingDashboard from '@/pages/StakingDashboard'
import DeveloperLeaderboard from '@/pages/DeveloperLeaderboard'
import EcosystemDashboard from '@/pages/EcosystemDashboard'

function App() {
  return (
    <Router>
      <div className="min-h-screen bg-background">
        {/* Navigation Header */}
        <header className="border-b bg-card">
          <div className="container mx-auto px-4 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-4">
                <h1 className="text-2xl font-bold text-primary">AITBC</h1>
                <span className="text-muted-foreground">Developer Ecosystem</span>
              </div>
              <nav className="flex items-center space-x-2">
                <Link to="/bounties">
                  <Button variant="ghost">Bounty Board</Button>
                </Link>
                <Link to="/staking">
                  <Button variant="ghost">Staking</Button>
                </Link>
                <Link to="/leaderboard">
                  <Button variant="ghost">Leaderboard</Button>
                </Link>
                <Link to="/ecosystem">
                  <Button variant="ghost">Ecosystem</Button>
                </Link>
              </nav>
            </div>
          </div>
        </header>

        {/* Main Content */}
        <main className="container mx-auto">
          <Routes>
            <Route path="/" element={<Navigate to="/bounties" replace />} />
            <Route path="/bounties" element={<BountyBoard />} />
            <Route path="/staking" element={<StakingDashboard />} />
            <Route path="/leaderboard" element={<DeveloperLeaderboard />} />
            <Route path="/ecosystem" element={<EcosystemDashboard />} />
          </Routes>
        </main>

        {/* Footer */}
        <footer className="border-t bg-card mt-8">
          <div className="container mx-auto px-4 py-6">
            <div className="text-center text-sm text-muted-foreground">
              <p>© 2024 AITBC Developer Ecosystem & DAO Grants System</p>
              <p className="mt-1">Built with React, TypeScript, and Tailwind CSS</p>
            </div>
          </div>
        </footer>
      </div>
    </Router>
  )
}

export default App
