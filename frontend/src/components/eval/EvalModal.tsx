import { useEffect, type ReactNode } from "react";

interface Props {
  title: string;
  subtitle?: string;
  children: ReactNode;
  onClose: () => void;
}

export function EvalModal({ title, subtitle, children, onClose }: Props) {
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <div className="eval-modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="eval-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="eval-modal-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <h2 id="eval-modal-title">{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button type="button" onClick={onClose} aria-label="Đóng cửa sổ">Đóng</button>
        </header>
        <div className="eval-modal__content">{children}</div>
      </section>
    </div>
  );
}
