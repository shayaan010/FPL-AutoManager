import { useEffect, useState } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { api, ApiError } from "./lib/api";
import SquadView from "./components/SquadView";
import TransferCard from "./components/TransferCard";
import FixtureGrid from "./components/FixtureGrid";
import TransferHistory from "./components/TransferHistory";
import DeadlineCountdown from "./components/DeadlineCountdown";
import EmptyState from "./components/EmptyState";
import PitchView from "./components/PitchView";
import ManualTransfer from "./components/ManualTransfer";
import ConnectAccount from "./components/ConnectAccount";
import AuthScreen from "./components/AuthScreen";
import AccountMenu from "./components/AccountMenu";
import Icon from "./components/Icon";
import ThemeToggle from "./components/ThemeToggle";

function friendlyError(error) {
  if (!error) return null;
  const raw = error.message || "";
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed === "string") return parsed;
    if (parsed?.message) return parsed.message;
  } catch { }
  return raw.replace(/^"|"$/g, "");
}

export default function App() {
  const queryClient = useQueryClient();

  const meQuery = useQuery({
    queryKey: ["me"],
    queryFn: api.getMe,
    retry: false,
  });

  const [linking, setLinking] = useState(false);
  useEffect(() => {
    const match = window.location.hash.match(/fpl_token=([^&]+)/);
    if (!match || !meQuery.data) return;
    const token = decodeURIComponent(match[1]);
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    setLinking(true);
    api
      .loginWithToken({ access_token: token })
      .then(() => queryClient.invalidateQueries())
      .catch(() => {})
      .finally(() => setLinking(false));
  }, [meQuery.data, queryClient]);

  if (meQuery.isLoading) {
    return (
      <div className="auth-screen">
        <EmptyState icon="clock" title="Loading..." />
      </div>
    );
  }

  if (meQuery.isError && meQuery.error instanceof ApiError && meQuery.error.status === 401) {
    return <AuthScreen />;
  }

  return <Dashboard user={meQuery.data} linking={linking} />;
}

function Dashboard({ user, linking }) {
  const queryClient = useQueryClient();
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
          <div className="brand-mark"><Icon name="ball" size={18} /></div>
          <div className="brand-text">
            <h1>FPL Auto-Manager</h1>
            <div className="subtitle">Gameweek {gameweek ?? "—"}</div>
          </div>
        </div>
        <div className="topbar-right">
          {linking && <span className="linking-note">Linking FPL account...</span>}
          <ConnectAccount />
          <DeadlineCountdown />
          <ThemeToggle />
          <AccountMenu user={user} />
        </div>
      </div>

      <div className="sidebar">
        <div className="section-heading">
          <h3><Icon name="squad" size={14} />Your Squad</h3>
        </div>
        {squadQuery.isLoading && (
          <EmptyState icon="clock" title="Loading squad..." />
        )}
        {squadQuery.isError && (
          <EmptyState
            icon="unlink"
            tone="error"
            title="Squad not connected"
            description={
              squadQuery.error?.status === 428
                ? "Click \"Connect FPL\" in the top right to link your team."
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
            <h3><Icon name="swap" size={14} />{transferMode === "suggested" ? "Recommended transfer" : "Build a transfer"}</h3>
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
                icon="check"
                title="No transfer recommendation right now"
                description={
                  recommendationQuery.isError
                    ? "This needs a connected FPL team first — use \"Connect FPL\" above."
                    : "Check back after the next player data refresh."
                }
              />
            </div>
          )}
        </div>

        <div>
          <div className="section-heading">
            <h3><Icon name={squadView === "pitch" ? "pitch" : "list"} size={14} />{squadView === "pitch" ? "Your team" : "Fixture difficulty"}</h3>
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
                  icon="pitch"
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
          <h3><Icon name="history" size={14} />Transfer history</h3>
        </div>
        <div className="card">
          <TransferHistory transfers={history} />
        </div>
      </div>
    </div>
  );
}
