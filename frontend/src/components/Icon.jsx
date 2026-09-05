const PATHS = {
  squad: "M16 3.13a4 4 0 0 1 0 7.75M21 21v-2a4 4 0 0 0-3-3.87M7 7a4 4 0 1 0 8 0 4 4 0 0 0-8 0M3 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2",
  pitch: "M3 5h18v14H3zM12 5v14M3 9h3v6H3M18 9h3v6h-3M12 9a3 3 0 0 0 0 6",
  list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  swap: "M7 4v13m0 0-3-3m3 3 3-3M17 20V7m0 0 3 3m-3-3-3 3",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18M12 7v5l3 2",
  link: "M10 13a5 5 0 0 0 7.07 0l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71M14 11a5 5 0 0 0-7.07 0l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71",
  unlink: "M9 17H7A5 5 0 0 1 7 7h2M15 7h2a5 5 0 0 1 4.9 6M8 12h3M3 3l18 18",
  check: "M20 6 9 17l-5-5",
  alert: "M12 9v4M12 17h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0",
  history: "M3 3v5h5M3.05 13A9 9 0 1 0 6 5.3L3 8M12 7v5l4 2",
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16M21 21l-4.35-4.35",
  chevronLeft: "m15 18-6-6 6-6",
  chevronRight: "m9 18 6-6-6-6",
  logout: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
  spark: "M12 3v3m0 12v3M5.6 5.6l2.1 2.1m8.6 8.6 2.1 2.1M3 12h3m12 0h3M5.6 18.4l2.1-2.1m8.6-8.6 2.1-2.1",
  ball: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18M12 7.5 8.4 10l1.4 4.2h4.4L15.6 10z",
};

export default function Icon({ name, size = 16, className = "", strokeWidth = 1.75 }) {
  const d = PATHS[name];
  if (!d) return null;
  return (
    <svg
      className={`icon ${className}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={d} />
    </svg>
  );
}
