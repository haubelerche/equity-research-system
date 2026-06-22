import { useGeneration } from "../../generation/GenerationContext";

const DEFAULT_GENERATE_LABEL = "Sinh báo cáo";

interface Props {
  ticker: string;
  onComplete: () => void;
  label?: string;
  forceFull?: boolean;
}

/**
 * Thin trigger: generation state, polling, the progress modal and the
 * completion toast all live in GenerationProvider, so the run keeps going even
 * if this button unmounts or the modal is hidden.
 */
export function GenerateButton({ ticker, onComplete, label = DEFAULT_GENERATE_LABEL, forceFull = false }: Props) {
  const gen = useGeneration();
  const run = gen.runs[ticker];

  if (run?.phase === "running") {
    return (
      <button
        type="button"
        className="run-state run-state--running"
        onClick={() => gen.openModal(ticker)}
      >
        Đang chạy...
      </button>
    );
  }

  return (
    <button type="button" className="btn-generate" onClick={() => gen.start(ticker, label, onComplete, { forceFull })}>
      {label}
    </button>
  );
}
