/**
 * Typed Axios API client for the Clone Yourself Platform backend.
 *
 * All functions attach the NextAuth JWT from the session as a Bearer token.
 * Base URL is read from NEXT_PUBLIC_API_URL (defaults to http://localhost:8000).
 *
 * Requirements: 1.4, 2.1, 4.4
 */

import axios, { AxiosInstance, InternalAxiosRequestConfig } from 'axios'
import { getSession } from 'next-auth/react'
import type {
  AnalyticsStats,
  DailyBrief,
  DailyMetrics,
  DashboardPayload,
  Email,
  FollowupSuggestion,
  MeetingSlot,
  ReplyDraft,
  TimeSlot,
  UserPreferences,
  CalendarEvent,
} from '@/types'

// ─── Axios instance ──────────────────────────────────────────────────────────

const baseURL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

const apiClient: AxiosInstance = axios.create({
  baseURL,
  headers: {
    'Content-Type': 'application/json',
  },
})

/**
 * Recursively converts object keys from snake_case to camelCase.
 */
function toCamelCase(obj: any): any {
  if (Array.isArray(obj)) {
    return obj.map(v => toCamelCase(v))
  } else if (obj !== null && obj !== undefined && obj.constructor === Object) {
    return Object.keys(obj).reduce((result, key) => {
      const camelKey = key.replace(/_([a-z0-9])/g, g => g[1].toUpperCase())
      result[camelKey] = toCamelCase(obj[key])
      return result
    }, {} as Record<string, any>)
  }
  return obj
}

/**
 * Recursively converts object keys from camelCase to snake_case.
 */
function toSnakeCase(obj: any): any {
  if (Array.isArray(obj)) {
    return obj.map(v => toSnakeCase(v))
  } else if (obj !== null && obj !== undefined && obj.constructor === Object) {
    const snakeObj: Record<string, any> = {}
    for (const key in obj) {
      const snakeKey = key.replace(/[A-Z]/g, letter => `_${letter.toLowerCase()}`)
      snakeObj[snakeKey] = toSnakeCase(obj[key])
    }
    return snakeObj
  }
  return obj
}

/**
 * Request interceptor — attaches Authorization: Bearer <token> and
 * converts data to snake_case.
 */
apiClient.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    const session = await getSession()
    const token = (session as { accessToken?: string } | null)?.accessToken
    if (token) {
      config.headers = config.headers ?? {}
      config.headers['Authorization'] = `Bearer ${token}`
    }

    if (config.data && config.headers?.['Content-Type'] === 'application/json') {
      config.data = toSnakeCase(config.data)
    }

    console.log(`API Request: ${config.method?.toUpperCase()} ${config.url}`, config.data)

    return config
  },
  (error) => {
    console.error('API Request Error:', error)
    return Promise.reject(error)
  },
)

/**
 * Response interceptor — converts all snake_case keys to camelCase and logs errors.
 */
apiClient.interceptors.response.use(
  (response) => {
    if (response.data && response.headers['content-type']?.includes('application/json')) {
      response.data = toCamelCase(response.data)
    }
    return response
  },
  (error) => {
    console.error('API Response Error:', {
      url: error.config?.url,
      status: error.response?.status,
      data: error.response?.data,
      message: error.message,
    })
    return Promise.reject(error)
  },
)

// ─── Dashboard ───────────────────────────────────────────────────────────────

/** Fetch the full dashboard payload (priority emails, drafts, analytics, etc.) */
export async function getDashboard(): Promise<DashboardPayload> {
  const { data } = await apiClient.get<DashboardPayload>('/dashboard')
  return data
}

// ─── Emails ──────────────────────────────────────────────────────────────────

/** Fetch and classify all emails for the current user. */
export async function getEmails(): Promise<Email[]> {
  const { data } = await apiClient.get<Email[]>('/emails')
  return data
}

/** Fetch a single email by ID. */
export async function getEmail(emailId: string): Promise<Email> {
  const { data } = await apiClient.get<Email>(`/emails/${emailId}`)
  return data
}

/** Generate an AI reply draft for the given email. */
export async function generateReply(emailId: string): Promise<ReplyDraft> {
  const { data } = await apiClient.post<ReplyDraft>('/emails/generate-reply', {
    email_id: emailId,
  })
  return data
}

/** Create a manual (empty) reply draft for the specified email. */
export async function createManualDraft(emailId: string): Promise<ReplyDraft> {
  const { data } = await apiClient.post<ReplyDraft>(
    `/emails/${emailId}/manual-draft`,
  )
  return data
}

/** Update an existing reply draft with new text. */
export async function updateReplyDraft(
  draftId: string,
  text: string,
): Promise<ReplyDraft> {
  const { data } = await apiClient.put<ReplyDraft>(`/emails/drafts/${draftId}`, {
    draft_text: text,
  })
  return data
}

/** Send an existing reply draft via Gmail. */
export async function sendReply(emailId: string, draftId: string): Promise<{ success: boolean; messageId?: string }> {
  const { data } = await apiClient.post<{ success: boolean; messageId?: string }>(
    `/emails/${emailId}/send-reply`,
    null,
    { params: { draft_id: draftId } },
  )
  return data
}

/** Embed an email into the FAISS vector store. */
export async function embedEmail(emailId: string): Promise<{ status: string }> {
  const { data } = await apiClient.post<{ status: string }>(`/emails/${emailId}/embed`)
  return data
}

// ─── Calendar ────────────────────────────────────────────────────────────────

/** Fetch free calendar slots for a date range. */
export async function getCalendarSlots(
  startDate: string,
  endDate: string,
): Promise<TimeSlot[]> {
  const { data } = await apiClient.get<TimeSlot[]>('/calendar/free-slots', {
    params: { start_date: startDate, end_date: endDate },
  })
  return data
}

/** Suggest up to 3 AI-ranked meeting times for a meeting-request email. */
export async function suggestMeetingTimes(emailId: string): Promise<MeetingSlot[]> {
  const { data } = await apiClient.post<MeetingSlot[]>('/calendar/suggest', {
    email_id: emailId,
  })
  return data
}

/** Create a calendar event for a confirmed meeting slot. */
export async function createCalendarEvent(
  slot: MeetingSlot,
  attendees: string[],
  emailId?: string,
): Promise<CalendarEvent> {
  const { data } = await apiClient.post<CalendarEvent>('/calendar/events', {
    slot,
    attendees,
    emailId,
  })
  return data
}

// ─── Follow-ups ──────────────────────────────────────────────────────────────

/** Fetch all pending follow-up suggestions. */
export async function getFollowups(): Promise<FollowupSuggestion[]> {
  const { data } = await apiClient.get<FollowupSuggestion[]>('/followups')
  return data
}

/** Snooze a follow-up until the specified datetime. */
export async function snoozeFollowup(
  id: string,
  until: string,
): Promise<{ status: string }> {
  const { data } = await apiClient.post<{ status: string }>(
    `/followups/${id}/snooze`,
    { until },
  )
  return data
}

/** Mark a follow-up as resolved. */
export async function resolveFollowup(id: string): Promise<{ status: string }> {
  const { data } = await apiClient.post<{ status: string }>(
    `/followups/${id}/resolve`,
  )
  return data
}

/** Generate a contextual follow-up draft. */
export async function generateFollowupDraft(id: string): Promise<ReplyDraft> {
  const { data } = await apiClient.post<ReplyDraft>(
    `/followups/${id}/generate-draft`,
  )
  return data
}

// ─── Analytics ───────────────────────────────────────────────────────────────

/** Fetch aggregated analytics stats for the given period. */
export async function getAnalyticsStats(
  period: 'week' | 'month' = 'week',
): Promise<AnalyticsStats> {
  const { data } = await apiClient.get<AnalyticsStats>('/analytics/stats', {
    params: { period },
  })
  return data
}

/** Fetch total time saved in minutes for the given period. */
export async function getTimeSaved(
  period: 'week' | 'month' = 'week',
): Promise<{ timeSavedMinutes: number }> {
  const { data } = await apiClient.get<{ time_saved_minutes: number }>(
    '/analytics/time-saved',
    { params: { period } },
  )
  return { timeSavedMinutes: data.time_saved_minutes }
}

/** Fetch per-event-type action counts for the given period. */
export async function getActionCounts(
  period: 'week' | 'month' = 'week',
): Promise<Record<string, number>> {
  const { data } = await apiClient.get<Record<string, number>>(
    '/analytics/actions',
    { params: { period } },
  )
  return data
}

/** Fetch daily metrics for the analytics chart. */
export async function getDailyMetrics(
  period: 'week' | 'month' = 'week',
): Promise<DailyMetrics[]> {
  const { data } = await apiClient.get<DailyMetrics[]>('/analytics/daily', {
    params: { period },
  })
  return data
}

// ─── Daily Brief ─────────────────────────────────────────────────────────────

/** Fetch the AI-generated daily brief. */
export async function getDailyBrief(): Promise<DailyBrief> {
  const { data } = await apiClient.get<DailyBrief>('/dashboard/brief')
  return data
}

// ─── User Preferences ────────────────────────────────────────────────────────

/** Fetch the current user's preferences. */
export async function getUserPreferences(): Promise<UserPreferences> {
  const { data } = await apiClient.get<UserPreferences>('/preferences')
  return data
}

/** Update the current user's preferences. */
export async function updatePreferences(
  prefs: Partial<UserPreferences>,
): Promise<UserPreferences> {
  const { data } = await apiClient.put<UserPreferences>('/preferences', prefs)
  return data
}

export default apiClient
