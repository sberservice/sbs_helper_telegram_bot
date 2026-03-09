/**
 * Контекст аутентификации и провайдер для React-приложения.
 *
 * Проверяет статус сессии при загрузке, предоставляет
 * login/logout и данные пользователя через React Context.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import { api, type PasswordLoginData, type WebUser, type TelegramAuthData } from './api'

interface AuthContextType {
  user: WebUser | null
  loading: boolean
  devMode: boolean
  botUsername: string
  passwordAuthEnabled: boolean
  login: (data: TelegramAuthData) => Promise<void>
  passwordLogin: (data: PasswordLoginData) => Promise<void>
  devLogin: (telegramId: number, firstName?: string) => Promise<void>
  logout: () => Promise<void>
  hasPermission: (moduleKey: string, accessType?: string) => boolean
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<WebUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [devMode, setDevMode] = useState(false)
  const [botUsername, setBotUsername] = useState('')
  const [passwordAuthEnabled, setPasswordAuthEnabled] = useState(false)

  // Проверить сессию при загрузке
  useEffect(() => {
    const init = async () => {
      try {
        const [checkResult, config] = await Promise.all([
          api.checkAuth(),
          api.getAuthConfig(),
        ])
        setDevMode(config.dev_mode)
        setBotUsername((config.bot_username || '').trim().replace(/^@+/, ''))
        setPasswordAuthEnabled(Boolean(config.password_auth_enabled))
        if (checkResult.authenticated && checkResult.user) {
          setUser(checkResult.user)
        }
      } catch {
        // Не аутентифицирован — OK
      } finally {
        setLoading(false)
      }
    }
    init()
  }, [])

  const login = useCallback(async (data: TelegramAuthData) => {
    const result = await api.telegramAuth(data)
    if (result.success && result.user) {
      setUser(result.user)
    } else {
      throw new Error(result.message || 'Ошибка аутентификации')
    }
  }, [])

  const devLogin = useCallback(async (telegramId: number, firstName?: string) => {
    const result = await api.devLogin(telegramId, firstName || 'Dev')
    if (result.success && result.user) {
      setUser(result.user)
    } else {
      throw new Error(result.message || 'Ошибка dev-аутентификации')
    }
  }, [])

  const passwordLogin = useCallback(async (data: PasswordLoginData) => {
    const result = await api.passwordLogin(data)
    if (result.success && result.user) {
      setUser(result.user)
    } else {
      throw new Error(result.message || 'Ошибка password-аутентификации')
    }
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } finally {
      setUser(null)
    }
  }, [])

  const hasPermission = useCallback(
    (moduleKey: string, accessType: string = 'view') => {
      if (!user) return false
      if (user.role === 'super_admin') return true
      return user.permissions.some(
        (p) =>
          p.module_key === moduleKey &&
          (accessType === 'view' ? p.can_view : p.can_edit),
      )
    },
    [user],
  )

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        devMode,
        botUsername,
        passwordAuthEnabled,
        login,
        passwordLogin,
        devLogin,
        logout,
        hasPermission,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return ctx
}
