const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8010";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ? JSON.stringify(body.detail) : `Request failed: ${res.status}`);
  }
  return res.json();
}

export interface ScoredPlayer {
  id: number;
  web_name: string;
  team: number;
  team_short_name: string;
  team_code: number | null;
  element_type: number;
  now_cost: number;
  event_points: number;
  form: number;
  selected_by_percent: number;
  cost_change_event: number;
  minutes: number;
  score: number;
  fixtures: { event: number; opponent_short_name: string; is_home: boolean; difficulty: number }[];
  breakdown: Record<string, number | null>;
  position?: number;
  is_captain?: boolean;
  is_vice_captain?: boolean;
  multiplier?: number;
}

export interface SquadResponse {
  squad: ScoredPlayer[];
  bank: number;
  team_value: number;
  free_transfers: number | null;
}

export interface TransferRecommendation {
  player_out: ScoredPlayer;
  player_in: ScoredPlayer;
  score_delta: number;
  is_hit: boolean;
  free_transfers: number;
  reasons: string[];
}

export interface TransferPreview {
  player_out: ScoredPlayer;
  player_in: ScoredPlayer;
  score_delta: number;
  reasons: string[];
  selling_price: number;
  purchase_price: number;
  bank_after: number;
  is_hit: boolean;
  free_transfers: number | null;
}

export interface TransferRecord {
  id: number;
  gameweek: number;
  player_out_id: number;
  player_out_name: string;
  player_in_id: number;
  player_in_name: string;
  selling_price: number;
  purchase_price: number;
  executed_at: string;
  points_gained: number | null;
}

export interface GameweekInfo {
  current_event: number | null;
  next_event: number | null;
  next_deadline_time: string | null;
  free_transfers: number | null;
}

export interface AuthStatus {
  connected: boolean;
  team_id: number | null;
}

export const api = {
  getSquad: () => request<SquadResponse>("/squad"),
  getRecommendations: () => request<TransferRecommendation[]>("/recommendations"),
  getHistory: () => request<TransferRecord[]>("/history"),
  searchPlayers: (q: string, element_type?: number) => {
    const params = new URLSearchParams({ q });
    if (element_type != null) params.set("element_type", String(element_type));
    return request<ScoredPlayer[]>(`/players/search?${params}`);
  },
  previewTransfer: (body: { element_out: number; element_in: number }) =>
    request<TransferPreview>("/transfer/preview", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getGameweek: () => request<GameweekInfo>("/gameweek"),
  getAuthStatus: () => request<AuthStatus>("/auth/status"),
  logout: () => request<{ status: string }>("/auth/logout", { method: "POST" }),
  browserLoginStart: (fresh = false) =>
    request<{ status: string }>("/auth/browser/start", {
      method: "POST",
      body: JSON.stringify({ fresh }),
    }),
  browserLoginStatus: () => request<{ status: string; error: string | null }>("/auth/browser/status"),
  loginWithToken: (body: { access_token: string; team_id?: number }) =>
    request<{ status: string; team_id: number }>("/auth/token", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  executeTransfer: (body: {
    element_in: number;
    element_out: number;
    element_in_cost: number;
    element_out_cost: number;
    event: number;
    player_in_name: string;
    player_out_name: string;
    accept_hit?: boolean;
  }) => request("/transfer/execute", { method: "POST", body: JSON.stringify(body) }),
};

export function wsUrl(path: string): string {
  const base = API_URL.replace(/^http/, "ws");
  return `${base}${path}`;
}
