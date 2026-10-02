import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import App from './App'

test('renders the House Management Agent heading', () => {
  render(<App />)

  expect(
    screen.getByRole('heading', { name: /house management agent/i })
  ).toBeInTheDocument()
})

function stubFetch({
  issues = [],
  articles = [],
  onSubmit,
}: {
  issues?: unknown[]
  articles?: unknown[]
  onSubmit: () => Promise<unknown>
}) {
  const fetchMock = vi.fn((url: string, options?: RequestInit) => {
    if (options?.method === 'POST') {
      return onSubmit()
    }
    if (url === '/api/news-feed') {
      return Promise.resolve({ ok: true, json: async () => articles })
    }
    return Promise.resolve({ ok: true, json: async () => issues })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

test('shows a thinking state while the agent researches costs, then a sourced cost estimate', async () => {
  let resolvePost!: (value: unknown) => void
  stubFetch({
    onSubmit: () => new Promise((resolve) => { resolvePost = resolve }),
  })
  const user = userEvent.setup()
  render(<App />)

  await user.type(
    screen.getByLabelText(/describe the issue/i),
    'The boiler is leaking'
  )
  await user.click(screen.getByRole('button', { name: /submit/i }))

  expect(screen.getByRole('button', { name: /researching costs/i })).toBeDisabled()

  resolvePost({
    ok: true,
    json: async () => ({
      status: 'done',
      cost_best: '95',
      cost_low: '70',
      cost_high: '150',
      sources: ['https://example.com/a', 'https://example.com/b'],
      clarifying_question: null,
      summary: 'A dripping tap is usually a worn washer, a quick and inexpensive fix.',
      contractors: [],
    }),
  })

  expect(await screen.findByText(/£95/)).toBeInTheDocument()
  expect(screen.getByText(/£70/)).toBeInTheDocument()
  expect(screen.getByText(/£150/)).toBeInTheDocument()
  expect(screen.getByText(/2 sources/i)).toBeInTheDocument()
  expect(screen.getByText(/a worn washer/i)).toBeInTheDocument()
})

test('shows the contractors the agent found alongside the cost estimate', async () => {
  stubFetch({
    onSubmit: () =>
      Promise.resolve({
        ok: true,
        json: async () => ({
          status: 'done',
          cost_best: '95',
          cost_low: '70',
          cost_high: '150',
          sources: ['https://example.com/a'],
          clarifying_question: null,
          summary: 'A dripping tap is usually a worn washer.',
          contractors: [
            {
              name: 'Test Plumbing Co',
              trade: 'plumbing',
              source_url: 'https://example.com/test-plumbing-co',
              email: null,
              phone_number: '0000 000 0001',
            },
          ],
        }),
      }),
  })
  const user = userEvent.setup()
  render(<App />)

  await user.type(screen.getByLabelText(/describe the issue/i), 'The boiler is leaking')
  await user.click(screen.getByRole('button', { name: /submit/i }))

  expect(await screen.findByText(/test plumbing co/i)).toBeInTheDocument()
  expect(screen.getByText(/0000 000 0001/)).toBeInTheDocument()
})

test('shows contractors without a broken cost line when only contractors were asked for', async () => {
  stubFetch({
    onSubmit: () =>
      Promise.resolve({
        ok: true,
        json: async () => ({
          status: 'done',
          cost_best: null,
          cost_low: null,
          cost_high: null,
          sources: [],
          clarifying_question: null,
          summary: null,
          contractors: [
            {
              name: 'Test Plumbing Co',
              trade: 'plumbing',
              source_url: 'https://example.com/test-plumbing-co',
              email: null,
              phone_number: '0000 000 0001',
            },
          ],
        }),
      }),
  })
  const user = userEvent.setup()
  render(<App />)

  await user.type(
    screen.getByLabelText(/describe the issue/i),
    'Do we already have a contractor for the boiler?'
  )
  await user.click(screen.getByRole('button', { name: /submit/i }))

  expect(await screen.findByText(/test plumbing co/i)).toBeInTheDocument()
  expect(screen.queryByText(/£null/i)).not.toBeInTheDocument()
})

test('shows the clarifying question when the issue is too vague to cost', async () => {
  stubFetch({
    onSubmit: () =>
      Promise.resolve({
        ok: true,
        json: async () => ({
          status: 'needs_info',
          cost_best: null,
          cost_low: null,
          cost_high: null,
          sources: [],
          clarifying_question: 'Which room is affected?',
        }),
      }),
  })
  const user = userEvent.setup()
  render(<App />)

  await user.type(screen.getByLabelText(/describe the issue/i), 'Something is broken')
  await user.click(screen.getByRole('button', { name: /submit/i }))

  expect(await screen.findByText(/which room is affected/i)).toBeInTheDocument()
})

test('shows an error state when the agent run fails', async () => {
  stubFetch({
    onSubmit: () =>
      Promise.resolve({
        ok: true,
        json: async () => ({
          status: 'failed',
          cost_best: null,
          cost_low: null,
          cost_high: null,
          sources: [],
          clarifying_question: null,
        }),
      }),
  })
  const user = userEvent.setup()
  render(<App />)

  await user.type(screen.getByLabelText(/describe the issue/i), 'The tap drips')
  await user.click(screen.getByRole('button', { name: /submit/i }))

  expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument()
})

test('shows an error state when the request to submit the issue fails outright', async () => {
  stubFetch({ onSubmit: () => Promise.reject(new Error('network down')) })
  const user = userEvent.setup()
  render(<App />)

  await user.type(screen.getByLabelText(/describe the issue/i), 'The tap drips')
  await user.click(screen.getByRole('button', { name: /submit/i }))

  expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument()
})

test('shows the latest news feed articles on load, newest first as returned by the API', async () => {
  stubFetch({
    articles: [
      {
        source: 'Tenancy Deposit Scheme',
        title: 'new deposit rules',
        url: 'https://www.tenancydepositscheme.com/news/new-deposit-rules',
        published_date: '2026-09-28',
        summary: null,
      },
      {
        source: 'NRLA',
        title: 'Landlord licensing update',
        url: 'https://www.nrla.org.uk/news/landlord-licensing-update',
        published_date: '2026-09-20',
        summary: 'A summary of the licensing changes.',
      },
    ],
    onSubmit: () => Promise.reject(new Error('should not be called')),
  })

  render(<App />)

  const firstArticleLink = await screen.findByRole('link', { name: /new deposit rules/i })
  const secondArticleLink = screen.getByRole('link', { name: /landlord licensing update/i })
  expect(firstArticleLink).toHaveAttribute(
    'href',
    'https://www.tenancydepositscheme.com/news/new-deposit-rules'
  )
  expect(screen.getByText(/a summary of the licensing changes/i)).toBeInTheDocument()
  const articleLinks = screen.getAllByRole('link')
  expect(articleLinks.indexOf(firstArticleLink)).toBeLessThan(
    articleLinks.indexOf(secondArticleLink)
  )
})

test('loads previously saved issues on mount without submitting anything', async () => {
  stubFetch({
    issues: [
      {
        id: 1,
        source_text: 'The kitchen tap is dripping',
        status: 'done',
        cost_best: '95',
        cost_low: '70',
        cost_high: '150',
        supporting_web_sources: ['https://example.com/a'],
        clarifying_question: null,
        created_at: '2026-09-28T10:00:00Z',
      },
    ],
    onSubmit: () => Promise.reject(new Error('should not be called')),
  })

  render(<App />)

  expect(await screen.findByText(/the kitchen tap is dripping/i)).toBeInTheDocument()
})

test('shows which issues have a linked contractor in the issues table', async () => {
  stubFetch({
    issues: [
      {
        id: 1,
        source_text: 'The boiler is leaking',
        status: 'done',
        cost_best: '95',
        cost_low: '70',
        cost_high: '150',
        supporting_web_sources: [],
        clarifying_question: null,
        has_contractor: true,
        created_at: '2026-09-30T10:00:00Z',
      },
      {
        id: 2,
        source_text: 'The kitchen tap is dripping',
        status: 'done',
        cost_best: '95',
        cost_low: '70',
        cost_high: '150',
        supporting_web_sources: [],
        clarifying_question: null,
        has_contractor: false,
        created_at: '2026-09-30T09:00:00Z',
      },
    ],
    onSubmit: () => Promise.reject(new Error('should not be called')),
  })

  render(<App />)

  const table = await screen.findByRole('table')
  const rows = within(table).getAllByRole('row')
  expect(within(rows[1]).getByText('Y')).toBeInTheDocument()
  expect(within(rows[2]).getByText('N')).toBeInTheDocument()
})

test('refreshes the issues table with the newly saved issue after a submit', async () => {
  const savedIssue = {
    id: 1,
    source_text: 'The boiler is leaking',
    status: 'done',
    cost_best: '95',
    cost_low: '70',
    cost_high: '150',
    supporting_web_sources: [],
    clarifying_question: null,
    created_at: '2026-09-29T10:00:00Z',
  }
  // Table starts empty on mount, then shows the saved issue once the agent's
  // write is visible after the refetch that follows a submit.
  let issues: unknown[] = []
  const fetchMock = vi.fn((url: string, options?: RequestInit) => {
    if (options?.method === 'POST') {
      issues = [savedIssue]
      return Promise.resolve({
        ok: true,
        json: async () => ({
          status: 'done',
          cost_best: '95',
          cost_low: '70',
          cost_high: '150',
          sources: [],
          clarifying_question: null,
          contractors: [],
        }),
      })
    }
    if (url === '/api/news-feed') {
      return Promise.resolve({ ok: true, json: async () => [] })
    }
    return Promise.resolve({ ok: true, json: async () => issues })
  })
  vi.stubGlobal('fetch', fetchMock)
  const user = userEvent.setup()
  render(<App />)

  expect(screen.queryByRole('table')).not.toBeInTheDocument()

  await user.type(screen.getByLabelText(/describe the issue/i), 'The boiler is leaking')
  await user.click(screen.getByRole('button', { name: /submit/i }))

  const table = await screen.findByRole('table')
  expect(within(table).getByText(/the boiler is leaking/i)).toBeInTheDocument()
})

test('limits the issue description to 2000 characters', () => {
  render(<App />)

  expect(screen.getByLabelText(/describe the issue/i)).toHaveAttribute(
    'maxLength',
    '2000'
  )
})
