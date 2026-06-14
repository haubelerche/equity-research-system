import type { Maturity } from "../../lib/evalStatus";

const OPTIONS: Maturity[] = ["P0", "P1", "P2"];

export function MaturityToggle({ value, onChange }: { value: Maturity; onChange: (m: Maturity) => void }) {
  return (
    <div role="group" aria-label="maturity">
      {OPTIONS.map((m) => (
        <button key={m} aria-pressed={value === m} onClick={() => onChange(m)}>{m}</button>
      ))}
    </div>
  );
}
