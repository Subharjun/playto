import { useState } from 'react'
import { login } from '../api'

export default function LoginForm({ onLogin }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!email.trim() || !password.trim()) {
      setError('Please enter your email and password.')
      return
    }

    setLoading(true)
    setError('')
    try {
      // Clear any invalid old token from localStorage so the interceptor doesn't send it
      localStorage.removeItem('authToken')
      
      const res = await login(email.trim(), password.trim())
      const token = res.data.token
      localStorage.setItem('authToken', token)
      onLogin(token)
    } catch (err) {
      if (err.response && err.response.status === 401) {
        setError('Invalid email or password.')
      } else {
        setError('An error occurred. Please try again.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
      <h2 className="text-xl font-bold text-white mb-6 text-center">Sign in to your account</h2>

      <form onSubmit={handleSubmit} className="space-y-4">
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
            autoComplete="current-password"
            required
          />
        </div>

        {error && <p className="text-red-400 text-xs mt-2">{error}</p>}

        <button type="submit" className="btn-primary w-full mt-4" disabled={loading}>
          {loading ? 'Signing in...' : 'Sign In'}
        </button>
      </form>
    </div>
  )
}
