export function formatRelativeTime(iso: string) {
  const timestamp = new Date(iso).getTime();
  if (!Number.isFinite(timestamp)) return "unknown";

  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
  if (elapsedSeconds < 60) return "just now";

  const units = [
    { label: "year", seconds: 365 * 24 * 60 * 60 },
    { label: "month", seconds: 30 * 24 * 60 * 60 },
    { label: "day", seconds: 24 * 60 * 60 },
    { label: "hour", seconds: 60 * 60 },
    { label: "minute", seconds: 60 },
  ];

  const unit = units.find((candidate) => elapsedSeconds >= candidate.seconds) ?? units[4];
  const value = Math.floor(elapsedSeconds / unit.seconds);
  return `${value} ${unit.label}${value === 1 ? "" : "s"} ago`;
}
