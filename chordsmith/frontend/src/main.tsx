import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { applyStoredTheme } from './hooks/useTheme'
import './index.css'

// Before React mounts: otherwise the first paint is the default theme and the
// page visibly flips a moment later.
applyStoredTheme()

const container = document.getElementById('root')
if (!container) throw new Error('Root element is missing from index.html')

createRoot(container).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
