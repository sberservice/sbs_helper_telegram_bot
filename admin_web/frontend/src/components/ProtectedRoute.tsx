/**
 * Защищённый маршрут: перенаправляет на логин если не аутентифицирован.
 * Проверяет доступ к модулю через RBAC.
 */

import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth'
import type { ReactNode } from 'react'

interface Props {
  children: ReactNode
  moduleKey?: string
  accessType?: string
}

export default function ProtectedRoute({ children, moduleKey, accessType = 'view' }: Props) {
  const { user, loading, hasPermission } = useAuth()

  if (loading) {
    return <div className="loading-screen">Загрузка...</div>
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  if (moduleKey && !hasPermission(moduleKey, accessType)) {
    return (
      <div className="card" style={{ marginTop: 40, textAlign: 'center' }}>
        <h2>Доступ запрещён</h2>
        <p className="text-dim">У вас нет прав для просмотра этого раздела.</p>
        <p className="text-dim">Роль: <strong>{user.role}</strong></p>
      </div>
    )
  }

  return <>{children}</>
}
