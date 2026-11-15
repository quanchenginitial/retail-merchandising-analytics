-- Read-only selection for the learner's CSV export; all sixteen cells, no TOTAL.
SELECT reference_timestamp_ms,
       recency_order,
       recency_band,
       frequency_order,
       frequency_band,
       visitor_ids,
       candidate_baskets
FROM rr_bi.rf_segment_summary
ORDER BY reference_timestamp_ms, recency_order, frequency_order;
