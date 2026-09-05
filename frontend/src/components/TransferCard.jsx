import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { FixtureSquares } from "./FixtureGrid";

const POSITION_NAMES = { 1: "GKP", 2: "DEF", 3: "MID", 4: "FWD" };

// The FPL API returns nested field-level validation errors; flatten them into
// something a person can actually read instead of dumping raw JSON.
function readableError(message) {
  let parsed;
  try {
    parsed = JSON.parse(message);
  } catch {
    return message;
  }

  const detail = parsed?.detail ?? parsed;
  const headline = detail?.message || "Transfer rejected";
  const notes = [];

  const walk = (node, path) => {
    if (node == null) return;
    if (Array.isArray(node)) {
      node.forEach((item) => walk(item, path));
    } else if (typeof node === "object") {
      if (node.message) {
        notes.push(path ? `${path}: ${node.message}` : node.message);
        return;
      }
      Object.entries(node).forEach(([key, value]) => walk(value, key));
    }
  };
  walk(detail?.fpl_response, "");

  const unique = [...new Set(notes)];
  return unique.length ? `${headline} — ${unique.join("; ")}` : headline;
}

function PlayerColumn({ player, side }) {
  return (
    <div className={`player-col ${side}`}>
      <div className="muted" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.05em" }}>
        {side === "out" ? "Transfer out" : "Transfer in"}
      </div>
      <div className="name" style={{ marginTop: 6 }}>{player.web_name}</div>
      <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>
        <span className="pos-pill">{POSITION_NAMES[player.element_type]}</span>
        £{(player.now_cost / 10).toFixed(1)}m
      </div>
      <div className="muted" style={{ fontSize: 13 }}>Form {player.form}</div>
      <div style={{ marginTop: 10 }}>
        <FixtureSquares fixtures={player.fixtures} count={3} />
      </div>
      <div className="score-pill">{player.score.toFixed(1)}</div>
    </div>
  );
}

export default function TransferCard({ recommendation, gameweek, index = 0, total = 1, onNext, onPrev }) {
  const [error, setError] = useState(null);
  const [confirmedHit, setConfirmedHit] = useState(false);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (accept_hit) =>
      api.executeTransfer({
        element_in: recommendation.player_in.id,
        element_out: recommendation.player_out.id,
        element_in_cost: recommendation.player_in.now_cost,
        element_out_cost: recommendation.player_out.now_cost,
        event: gameweek,
        player_in_name: recommendation.player_in.web_name,
        player_out_name: recommendation.player_out.web_name,
        accept_hit,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["squad"] });
      queryClient.invalidateQueries({ queryKey: ["history"] });
      queryClient.invalidateQueries({ queryKey: ["recommendations"] });
    },
    onError: (err) => setError(readableError(err.message)),
  });

  if (!recommendation) return null;

  const handleApprove = () => {
    setError(null);
    mutation.mutate(recommendation.is_hit && !confirmedHit ? false : confirmedHit || !recommendation.is_hit);
  };

  return (
    <div className="card">
      {total > 1 && (
        <div className="rec-nav">
          <button className="rec-nav-btn" onClick={onPrev} disabled={index === 0}>
            ‹
          </button>
          <span className="rec-nav-label">
            Option {index + 1} of {total}
          </span>
          <button className="rec-nav-btn" onClick={onNext} disabled={index >= total - 1}>
            ›
          </button>
        </div>
      )}

      <div className="transfer-card">
        <PlayerColumn player={recommendation.player_out} side="out" />
        <div className="arrow-badge">→</div>
        <PlayerColumn player={recommendation.player_in} side="in" />
      </div>

      <div className={`delta-banner ${recommendation.score_delta <= 0 ? "negative" : ""}`}>
        Score delta {recommendation.score_delta > 0 ? "+" : ""}
        {recommendation.score_delta.toFixed(1)}
      </div>

      {recommendation.reasons?.length > 0 && (
        <div className="reasons">
          <div className="reasons-title">Why this transfer</div>
          <ul>
            {recommendation.reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      {recommendation.is_hit && (
        <div className="hit-warning">
          No free transfers left — this will cost a 4-point hit.
          <label>
            <input type="checkbox" checked={confirmedHit} onChange={(e) => setConfirmedHit(e.target.checked)} />
            I understand and accept the hit
          </label>
        </div>
      )}

      {error && <div className="hit-warning" style={{ marginTop: 12 }}>{error}</div>}

      <div className="actions-row">
        <button
          className="btn btn-approve"
          disabled={mutation.isPending || (recommendation.is_hit && !confirmedHit)}
          onClick={handleApprove}
        >
          {mutation.isPending ? "Submitting..." : "Approve"}
        </button>
        <button
          className="btn btn-dismiss"
          onClick={onNext}
          disabled={index >= total - 1}
        >
          Next suggestion
        </button>
      </div>
    </div>
  );
}
