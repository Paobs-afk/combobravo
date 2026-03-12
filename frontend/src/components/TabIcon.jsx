const ICON_PATHS = {
  dashboard: "M3 10.5L12 3l9 7.5V21a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1v-10.5Z",
  menu: "M4 6h16M4 12h16M4 18h10M17 17l2 2 3-4",
  analysis: "M4 19V9m6 10V5m6 14v-8m6 8V11",
  rules: "M6 5h12l-5 6v8l-2-1v-7L6 5Z",
  upload: "M12 16V5m0 0 4 4m-4-4-4 4M5 18v2h14v-2",
  iterations: "M4 12a8 8 0 1 0 2.3-5.7M4 4v5h5",
  about: "M12 17v-5m0-4h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
  sun: "M12 4V2m0 20v-2m8-8h2M2 12h2m13.66 5.66 1.42 1.42M2.92 2.92l1.42 1.42m11.32-1.42-1.42 1.42M4.34 17.66l-1.42 1.42M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z",
  moon: "M20 14.2A8 8 0 1 1 9.8 4 6.8 6.8 0 1 0 20 14.2Z",
};

function TabIcon({ name = "dashboard", size = 18, className = "" }) {
  const path = ICON_PATHS[name] || ICON_PATHS.dashboard;
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={path} />
    </svg>
  );
}

export default TabIcon;
