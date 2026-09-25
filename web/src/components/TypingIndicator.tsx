import { agentLabel } from "../lib/colors";
import { Avatar } from "./Avatar";

export function TypingIndicator({ agentIds }: { agentIds: string[] }) {
  if (!agentIds.length) return null;
  const names = agentIds.map(agentLabel);
  const text =
    names.length === 1
      ? `${names[0]} is thinking`
      : names.length <= 3
        ? `${names.slice(0, -1).join(", ")} and ${names.at(-1)} are thinking`
        : `${names.slice(0, 2).join(", ")} and ${names.length - 2} others are thinking`;
  return (
    <div className="typing" role="status" aria-live="polite">
      <span className="typing__avatars">
        {agentIds.slice(0, 4).map((id) => (
          <Avatar key={id} agentId={id} size="sm" />
        ))}
      </span>
      <span className="typing__text">{text}</span>
      <span className="typing__dots" aria-hidden="true"><i /><i /><i /></span>
    </div>
  );
}
