#!/usr/bin/env bash
cd "c:/Users/Admin/Desktop/multi-agent-equity-research"
SUMMARY=output/ingest16_summary.log
: > "$SUMMARY"
TICKERS="AMP BCP BIO CDP CNC DAN DBM DDN DHD DHN DP2 DPH DTG HDP MTP NDC"
i=0
for T in $TICKERS; do
  i=$((i+1))
  echo "===== [$i/16] $T $(date +%H:%M:%S) =====" | tee -a "$SUMMARY"
  out=$(PYTHONUTF8=1 PYTHONIOENCODING=utf-8 timeout 300 python scripts/ingest_ticker.py --ticker "$T" --years 4 --skip-catalysts --from-year 2022 --to-year 2025 2>&1)
  fin=$(echo "$out" | grep -iE "\] $T financials:" | head -1)
  pri=$(echo "$out" | grep -iE "\] $T price:" | head -1)
  com=$(echo "$out" | grep -iE "\] $T company:" | head -1)
  rate=$(echo "$out" | grep -ciE "rate limit|Process terminated")
  echo "  FIN: $fin" | tee -a "$SUMMARY"
  echo "  PRICE: $pri" | tee -a "$SUMMARY"
  echo "  COMPANY: $com" | tee -a "$SUMMARY"
  [ "$rate" -gt 0 ] && echo "  !! RATE-LIMIT/KILL detected" | tee -a "$SUMMARY"
  if [ "$i" -lt 16 ]; then sleep 45; fi
done
echo "===== BATCH DONE $(date +%H:%M:%S) =====" | tee -a "$SUMMARY"
