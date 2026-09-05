import { useState } from "react";

const POSITION_NAMES = { 1: "GKP", 2: "DEF", 3: "MID", 4: "FWD" };

// FPL serves kit images off its own CDN, keyed by team code.
function kitUrl(player) {
  if (!player.team_code) return null;
  const suffix = player.element_type === 1 ? "_1" : "";
  return `https://fantasy.premierleague.com/dist/img/shirts/standard/shirt_${player.team_code}${suffix}-66.png`;
}

function PlayerChip({ player }) {
  const [imgFailed, setImgFailed] = useState(false);
  const url = kitUrl(player);
  const points = (player.event_points ?? 0) * (player.multiplier || 1);

  return (
    <div className="pitch-player" title={`${player.web_name} · ${POSITION_NAMES[player.element_type]} · £${(player.now_cost / 10).toFixed(1)}m`}>
      <div className="kit-wrap">
        {url && !imgFailed ? (
          <img
            className="kit-img"
            src={url}
            alt=""
            loading="lazy"
            onError={() => setImgFailed(true)}
          />
        ) : (
          <div className="kit-fallback">{player.team_short_name || "?"}</div>
        )}
        {player.is_captain && <span className="armband">C</span>}
        {player.is_vice_captain && <span className="armband vice">V</span>}
      </div>
      <div className="pitch-name">{player.web_name}</div>
      <div className="pitch-points">{points}</div>
    </div>
  );
}

export default function PitchView({ squad = [] }) {
  const starters = squad.filter((p) => (p.position ?? 99) <= 11);
  const bench = squad.filter((p) => (p.position ?? 99) > 11);

  if (squad.length === 0) return null;

  const rows = [1, 2, 3, 4].map((type) => starters.filter((p) => p.element_type === type));
  const formation = rows
    .slice(1)
    .map((r) => r.length)
    .join("-");

  return (
    <div className="pitch-wrap">
      <div className="pitch">
        {rows.map((row, i) =>
          row.length === 0 ? null : (
            <div className="pitch-row" key={i}>
              {row.map((p) => (
                <PlayerChip key={p.id} player={p} />
              ))}
            </div>
          )
        )}
      </div>

      {bench.length > 0 && (
        <div className="bench">
          <div className="bench-label">Bench · {formation}</div>
          <div className="bench-row">
            {bench.map((p) => (
              <PlayerChip key={p.id} player={p} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
