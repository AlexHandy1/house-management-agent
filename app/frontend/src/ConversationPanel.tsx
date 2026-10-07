import { useEffect, useState } from 'react'
import type { Issue } from './App'

const MAX_USER_TURNS = 10
const MAX_MESSAGE_LENGTH = 2000

type Step = {
  id: number
  conversation_id: number
  turn_number: number
  role: 'user' | 'assistant' | 'tool'
  content: string | null
  tool_calls: unknown[] | null
  tool_call_id: string | null
  created_at: string
}

type Conversation = {
  id: number
  issue_id: number
  created_at: string
  steps: Step[]
}

function ConversationPanel({
  issues,
  openConversationId,
}: {
  issues: Issue[]
  openConversationId?: number | null
}) {
  const [selectedIssueId, setSelectedIssueId] = useState<number | ''>('')
  const [conversation, setConversation] = useState<Conversation | null>(null)
  const [messageText, setMessageText] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [capReached, setCapReached] = useState(false)

  useEffect(() => {
    if (openConversationId == null) {
      return
    }
    setCapReached(false)
    fetch(`/api/conversations/${openConversationId}`)
      .then((result) => result.json())
      .then((opened: Conversation) => {
        setConversation(opened)
        setSelectedIssueId(opened.issue_id)
      })
  }, [openConversationId])

  async function handleSelectIssue(issueId: number | '') {
    setSelectedIssueId(issueId)
    setConversation(null)
    setCapReached(false)
    if (issueId === '') {
      return
    }
    const result = await fetch(`/api/issues/${issueId}/conversations`)
    const conversations: Conversation[] = await result.json()
    setConversation(conversations[0] ?? null)
  }

  async function handleSendMessage(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!conversation) {
      return
    }
    setIsSending(true)
    const postResult = await fetch(`/api/conversations/${conversation.id}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: messageText }),
    })
    if (postResult.status === 409) {
      setCapReached(true)
      setIsSending(false)
      return
    }
    const result = await fetch(`/api/conversations/${conversation.id}`)
    setConversation(await result.json())
    setMessageText('')
    setIsSending(false)
  }

  const userTurnCount = conversation
    ? new Set(
        conversation.steps.filter((step) => step.role === 'user').map((step) => step.turn_number)
      ).size
    : 0
  const isClosed = capReached || userTurnCount >= MAX_USER_TURNS

  return (
    <section className="conversation-panel">
      <label htmlFor="conversation-issue">Discuss an existing issue</label>
      <select
        id="conversation-issue"
        value={selectedIssueId}
        onChange={(event) => handleSelectIssue(Number(event.target.value) || '')}
      >
        <option value="">Select an issue…</option>
        {issues.map((issue) => (
          <option key={issue.id} value={issue.id}>
            {issue.source_text.slice(0, 60)}
          </option>
        ))}
      </select>
      {conversation && (
        <>
          <ConversationThread conversation={conversation} />
          {isSending && <p className="conversation-status">Thinking…</p>}
          {isClosed && (
            <p className="conversation-status conversation-closed">
              This conversation is closed — it's reached the message limit.
            </p>
          )}
          <form className="conversation-form" onSubmit={handleSendMessage}>
            <label htmlFor="conversation-message">Your message</label>
            <textarea
              id="conversation-message"
              value={messageText}
              maxLength={MAX_MESSAGE_LENGTH}
              disabled={isSending || isClosed}
              onChange={(event) => setMessageText(event.target.value)}
            />
            <button type="submit" disabled={isSending || isClosed}>
              Send
            </button>
            <span className="conversation-counter">
              {userTurnCount}/{MAX_USER_TURNS} messages used
            </span>
          </form>
        </>
      )}
    </section>
  )
}

function ConversationThread({ conversation }: { conversation: Conversation }) {
  const turnNumbers = [...new Set(conversation.steps.map((step) => step.turn_number))]
  return (
    <div className="conversation-thread">
      {turnNumbers.map((turnNumber) => {
        const stepsInTurn = conversation.steps.filter((step) => step.turn_number === turnNumber)
        const userStep = stepsInTurn.find((step) => step.role === 'user')
        const replyStep = stepsInTurn.find(
          (step) => step.role === 'assistant' && !step.tool_calls
        )
        return (
          <div key={turnNumber} className="conversation-turn">
            {userStep && <p className="conversation-message user">{userStep.content}</p>}
            {replyStep && (
              <p className="conversation-message assistant">{replyStep.content}</p>
            )}
          </div>
        )
      })}
    </div>
  )
}

export default ConversationPanel
