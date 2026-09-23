import { render, screen } from '@testing-library/react'
import App from './App'

test('renders the House Management Agent heading', () => {
  render(<App />)

  expect(
    screen.getByRole('heading', { name: /house management agent/i })
  ).toBeInTheDocument()
})
