
SET threads=2;
SET memory_limit='512MB';
SET temp_directory='./tmp/retailrocket_source_check_spill';
SET TimeZone='UTC';
CREATE TEMP TABLE events_raw AS
SELECT * FROM read_csv('D:/database/retailrocket/events.csv',
 header=true, columns={'timestamp':'VARCHAR','visitorid':'VARCHAR','event':'VARCHAR',
                       'itemid':'VARCHAR','transactionid':'VARCHAR'},
 delim=',', quote='"', escape='"', nullstr='', strict_mode=true, ignore_errors=false);
CREATE TEMP TABLE category_raw AS
SELECT * FROM read_csv('D:/database/retailrocket/category_tree.csv',
 header=true, columns={'categoryid':'VARCHAR','parentid':'VARCHAR'},
 delim=',', quote='"', escape='"', nullstr='', strict_mode=true, ignore_errors=false);
CREATE TEMP TABLE duplicate_events AS
SELECT timestamp,visitorid,event,itemid,transactionid,count(*) AS n
FROM events_raw GROUP BY ALL HAVING count(*)>1;
CREATE TEMP TABLE transaction_groups AS
SELECT transactionid,count(*) AS event_rows,
 count(DISTINCT visitorid) AS visitors,count(DISTINCT itemid) AS items,
 count(DISTINCT timestamp) AS timestamps,count(DISTINCT event) AS event_types
FROM events_raw WHERE transactionid IS NOT NULL AND trim(transactionid)<>''
GROUP BY transactionid;
CREATE TEMP TABLE category_ids AS
SELECT categoryid,count(*) AS n FROM category_raw GROUP BY categoryid;
SELECT json_object(
 'events', (SELECT json_object(
   'rows',count(*),'distinct_visitor_ids',count(DISTINCT visitorid),
   'distinct_item_ids',count(DISTINCT itemid),'distinct_event_types',count(DISTINCT event),
   'timestamp_blank_rows',count(*) FILTER(WHERE timestamp IS NULL OR trim(timestamp)=''),
   'visitorid_blank_rows',count(*) FILTER(WHERE visitorid IS NULL OR trim(visitorid)=''),
   'event_blank_rows',count(*) FILTER(WHERE event IS NULL OR trim(event)=''),
   'itemid_blank_rows',count(*) FILTER(WHERE itemid IS NULL OR trim(itemid)=''),
   'transactionid_blank_rows',count(*) FILTER(WHERE transactionid IS NULL OR trim(transactionid)=''),
   'timestamp_nonblank_invalid_integer_rows',count(*) FILTER(WHERE timestamp IS NOT NULL AND trim(timestamp)<>'' AND (NOT regexp_full_match(timestamp,'[0-9]+') OR try_cast(timestamp AS BIGINT) IS NULL)),
   'visitorid_nonblank_invalid_integer_rows',count(*) FILTER(WHERE visitorid IS NOT NULL AND trim(visitorid)<>'' AND (NOT regexp_full_match(visitorid,'[0-9]+') OR try_cast(visitorid AS BIGINT) IS NULL)),
   'itemid_nonblank_invalid_integer_rows',count(*) FILTER(WHERE itemid IS NOT NULL AND trim(itemid)<>'' AND (NOT regexp_full_match(itemid,'[0-9]+') OR try_cast(itemid AS BIGINT) IS NULL)),
   'transactionid_nonblank_invalid_integer_rows',count(*) FILTER(WHERE transactionid IS NOT NULL AND trim(transactionid)<>'' AND (NOT regexp_full_match(transactionid,'[0-9]+') OR try_cast(transactionid AS BIGINT) IS NULL)),
   'min_timestamp_ms',min(try_cast(timestamp AS BIGINT)),
   'max_timestamp_ms',max(try_cast(timestamp AS BIGINT)),
   'min_timestamp_utc',CAST(epoch_ms(min(try_cast(timestamp AS BIGINT))) AS VARCHAR),
   'max_timestamp_utc',CAST(epoch_ms(max(try_cast(timestamp AS BIGINT))) AS VARCHAR),
   'distinct_utc_dates',count(DISTINCT CAST(epoch_ms(try_cast(timestamp AS BIGINT)) AS DATE)),
   'unexpected_event_type_rows',count(*) FILTER(WHERE event NOT IN ('view','addtocart','transaction')),
   'transaction_event_missing_transactionid_rows',count(*) FILTER(WHERE event='transaction' AND (transactionid IS NULL OR trim(transactionid)='')),
   'nontransaction_event_with_transactionid_rows',count(*) FILTER(WHERE event<>'transaction' AND transactionid IS NOT NULL AND trim(transactionid)<>''),
   'transaction_id_present_rows',count(*) FILTER(WHERE transactionid IS NOT NULL AND trim(transactionid)<>''),
   'distinct_nonblank_transaction_ids',count(DISTINCT transactionid) FILTER(WHERE trim(transactionid)<>''))
 FROM events_raw),
 'event_type_counts', (SELECT to_json(list(row_value ORDER BY event)) FROM (
   SELECT event,json_object('event_type',event,'rows',count(*),
     'transaction_id_present_rows',count(*) FILTER(WHERE transactionid IS NOT NULL AND trim(transactionid)<>''),
     'distinct_transaction_ids',count(DISTINCT transactionid),
     'distinct_visitor_ids',count(DISTINCT visitorid),'distinct_item_ids',count(DISTINCT itemid)) AS row_value
   FROM events_raw GROUP BY event)),
 'exact_event_duplicates', (SELECT json_object('group_count',count(*),
   'rows_in_duplicate_groups',coalesce(sum(n),0),'surplus_rows',coalesce(sum(n-1),0),
   'largest_multiplicity',coalesce(max(n),0)) FROM duplicate_events),
 'exact_duplicate_counts_by_event', (SELECT to_json(list(row_value ORDER BY event)) FROM (
   SELECT event,json_object('event_type',event,'group_count',count(*),
     'rows_in_duplicate_groups',sum(n),'surplus_rows',sum(n-1)) AS row_value
   FROM duplicate_events GROUP BY event)),
 'transaction_id_groups', (SELECT json_object('distinct_nonblank_transaction_ids',count(*),
   'ids_with_multiple_event_rows',count(*) FILTER(WHERE event_rows>1),
   'ids_with_multiple_visitors',count(*) FILTER(WHERE visitors>1),
   'ids_with_multiple_items',count(*) FILTER(WHERE items>1),
   'ids_with_multiple_timestamps',count(*) FILTER(WHERE timestamps>1),
   'ids_with_multiple_event_types',count(*) FILTER(WHERE event_types>1),
   'max_event_rows_per_id',max(event_rows)) FROM transaction_groups),
 'categories', (SELECT json_object('rows',count(*),
   'distinct_category_ids',count(DISTINCT categoryid),
   'categoryid_blank_rows',count(*) FILTER(WHERE categoryid IS NULL OR trim(categoryid)=''),
   'parentid_blank_root_rows',count(*) FILTER(WHERE parentid IS NULL OR trim(parentid)=''),
   'categoryid_nonblank_invalid_integer_rows',count(*) FILTER(WHERE categoryid IS NOT NULL AND trim(categoryid)<>'' AND (NOT regexp_full_match(categoryid,'[0-9]+') OR try_cast(categoryid AS BIGINT) IS NULL)),
   'parentid_nonblank_invalid_integer_rows',count(*) FILTER(WHERE parentid IS NOT NULL AND trim(parentid)<>'' AND (NOT regexp_full_match(parentid,'[0-9]+') OR try_cast(parentid AS BIGINT) IS NULL)),
   'self_parent_rows',count(*) FILTER(WHERE categoryid=parentid)) FROM category_raw),
 'category_duplicate_ids', (SELECT json_object('group_count',count(*) FILTER(WHERE n>1),
   'surplus_rows',coalesce(sum(n-1) FILTER(WHERE n>1),0)) FROM category_ids),
 'category_parent_orphans', (SELECT json_object('row_count',count(*),
   'distinct_parent_ids',count(DISTINCT c.parentid)) FROM category_raw c
   LEFT JOIN category_ids p ON c.parentid=p.categoryid
   WHERE c.parentid IS NOT NULL AND trim(c.parentid)<>'' AND p.categoryid IS NULL)
) AS aggregate_audit;
