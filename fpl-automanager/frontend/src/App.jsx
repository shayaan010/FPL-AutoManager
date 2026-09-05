import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./lib/api";
import SquadView from "./components/SquadView";
import TransferCard from "./components/TransferCard";
import FixtureGrid from "./components/FixtureGrid";
import TransferHistory from "./components/TransferHistory";
import DeadlineCountdown from "./components/DeadlineCountdown";
import EmptyState from "./components/EmptyState";
import PitchView from "./components/PitchView";
import ManualTransfer from "./components/ManualTransfer";
import ConnectAccount from "./components/ConnectAccount";

function friendlyError(error) {
  if (!error) return null;
  const raw = error.message || "";
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed === "string") return parsed;
    if (parsed?.message) return parsed.message;
  } catch {
    // not JSON, fall through to raw message
  }
  return raw.replace(/^"|"$/g, "");
}

export default function App() {
  const [recIndex, setRecIndex] = useState(0);
  const [squadView, setSquadView] = useState("pitch");
  const [transferMode, setTransferMode] = useState("suggested");

  const squadQuery = useQuery({ queryKey: ["squad"], queryFn: api.getSquad, refetchInterval: 60_000 });
  const recommendationQuery = useQuery({
    queryKey: ["recommendations"],
    queryFn: api.getRecommendations,
    retry: false,
  });
  const historyQuery = useQuery({ queryKey: ["history"], queryFn: api.getHistory });
  const gameweekQuery = useQuery({ queryKey: ["gameweek"], queryFn: api.getGameweek });

  const squad = squadQuery.data?.squad ?? [];
  const gameweek = gameweekQuery.data?.next_event ?? gameweekQuery.data?.current_event ?? null;
  const history = historyQuery.data ?? [];
  const recommendations = recommendationQuery.data ?? [];
  const currentRec = recommendations[recIndex];

  return (
    <div className="app-shell">
      <div className="topbar">
        <div className="brand">
          <div className="brand-mark">⚽</div>
          <div className="brand-text">
            <h1>FPL Auto-Manager</h1>
            <div className="subtitle">Gameweek {gameweek ?? "—"}</div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <ConnectAccount />
          <DeadlineCountdown />
        </div>
      </div>

      <div className="sidebar">
        <div className="section-heading">
          <h3>Your Squad</h3>
        </div>
        {squadQuery.isLoading && (
          <EmptyState icon="⏳" title="Loading squad..." />
        )}
        {squadQuery.isError && (
          <EmptyState
            icon="🔌"
            tone="error"
            title="Squad not connected"
            description={
              friendlyError(squadQuery.error) === "FPL account not connected"
                ? "Click \"Connect FPL Account\" in the top right to link your team."
                : friendlyError(squadQuery.error)
            }
          />
        )}
        {squadQuery.data && (
          <SquadView
            squad={squad}
            bank={squadQuery.data.bank}
            teamValue={squadQuery.data.team_value}
            freeTransfers={squadQuery.data.free_transfers}
          />
        )}
      </div>

      <div className="main-panel">
        <div>
          <div className="section-heading">
            <h3>{transferMode === "suggested" ? "Recommended Transfer" : "Build a Transfer"}</h3>
            <div className="view-toggle">
              <button
                className={`toggle-btn ${transferMode === "suggested" ? "active" : ""}`}
                onClick={() => setTransferMode("suggested")}
              >
                Suggested
              </button>
              <button
                className={`toggle-btn ${transferMode === "manual" ? "active" : ""}`}
                onClick={() => setTransferMode("manual")}
              >
                Manual
              </button>
            </div>
          </div>
          {transferMode === "manual" && (
            <ManualTransfer squad={squad} gameweek={gameweek} />
          )}
          {transferMode === "suggested" && currentRec && (
            <TransferCard
              recommendation={currentRec}
              gameweek={gameweek}
              index={recIndex}
              total={recommendations.length}
              onNext={() => setRecIndex((i) => Math.min(i + 1, recommendations.length - 1))}
              onPrev={() => setRecIndex((i) => Math.max(i - 1, 0))}
            />
          )}
          {transferMode === "suggested" && !currentRec && (
            <div className="card">
              <EmptyState
                icon="✅"
                title="No transfer recommendation right now"
                description={
                  recommendationQuery.isError
                    ? "This needs a connected squad first — sign in to FPL above."
                    : "Check back after the next player data refresh."
                }
              />
            </div>
          )}
        </div>

        <div>
          <div className="section-heading">
            <h3>{squadView === "pitch" ? "Your Team" : "Fixture Difficulty"}</h3>
            <div className="view-toggle">
              <button
                className={`toggle-btn ${squadView === "pitch" ? "active" : ""}`}
                onClick={() => setSquadView("pitch")}
              >
                Pitch
              </button>
              <button
                className={`toggle-btn ${squadView === "list" ? "active" : ""}`}
                onClick={() => setSquadView("list")}
              >
                List
              </button>
            </div>
          </div>
          {squadView === "pitch" ? (
            squad.length > 0 ? (
              <div className="card">
                <PitchView squad={squad} />
              </div>
            ) : (
              <div className="card">
                <EmptyState
                  icon="🏟️"
                  title="No team to show yet"
                  description="Your line-up appears here once your squad is loaded."
                />
              </div>
            )
          ) : (
            <FixtureGrid squad={squad} />
          )}
        </div>
      </div>

      <div className="history-panel">
        <div className="section-heading">
          <h3>Transfer History</h3>
        </div>
        <div className="card">
          <TransferHistory transfers={history} />
        </div>
      </div>
    </div>
  );
}
