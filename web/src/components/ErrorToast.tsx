import { CircleAlert, X } from "lucide-react";
import { useEffect } from "react";
import type { Toast } from "../lib/runReducer";

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: (id: number) => void }) {
  useEffect(() => {
    const id = setTimeout(() => onDismiss(toast.id), 8000);
    return () => clearTimeout(id);
  }, [toast.id, onDismiss]);
  return (
    <div className="toast" role="alert">
      <CircleAlert size={16} aria-hidden="true" />
      <p>{toast.message}</p>
      <button className="icon-btn" onClick={() => onDismiss(toast.id)} aria-label="Dismiss">
        <X size={14} />
      </button>
    </div>
  );
}

export function ErrorToast({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: number) => void }) {
  return (
    <div className="toasts" aria-live="assertive">
      {toasts.map((t) => <ToastItem key={t.id} toast={t} onDismiss={onDismiss} />)}
    </div>
  );
}
