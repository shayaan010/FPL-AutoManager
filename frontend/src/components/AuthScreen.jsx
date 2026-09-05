import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";

export default function AuthScreen() {
  const [mode, setMode] = useState("signin"); // signin | register
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () =>
      mode === "register"
        ? api.register({ email: email.trim(), password })
        : api.signIn({ email: email.trim(), password }),
    onSuccess: (user) => {
      queryClient.setQueryData(["me"], user);
      queryClient.invalidateQueries();
    },
    onError: (err) => setError(err.message),
  });

  const submit = (e) => {
    e.preventDefault();
    setError(null);
    mutation.mutate();
  };

  const registering = mode === "register";

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <div className="brand" style={{ justifyContent: "center", marginBottom: 18 }}>
          <div className="brand-mark">⚽</div>
          <div className="brand-text">
            <h1 style={{ fontSize: 18 }}>FPL Auto-Manager</h1>
            <div className="subtitle">Smarter transfers, every gameweek</div>
          </div>
        </div>

        <div className="view-toggle" style={{ marginBottom: 18 }}>
          <button
            className={`toggle-btn ${!registering ? "active" : ""}`}
            onClick={() => { setMode("signin"); setError(null); }}
            style={{ flex: 1 }}
          >
            Sign in
          </button>
          <button
            className={`toggle-btn ${registering ? "active" : ""}`}
            onClick={() => { setMode("register"); setError(null); }}
            style={{ flex: 1 }}
          >
            Create account
          </button>
        </div>

        <form onSubmit={submit}>
          <div className="form-field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              required
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="form-field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              required
              minLength={registering ? 8 : undefined}
              autoComplete={registering ? "new-password" : "current-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {registering && <div className="form-hint">At least 8 characters.</div>}
          </div>

          {error && <div className="hit-warning">{error}</div>}

          <button
            type="submit"
            className="btn connect-btn"
            style={{ width: "100%", marginTop: 8 }}
            disabled={mutation.isPending}
          >
            {mutation.isPending
              ? registering ? "Creating account..." : "Signing in..."
              : registering ? "Create account" : "Sign in"}
          </button>
        </form>

        <div className="auth-footnote">
          You'll link your Fantasy Premier League account after signing in.
          We never see or store your FPL password.
        </div>
      </div>
    </div>
  );
}
