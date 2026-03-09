/**
 * Страница входа: Telegram Login Widget или Dev-режим.
 */

import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import type { TelegramAuthData } from '../api'

// Расширяем window для Telegram Login Widget callback
declare global {
  interface Window {
    onTelegramAuth?: (user: TelegramAuthData) => void
  }
}

export default function LoginPage() {
  const {
    user,
    loading,
    devMode,
    botUsername,
    passwordAuthEnabled,
    login,
    passwordLogin,
    devLogin,
  } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const [authMode, setAuthMode] = useState<'telegram' | 'password'>('telegram')
  const [passwordLoginValue, setPasswordLoginValue] = useState('')
  const [passwordValue, setPasswordValue] = useState('')
  const [devTelegramId, setDevTelegramId] = useState('')
  const [devName, setDevName] = useState('Dev')
  const [loggingIn, setLoggingIn] = useState(false)
  const widgetRef = useRef<HTMLDivElement>(null)

  // Если уже залогинен — редирект
  useEffect(() => {
    if (!loading && user) {
      navigate('/expert', { replace: true })
    }
  }, [user, loading, navigate])

  // Telegram Login Widget
  useEffect(() => {
    if (loading || devMode || !botUsername || user) return

    // Callback для виджета
    window.onTelegramAuth = async (data: TelegramAuthData) => {
      setLoggingIn(true)
      setError('')
      try {
        await login(data)
        navigate('/expert', { replace: true })
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Ошибка аутентификации')
      } finally {
        setLoggingIn(false)
      }
    }

    // Вставляем скрипт виджета
    if (widgetRef.current && !widgetRef.current.hasChildNodes()) {
      const script = document.createElement('script')
      script.src = 'https://telegram.org/js/telegram-widget.js?22'
      script.async = true
      script.setAttribute('data-telegram-login', botUsername)
      script.setAttribute('data-size', 'large')
      script.setAttribute('data-radius', '8')
      script.setAttribute('data-onauth', 'onTelegramAuth(user)')
      script.setAttribute('data-request-access', 'write')
      widgetRef.current.appendChild(script)
    }

    return () => {
      delete window.onTelegramAuth
    }
  }, [loading, devMode, botUsername, user, login, navigate])

  useEffect(() => {
    if (!devMode && passwordAuthEnabled && !botUsername) {
      setAuthMode('password')
    }
  }, [devMode, passwordAuthEnabled, botUsername])

  const handleDevLogin = async () => {
    const tid = parseInt(devTelegramId, 10)
    if (!tid || isNaN(tid)) {
      setError('Введите корректный Telegram ID')
      return
    }
    setLoggingIn(true)
    setError('')
    try {
      await devLogin(tid, devName || 'Dev')
      navigate('/expert', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка')
    } finally {
      setLoggingIn(false)
    }
  }

  const handlePasswordLogin = async () => {
    if (!passwordLoginValue.trim() || !passwordValue) {
      setError('Введите логин и пароль')
      return
    }
    setLoggingIn(true)
    setError('')
    try {
      await passwordLogin({
        login: passwordLoginValue,
        password: passwordValue,
      })
      navigate('/expert', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка входа по паролю')
    } finally {
      setLoggingIn(false)
    }
  }

  if (loading) {
    return <div className="loading-screen">Загрузка...</div>
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-header">
          <span className="login-logo">🏗️</span>
          <h1>SBS Archie Admin</h1>
          <p className="text-dim">Единая веб-платформа администрирования</p>
        </div>

        {error && <div className="alert alert-danger">{error}</div>}

        {loggingIn && (
          <div className="alert alert-info">Выполняется вход...</div>
        )}

        {passwordAuthEnabled && !devMode && (
          <div className="auth-mode-switch" style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            <button
              className={`btn btn-sm ${authMode === 'telegram' ? 'btn-primary' : ''}`}
              onClick={() => setAuthMode('telegram')}
            >
              Telegram
            </button>
            <button
              className={`btn btn-sm ${authMode === 'password' ? 'btn-primary' : ''}`}
              onClick={() => setAuthMode('password')}
            >
              Пароль
            </button>
          </div>
        )}

        {devMode ? (
          <div className="dev-login">
            <h3>🔧 Dev-режим</h3>
            <p className="text-dim">Telegram-верификация отключена</p>
            <div className="form-group">
              <label>Telegram ID</label>
              <input
                type="number"
                className="input"
                value={devTelegramId}
                onChange={(e) => setDevTelegramId(e.target.value)}
                placeholder="123456789"
                onKeyDown={(e) => e.key === 'Enter' && handleDevLogin()}
              />
            </div>
            <div className="form-group">
              <label>Имя</label>
              <input
                type="text"
                className="input"
                value={devName}
                onChange={(e) => setDevName(e.target.value)}
                placeholder="Dev"
                onKeyDown={(e) => e.key === 'Enter' && handleDevLogin()}
              />
            </div>
            <button
              className="btn btn-primary btn-full"
              onClick={handleDevLogin}
              disabled={loggingIn}
            >
              Войти (Dev)
            </button>
          </div>
        ) : passwordAuthEnabled && authMode === 'password' ? (
          <div className="password-login">
            <p>Войдите по логину и паролю</p>
            <div className="form-group">
              <label>Логин</label>
              <input
                type="text"
                className="input"
                value={passwordLoginValue}
                onChange={(e) => setPasswordLoginValue(e.target.value)}
                placeholder="admin"
                autoComplete="username"
                onKeyDown={(e) => e.key === 'Enter' && handlePasswordLogin()}
              />
            </div>
            <div className="form-group">
              <label>Пароль</label>
              <input
                type="password"
                className="input"
                value={passwordValue}
                onChange={(e) => setPasswordValue(e.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
                onKeyDown={(e) => e.key === 'Enter' && handlePasswordLogin()}
              />
            </div>
            <button
              className="btn btn-primary btn-full"
              onClick={handlePasswordLogin}
              disabled={loggingIn}
            >
              Войти по паролю
            </button>
          </div>
        ) : (
          <div className="telegram-login">
            <p>Войдите через Telegram для доступа к платформе</p>
            <div ref={widgetRef} className="telegram-widget-container" />
            {!botUsername && (
              <p className="text-dim" style={{ marginTop: 12 }}>
                Telegram Login Widget недоступен. Укажите `ADMIN_WEB_TELEGRAM_BOT_USERNAME` (без @).
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
