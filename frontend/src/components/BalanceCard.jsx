import { useState } from 'react'
import { simulatePayment } from '../api'

const formatINR = (paise) => {
  const rupees = paise / 100
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
  }).format(rupees)
}

export default function BalanceCard({ merchant, loading, onRefresh }) {
  const [isAdding, setIsAdding] = useState(false)
  const [amount, setAmount] = useState('50000')
  const [addingLoading, setAddingLoading] = useState(false)

  const handleAddFunds = async (e) => {
    e.preventDefault()
    setAddingLoading(true)
    try {
      await simulatePayment(parseFloat(amount))
      setIsAdding(false)
      if (onRefresh) onRefresh()
    } catch (err) {
      console.error('Failed to add funds:', err)
      alert('Failed to simulate payment: ' + (err.response?.data?.error || err.message))
    } finally {
      setAddingLoading(false)
    }
  }

  if (loading || !merchant) {
    return (
      <div className="glass-card p-6 animate-pulse">
        <div className="h-4 bg-gray-800 rounded w-1/3 mb-4"></div>
        <div className="h-10 bg-gray-800 rounded w-2/3"></div>
      </div>
    )
  }

  const available = merchant.available_balance_paise ?? 0
  const held = merchant.held_balance_paise ?? 0
  const total = available + held

  return (
    <div className="glass-card p-6">
      <div className="flex items-start justify-between mb-6">
        <div>
          <p className="text-gray-400 text-sm font-medium mb-1">Merchant Account</p>
          <h2 className="text-xl font-semibold text-white">{merchant.name}</h2>
          <p className="text-gray-500 text-xs font-mono mt-1">{merchant.bank_account_id}</p>
        </div>
        <button 
          onClick={() => setIsAdding(!isAdding)}
          className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center hover:bg-emerald-500/20 transition-colors group"
          title="Simulate Incoming Payment"
        >
          <svg className="w-5 h-5 text-emerald-400 group-hover:scale-110 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
          </svg>
        </button>
      </div>

      {isAdding && (
        <form onSubmit={handleAddFunds} className="mb-6 bg-emerald-500/5 border border-emerald-500/10 rounded-xl p-4 animate-in fade-in slide-in-from-top-2 duration-300">
          <label className="block text-emerald-400 text-[10px] font-bold uppercase tracking-wider mb-2">Simulate Customer Payment (INR)</label>
          <div className="flex gap-2">
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="bg-gray-900/50 border border-gray-700/50 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500/50 flex-grow"
              placeholder="Amount in ₹"
              min="1"
              required
            />
            <button
              type="submit"
              disabled={addingLoading}
              className="bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-gray-900 text-xs font-bold px-4 py-2 rounded-lg transition-colors whitespace-nowrap"
            >
              {addingLoading ? 'Processing...' : 'Add Balance'}
            </button>
            <button
              type="button"
              onClick={() => setIsAdding(false)}
              className="bg-gray-800 hover:bg-gray-700 text-gray-400 px-3 py-2 rounded-lg transition-colors"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </form>
      )}

      <div className="grid grid-cols-2 gap-4">
        {/* Available balance */}
        <div className="bg-gray-800/50 rounded-xl p-4 border border-gray-700/40">
          <p className="text-gray-400 text-xs font-medium mb-2 uppercase tracking-wider">Available</p>
          <p className="text-2xl font-bold text-emerald-400">{formatINR(available)}</p>
          <p className="text-gray-600 text-xs font-mono mt-1">{available.toLocaleString()} paise</p>
        </div>

        {/* Held balance */}
        <div className="bg-gray-800/50 rounded-xl p-4 border border-gray-700/40">
          <p className="text-gray-400 text-xs font-medium mb-2 uppercase tracking-wider">Held</p>
          <p className="text-2xl font-bold text-amber-400">{formatINR(held)}</p>
          <p className="text-gray-600 text-xs font-mono mt-1">{held.toLocaleString()} paise</p>
        </div>
      </div>

      {total > 0 && (
        <div className="mt-4 h-1.5 bg-gray-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-emerald-500 to-emerald-400 rounded-full transition-all duration-700"
            style={{ width: `${Math.round((available / total) * 100)}%` }}
          />
        </div>
      )}
      <p className="text-gray-600 text-xs mt-2">
        {total > 0 ? `${Math.round((available / total) * 100)}% available` : 'No balance yet'}
      </p>
    </div>
  )
}
