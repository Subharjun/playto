import { useState } from 'react'
import LoginForm from './LoginForm'
import SignupForm from './SignupForm'

export default function AuthScreen({ onLogin }) {
  const [activeTab, setActiveTab] = useState('login') // 'login' or 'signup'

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-8">
      <div className="w-full max-w-md">
        {/* Logo / Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-brand-600/20 border border-brand-500/30 mb-6 shadow-[0_0_15px_rgba(234,88,12,0.2)]">
            <svg className="w-8 h-8 text-brand-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M2.25 8.25h19.5M2.25 9h19.5m-16.5 5.25h6m-6 2.25h3m-3.75 3h15a2.25 2.25 0 002.25-2.25V6.75A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25v10.5A2.25 2.25 0 004.5 19.5z" />
            </svg>
          </div>
          <h1 className="text-3xl font-bold text-white mb-2 tracking-tight">Playto Pay</h1>
          <p className="text-gray-400 text-sm">Merchant Payout Dashboard</p>
        </div>

        <div className="glass-card p-1 sm:p-2 mb-6 flex rounded-xl bg-gray-900/50">
          <button
            onClick={() => setActiveTab('signup')}
            className={`flex-1 py-3 text-sm font-medium rounded-lg transition-all duration-200 ${
              activeTab === 'signup' 
                ? 'bg-brand-500 text-white shadow-lg shadow-brand-500/25' 
                : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
            }`}
          >
            New Merchant? Sign Up
          </button>
          <button
            onClick={() => setActiveTab('login')}
            className={`flex-1 py-3 text-sm font-medium rounded-lg transition-all duration-200 ${
              activeTab === 'login' 
                ? 'bg-brand-500 text-white shadow-lg shadow-brand-500/25' 
                : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
            }`}
          >
            Already a User? Sign In
          </button>
        </div>

        <div className="glass-card p-8 relative overflow-hidden">
          {/* Subtle background glow based on active tab */}
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full h-32 bg-brand-500/10 blur-3xl -z-10 rounded-full" />
          
          {activeTab === 'signup' ? (
            <SignupForm onLogin={onLogin} />
          ) : (
            <LoginForm onLogin={onLogin} />
          )}
        </div>
      </div>
    </div>
  )
}
