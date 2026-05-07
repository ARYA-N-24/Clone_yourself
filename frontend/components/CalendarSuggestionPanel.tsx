/**
 * CalendarSuggestionPanel — displays up to 3 AI-ranked meeting slot suggestions.
 * Requirements: 6.7, 6.8
 */

import { useState } from 'react'
import type { MeetingSlot } from '@/types'
import { createCalendarEvent } from '@/services/api'

interface CalendarSuggestionPanelProps {
  slots: MeetingSlot[]
  attendees?: string[]
  onEventCreated?: (slotIndex: number) => void
}

function formatSlot(start: string, end: string): string {
  try {
    const s = new Date(start)
    const e = new Date(end)
    const dateStr = s.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
    const startTime = s.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
    const endTime = e.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
    return `${dateStr} · ${startTime} – ${endTime}`
  } catch {
    return `${start} – ${end}`
  }
}

function ConfidenceBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const color = pct >= 80 ? 'text-green-700 bg-green-50' : pct >= 60 ? 'text-yellow-700 bg-yellow-50' : 'text-gray-600 bg-gray-100'
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${color}`}>
      {pct}% match
    </span>
  )
}

export default function CalendarSuggestionPanel({
  slots,
  attendees = [],
  onEventCreated,
}: CalendarSuggestionPanelProps) {
  const [confirmedIndex, setConfirmedIndex] = useState<number | null>(null)
  const [loadingIndex, setLoadingIndex] = useState<number | null>(null)
  const [error, setError] = useState('')

  // Show at most 3 slots (Req 6.7)
  const displaySlots = slots.slice(0, 3)

  async function handleConfirm(slot: MeetingSlot, index: number) {
    setLoadingIndex(index)
    setError('')
    try {
      await createCalendarEvent(slot, attendees)
      setConfirmedIndex(index)
      onEventCreated?.(index)
    } catch {
      setError('Failed to create calendar event. Please try again.')
    } finally {
      setLoadingIndex(null)
    }
  }

  if (displaySlots.length === 0) {
    return (
      <p className="text-sm text-gray-500 italic">No meeting slots available.</p>
    )
  }

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-gray-800">Suggested Meeting Times</h3>

      {error && (
        <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded p-2">{error}</p>
      )}

      {displaySlots.map((slot, i) => {
        const isConfirmed = confirmedIndex === i
        const isLoading = loadingIndex === i

        return (
          <div
            key={i}
            className={`rounded-lg border p-3 flex items-start justify-between gap-3 transition-colors ${
              isConfirmed ? 'border-green-300 bg-green-50' : 'border-gray-200 bg-white'
            }`}
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-medium text-gray-900">
                  {formatSlot(slot.slot.start, slot.slot.end)}
                </span>
                <ConfidenceBadge score={slot.confidenceScore} />
              </div>
              {slot.reason && (
                <p className="text-xs text-gray-500 mt-1">{slot.reason}</p>
              )}
            </div>

            {isConfirmed ? (
              <span className="text-xs font-medium text-green-700 whitespace-nowrap">
                ✓ Confirmed
              </span>
            ) : (
              <button
                onClick={() => handleConfirm(slot, i)}
                disabled={isLoading || confirmedIndex !== null}
                className="text-sm font-medium text-blue-600 hover:text-blue-800 whitespace-nowrap disabled:opacity-40 transition-colors"
                aria-label={`Confirm slot ${i + 1}`}
              >
                {isLoading ? 'Confirming…' : 'Confirm'}
              </button>
            )}
          </div>
        )
      })}
    </div>
  )
}
