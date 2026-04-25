import { useState, useEffect, useCallback } from 'react'
import AuthScreen from './components/AuthScreen'
import BalanceCard from './components/BalanceCard'
import PayoutForm from './components/PayoutForm'
import PayoutHistory from './components/PayoutHistory'
import { getMerchantProfile, getPayouts } from './api'

export default function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(() => !!localStorage.getItem('authToken'))
  const [merchant, setMerchant] = useState(null)
  const [payouts, setPayouts] = useState([])
  const [merchantLoading, setMerchantLoading] = useState(false)
  const [payoutsLoading, setPayoutsLoading] = useState(false)
  const [error, setError] = useState(null)

  const fetchMerchant = useCallback(async () => {
    setMerchantLoading(true)
    try {
      const res = await getMerchantProfile()
      setMerchant(res.data)
      setError(null)
    } catch (err) {
      if (err.response?.status === 401 || err.response?.status === 403) {
        handleLogout()
      } else {
        setError('Failed to load merchant profile.')
      }
    } finally {
      setMerchantLoading(false)
    }
  }, [])

  const fetchPayouts = useCallback(async () => {
    setPayoutsLoading(true)
    try {
      const res = await getPayouts()
      setPayouts(res.data)
    } catch {
      // Silently fail on background refresh
    } finally {
      setPayoutsLoading(false)
    }
  }, [])

  const refreshAll = useCallback(() => {
    fetchMerchant()
    fetchPayouts()
  }, [fetchMerchant, fetchPayouts])

  useEffect(() => {
    if (isLoggedIn) {
      fetchMerchant()
      fetchPayouts()
    }
  }, [isLoggedIn, fetchMerchant, fetchPayouts])

  const handleLogin = () => {
    setIsLoggedIn(true)
  }

  const handleLogout = () => {
    localStorage.removeItem('authToken')
    setIsLoggedIn(false)
    setMerchant(null)
    setPayouts([])
  }

  if (!isLoggedIn) {
    return <AuthScreen onLogin={handleLogin} />
  }

  return (
    <div className="min-h-screen">
      {/* Top Navigation */}
      <nav className="border-b border-gray-800/60 bg-gray-950/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-brand-600/20 border border-brand-500/30 flex items-center justify-center">
              <svg className="w-4 h-4 text-brand-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M2.25 8.25h19.5M2.25 9h19.5m-16.5 5.25h6m-6 2.25h3m-3.75 3h15a2.25 2.25 0 002.25-2.25V6.75A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25v10.5A2.25 2.25 0 004.5 19.5z" />
              </svg>
            </div>
            <span className="font-bold text-white text-lg">Playto Pay</span>
            <span className="text-gray-600 text-sm hidden sm:block">/ Merchant Dashboard</span>
          </div>
          <button onClick={handleLogout} className="btn-secondary text-xs">
            Sign Out
          </button>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-6 py-8">
        {error && (
          <div className="mb-6 bg-red-500/10 border border-red-500/20 text-red-400 rounded-xl px-4 py-3 text-sm">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left column — balance + form */}
          <div className="lg:col-span-1 space-y-6">
            <BalanceCard merchant={merchant} loading={merchantLoading} onRefresh={refreshAll} />
            <PayoutForm merchant={merchant} onPayoutCreated={refreshAll} />
          </div>

          {/* Right column — payout history */}
          <div className="lg:col-span-2">
            <PayoutHistory
              payouts={payouts}
              loading={payoutsLoading}
              onRefresh={refreshAll}
            />
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-800/40 mt-16 py-6">
        <div className="max-w-6xl mx-auto px-6 text-center text-gray-700 text-xs">
          Playto Pay — Payout Engine Demo • Balances in paise • No floats, no race conditions
        </div>
      </footer>
    </div>
  )
}
