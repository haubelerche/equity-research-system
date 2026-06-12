"""Authoritative production fiscal-year scope."""

DEFAULT_FROM_YEAR = 2022
DEFAULT_TO_YEAR = 2025


def required_periods(
    from_year: int = DEFAULT_FROM_YEAR,
    to_year: int = DEFAULT_TO_YEAR,
) -> list[str]:
    return [f"{year}FY" for year in range(from_year, to_year + 1)]
