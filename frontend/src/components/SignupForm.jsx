import { useState } from 'react'
import { signup } from '../api'

export default function SignupForm({ onLogin }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [bankAccountId, setBankAccountId] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!email.trim() || !password.trim() || !companyName.trim() || !bankAccountId.trim()) {
      setError('Please fill in all fields.')
      return
    }

    setLoading(true)
    setError('')
    try {
      localStorage.removeItem('authToken')
      
      const res = await signup(
        email.trim(), 
        password.trim(), 
        companyName.trim(), 
        bankAccountId.trim()
      )
      
      const token = res.data.token
      localStorage.setItem('authToken', token)
      onLogin(token)
    } catch (err) {
      if (err.response && err.response.data && err.response.data.error) {
        setError(err.response.data.error)
      } else {
        setError('An error occurred during sign up. Please try again.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
      <h2 className="text-xl font-bold text-white mb-6 text-center">Create a new account</h2>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="companyName" className="block text-sm font-medium text-gray-400 mb-2">
            Company / Business Name
          </label>
          <input
            id="companyName"
            type="text"
            className="input-field"
            placeholder="Acme Corp"
            value={companyName}
            onChange={(e) => { setCompanyName(e.target.value); setError('') }}
            required
          />
        </div>

        <div>
          <label htmlFor="email" className="block text-sm font-medium text-gray-400 mb-2">
            Email Address
          </label>
          <input
            id="email"
            type="email"
            className="input-field"
            placeholder="merchant@example.com"
            value={email}
            onChange={(e) => { setEmail(e.target.value); setError('') }}
            autoComplete="email"
            required
          />
        </div>

        <div>
          <label htmlFor="password" className="block text-sm font-medium text-gray-400 mb-2">
            Password
          </label>
          <input
            id="password"
            type="password"
            className="input-field"
            placeholder="••••••••"
            value={password}
            onChange={(e) => { setPassword(e.target.value); setError('') }}
            autoComplete="new-password"
            required
            minLength={8}
          />
        </div>

        <div>
          <label htmlFor="bankAccountId" className="block text-sm font-medium text-gray-400 mb-2">
            Settlement Bank Account ID
          </label>
          <input
            id="bankAccountId"
            type="text"
            className="input-field"
            placeholder="e.g. HDFC_123456"
            value={bankAccountId}
            onChange={(e) => { setBankAccountId(e.target.value); setError('') }}
            required
          />
        </div>

        {error && <p className="text-red-400 text-xs mt-2">{error}</p>}

        <button type="submit" className="btn-primary w-full mt-4" disabled={loading}>
          {loading ? 'Creating account...' : 'Sign Up'}
        </button>
      </form>
    </div>
  )
}
