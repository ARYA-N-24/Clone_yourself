/**
 * Calendar page — free slot detection and meeting suggestions.
 * Requirements: 6.1, 6.7
 */

import { useState, useEffect } from 'react'
import { GetServerSideProps } from 'next'
import { getServerSession } from 'next-auth/next'
import { authOptions } from './api/auth/[...nextauth]'
import Navbar from '@/components/Navbar'
import CalendarSuggestionPanel from '@/components/CalendarSuggestionPanel'
import { getCalendarSlots } from '@/services/api'
import type { TimeSlot } from '@/types'

export const getServerSideProps: GetServerSideProps = async (context) => {
  const session = await getServerSession(context.req, context.res, authOptions)
  if (!session) {
    return { redirect: { destination: '/', permanent: false } }
  }
  return { props: {} }
}

function formatSlot(slot: TimeSlot): string {
  try {
    const s = new Date(slot.start)
    const e = new Date(slot.end)
    const date = s.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
    const start = s.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
    const end = e.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
    return `${date} · ${start} – ${end}`
  } catch {
    return `${slot.start} – ${slot.end}`
  }
}

export default function CalendarPage() {
  const [freeSlots, setFreeSlots] = useState<TimeSlot[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const today = new Date()
    const nextWeek = new Date(today)
    nextWeek.setDate(today.getDate() + 7)

    getCalendarSlots(
      today.toISOString().split('T')[0],
      nextWeek.toISOString().split('T')[0],
    )
      .then(setFreeSlots)
      .catch(() => setError('Could not load calendar slots.'))
      .finally(() => setIsLoading(false))
  }, [])

  // Convert free TimeSlots to MeetingSlots for the suggestion panel
  const meetingSlots = freeSlots.slice(0, 3).map((slot) => ({
    slot,
    confidenceScore: 0.85,
    reason: 'Available slot within your working hours',
  }))

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />

      <main className="max-w-4xl mx-auto px-4 py-6 space-y-8">
        <h1 className="text-xl font-bold text-gray-900">Calendar</h1>

        {/* Meeting suggestions */}
        <section aria-label="Meeting suggestions">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
            Suggested Meeting Times
          </h2>
          {isLoading ? (
            <div className="animate-pulse space-y-2">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-14 bg-gray-200 rounded-lg" />
              ))}
            </div>
          ) : error ? (
            <p className="text-sm text-red-500">{error}</p>
          ) : (
            <CalendarSuggestionPanel slots={meetingSlots} />
          )}
        </section>

        {/* All free slots */}
        <section aria-label="Free slots">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
            All Free Slots (Next 7 Days)
          </h2>
          {isLoading ? (
            <div className="animate-pulse space-y-2">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="h-10 bg-gray-200 rounded" />
              ))}
            </div>
          ) : freeSlots.length > 0 ? (
            <ul className="space-y-1">
              {freeSlots.map((slot, i) => (
                <li
                  key={i}
                  className="text-sm text-gray-700 bg-white border border-gray-200 rounded px-3 py-2"
                >
                  {formatSlot(slot)}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-400 italic">No free slots found.</p>
          )}
        </section>
      </main>
    </div>
  )
}
