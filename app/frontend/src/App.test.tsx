import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import App from './App'

test('renders the House Management Agent heading', () => {
  render(<App />)

  expect(
    screen.getByRole('heading', { name: /house management agent/i })
  ).toBeInTheDocument()
})

test('lets the landlord describe an issue and see the agent response', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ response: 'Contact a plumber to inspect the leak.' }),
  })
  vi.stubGlobal('fetch', fetchMock)
  const user = userEvent.setup()
  render(<App />)

  await user.type(
    screen.getByLabelText(/describe the issue/i),
    'The boiler is leaking'
  )
  await user.click(screen.getByRole('button', { name: /submit/i }))

  expect(fetchMock).toHaveBeenCalledWith(
    '/api/issue',
    expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ issue_text: 'The boiler is leaking' }),
    })
  )
  expect(
    await screen.findByText('Contact a plumber to inspect the leak.')
  ).toBeInTheDocument()
})

test('limits the issue description to 2000 characters', () => {
  render(<App />)

  expect(screen.getByLabelText(/describe the issue/i)).toHaveAttribute(
    'maxLength',
    '2000'
  )
})
