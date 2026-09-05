import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import Icon from "./Icon";

function invalidateAfterConnect(queryClient) {
  queryClient.invalidateQueries({ queryKey: ["authStatus"] });
  queryClient.invalidateQueries({ queryKey: ["squad"] });
  queryClient.invalidateQueries({ queryKey: ["recommendations"] });
  queryClient.invalidateQueries({ queryKey: ["history"] });
}

function bookmarkletSource() {
  const target = `${window.location.origin}${window.location.pathname}`;
  return `javascript:(function(){try{var k=Object.keys(localStorage).find(function(x){return x.indexOf('oidc.user:')===0});if(!k){alert('Sign in at fantasy.premierleague.com first, then click this again.');return}var t=JSON.parse(localStorage.getItem(k)).access_token;if(!t){alert('Signed in, but no FPL token found. Reload the page and try again.');return}location.href='${target}#fpl_token='+encodeURIComponent(t)}catch(e){alert('Could not read your FPL session: '+e.message)}})()`;
}

function BookmarkletPanel() {
  const [copied, setCopied] = useState(false);
  const href = bookmarkletSource();

  return (
    <div className="connect-option recommended">
      <div className="connect-option-badge">Easiest</div>
      <h3>Connect with one click</h3>
      <ol className="setup-steps">
        <li>
          Drag this button to your bookmarks bar:{" "}
          <a className="bookmarklet" href={href} onClick={(e) => e.preventDefault()}>
            <Icon name="link" size={13} /> Connect FPL
          </a>
        </li>
        <li>
          Go to{" "}
          <a href="https://fantasy.premierleague.com/" target="_blank" rel="noreferrer">
            fantasy.premierleague.com
          </a>{" "}
          and sign in as normal
        </li>
        <li>Click the bookmark — you'll come straight back here, connected</li>
      </ol>
      <button
        type="button"
        className="btn btn-dismiss btn-sm copy-link-btn"
        onClick={() => {
          navigator.clipboard?.writeText(href).then(
            () => { setCopied(true); setTimeout(() => setCopied(false), 2000); },
            () => setCopied(false)
          );
        }}
      >
        {copied ? "Copied!" : "Can't drag? Copy the link"}
      </button>
    </div>
  );
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
        Advanced: paste a token manually →
      </button>
    );
  }

  return (
    <div className="fallback-panel">
      <div className="modal-subtitle flush">
        On fantasy.premierleague.com, open DevTools → <strong>Console</strong>, run
        this, and paste the result:
        <pre className="snippet">
{`JSON.parse(localStorage.getItem(
  Object.keys(localStorage)
    .find(k => k.startsWith('oidc.user:'))
)).access_token`}
        </pre>
      </div>

      <form
        onSubmit={(e) => { e.preventDefault(); setError(null); mutation.mutate(); }}
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

function LocalBrowserLogin({ onConnected }) {
  const [phase, setPhase] = useState("idle");
  const [error, setError] = useState(null);
  const pollRef = useRef(null);
  const queryClient = useQueryClient();

  useEffect(() => () => clearInterval(pollRef.current), []);

  const start = async (fresh) => {
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
          onConnected();
        } else if (s.status === "error") {
          clearInterval(pollRef.current);
          setError(s.error || "Sign-in failed");
          setPhase("idle");
        }
      } catch { }
    }, 1500);
  };

  return (
    <div className="connect-option">
      <h3>Open a browser here (local only)</h3>
      <p className="modal-subtitle tight">
        Opens FPL in a Chrome window on this machine. Only works when the app
        runs on your own computer.
      </p>
      {error && <div className="hit-warning">{error}</div>}
      <div className="modal-actions start">
        <button
          type="button"
          className="btn connect-btn"
          disabled={phase === "waiting"}
          onClick={() => start(false)}
        >
          {phase === "waiting" ? "Waiting for sign-in..." : "Open login window"}
        </button>
        <button
          type="button"
          className="btn btn-dismiss"
          disabled={phase === "waiting"}
          onClick={() => start(true)}
        >
          Different account
        </button>
      </div>
    </div>
  );
}

function ConnectModal({ onClose, allowBrowserLogin }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <h2>Connect your FPL account</h2>
        <div className="modal-subtitle">
          FPL has no "sign in with FPL" for other apps, so your browser hands us
          a session token instead. We never see your FPL password, and you can
          disconnect at any time.
        </div>

        <BookmarkletPanel />
        {allowBrowserLogin && <LocalBrowserLogin onConnected={onClose} />}

        <div className="fallback-divider" />
        <ManualTokenFallback onConnected={onClose} />

        <div className="modal-actions">
          <button type="button" className="btn btn-dismiss" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ConnectAccount() {
  const [showModal, setShowModal] = useState(false);
  const queryClient = useQueryClient();

  const statusQuery = useQuery({ queryKey: ["authStatus"], queryFn: api.getAuthStatus });
  const configQuery = useQuery({ queryKey: ["config"], queryFn: api.getConfig, staleTime: Infinity });

  const unlink = useMutation({
    mutationFn: api.unlinkFpl,
    onSuccess: () => invalidateAfterConnect(queryClient),
  });

  useEffect(() => {
    if (statusQuery.data?.connected) setShowModal(false);
  }, [statusQuery.data?.connected]);

  if (statusQuery.data?.connected) {
    return (
      <div className="connected-pill">
        <span className="status-dot" />
        Team <strong className="tabular">{statusQuery.data.team_id}</strong>
        <button
          className="logout-link"
          onClick={() => unlink.mutate()}
          disabled={unlink.isPending}
        >
          Disconnect
        </button>
      </div>
    );
  }

  return (
    <>
      <button className="btn connect-btn" onClick={() => setShowModal(true)}>
        <Icon name="link" size={13} />
        Connect FPL
      </button>
      {showModal && (
        <ConnectModal
          onClose={() => setShowModal(false)}
          allowBrowserLogin={Boolean(configQuery.data?.browser_login)}
        />
      )}
    </>
  );
}
