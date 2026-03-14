import { useState } from 'react'

import PromptTesterTab from './gk_tabs/PromptTesterTab'
import RagDocumentsTab from './rag_tabs/RagDocumentsTab'
import RagStatsTab from './rag_tabs/RagStatsTab'

const RAG_TABS = [
  { key: 'documents', label: 'Документы', icon: '📚' },
  { key: 'stats', label: 'Статистика', icon: '📊' },
  { key: 'prompt-tester', label: 'Prompt Tester', icon: '🧪' },
] as const

type RagTabKey = (typeof RAG_TABS)[number]['key']

export default function RagPage() {
  const [activeTab, setActiveTab] = useState<RagTabKey>('documents')

  return (
    <div className="gk-page">
      <div className="page-header">
        <h1>🧩 RAG</h1>
        <p className="text-dim">Инструменты тестирования RAG и промптов</p>
      </div>

      <div className="gk-tab-bar">
        {RAG_TABS.map(tab => (
          <button
            key={tab.key}
            className={`gk-tab ${activeTab === tab.key ? 'gk-tab-active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            <span className="gk-tab-icon">{tab.icon}</span>
            <span className="gk-tab-label">{tab.label}</span>
          </button>
        ))}
      </div>

      <div className="gk-tab-content">
        {activeTab === 'documents' && <RagDocumentsTab />}
        {activeTab === 'stats' && <RagStatsTab />}
        {activeTab === 'prompt-tester' && <PromptTesterTab />}
      </div>
    </div>
  )
}
