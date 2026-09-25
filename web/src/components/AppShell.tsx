import type { ReactNode } from "react";

interface Props {
  top: ReactNode;
  sidebar: ReactNode;
  stream: ReactNode;
  conclusion: ReactNode;
  overlay: ReactNode;
  sidebarOpen: boolean;
  onCloseSidebar: () => void;
}

/** Grid: top bar / (sidebar | stream) / conclusion. Sidebar becomes a drawer below 1024px. */
export function AppShell({ top, sidebar, stream, conclusion, overlay, sidebarOpen, onCloseSidebar }: Props) {
  return (
    <div className="shell">
      <div className="shell__top">{top}</div>
      <div className="shell__side">{sidebar}</div>
      {sidebarOpen && <div className="shell__backdrop" onClick={onCloseSidebar} aria-hidden="true" />}
      <main className="shell__main">{stream}</main>
      <div className="shell__bottom">{conclusion}</div>
      {overlay}
    </div>
  );
}
