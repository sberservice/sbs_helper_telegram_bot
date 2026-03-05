interface Props {
  label: string
  text: string | null
}

export default function SummaryCard({ label, text }: Props) {
  return (
    <div className="summary-card">
      <div className="summary-card-label">{label}</div>
      <div className="summary-card-text">
        {text ?? 'Ошибка генерации'}
      </div>
    </div>
  )
}
