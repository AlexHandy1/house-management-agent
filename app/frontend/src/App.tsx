import { useState } from 'react'

const MAX_ISSUE_TEXT_LENGTH = 2000

function App() {
  const [issueText, setIssueText] = useState('')
  const [response, setResponse] = useState<string | null>(null)

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const result = await fetch('/api/issue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ issue_text: issueText }),
    })
    const body = await result.json()
    setResponse(body.response)
  }

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
        <button type="submit">Submit</button>
      </form>
      {response && <p className="agent-response">{response}</p>}
    </main>
  )
}

export default App
