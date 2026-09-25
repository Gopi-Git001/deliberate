import { ArrowDown } from "lucide-react";

export function JumpToLatestButton({ unseen, onClick }: { unseen: number; onClick: () => void }) {
  return (
    <button className="jump-latest" onClick={onClick}>
      <ArrowDown size={14} aria-hidden="true" />
      Jump to latest{unseen > 0 && <span className="jump-latest__count">{unseen > 99 ? "99+" : unseen}</span>}
    </button>
  );
}
