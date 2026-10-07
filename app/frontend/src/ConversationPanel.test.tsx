import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import ConversationPanel from './ConversationPanel'
import type { Issue } from './App'

const issues: Issue[] = [
  {
    id: 1,
    source_text: 'The kitchen tap is dripping',
    status: 'done',
    cost_best: '95',
    cost_low: '70',
    cost_high: '150',
    supporting_web_sources: [],
    clarifying_question: null,
    has_contractor: false,
    created_at: '2026-09-30T10:00:00Z',
  },
  {
    id: 2,
    source_text: 'The boiler is leaking',
    status: 'done',
    cost_best: '200',
    cost_low: '150',
    cost_high: '300',
    supporting_web_sources: [],
    clarifying_question: null,
    has_contractor: false,
    created_at: '2026-09-29T10:00:00Z',
  },
]

test('an openConversationId prop opens that conversation directly, syncing the dropdown', async () => {
  const fetchMock = vi.fn((url: string) => {
    expect(url).toBe('/api/conversations/7')
    return Promise.resolve({
      ok: true,
      json: async () => ({
        id: 7,
        issue_id: 2,
        created_at: '2026-10-07T10:00:00Z',
        steps: [],
      }),
    })
  })
  vi.stubGlobal('fetch', fetchMock)

  render(<ConversationPanel issues={issues} openConversationId={7} />)

  expect(await screen.findByLabelText(/your message/i)).toBeInTheDocument()
  expect(screen.getByLabelText(/discuss an existing issue/i)).toHaveValue('2')
})

test('shows a dropdown option for each issue', () => {
  vi.stubGlobal('fetch', vi.fn())
  render(<ConversationPanel issues={issues} />)

  expect(
    screen.getByRole('option', { name: /the kitchen tap is dripping/i })
  ).toBeInTheDocument()
  expect(screen.getByRole('option', { name: /the boiler is leaking/i })).toBeInTheDocument()
})

test('selecting an issue shows its conversation thread, skipping tool-call steps', async () => {
  const fetchMock = vi.fn((url: string) => {
    expect(url).toBe('/api/issues/1/conversations')
    return Promise.resolve({
      ok: true,
      json: async () => [
        {
          id: 7,
          issue_id: 1,
          created_at: '2026-10-07T10:00:00Z',
          steps: [
            {
              id: 1,
              conversation_id: 7,
              turn_number: 1,
              role: 'user',
              content: 'Why that estimate?',
              tool_calls: null,
              tool_call_id: null,
              created_at: '2026-10-07T10:00:00Z',
            },
            {
              id: 2,
              conversation_id: 7,
              turn_number: 1,
              role: 'assistant',
              content: null,
              tool_calls: [{ id: 'call_1', type: 'function', function: { name: 'lookup_issue' } }],
              tool_call_id: null,
              created_at: '2026-10-07T10:00:01Z',
            },
            {
              id: 3,
              conversation_id: 7,
              turn_number: 1,
              role: 'tool',
              content: '{"issue": {}}',
              tool_calls: null,
              tool_call_id: 'call_1',
              created_at: '2026-10-07T10:00:02Z',
            },
            {
              id: 4,
              conversation_id: 7,
              turn_number: 1,
              role: 'assistant',
              content: 'It was based on a worn washer estimate.',
              tool_calls: null,
              tool_call_id: null,
              created_at: '2026-10-07T10:00:03Z',
            },
          ],
        },
      ],
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  const user = userEvent.setup()
  render(<ConversationPanel issues={issues} />)

  await user.selectOptions(
    screen.getByLabelText(/discuss an existing issue/i),
    screen.getByRole('option', { name: /the kitchen tap is dripping/i })
  )

  expect(await screen.findByText(/why that estimate\?/i)).toBeInTheDocument()
  expect(screen.getByText(/worn washer estimate/i)).toBeInTheDocument()
  expect(screen.queryByText(/lookup_issue/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/"issue": \{\}/)).not.toBeInTheDocument()
})

function conversationWithSteps(steps: unknown[]) {
  return {
    id: 7,
    issue_id: 1,
    created_at: '2026-10-07T10:00:00Z',
    steps,
  }
}

function userStep(turnNumber: number, content: string) {
  return {
    id: turnNumber * 10,
    conversation_id: 7,
    turn_number: turnNumber,
    role: 'user',
    content,
    tool_calls: null,
    tool_call_id: null,
    created_at: '2026-10-07T10:00:00Z',
  }
}

function assistantStep(turnNumber: number, content: string) {
  return {
    id: turnNumber * 10 + 1,
    conversation_id: 7,
    turn_number: turnNumber,
    role: 'assistant',
    content,
    tool_calls: null,
    tool_call_id: null,
    created_at: '2026-10-07T10:00:01Z',
  }
}

test('sending a message shows a thinking state then the new reply', async () => {
  let resolvePost!: (value: unknown) => void
  const fetchMock = vi.fn((url: string, options?: RequestInit) => {
    if (options?.method === 'POST') {
      expect(url).toBe('/api/conversations/7/messages')
      expect(JSON.parse(options.body as string)).toEqual({ message: 'Why that estimate?' })
      return new Promise((resolve) => {
        resolvePost = () =>
          resolve({
            ok: true,
            json: async () => ({ reply: 'Because of a worn washer.', turn_number: 1 }),
          })
      })
    }
    if (url === '/api/issues/1/conversations') {
      return Promise.resolve({ ok: true, json: async () => [conversationWithSteps([])] })
    }
    expect(url).toBe('/api/conversations/7')
    return Promise.resolve({
      ok: true,
      json: async () =>
        conversationWithSteps([
          userStep(1, 'Why that estimate?'),
          assistantStep(1, 'Because of a worn washer.'),
        ]),
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  const user = userEvent.setup()
  render(<ConversationPanel issues={issues} />)
  await user.selectOptions(
    screen.getByLabelText(/discuss an existing issue/i),
    screen.getByRole('option', { name: /the kitchen tap is dripping/i })
  )
  await user.type(screen.getByLabelText(/your message/i), 'Why that estimate?')

  await user.click(screen.getByRole('button', { name: /send/i }))

  expect(screen.getByText(/thinking/i)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /send/i })).toBeDisabled()

  resolvePost({ ok: true, json: async () => ({ reply: 'Because of a worn washer.', turn_number: 1 }) })

  expect(await screen.findByText(/because of a worn washer/i)).toBeInTheDocument()
  expect(screen.queryByText(/thinking/i)).not.toBeInTheDocument()
})

test('a 409 response shows the conversation-closed state and disables the input', async () => {
  const fetchMock = vi.fn((url: string, options?: RequestInit) => {
    if (options?.method === 'POST') {
      return Promise.resolve({ ok: false, status: 409 })
    }
    if (url === '/api/issues/1/conversations') {
      return Promise.resolve({ ok: true, json: async () => [conversationWithSteps([])] })
    }
    return Promise.resolve({ ok: true, json: async () => conversationWithSteps([]) })
  })
  vi.stubGlobal('fetch', fetchMock)
  const user = userEvent.setup()
  render(<ConversationPanel issues={issues} />)
  await user.selectOptions(
    screen.getByLabelText(/discuss an existing issue/i),
    screen.getByRole('option', { name: /the kitchen tap is dripping/i })
  )
  await user.type(screen.getByLabelText(/your message/i), 'one too many')
  await user.click(screen.getByRole('button', { name: /send/i }))

  expect(await screen.findByText(/this conversation is closed/i)).toBeInTheDocument()
  expect(screen.getByLabelText(/your message/i)).toBeDisabled()
  expect(screen.getByRole('button', { name: /send/i })).toBeDisabled()
})

test('the input is disabled once the message counter reaches the cap', async () => {
  const steps: unknown[] = []
  for (let i = 1; i <= 10; i++) {
    steps.push(userStep(i, `message ${i}`))
    steps.push(assistantStep(i, `reply ${i}`))
  }
  const fetchMock = vi.fn((url: string) => {
    if (url === '/api/issues/1/conversations') {
      return Promise.resolve({ ok: true, json: async () => [conversationWithSteps(steps)] })
    }
    return Promise.reject(new Error('should not be called'))
  })
  vi.stubGlobal('fetch', fetchMock)
  const user = userEvent.setup()
  render(<ConversationPanel issues={issues} />)

  await user.selectOptions(
    screen.getByLabelText(/discuss an existing issue/i),
    screen.getByRole('option', { name: /the kitchen tap is dripping/i })
  )

  expect(await screen.findByText(/10\/10 messages used/i)).toBeInTheDocument()
  expect(screen.getByLabelText(/your message/i)).toBeDisabled()
  expect(screen.getByRole('button', { name: /send/i })).toBeDisabled()
})
