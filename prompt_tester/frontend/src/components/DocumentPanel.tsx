import type { DocumentContent } from '../api'

interface Props {
  document: DocumentContent | null
  documentName: string
}

export default function DocumentPanel({ document, documentName }: Props) {
  return (
    <div className="doc-panel">
      <div className="doc-panel-header">
        📄 {document?.filename ?? documentName}
        {document && (
          <span className="text-dim" style={{ marginLeft: 8 }}>
            ({document.chunks_count} чанков, {document.total_chars.toLocaleString('ru')} символов)
          </span>
        )}
      </div>
      <div className="doc-panel-content">
        {document
          ? document.chunks.join('\n\n---\n\n')
          : 'Загрузка документа...'}
      </div>
    </div>
  )
}
