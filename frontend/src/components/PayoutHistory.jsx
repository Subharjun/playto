import { useEffect, useRef } from 'react'

const STATUS_CONFIG = {
  pending:    { label: 'Pending',    cls: 'status-pending',    dot: 'bg-amber-400' },
  processing: { label: 'Processing', cls: 'status-processing', dot: 'bg-blue-400 animate-pulse' },
  completed:  { label: 'Completed',  cls: 'status-completed',  dot: 'bg-emerald-400' },
  failed:     { label: 'Failed',     cls: 'status-failed',     dot: 'bg-red-400' },
}

const formatINR = (paise) => {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
  }).format(paise / 100)
}

const formatDate = (iso) => {
  return new Date(iso).toLocaleString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export default function PayoutHistory({ payouts, loading, onRefresh }) {
  // Auto-refresh while any payout is in a non-terminal state
  const intervalRef = useRef(null)
  const hasPending = payouts.some(
    (p) => p.status === 'pending' || p.status === 'processing'
  )

  useEffect(() => {
    if (hasPending) {
      intervalRef.current = setInterval(onRefresh, 3000)
    }
    return () => clearInterval(intervalRef.current)
  }, [hasPending, onRefresh])

  return (
    <div className="glass-card overflow-hidden">
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800/60">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-purple-500/20 border border-purple-500/30 flex items-center justify-center">
            <svg className="w-4 h-4 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          </div>
          <h3 className="text-base font-semibold text-gray-100">Payout History</h3>
          {hasPending && (
            <span className="flex items-center gap-1 text-xs text-blue-400">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse"></span>
              Live
            </span>
          )}
        </div>
        <button
          onClick={onRefresh}
          className="btn-secondary text-xs"
          disabled={loading}
        >
          {loading ? '↻ Refreshing...' : '↻ Refresh'}
        </button>
      </div>

      {loading && payouts.length === 0 ? (
        <div className="p-6 space-y-3">
          {[1,2,3].map(i => (
            <div key={i} className="h-16 bg-gray-800/50 rounded-xl animate-pulse"></div>
          ))}
        </div>
      ) : payouts.length === 0 ? (
        <div className="px-6 py-16 text-center">
          <div className="w-12 h-12 rounded-2xl bg-gray-800/60 flex items-center justify-center mx-auto mb-4">
            <svg className="w-6 h-6 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2" />
            </svg>
          </div>
          <p className="text-gray-500 text-sm">No payouts yet.</p>
          <p className="text-gray-600 text-xs mt-1">Use the form above to request your first payout.</p>
        </div>
      ) : (
        <div className="divide-y divide-gray-800/50">
          {payouts.map((payout) => {
            const cfg = STATUS_CONFIG[payout.status] || STATUS_CONFIG.pending
            return (
              <div key={payout.id} className="px-6 py-4 hover:bg-gray-800/20 transition-colors group">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={cfg.cls}>
                        <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`}></span>
                        {cfg.label}
                      </span>
                      {payout.attempt_count > 1 && (
                        <span className="text-xs text-gray-600 font-mono">
                          attempt #{payout.attempt_count}
                        </span>
                      )}
                    </div>
                    <p className="text-white font-semibold text-lg">{formatINR(payout.amount_paise)}</p>
                    <p className="text-gray-600 text-xs font-mono mt-0.5 truncate">
                      → {payout.bank_account_id}
                    </p>
                    {payout.failure_reason && (
                      <p className="text-red-500 text-xs mt-1">{payout.failure_reason}</p>
                    )}
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-gray-400 text-xs">{formatDate(payout.created_at)}</p>
                    <p className="text-gray-700 text-xs font-mono mt-1 hidden group-hover:block truncate max-w-[140px]">
                      {payout.id.substring(0, 8)}...
                    </p>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
