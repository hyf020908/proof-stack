export const formatDate = (value?: string | null): string => {
  if (!value) return "Not available";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
};

export const formatDuration = (milliseconds?: number | null): string => {
  if (milliseconds === undefined || milliseconds === null) return "—";
  if (milliseconds < 1000) return `${milliseconds} ms`;
  if (milliseconds < 60_000) return `${(milliseconds / 1000).toFixed(1)} s`;
  return `${Math.floor(milliseconds / 60_000)}m ${Math.round((milliseconds % 60_000) / 1000)}s`;
};

export const formatBytes = (bytes?: number | null): string => {
  if (bytes === undefined || bytes === null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
};

export const formatPercent = (value?: number | null): string => {
  if (value === undefined || value === null) return "—";
  const percentage = value <= 1 ? value * 100 : value;
  return `${Math.round(percentage)}%`;
};

export const titleCase = (value: string): string =>
  value
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());

export const getStringList = (
  values?: Array<string | Record<string, unknown>>,
  preferredKeys: string[] = ["name", "path", "qualified_name"],
): string[] =>
  (values ?? []).map((value) => {
    if (typeof value === "string") return value;
    for (const key of preferredKeys) {
      if (typeof value[key] === "string") return String(value[key]);
    }
    return "Linked evidence";
  });
