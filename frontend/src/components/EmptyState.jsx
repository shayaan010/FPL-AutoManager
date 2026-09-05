import Icon from "./Icon";

export default function EmptyState({ icon = "spark", title, description, tone = "muted" }) {
  return (
    <div className={`empty-state ${tone}`}>
      <div className="empty-state-icon">
        <Icon name={icon} size={20} />
      </div>
      <div className="empty-state-title">{title}</div>
      {description && <div className="empty-state-desc">{description}</div>}
    </div>
  );
}
