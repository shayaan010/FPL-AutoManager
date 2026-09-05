import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import Icon from "./Icon";
import ThemeToggle from "./ThemeToggle";

export default function AuthScreen() {
  const [mode, setMode] = useState("signin");
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
      <div className="auth-screen-toolbar">
        <ThemeToggle />
      </div>
      <div className="auth-card">
        <div className="auth-brand">
          <div className="brand-mark"><Icon name="ball" size={20} /></div>
          <h1>FPL Auto-Manager</h1>
          <p>Smarter transfers, every gameweek</p>
        </div>

        <div className="view-toggle auth-toggle">
          <button
            className={`toggle-btn ${!registering ? "active" : ""}`}
            onClick={() => { setMode("signin"); setError(null); }}
          >
            Sign in
          </button>
          <button
            className={`toggle-btn ${registering ? "active" : ""}`}
            onClick={() => { setMode("register"); setError(null); }}
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
            className="btn connect-btn btn-block"
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
