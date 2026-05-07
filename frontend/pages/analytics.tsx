/**
 * Analytics page — full stats with time-series chart.
 * Requirements: 11.4
 */

import { useState } from 'react'
import { GetServerSideProps } from 'next'
import { getServerSession } from 'next-auth/next'
import { authOptions } from './api/auth/[...nextauth]'
import Navbar from '@/components/Navbar'
import AnalyticsWidget from '@/components/AnalyticsWidget'
import { useAnalytics } from '@/hooks/useAnalytics'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'

export const getServerSideProps: GetServerSideProps = async (context) => {
  const session = await getServerSession(context.req, context.res, authOptions)
  if (!session) {
    return { redirect: { destination: '/', permanent: false } }
  }
  return { props: {} }
}

// Generate mock time-series data for the past 7 days
function generateWeeklyData() {
  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
  return days.map((day) => ({
    day,
    replies: Math.floor(Math.random() * 8),
    events: Math.floor(Math.random() * 4),
    classified: Math.floor(Math.random() * 15),
  }))
}

const weeklyData = generateWeeklyData()

export default function AnalyticsPage() {
  const [period, setPeriod] = useState<'week' | 'month'>('week')
  const { stats, isLoading } = useAnalytics(period)

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />

      <main className="max-w-5xl mx-auto px-4 py-6 space-y-8">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold text-gray-900">Analytics</h1>

          {/* Period toggle */}
          <div className="flex gap-1">
            {(['week', 'month'] as const).map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={`px-3 py-1 text-sm font-medium rounded-md transition-colors ${
                  period === p
                    ? 'bg-blue-600 text-white'
                    : 'bg-white text-gray-600 border border-gray-300 hover:bg-gray-50'
                }`}
                aria-pressed={period === p}
              >
                {p === 'week' ? 'This Week' : 'This Month'}
              </button>
            ))}
          </div>
        </div>

        {/* Stats widget */}
        <section aria-label="Stats summary">
          {isLoading ? (
            <div className="animate-pulse grid grid-cols-2 gap-3 sm:grid-cols-3">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="h-20 bg-gray-200 rounded-lg" />
              ))}
            </div>
          ) : stats ? (
            <AnalyticsWidget stats={stats} />
          ) : (
            <p className="text-sm text-gray-400 italic">No analytics data available.</p>
          )}
        </section>

        {/* Time-series chart */}
        <section aria-label="Weekly activity chart">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
            Activity Over the Past Week
          </h2>
          <div className="bg-white rounded-lg border border-gray-200 p-4">
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={weeklyData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis
                  dataKey="day"
                  tick={{ fontSize: 12, fill: '#6b7280' }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 12, fill: '#6b7280' }}
                  axisLine={false}
                  tickLine={false}
                  allowDecimals={false}
                />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 6 }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line
                  type="monotone"
                  dataKey="replies"
                  stroke="#3b82f6"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  name="Replies Sent"
                />
                <Line
                  type="monotone"
                  dataKey="events"
                  stroke="#8b5cf6"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  name="Events Created"
                />
                <Line
                  type="monotone"
                  dataKey="classified"
                  stroke="#10b981"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  name="Emails Classified"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>
      </main>
    </div>
  )
}
