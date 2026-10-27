const SEVERITIES = ["high", "medium", "low", "info"];

export function formatDate(value) {
  if (!value) return "Not available";

  const date = new Date(value);

  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString();
}

export function getSeverityClass(severity) {
  return SEVERITIES.includes(String(severity).toLowerCase())
    ? String(severity).toLowerCase()
    : "info";
}

export function countFindings(findings = [], severity) {
  return findings.filter(
    (finding) =>
      getSeverityClass(finding.severity) === severity
  ).length;
}