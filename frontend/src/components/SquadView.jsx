import EmptyState from "./EmptyState";

const POSITION_NAMES = { 1: "GKP", 2: "DEF", 3: "MID", 4: "FWD" };

export default function SquadView({ squad = [], bank, teamValue, freeTransfers }) {
  const maxScore = Math.max(1, ...squad.map((p) => p.score));

  return (
    <div>
      <div className="stat-grid">
        <div className="stat-tile">
          <div className="stat-label">Bank</div>
          <div className="stat-value">£{((bank ?? 0) / 10).toFixed(1)}m</div>
        </div>
        <div className="stat-tile">
          <div className="stat-label">Value</div>
          <div className="stat-value">£{((teamValue ?? 0) / 10).toFixed(1)}m</div>
        </div>
        <div className="stat-tile">
          <div className="stat-label">FT</div>
          <div className="stat-value">{freeTransfers ?? "—"}</div>
        </div>
      </div>

      {squad.length === 0 ? (
        <EmptyState icon="squad" title="Squad is empty" description="Nothing to show yet." />
      ) : (
        squad.map((p) => (
          <div className="squad-row" key={p.id}>
            <div className="squad-row-main">
              <div className="player-name">
                <span className="pos-pill">{POSITION_NAMES[p.element_type]}</span>
                {p.web_name}
                {p.is_captain && <span className="captain-badge">C</span>}
              </div>
              <div className="squad-row-meta">
                £{(p.now_cost / 10).toFixed(1)}m · form {p.form}
              </div>
              <div className="score-bar-track">
                <div
                  className="score-bar-fill"
                  style={{ width: `${Math.max(0, (p.score / maxScore) * 100)}%` }}
                />
              </div>
            </div>
            <div className="score-value">{p.score.toFixed(1)}</div>
          </div>
        ))
      )}
    </div>
  );
}
