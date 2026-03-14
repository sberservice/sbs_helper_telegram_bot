/**
 * Главная страница модуля Group Knowledge.
 * Горизонтальная панель вкладок с lazy-загрузкой содержимого.
 */

import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import StatsTab from './gk_tabs/StatsTab'
import QAPairsTab from './gk_tabs/QAPairsTab'
import ExpertValidationTab from './gk_tabs/ExpertValidationTab'
import GroupsTab from './gk_tabs/GroupsTab'
import ResponderTab from './gk_tabs/ResponderTab'
import ImagesTab from './gk_tabs/ImagesTab'
import ImagePromptTesterTab from './gk_tabs/ImagePromptTesterTab'
import SearchTab from './gk_tabs/SearchTab'
import QAAnalyzerSandboxTab from './gk_tabs/QAAnalyzerSandboxTab'
import TermsTab from './gk_tabs/TermsTab'
import SettingsTab from './gk_tabs/SettingsTab'

interface TabDef {
  key: string
  label: string
  icon: string
}

const TABS: TabDef[] = [
  { key: 'stats', label: 'Статистика', icon: '📊' },
  { key: 'qa-pairs', label: 'Q&A-пары', icon: '💬' },
  { key: 'expert', label: 'Валидация', icon: '🔍' },
  { key: 'groups', label: 'Группы', icon: '👥' },
  { key: 'responder', label: 'Автоответчик', icon: '🤖' },
  { key: 'images', label: 'Изображения', icon: '🖼' },
  { key: 'image-prompt-tester', label: 'Image Prompt Tester', icon: '🧪' },
  { key: 'search', label: 'Поиск', icon: '🔎' },
  { key: 'terms', label: 'Термины', icon: '📖' },
  { key: 'settings', label: 'Настройки', icon: '⚙️' },
  { key: 'qa-analyzer-sandbox', label: 'Песочница анализатора', icon: '🧬' },
]

const TAB_COMPONENTS: Record<string, React.FC> = {
  'stats': StatsTab,
  'qa-pairs': QAPairsTab,
  'expert': ExpertValidationTab,
  'groups': GroupsTab,
  'responder': ResponderTab,
  'images': ImagesTab,
  'image-prompt-tester': ImagePromptTesterTab,
  'search': SearchTab,
  'terms': TermsTab,
  'settings': SettingsTab,
  'qa-analyzer-sandbox': QAAnalyzerSandboxTab,
}

export default function GKKnowledgePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tabFromUrl = searchParams.get('tab')
  const [activeTab, setActiveTab] = useState(
    TABS.some(t => t.key === tabFromUrl) ? tabFromUrl! : 'stats'
  )

  const handleTabChange = (key: string) => {
    setActiveTab(key)
    setSearchParams({ tab: key }, { replace: true })
  }

  const ActiveComponent = TAB_COMPONENTS[activeTab] || StatsTab

  return (
    <div className="gk-page">
      <div className="page-header">
        <h1>🧠 Group Knowledge</h1>
        <p className="text-dim">Аналитика, валидация и тестирование Q&A из Telegram-групп</p>
      </div>

      {/* Tab bar */}
      <div className="gk-tab-bar">
        {TABS.map(tab => (
          <button
            key={tab.key}
            className={`gk-tab ${activeTab === tab.key ? 'gk-tab-active' : ''}`}
            onClick={() => handleTabChange(tab.key)}
          >
            <span className="gk-tab-icon">{tab.icon}</span>
            <span className="gk-tab-label">{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="gk-tab-content">
        <ActiveComponent />
      </div>
    </div>
  )
}
