import { useState } from 'react'
import { createPayout } from '../api'

// Generate a fresh UUID v4 for idempotency keys
const generateUUID = () => {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = Math.random() * 16 | 0
    return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16)
  })
}

export default function PayoutForm({ merchant, onPayoutCreated }) {
  const [amountRupees, setAmountRupees] = useState('')
  const [bankAccountId, setBankAccountId] = useState(merchant?.bank_account_id || '')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null) // { success: bool, message: str, payout?: obj }
  const [idempotencyKey] = useState(generateUUID) // stable for this form mount

  // Regenerate the idempotency key for a new request
  const [currentKey, setCurrentKey] = useState(idempotencyKey)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setResult(null)

    const rupees = parseFloat(amountRupees)
    if (!rupees || rupees <= 0) {
      setResult({ success: false, message: 'Please enter a valid amount.' })
      return
    }

    const amountPaise = Math.round(rupees * 100)
    if (amountPaise < 100) {
      setResult({ success: false, message: 'Minimum payout is ₹1.00 (100 paise).' })
      return
    }

    setLoading(true)
    try {
      const response = await createPayout(
        { amount_paise: amountPaise, bank_account_id: bankAccountId || merchant.bank_account_id },
        currentKey,
      )
      setResult({
        success: true,
        message: `Payout of ₹${rupees.toFixed(2)} requested successfully.`,
        payout: response.data,
      })
      setAmountRupees('')
      // Generate a fresh idempotency key for the next request
      setCurrentKey(generateUUID())
      if (onPayoutCreated) onPayoutCreated()
    } catch (err) {
      const status = err.response?.status
      const errorData = err.response?.data

      if (status === 402) {
        setResult({ success: false, message: 'Insufficient funds. Reduce the amount and try again.' })
      } else if (status === 409) {
        setResult({ success: false, message: 'Duplicate request detected. This payout is already being processed.' })
      } else if (status === 400) {
        setResult({ success: false, message: `Validation error: ${JSON.stringify(errorData)}` })
      } else {
        setResult({ success: false, message: 'Server error. Please try again.' })
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="glass-card p-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-8 h-8 rounded-lg bg-brand-500/20 border border-brand-500/30 flex items-center justify-center">
          <svg className="w-4 h-4 text-brand-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
        </div>
        <h3 className="text-base font-semibold text-gray-100">Request Payout</h3>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-2 uppercase tracking-wider">
            Amount (INR)
          </label>
          <div className="relative">
            <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-500 font-semibold">₹</span>
            <input
              type="number"
              step="0.01"
              min="1"
              className="input-field pl-8"
              placeholder="0.00"
              value={amountRupees}
              onChange={(e) => setAmountRupees(e.target.value)}
              disabled={loading}
            />
          </div>
          {amountRupees && (
            <p className="text-gray-600 text-xs font-mono mt-1.5">
              = {Math.round(parseFloat(amountRupees || 0) * 100).toLocaleString()} paise
            </p>
          )}
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-400 mb-2 uppercase tracking-wider">
            Bank Account
          </label>
          <input
            type="text"
            className="input-field"
            value={bankAccountId}
            onChange={(e) => setBankAccountId(e.target.value)}
            disabled={loading}
          />
        </div>

        {/* Idempotency key — shown for transparency */}
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-2 uppercase tracking-wider">
            Idempotency Key
            <span className="ml-2 text-gray-600 normal-case font-normal">(auto-generated)</span>
          </label>
          <div className="bg-gray-900/60 border border-gray-700/40 rounded-lg px-3 py-2 font-mono text-xs text-gray-500 break-all">
            {currentKey}
          </div>
        </div>

        {result && (
          <div className={`rounded-xl px-4 py-3 text-sm border ${
            result.success
              ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
              : 'bg-red-500/10 border-red-500/20 text-red-400'
          }`}>
            {result.success ? '✓ ' : '✗ '}{result.message}
            {result.payout && (
              <p className="font-mono text-xs mt-1 opacity-70">ID: {result.payout.id}</p>
            )}
          </div>
        )}

        <button
          type="submit"
          className="btn-primary w-full"
          disabled={loading || !amountRupees}
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
              </svg>
              Processing...
            </span>
          ) : 'Request Payout'}
        </button>
      </form>
    </div>
  )
}
