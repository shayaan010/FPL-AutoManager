import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";

function invalidateAfterConnect(queryClient) {
  queryClient.invalidateQueries({ queryKey: ["authStatus"] });
  queryClient.invalidateQueries({ queryKey: ["squad"] });
  queryClient.invalidateQueries({ queryKey: ["recommendations"] });
  queryClient.invalidateQueries({ queryKey: ["history"] });
}

function ManualTokenFallback({ onConnected }) {
  const [open, setOpen] = useState(false);
  const [accessToken, setAccessToken] = useState("");
  const [error, setError] = useState(null);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => api.loginWithToken({ access_token: accessToken.trim() }),
    onSuccess: () => {
      invalidateAfterConnect(queryClient);
      onConnected();
    },
    onError: (err) => setError(err.message),
  });

  if (!open) {
    return (
      <button type="button" className="fallback-toggle" onClick={() => setOpen(true)}>
        Having trouble? Connect manually →
      </button>
    );
  }

  return (
    <div className="fallback-panel">
      <div className="modal-subtitle" style={{ marginTop: 0 }}>
        In a browser already signed into FPL, open DevTools → <strong>Console</strong>{" "}
        and run this, then paste the result:
        <pre className="snippet">
{`JSON.parse(localStorage.getItem(
  Object.keys(localStorage)
    .find(k => k.startsWith('oidc.user:'))
)).access_token`}
        </pre>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          mutation.mutate();
        }}
      >
        <div className="form-field">
          <label htmlFor="access-token">Access token</label>
          <input
            id="access-token"
            type="text"
            required
            value={accessToken}
            onChange={(e) => setAccessToken(e.target.value)}
          />
        </div>

        {error && <div className="hit-warning">{error}</div>}

        <div className="modal-actions">
          <button type="submit" className="btn connect-btn" disabled={mutation.isPending}>
            {mutation.isPending ? "Connecting..." : "Connect"}
          </button>
        </div>
      </form>
    </div>
  );
}

function LoginModal({ onClose }) {
  const [phase, setPhase] = useState("idle"); // idle | waiting
  const [error, setError] = useState(null);
  const pollRef = useRef(null);
  const queryClient = useQueryClient();

  useEffect(() => () => clearInterval(pollRef.current), []);

  const start = async (fresh = false) => {
    setError(null);
    setPhase("waiting");
    try {
      await api.browserLoginStart(fresh);
    } catch (e) {
      setError(e.message);
      setPhase("idle");
      return;
    }
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.browserLoginStatus();
        if (s.status === "success") {
          clearInterval(pollRef.current);
          invalidateAfterConnect(queryClient);
          onClose();
        } else if (s.status === "error") {
          clearInterval(pollRef.current);
          setError(s.error || "Sign-in failed");
          setPhase("idle");
        }
      } catch {
        // transient network hiccup while polling -- try again next tick
      }
    }, 1500);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <h2>Connect your FPL account</h2>
        <div className="modal-subtitle">
          {phase === "waiting"
            ? "A Chrome window is open — sign in to FPL there and this will connect automatically."
            : "Opens FPL in a Chrome window. Sign in however you normally do — including with Google. We never see your password, and your team is detected automatically."}
        </div>

        {error && <div className="hit-warning">{error}</div>}

        <div className="modal-actions">
          <button type="button" className="btn btn-dismiss" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn connect-btn"
            disabled={phase === "waiting"}
            onClick={() => start(false)}
          >
            {phase === "waiting" ? "Waiting for sign-in..." : "Sign in to FPL"}
          </button>
        </div>

        <button
          type="button"
          className="fallback-toggle"
          disabled={phase === "waiting"}
          onClick={() => start(true)}
        >
          Sign in as a different account →
        </button>

        <div className="fallback-divider" />
        <ManualTokenFallback onConnected={onClose} />
      </div>
    </div>
  );
}

export default function ConnectAccount() {
  const [showModal, setShowModal] = useState(false);
  const queryClient = useQueryClient();

  const statusQuery = useQuery({
    queryKey: ["authStatus"],
    queryFn: api.getAuthStatus,
    refetchInterval: 3000,
  });

  const logoutMutation = useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["authStatus"] });
      queryClient.invalidateQueries({ queryKey: ["squad"] });
      queryClient.invalidateQueries({ queryKey: ["recommendations"] });
    },
  });

  useEffect(() => {
    if (statusQuery.data?.connected) setShowModal(false);
  }, [statusQuery.data?.connected]);

  if (statusQuery.data?.connected) {
    return (
      <div className="connected-pill">
        <span className="status-dot" />
        Team {statusQuery.data.team_id}
        <button
          className="logout-link"
          onClick={() => logoutMutation.mutate()}
          disabled={logoutMutation.isPending}
        >
          Disconnect
        </button>
      </div>
    );
  }

  return (
    <>
      <button className="btn connect-btn" onClick={() => setShowModal(true)}>
        Sign in to FPL
      </button>
      {showModal && <LoginModal onClose={() => setShowModal(false)} />}
    </>
  );
}
