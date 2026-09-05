import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";

const POSITION_NAMES = { 1: "GKP", 2: "DEF", 3: "MID", 4: "FWD" };

function readableError(message) {
  try {
    const parsed = JSON.parse(message);
    const detail = parsed?.detail ?? parsed;
    if (typeof detail === "string") return detail;
    if (detail?.message) return detail.message;
  } catch {
    /* not JSON */
  }
  return message;
}

function PlayerSearch({ position, onPick, picked, onClear }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const debounceRef = useRef(null);

  useEffect(() => {
    if (picked) return;
    clearTimeout(debounceRef.current);
    if (!query.trim()) {
      setResults([]);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      try {
        setResults(await api.searchPlayers(query.trim(), position ?? undefined));
        setOpen(true);
      } catch {
        setResults([]);
      }
    }, 250);
    return () => clearTimeout(debounceRef.current);
  }, [query, position, picked]);

  if (picked) {
    return (
      <div className="picked-player">
        <div>
          <strong>{picked.web_name}</strong>
          <div className="muted" style={{ fontSize: 12 }}>
            {picked.team_short_name} · {POSITION_NAMES[picked.element_type]} · £
            {(picked.now_cost / 10).toFixed(1)}m
          </div>
        </div>
        <button className="logout-link" onClick={onClear}>
          Change
        </button>
      </div>
    );
  }

  return (
    <div className="search-wrap">
      <input
        type="text"
        placeholder={position ? `Search ${POSITION_NAMES[position]}s...` : "Search players..."}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => results.length && setOpen(true)}
      />
      {open && results.length > 0 && (
        <div className="search-results">
          {results.map((p) => (
            <button
              key={p.id}
              className="search-result"
              onClick={() => {
                onPick(p);
                setOpen(false);
                setQuery("");
              }}
            >
              <span>
                {p.web_name}{" "}
                <span className="muted">
                  {p.team_short_name} · {POSITION_NAMES[p.element_type]}
                </span>
              </span>
              <span className="muted">£{(p.now_cost / 10).toFixed(1)}m</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ManualTransfer({ squad = [], gameweek }) {
  const [outPlayer, setOutPlayer] = useState(null);
  const [inPlayer, setInPlayer] = useState(null);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState(null);
  const [confirmedHit, setConfirmedHit] = useState(false);
  const [done, setDone] = useState(null);
  const queryClient = useQueryClient();

  // Ask the backend to validate as soon as both sides are chosen, so problems
  // (wrong position, not enough money) surface before anything is submitted.
  useEffect(() => {
    setPreview(null);
    setError(null);
    setDone(null);
    if (!outPlayer || !inPlayer) return;
    let cancelled = false;
    (async () => {
      try {
        const p = await api.previewTransfer({
          element_out: outPlayer.id,
          element_in: inPlayer.id,
        });
        if (!cancelled) setPreview(p);
      } catch (e) {
        if (!cancelled) setError(readableError(e.message));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [outPlayer, inPlayer]);

  const mutation = useMutation({
    mutationFn: (accept_hit) =>
      api.executeTransfer({
        element_in: inPlayer.id,
        element_out: outPlayer.id,
        element_in_cost: inPlayer.now_cost,
        element_out_cost: outPlayer.now_cost,
        event: gameweek,
        player_in_name: inPlayer.web_name,
        player_out_name: outPlayer.web_name,
        accept_hit,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["squad"] });
      queryClient.invalidateQueries({ queryKey: ["history"] });
      queryClient.invalidateQueries({ queryKey: ["recommendations"] });
      setDone(`${outPlayer.web_name} → ${inPlayer.web_name} completed.`);
      setOutPlayer(null);
      setInPlayer(null);
      setPreview(null);
    },
    onError: (err) => setError(readableError(err.message)),
  });

  const blockedByHit = preview?.is_hit && !confirmedHit;

  return (
    <div className="card">
      <div className="manual-grid">
        <div>
          <label className="manual-label">Transfer out</label>
          <select
            value={outPlayer?.id ?? ""}
            onChange={(e) => {
              const p = squad.find((s) => s.id === Number(e.target.value));
              setOutPlayer(p || null);
              setInPlayer(null);
            }}
          >
            <option value="">Select from your squad...</option>
            {squad.map((p) => (
              <option key={p.id} value={p.id}>
                {p.web_name} ({POSITION_NAMES[p.element_type]}) · £{(p.now_cost / 10).toFixed(1)}m
              </option>
            ))}
          </select>
        </div>

        <div className="arrow-badge manual-arrow">→</div>

        <div>
          <label className="manual-label">Transfer in</label>
          <PlayerSearch
            position={outPlayer?.element_type}
            picked={inPlayer}
            onPick={setInPlayer}
            onClear={() => setInPlayer(null)}
          />
          {!outPlayer && (
            <div className="form-hint">Pick who's leaving first — we'll match the position.</div>
          )}
        </div>
      </div>

      {preview && (
        <>
          <div className={`delta-banner ${preview.score_delta <= 0 ? "negative" : ""}`}>
            Score delta {preview.score_delta > 0 ? "+" : ""}
            {preview.score_delta.toFixed(1)} · Bank after £{(preview.bank_after / 10).toFixed(1)}m
          </div>

          {preview.reasons?.length > 0 && (
            <div className="reasons">
              <div className="reasons-title">What this changes</div>
              <ul>
                {preview.reasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          )}

          {preview.is_hit && (
            <div className="hit-warning">
              No free transfers left — this will cost a 4-point hit.
              <label>
                <input
                  type="checkbox"
                  checked={confirmedHit}
                  onChange={(e) => setConfirmedHit(e.target.checked)}
                />
                I understand and accept the hit
              </label>
            </div>
          )}
        </>
      )}

      {error && <div className="hit-warning" style={{ marginTop: 12 }}>{error}</div>}
      {done && <div className="success-banner">{done}</div>}

      <div className="actions-row">
        <button
          className="btn btn-approve"
          disabled={!preview || mutation.isPending || blockedByHit}
          onClick={() => {
            setError(null);
            mutation.mutate(Boolean(confirmedHit));
          }}
        >
          {mutation.isPending ? "Submitting..." : "Make transfer"}
        </button>
      </div>
    </div>
  );
}
