import { useEffect, useState } from 'react'

const MAX_ISSUE_TEXT_LENGTH = 2000

type AgentOutcome = {
  status: 'done' | 'needs_info' | 'failed'
  cost_best: string | null
  cost_low: string | null
  cost_high: string | null
  sources: string[]
  clarifying_question: string | null
  summary: string | null
}

type Issue = {
  id: number
  source_text: string
  status: 'done' | 'needs_info' | 'failed'
  cost_best: string | null
  cost_low: string | null
  cost_high: string | null
  supporting_web_sources: string[]
  clarifying_question: string | null
  created_at: string
}

type SubmitState =
  | { kind: 'idle' }
  | { kind: 'thinking' }
  | { kind: 'outcome'; outcome: AgentOutcome }
  | { kind: 'error' }

function App() {
  const [issueText, setIssueText] = useState('')
  const [submitState, setSubmitState] = useState<SubmitState>({ kind: 'idle' })
  const [issues, setIssues] = useState<Issue[]>([])

  async function loadIssues() {
    const result = await fetch('/api/issues')
    const body = await result.json()
    setIssues(body)
  }

  useEffect(() => {
    loadIssues()
  }, [])

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitState({ kind: 'thinking' })
    try {
      const result = await fetch('/api/issue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ issue_text: issueText }),
      })
      if (!result.ok) {
        setSubmitState({ kind: 'error' })
        return
      }
      const outcome: AgentOutcome = await result.json()
      setSubmitState({ kind: 'outcome', outcome })
      await loadIssues()
    } catch {
      setSubmitState({ kind: 'error' })
    }
  }

  const isThinking = submitState.kind === 'thinking'

  return (
    <main>
      <h1>House Management Agent</h1>
      <form className="issue-form" onSubmit={handleSubmit}>
        <label htmlFor="issue-text">Describe the issue</label>
        <textarea
          id="issue-text"
          value={issueText}
          maxLength={MAX_ISSUE_TEXT_LENGTH}
          placeholder="e.g. The kitchen tap has been dripping constantly since Tuesday."
          onChange={(event) => setIssueText(event.target.value)}
        />
        <button type="submit" disabled={isThinking}>
          {isThinking ? 'Researching costs…' : 'Submit'}
        </button>
      </form>
      <SubmitResult state={submitState} />
      <IssuesTable issues={issues} />
    </main>
  )
}

function SubmitResult({ state }: { state: SubmitState }) {
  if (state.kind === 'error') {
    return <p className="agent-error">Something went wrong — please try again.</p>
  }
  if (state.kind !== 'outcome') {
    return null
  }
  const { outcome } = state
  if (outcome.status === 'failed') {
    return <p className="agent-error">Something went wrong — please try again.</p>
  }
  if (outcome.status === 'needs_info') {
    return (
      <p className="agent-needs-info">
        We need more information: {outcome.clarifying_question}
      </p>
    )
  }
  return (
    <div className="agent-success">
      <p>
        Estimated cost: £{outcome.cost_best} (£{outcome.cost_low}–£{outcome.cost_high}).{' '}
        {outcome.sources.length} sources.
      </p>
      {outcome.summary && <p className="agent-summary">{outcome.summary}</p>}
    </div>
  )
}

function IssuesTable({ issues }: { issues: Issue[] }) {
  if (issues.length === 0) {
    return null
  }
  return (
    <table>
      <thead>
        <tr>
          <th>Date</th>
          <th>Issue</th>
          <th>Status</th>
          <th>Estimate</th>
          <th>Sources</th>
        </tr>
      </thead>
      <tbody>
        {issues.map((issue) => (
          <tr key={issue.id}>
            <td>{new Date(issue.created_at).toLocaleDateString()}</td>
            <td>{issue.source_text.slice(0, 60)}</td>
            <td>{issue.status}</td>
            <td>
              {issue.cost_best
                ? `£${issue.cost_best} (£${issue.cost_low}–£${issue.cost_high})`
                : '—'}
            </td>
            <td>{issue.supporting_web_sources.length}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default App
