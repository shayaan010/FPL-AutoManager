import { useEffect, useRef, useState } from "react";
import { wsUrl } from "../lib/api";

function formatMinutes(totalMinutes) {
  const days = Math.floor(totalMinutes / (60 * 24));
  const hours = Math.floor((totalMinutes % (60 * 24)) / 60);
  const minutes = totalMinutes % 60;
  return `${days}d ${hours}h ${minutes}m`;
}

export default function DeadlineCountdown() {
  const [minutesLeft, setMinutesLeft] = useState(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    let retryTimeout;

    function connect() {
      const ws = new WebSocket(wsUrl("/ws/deadline"));
      wsRef.current = ws;

      ws.onopen = () => !cancelled && setConnected(true);
      ws.onmessage = (event) => {
        if (cancelled) return;
        try {
          const data = JSON.parse(event.data);
          if (typeof data.minutes_left === "number") setMinutesLeft(data.minutes_left);
        } catch { }
      };
      ws.onclose = () => {
        if (cancelled) return;
        setConnected(false);
        retryTimeout = setTimeout(connect, 3000);
      };
      ws.onerror = () => ws.close();
    }

    connect();
    return () => {
      cancelled = true;
      clearTimeout(retryTimeout);
      wsRef.current?.close();
    };
  }, []);

  const urgent = minutesLeft !== null && minutesLeft < 60;

  return (
    <div className={`countdown-pill ${urgent ? "urgent" : ""}`}>
      <span className={`status-dot ${connected ? "" : "off"}`} />
      {minutesLeft === null ? (
        <span className="muted">{connected ? "Awaiting deadline" : "Connecting..."}</span>
      ) : (
        <>
          Deadline <strong>{formatMinutes(minutesLeft)}</strong>
        </>
      )}
    </div>
  );
}
