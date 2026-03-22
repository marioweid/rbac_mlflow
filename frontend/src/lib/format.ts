export function formatTimestamp(epochMs: number | null): string {
  if (epochMs === null) return "\u2014";
  return new Date(epochMs).toLocaleString();
}

export function formatDuration(
  startMs: number | null,
  endMs: number | null,
): string {
  if (startMs === null || endMs === null) return "\u2014";
  const seconds = Math.round((endMs - startMs) / 1000);
  if (seconds < 60) return `${String(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  return `${String(minutes)}m ${String(remaining)}s`;
}

export function statusColor(status: string | null): string {
  switch (status) {
    case "FINISHED":
      return "text-green-600";
    case "RUNNING":
      return "text-yellow-600";
    case "FAILED":
      return "text-red-600";
    default:
      return "text-gray-400";
  }
}
