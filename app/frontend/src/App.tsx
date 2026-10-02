import { useEffect, useState } from 'react'

const MAX_ISSUE_TEXT_LENGTH = 2000

type Contractor = {
  name: string
  trade: string | null
  source_url: string | null
  email: string | null
  phone_number: string | null
}

type AgentOutcome = {
  status: 'done' | 'needs_info' | 'failed'
  cost_best: string | null
  cost_low: string | null
  cost_high: string | null
  sources: string[]
  clarifying_question: string | null
  summary: string | null
  contractors: Contractor[]
}

type Article = {
  source: string
  title: string
  url: string
  published_date: string | null
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
  has_contractor: boolean
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
  const [articles, setArticles] = useState<Article[]>([])

  async function loadIssues() {
    const result = await fetch('/api/issues')
    const body = await result.json()
    setIssues(body)
  }

  async function loadNewsFeed() {
    const result = await fetch('/api/news-feed')
    const body = await result.json()
    setArticles(body)
  }

  useEffect(() => {
    loadIssues()
    loadNewsFeed()
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
      <NewsFeed articles={articles} />
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
      {outcome.cost_best && (
        <p>
          Estimated cost: £{outcome.cost_best} (£{outcome.cost_low}–£{outcome.cost_high}).{' '}
          {outcome.sources.length} sources.
        </p>
      )}
      {outcome.summary && <p className="agent-summary">{outcome.summary}</p>}
      {outcome.contractors.length > 0 && (
        <ul className="agent-contractors">
          {outcome.contractors.map((contractor) => (
            <li key={contractor.name}>
              {contractor.name}
              {contractor.trade && ` (${contractor.trade})`}
              {contractor.phone_number && ` — ${contractor.phone_number}`}
              {contractor.email && ` — ${contractor.email}`}
            </li>
          ))}
        </ul>
      )}
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
          <th>Contractor</th>
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
            <td>{issue.has_contractor ? 'Y' : 'N'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function NewsFeed({ articles }: { articles: Article[] }) {
  if (articles.length === 0) {
    return null
  }
  return (
    <section className="news-feed">
      <h2>Landlord news</h2>
      {articles.map((article) => (
        <article className="article-card" key={article.url}>
          <div className="article-meta">
            <span className="article-source">{article.source}</span>
            {article.published_date && (
              <span>{new Date(article.published_date).toLocaleDateString('en-GB')}</span>
            )}
          </div>
          <h3>
            <a href={article.url} target="_blank" rel="noopener noreferrer">
              {article.title}
            </a>
          </h3>
          {article.summary ? (
            <p className="article-summary">{article.summary}</p>
          ) : (
            <p className="article-summary missing">No summary available for this source.</p>
          )}
        </article>
      ))}
    </section>
  )
}

export default App
