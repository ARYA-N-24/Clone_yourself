/**
 * EmailCard — displays a single email with classification badge and reply action.
 * Requirements: 3.1, 3.2
 */

import { useState } from 'react'
import type { Email } from '@/types'
import EmailReplyPanel from './EmailReplyPanel'

interface EmailCardProps {
  email: Email
  onReplyGenerated?: () => void
}

const CLASSIFICATION_STYLES: Record<string, string> = {
  urgent: 'bg-red-100 text-red-700 border border-red-200',
  normal: 'bg-yellow-100 text-yellow-700 border border-yellow-200',
  low: 'bg-gray-100 text-gray-600 border border-gray-200',
}

const CATEGORY_STYLES: Record<string, string> = {
  'meeting-request': 'bg-blue-50 text-blue-700',
  'action-required': 'bg-orange-50 text-orange-700',
  info: 'bg-green-50 text-green-700',
  other: 'bg-gray-50 text-gray-600',
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

export default function EmailCard({ email, onReplyGenerated }: EmailCardProps) {
  const [showReplyPanel, setShowReplyPanel] = useState(false)

  const classificationStyle =
    email.classification ? CLASSIFICATION_STYLES[email.classification] ?? CLASSIFICATION_STYLES.low : null
  const categoryStyle =
    email.category ? CATEGORY_STYLES[email.category] ?? CATEGORY_STYLES.other : null

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm hover:shadow-md transition-shadow">
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-gray-900 truncate">
            {email.subject ?? '(no subject)'}
          </p>
          <p className="text-xs text-gray-500 mt-0.5 truncate">
            From: <span className="font-medium text-gray-700">{email.sender}</span>
          </p>
        </div>

        {/* Timestamp */}
        <time
          dateTime={email.receivedAt}
          className="text-xs text-gray-400 whitespace-nowrap flex-shrink-0"
        >
          {formatDate(email.receivedAt)}
        </time>
      </div>

      {/* Badges row */}
      <div className="flex items-center gap-2 mt-2 flex-wrap">
        {classificationStyle && email.classification && (
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${classificationStyle}`}
            aria-label={`Classification: ${email.classification}`}
          >
            {email.classification.charAt(0).toUpperCase() + email.classification.slice(1)}
          </span>
        )}

        {categoryStyle && email.category && (
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${categoryStyle}`}
            aria-label={`Category: ${email.category}`}
          >
            {email.category.replace('-', ' ')}
          </span>
        )}

        {email.isReplied && (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-50 text-green-700">
            Replied
          </span>
        )}
      </div>

      {/* Body preview */}
      {email.bodyText && (
        <p className="text-xs text-gray-500 mt-2 line-clamp-2">
          {email.bodyText}
        </p>
      )}

      {/* Actions */}
      {!email.isReplied && (
        <div className="mt-3">
          <button
            onClick={() => setShowReplyPanel((v) => !v)}
            className="text-sm font-medium text-blue-600 hover:text-blue-800 transition-colors"
            aria-expanded={showReplyPanel}
            aria-controls={`reply-panel-${email.id}`}
          >
            {showReplyPanel ? 'Hide Reply' : 'Generate Reply'}
          </button>
        </div>
      )}

      {/* Inline reply panel */}
      {showReplyPanel && (
        <div id={`reply-panel-${email.id}`} className="mt-3">
          <EmailReplyPanel
            email={email}
            onClose={() => setShowReplyPanel(false)}
            onSent={() => {
              setShowReplyPanel(false)
              onReplyGenerated?.()
            }}
          />
        </div>
      )}
    </div>
  )
}
