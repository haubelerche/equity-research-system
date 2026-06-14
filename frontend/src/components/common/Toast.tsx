import type { Toast } from "../../generation/types";

interface Props {
  toasts: Toast[];
  onDismiss: (id: number) => void;
}

export function ToastContainer({ toasts, onDismiss }: Props) {
  if (toasts.length === 0) return null;
  return (
    <div className="toast-container" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast toast--${t.kind}`} role="status">
          <span className="toast__msg">{t.message}</span>
          <button type="button" className="toast__close" onClick={() => onDismiss(t.id)} aria-label="Đóng thông báo">
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
