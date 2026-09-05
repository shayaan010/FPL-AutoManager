export default function EmptyState({ icon = "⚽", title, description, tone = "muted" }) {
  return (
    <div className={`empty-state ${tone}`}>
      <div className="empty-state-icon">{icon}</div>
      <div className="empty-state-title">{title}</div>
      {description && <div className="empty-state-desc">{description}</div>}
    </div>
  );
}
