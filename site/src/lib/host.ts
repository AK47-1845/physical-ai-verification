// Display helper: cloud hosts contain machine segments (e.g. Modal's
// double-hyphen workspace prefix). Show the registered domain; the full
// host stays available via the title tooltip.
export function shortHost(host: string): string {
  if (host.includes('--')) return host.split('.').slice(-2).join('.');
  return host;
}
