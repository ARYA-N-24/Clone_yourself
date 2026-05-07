/**
 * DailyBriefPanel — fetches and renders the AI daily brief on mount.
 * Renders exactly 3 urgent items, 2 follow-up items, and 1 risk string.
 * Requirements: 8.1, 8.2, 8.3
 */

import { useEffect, useState } from 'react'
import type { DailyBrief } from '@/types'
import { getDailyBrief } from '@/services/api'

type LoadState = 'loading' | 'ready' | 'error'

function BriefSection({
  title,
  items,
  icon,
  itemClass,
}: {
  title: string
  items: string[]
  icon: string
  itemClass: string
}) {
  return (
    <div>
      <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2 flex items-center gap-1">
        <span aria-hidden="true">{icon}</span> {title}
      </h4>
      <ul className="space-y-1">
        {items.map((item, i) => (
          <li key={i} className={`text-sm rounded px-2 py-1 ${itemClass}`}>
            {item}
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function DailyBriefPanel() {
  const [brief, setBrief] = useState<DailyBrief | null>(null)
  const [loadState, setLoadState] = useState<LoadState>('loading')

  useEffect(() => {
    let cancelled = false
    getDailyBrief()
      .then((data) => {
        if (!cancelled) {
          setBrief(data)
          setLoadState('ready')
        }
      })
      .catch(() => {
        if (!cancelled) setLoadState('error')
      })
    return () => { cancelled = true }
  }, [])

  if (loadState === 'loading') {
    return (
      <div className="animate-pulse space-y-3 p-4">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-4 bg-gray-200 rounded w-full" />
        ))}
      </div>
    )
  }

  if (loadState === 'error' || !brief) {
    return (
      <p className="text-sm text-gray-400 italic p-4">
        Daily brief unavailable right now.
      </p>
    )
  }

  const generatedAt = new Date(brief.generatedAt).toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
  })

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-800">Daily Brief</h3>
        <span className="text-xs text-gray-400">Generated {generatedAt}</span>
      </div>

      {/* Urgent items — exactly 3 (Req 8.1) */}
      <BriefSection
        title="Urgent"
        items={brief.urgentItems.slice(0, 3)}
        icon="🔴"
        itemClass="bg-red-50 text-red-800"
      />

      {/* Follow-up items — exactly 2 (Req 8.2) */}
      <BriefSection
        title="Follow-ups"
        items={brief.followups.slice(0, 2)}
        icon="🔁"
        itemClass="bg-yellow-50 text-yellow-800"
      />

      {/* Risk — exactly 1 (Req 8.3) */}
      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2 flex items-center gap-1">
          <span aria-hidden="true">⚠️</span> Risk
        </h4>
        <p className="text-sm bg-orange-50 text-orange-800 rounded px-2 py-1">
          {brief.risk}
        </p>
      </div>
    </div>
  )
}
