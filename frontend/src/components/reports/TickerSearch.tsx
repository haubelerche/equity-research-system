import type { UniverseTicker } from "../../data/universe";

interface Props {
  value: string;
  onChange: (query: string) => void;
  options: UniverseTicker[];
}

/**
 * Dropdown to pick one of the 53 tickers (or "all"). Selecting a ticker filters
 * the list below to that code; the empty value shows the whole universe.
 */
export function TickerSearch({ value, onChange, options }: Props) {
  return (
    <div className="ticker-search" role="search">
      <label htmlFor="ticker-select">Ch?n m� c? phi?u</label>
      <select
        id="ticker-select"
        aria-label="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">T?t c? {options.length} m�</option>
        {options.map((o) => (
          <option key={o.ticker} value={o.ticker}>
            {`${o.ticker} � ${o.company_name}`}
          </option>
        ))}
      </select>
      {value && (
        <button type="button" className="ticker-search__clear" onClick={() => onChange("")}>
          B? l?c
        </button>
      )}
    </div>
  );
}
