/**
 * FollowupList — displays pending follow-up suggestions with snooze/resolve actions.
 * Requirements: 7.4, 7.6, 7.7
 */

import { useState } from 'react'
import type { FollowupSuggestion } from '@/types'
import { snoozeFollowup, resolveFollowup } from '@/services/api'

interface FollowupListProps {
  followups: FollowupSuggestion[]
  onUpdate?: () => void
}

// Default snooze duration: 3 days from now
function defaultSnoozeUntil(): string {
  const d = new Date()
  d.setDate(d.getDate() + 3)
  return d.toISOString()
}

interface FollowupItemProps {
  followup: FollowupSuggestion
  onUpdate?: () => void
}

function FollowupItem({ followup, onUpdate }: FollowupItemProps) {
  const [actionState, setActionState] = useState<'idle' | 'snoozing' | 'resolving' | 'done'>('idle')
  const [error, setError] = useState('')

  async function handleSnooze() {
    setActionState('snoozing')
    setError('')
    try {
      await snoozeFollowup(followup.id, defaultSnoozeUntil())
      setActionState('done')
      onUpdate?.()
    } catch {
      setError('Failed to snooze. Try again.')
      setActionState('idle')
    }
  }

  async function handleResolve() {
    setActionState('resolving')
    setError('')
    try {
      await resolveFollowup(followup.id)
      setActionState('done')
      onUpdate?.()
    } catch {
      setError('Failed to resolve. Try again.')
      setActionState('idle')
    }
  }

  if (actionState === 'done') return null

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 space-y-2">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-gray-900 truncate">
            {followup.subject ?? '(no subject)'}
          </p>
          <p className="text-xs text-gray-500 mt-0.5">
            From: <span className="font-medium text-gray-700">{followup.sender}</span>
          </p>
        </div>
        <span className="text-xs font-medium text-orange-600 bg-orange-50 px-2 py-0.5 rounded-full whitespace-nowrap flex-shrink-0">
          {followup.daysElapsed}d ago
        </span>
      </div>

      {/* Draft preview */}
      {followup.draftText && (
        <p className="text-xs text-gray-500 bg-gray-50 rounded p-2 line-clamp-2 italic">
          &ldquo;{followup.draftText}&rdquo;
        </p>
      )}

      {/* Error */}
      {error && (
        <p className="text-xs text-red-600">{error}</p>
      )}

      {/* Actions */}
      <div className="flex gap-2 pt-1">
        <button
          onClick={handleSnooze}
          disabled={actionState !== 'idle'}
          className="text-xs font-medium text-gray-600 border border-gray-300 rounded px-3 py-1.5 hover:bg-gray-50 transition-colors disabled:opacity-40"
          aria-label={`Snooze follow-up for ${followup.sender}`}
        >
          {actionState === 'snoozing' ? 'Snoozing…' : 'Snooze 3d'}
        </button>
        <button
          onClick={handleResolve}
          disabled={actionState !== 'idle'}
          className="text-xs font-medium text-green-700 border border-green-300 rounded px-3 py-1.5 hover:bg-green-50 transition-colors disabled:opacity-40"
          aria-label={`Resolve follow-up for ${followup.sender}`}
        >
          {actionState === 'resolving' ? 'Resolving…' : 'Resolve'}
        </button>
      </div>
    </div>
  )
}

export default function FollowupList({ followups, onUpdate }: FollowupListProps) {
  if (followups.length === 0) {
    return (
      <p className="text-sm text-gray-400 italic">No pending follow-ups.</p>
    )
  }

  return (
    <div className="space-y-3">
      {followups.map((f) => (
        <FollowupItem key={f.id} followup={f} onUpdate={onUpdate} />
      ))}
    </div>
  )
}
