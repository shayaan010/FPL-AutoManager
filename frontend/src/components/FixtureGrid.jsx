import EmptyState from "./EmptyState";

const POSITION_NAMES = { 1: "GKP", 2: "DEF", 3: "MID", 4: "FWD" };

function difficultyClass(difficulty) {
  if (difficulty <= 2) return "good";
  if (difficulty === 3) return "mid";
  return "bad";
}

export function FixtureSquares({ fixtures = [], count = 5 }) {
  const shown = fixtures.slice(0, count);
  if (shown.length === 0) return <span className="muted">—</span>;
  return (
    <span>
      {shown.map((f, i) => (
        <span
          key={i}
          className={`fixture-square ${difficultyClass(f.difficulty)}`}
          title={`GW${f.event} vs ${f.opponent_short_name} (${f.is_home ? "H" : "A"}), FDR ${f.difficulty}`}
        />
      ))}
    </span>
  );
}

export default function FixtureGrid({ squad = [] }) {
  if (squad.length === 0) {
    return (
      <div className="card">
        <EmptyState
          icon="list"
          title="No fixtures to show yet"
          description="Fixture difficulty appears here once your squad is loaded."
        />
      </div>
    );
  }

  return (
    <div className="card">
      <table>
        <thead>
          <tr>
            <th>Player</th>
            <th>Pos</th>
            <th>Next 5 fixtures</th>
          </tr>
        </thead>
        <tbody>
          {squad.map((p) => (
            <tr key={p.id}>
              <td className="player-cell">{p.web_name}</td>
              <td>
                <span className="pos-pill">{POSITION_NAMES[p.element_type]}</span>
              </td>
              <td>
                <FixtureSquares fixtures={p.fixtures} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
