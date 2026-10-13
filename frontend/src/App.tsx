import { useEffect } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useMe } from './api/hooks'
import { isDark, useChat } from './chat/store'
import { AuthPage } from './pages/AuthPage'
import { ChatPage } from './pages/ChatPage'

function Protected() {
  const { data: user, isPending, isError } = useMe()
  if (isPending) return null
  if (isError) {
    return (
      <p role="alert" className="p-8 text-center text-danger">
        Le serveur ne répond pas. Vérifiez qu'il est démarré, puis rechargez la page.
      </p>
    )
  }
  return user ? <ChatPage /> : <Navigate to="/login" replace />
}

export default function App() {
  const theme = useChat((state) => state.theme)

  useEffect(() => {
    const apply = () => document.documentElement.classList.toggle('dark', isDark(theme))
    apply()
    // En mode « système », on suit les changements du réglage de l'appareil.
    const system = matchMedia('(prefers-color-scheme: dark)')
    system.addEventListener('change', apply)
    return () => system.removeEventListener('change', apply)
  }, [theme])

  return (
    <Routes>
      <Route path="/login" element={<AuthPage mode="login" />} />
      <Route path="/register" element={<AuthPage mode="register" />} />
      <Route path="/" element={<Protected />} />
      <Route path="/c/:id" element={<Protected />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
