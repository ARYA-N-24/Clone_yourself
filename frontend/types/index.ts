// ─── Primitive types ────────────────────────────────────────────────────────

export type EmailClassification = 'urgent' | 'normal' | 'low'
export type ExecutionMode = 'suggest' | 'approval' | 'auto'
export type DraftStatus = 'pending' | 'approved' | 'sent' | 'discarded'

// ─── User ────────────────────────────────────────────────────────────────────

export interface User {
  id: string
  email: string
  name: string
  pictureUrl?: string
}

// ─── Email ───────────────────────────────────────────────────────────────────

export interface Email {
  id: string
  gmailId: string
  threadId: string
  subject?: string
  sender: string
  recipient: string
  bodyText?: string
  receivedAt: string
  classification?: EmailClassification
  category?: string
  isReplied: boolean
  embeddingId?: string
}

// ─── Reply Draft ─────────────────────────────────────────────────────────────

export interface ReplyDraft {
  id: string
  emailId: string
  draftText: string
  status: DraftStatus
  sentAt?: string
  createdAt?: string
}

// ─── Calendar ────────────────────────────────────────────────────────────────

export interface TimeSlot {
  start: string
  end: string
}

export interface MeetingSlot {
  slot: TimeSlot
  confidenceScore: number
  reason: string
}

export interface CalendarEvent {
  id: string
  gcalEventId?: string
  title: string
  startTime: string
  endTime: string
  attendees?: string[]
  sourceEmailId?: string
  createdByAi: boolean
}

// ─── Dashboard ───────────────────────────────────────────────────────────────

export interface DashboardPayload {
  priorityEmails: Email[]
  pendingReplies: ReplyDraft[]
  suggestedActions: string[]
  followupCount: number
  analytics: AnalyticsStats
}

// ─── Analytics ───────────────────────────────────────────────────────────────

export interface AnalyticsStats {
  actionsAutomated: number
  timeSavedMinutes: number
  emailsClassified: number
  repliesSent: number
  eventsCreated: number
}

// ─── Daily Brief ─────────────────────────────────────────────────────────────

export interface DailyBrief {
  urgentItems: string[]   // exactly 3
  followups: string[]     // exactly 2
  risk: string            // exactly 1
  generatedAt: string
}

// ─── Follow-up ───────────────────────────────────────────────────────────────

export interface FollowupSuggestion {
  id: string
  emailId: string
  subject?: string
  sender: string
  daysElapsed: number
  draftText: string
  status: 'pending' | 'snoozed' | 'resolved' | 'sent'
  snoozeUntil?: string
  detectedAt: string
}

// ─── User Preferences ────────────────────────────────────────────────────────

export interface UserPreferences {
  tone: 'formal' | 'casual'
  workingHoursStart: string   // e.g. "09:00"
  workingHoursEnd: string     // e.g. "18:00"
  workingDays: number[]       // 1=Mon … 7=Sun
  meetingDuration: number     // minutes
  followupThreshold: number   // days
  executionMode: ExecutionMode
}

// ─── API response helpers ────────────────────────────────────────────────────

export interface ApiError {
  error: string
  message?: string
}

export interface TokenResponse {
  accessToken: string
}
