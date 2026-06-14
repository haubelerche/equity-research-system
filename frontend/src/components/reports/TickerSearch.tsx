import type { UniverseTicker } from "../../data/universe";

interface Props {
  value: string;
  onChange: (query: string) => void;
  options: UniverseTicker[];
}

/**
 * Type-ahead combobox over the full 53-ticker universe (native <datalist>):
 * users can type to filter or open the dropdown to pick a ticker. Selecting an
 * option fills the input with the ticker code, which filters the list below.
 */
export function TickerSearch({ value, onChange, options }: Props) {
  return (
    <div className="ticker-search" role="search">
      <input
        aria-label="search"
        list="ticker-options"
        placeholder="Tìm hoặc chọn mã cổ phiếu…"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <datalist id="ticker-options">
        {options.map((o) => (
          <option key={o.ticker} value={o.ticker}>
            {`${o.ticker} — ${o.company_name}`}
          </option>
        ))}
      </datalist>
      {value && (
        <button type="button" className="ticker-search__clear" onClick={() => onChange("")}>
          Xóa lọc
        </button>
      )}
    </div>
  );
}
