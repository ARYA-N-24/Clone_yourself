/**
 * AnalyticsWidget — displays productivity stats using stat cards and a bar chart.
 * Requirements: 11.4
 */

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import type { AnalyticsStats } from '@/types'

interface AnalyticsWidgetProps {
  stats: AnalyticsStats
}

interface StatCardProps {
  label: string
  value: number | string
  unit?: string
  color?: string
}

function StatCard({ label, value, unit, color = 'text-blue-600' }: StatCardProps) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 flex flex-col gap-1">
      <span className="text-xs text-gray-500 font-medium uppercase tracking-wide">{label}</span>
      <span className={`text-2xl font-bold ${color}`}>
        {value}
        {unit && <span className="text-sm font-normal text-gray-400 ml-1">{unit}</span>}
      </span>
    </div>
  )
}

export default function AnalyticsWidget({ stats }: AnalyticsWidgetProps) {
  const chartData = [
    { name: 'Replies', value: stats.repliesSent, fill: '#3b82f6' },
    { name: 'Events', value: stats.eventsCreated, fill: '#8b5cf6' },
    { name: 'Classified', value: stats.emailsClassified, fill: '#10b981' },
    { name: 'Automated', value: stats.actionsAutomated, fill: '#f59e0b' },
  ]

  const timeSavedHours = (stats.timeSavedMinutes / 60).toFixed(1)

  return (
    <div className="space-y-4">
      {/* Stat cards grid */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatCard
          label="Actions Automated"
          value={stats.actionsAutomated}
          color="text-amber-600"
        />
        <StatCard
          label="Time Saved"
          value={timeSavedHours}
          unit="hrs"
          color="text-green-600"
        />
        <StatCard
          label="Emails Classified"
          value={stats.emailsClassified}
          color="text-blue-600"
        />
        <StatCard
          label="Replies Sent"
          value={stats.repliesSent}
          color="text-indigo-600"
        />
        <StatCard
          label="Events Created"
          value={stats.eventsCreated}
          color="text-purple-600"
        />
      </div>

      {/* Bar chart */}
      <div className="bg-white rounded-lg border border-gray-200 p-4">
        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
          Activity Breakdown
        </h4>
        <ResponsiveContainer width="100%" height={140}>
          <BarChart data={chartData} barSize={28}>
            <XAxis
              dataKey="name"
              tick={{ fontSize: 11, fill: '#6b7280' }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: '#6b7280' }}
              axisLine={false}
              tickLine={false}
              allowDecimals={false}
            />
            <Tooltip
              contentStyle={{ fontSize: 12, borderRadius: 6 }}
              cursor={{ fill: '#f3f4f6' }}
            />
            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
              {chartData.map((entry, index) => (
                <Cell key={index} fill={entry.fill} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
