/**
 * BalanceCard — displays available and held balance for the merchant.
 * Amounts are always displayed in INR (converting from paise) but the
 * raw paise values are also shown for transparency.
 */

const formatINR = (paise) => {
  const rupees = paise / 100
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
  }).format(rupees)
}

export default function BalanceCard({ merchant, loading }) {
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
        <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
          <svg className="w-5 h-5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
      </div>

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
