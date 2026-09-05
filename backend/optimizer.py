"""
Transfer recommendation logic. Pure Python scoring -- no LLM involved.

Scores each player using fixture difficulty, recent form, ownership trend,
price-change direction, and rotation/injury risk, then finds the squad swap
with the largest score improvement.
"""
from __future__ import annotations

from models import ScoredPlayer, TransferRecommendation

# Weights are deliberately simple and hand-tuned, not fit to data.
W_FORM = 2.0
W_FIXTURE = 1.5
W_OWNERSHIP = 0.05
W_PRICE_CHANGE = 1.0
W_MINUTES_RISK = 1.0

POSITION_NAMES = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def _next_fixtures_for_player(player_id: int, teams_by_id: dict, fixtures: list[dict], team_id: int, n: int = 5) -> list[dict]:
    """Pull the next n unplayed fixtures for a player's team, with a simple difficulty rating."""
    upcoming = [f for f in fixtures if not f.get("finished") and (f.get("team_h") == team_id or f.get("team_a") == team_id)]
    upcoming.sort(key=lambda f: (f.get("event") or 999, f.get("kickoff_time") or ""))
    out = []
    for f in upcoming[:n]:
        is_home = f.get("team_h") == team_id
        fdr = f.get("team_h_difficulty") if is_home else f.get("team_a_difficulty")
        opponent_id = f.get("team_a") if is_home else f.get("team_h")
        opponent = teams_by_id.get(opponent_id, {})
        out.append({
            "event": f.get("event"),
            "opponent_short_name": opponent.get("short_name", "?"),
            "is_home": is_home,
            "difficulty": fdr or 3,
        })
    return out


def score_breakdown(player: dict, fixtures: list[dict]) -> dict:
    """
    Itemised score for one player, so the UI can explain its recommendations.
    Fixtures must already be filtered to the player's team, soonest first.
    """
    form = float(player.get("form") or 0.0)

    next_three = fixtures[:3]
    avg_fdr = sum(f["difficulty"] for f in next_three) / len(next_three) if next_three else 3.0

    ownership = float(player.get("selected_by_percent") or 0.0)
    cost_change_event = int(player.get("cost_change_event") or 0)

    minutes = int(player.get("minutes") or 0)
    chance_of_playing = player.get("chance_of_playing_next_round")
    if chance_of_playing is not None:
        minutes_risk_penalty = (100 - chance_of_playing) / 100.0
    else:
        minutes_risk_penalty = 0.0 if minutes >= 60 else 0.5

    breakdown = {
        "form": round(form, 2),
        "form_points": round(W_FORM * form, 2),
        "avg_fdr": round(avg_fdr, 2),
        # FDR 1 is a great fixture, 5 is a terrible one, so invert it.
        "fixture_points": round(W_FIXTURE * (5.0 - avg_fdr), 2),
        "ownership": round(ownership, 1),
        "ownership_points": round(W_OWNERSHIP * ownership, 2),
        "cost_change_event": cost_change_event,
        "price_points": round(W_PRICE_CHANGE * cost_change_event, 2),
        "minutes": minutes,
        "chance_of_playing": chance_of_playing,
        "risk_points": round(-W_MINUTES_RISK * minutes_risk_penalty * 5.0, 2),
    }
    breakdown["total"] = round(
        breakdown["form_points"]
        + breakdown["fixture_points"]
        + breakdown["ownership_points"]
        + breakdown["price_points"]
        + breakdown["risk_points"],
        3,
    )
    return breakdown


def _fmt(value: float) -> str:
    return f"{value:+.1f}"


def build_reasons(out_b: dict, in_b: dict) -> list[str]:
    """Plain-English justification for swapping one player for another."""
    reasons: list[str] = []

    d_form = in_b["form_points"] - out_b["form_points"]
    if abs(d_form) >= 0.5:
        better = "better" if d_form > 0 else "worse"
        reasons.append(
            f"Recent form is {better}: {in_b['form']} vs {out_b['form']} "
            f"({_fmt(d_form)} score)"
        )

    d_fix = in_b["fixture_points"] - out_b["fixture_points"]
    if abs(d_fix) >= 0.3:
        easier = "easier" if d_fix > 0 else "harder"
        reasons.append(
            f"Next 3 fixtures look {easier}: average difficulty "
            f"{in_b['avg_fdr']} vs {out_b['avg_fdr']} ({_fmt(d_fix)} score)"
        )

    d_risk = in_b["risk_points"] - out_b["risk_points"]
    if abs(d_risk) >= 0.5:
        if d_risk > 0:
            reasons.append(
                f"Lower rotation/injury risk ({in_b['minutes']} mins played vs "
                f"{out_b['minutes']}) ({_fmt(d_risk)} score)"
            )
        else:
            reasons.append(
                f"Takes on more rotation/injury risk ({in_b['minutes']} mins played vs "
                f"{out_b['minutes']}) ({_fmt(d_risk)} score)"
            )

    if in_b["cost_change_event"] > 0:
        reasons.append(
            f"Price is rising this gameweek (+£{in_b['cost_change_event'] / 10:.1f}m) — "
            "buying before it goes up"
        )
    if out_b["cost_change_event"] < 0:
        reasons.append(
            f"Outgoing player's price is falling (£{out_b['cost_change_event'] / 10:.1f}m)"
        )

    d_own = in_b["ownership_points"] - out_b["ownership_points"]
    if abs(d_own) >= 0.3:
        if d_own > 0:
            reasons.append(
                f"More widely owned ({in_b['ownership']}% vs {out_b['ownership']}%) — "
                "a safer, template pick"
            )
        else:
            reasons.append(
                f"Lower owned ({in_b['ownership']}% vs {out_b['ownership']}%) — "
                "a differential pick"
            )

    if in_b.get("chance_of_playing") is not None and in_b["chance_of_playing"] < 100:
        reasons.append(
            f"Heads up: incoming player is only {in_b['chance_of_playing']}% likely to play"
        )

    if not reasons:
        reasons.append("Marginal gain — the two players score almost identically.")

    return reasons


def build_scored_players(bootstrap: dict, fixtures: list[dict]) -> list[ScoredPlayer]:
    teams_by_id = {t["id"]: t for t in bootstrap.get("teams", [])}
    scored: list[ScoredPlayer] = []
    for p in bootstrap.get("elements", []):
        player_fixtures = _next_fixtures_for_player(p["id"], teams_by_id, fixtures, p["team"])
        breakdown = score_breakdown(p, player_fixtures)
        team = teams_by_id.get(p["team"], {})
        scored.append(ScoredPlayer(
            id=p["id"],
            web_name=p["web_name"],
            team=p["team"],
            team_short_name=team.get("short_name", ""),
            team_code=team.get("code"),
            element_type=p["element_type"],
            now_cost=p["now_cost"],
            event_points=int(p.get("event_points") or 0),
            form=float(p.get("form") or 0.0),
            selected_by_percent=float(p.get("selected_by_percent") or 0.0),
            cost_change_event=int(p.get("cost_change_event") or 0),
            minutes=int(p.get("minutes") or 0),
            score=breakdown["total"],
            fixtures=player_fixtures,
            breakdown=breakdown,
        ))
    return scored


def recommend_transfers(
    squad_player_ids: list[int],
    bank: int,
    scored_players: list[ScoredPlayer],
    free_transfers: int = 1,
) -> list[TransferRecommendation]:
    """
    For every player in the squad, find the best affordable replacement at the
    same position that isn't already owned. Returns one recommendation per
    squad player, ranked by score gain -- so the UI can offer alternatives
    rather than a single take-it-or-leave-it suggestion.
    """
    by_id = {p.id: p for p in scored_players}
    squad = [by_id[pid] for pid in squad_player_ids if pid in by_id]
    if not squad:
        return []

    recommendations: list[TransferRecommendation] = []

    for out_player in squad:
        budget = out_player.now_cost + bank
        candidates = [
            p for p in scored_players
            if p.element_type == out_player.element_type
            and p.id not in squad_player_ids
            and p.now_cost <= budget
        ]
        if not candidates:
            continue

        best_candidate = max(candidates, key=lambda p: p.score)
        delta = round(best_candidate.score - out_player.score, 3)

        recommendations.append(
            TransferRecommendation(
                player_out=out_player,
                player_in=best_candidate,
                score_delta=delta,
                is_hit=free_transfers <= 0,
                free_transfers=free_transfers,
                reasons=build_reasons(out_player.breakdown, best_candidate.breakdown),
            )
        )

    recommendations.sort(key=lambda r: r.score_delta, reverse=True)
    return recommendations
