interface Props {
  completed: number
  total: number
}

export default function ProgressBar({ completed, total }: Props) {
  const pct = total > 0 ? (completed / total) * 100 : 0

  return (
    <div>
      <div className="flex items-center justify-between mb-4" style={{ marginBottom: 4 }}>
        <span className="text-dim" style={{ fontSize: 12 }}>
          Прогресс: {completed} / {total}
        </span>
        <span className="text-dim" style={{ fontSize: 12 }}>
          {pct.toFixed(0)}%
        </span>
      </div>
      <div className="progress-bar">
        <div className="progress-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}
