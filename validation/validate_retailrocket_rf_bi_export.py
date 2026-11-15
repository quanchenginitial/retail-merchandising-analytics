"""Read-only validation of a learner-supplied RF summary CSV; no database access."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sys

FIELDS=['reference_timestamp_ms','recency_order','recency_band','frequency_order','frequency_band','visitor_ids','candidate_baskets']
INTEGER_POSITIONS=(0,1,3,5,6)
REFERENCE_MS=1442545187788
MAX_BYTES=1024*1024
PREFLIGHT='data/retailrocket_rf_bi_summary_preflight.json'
ACCEPTANCE='data/retailrocket_rf_bi_summary_learner_acceptance.json'
PREFLIGHT_SHA='25f93a5e4d96a89a5b3686680cfacb33c3626d1321247f3c53cc8739587fb573'
ACCEPTANCE_SHA='a12cea17f13ff407edf138eadfc4a83e938ef166ec9e287fe40ea41d59439a46'


def require(condition,message):
    if not condition:raise ValueError(message)


def semantic_hash(rows):
    return hashlib.sha256(''.join(json.dumps(row,separators=(',',':'))+'\n' for row in rows).encode('utf-8')).hexdigest()


def expected_rows(root):
    payload=(root/PREFLIGHT).read_bytes();acceptance_payload=(root/ACCEPTANCE).read_bytes()
    require(hashlib.sha256(payload).hexdigest()==PREFLIGHT_SHA,'Accepted SQL89 preflight fingerprint differs.')
    require(hashlib.sha256(acceptance_payload).hexdigest()==ACCEPTANCE_SHA,'SQL89 learner acceptance fingerprint differs.')
    proof=json.loads(payload);acceptance=json.loads(acceptance_payload)
    require(acceptance['acceptance_status']=='accepted' and acceptance['assistant_preflight_sha256']==PREFLIGHT_SHA,
        'SQL89 learner acceptance does not match the expected evidence.')
    require(acceptance['report_sha256']==proof['report_sha256'] and proof['checks_passed']==20 and proof['independent_target_all_matched'],
        'SQL89 proof is not the accepted complete table proof.')
    require(proof['target_column_names']==FIELDS and proof['target_column_types']==['BIGINT','BIGINT','VARCHAR','BIGINT','VARCHAR','BIGINT','BIGINT'],
        'Accepted SQL89 column contract differs.')
    rows=[tuple(row[name] for name in FIELDS) for row in proof['aggregate_target_rows']]
    require(len(rows)==16 and semantic_hash(rows)==proof['independent_target_sha256'],'Accepted aggregate table fingerprint differs.')
    return rows


def validate_bytes(payload,expected):
    require(0<len(payload)<=MAX_BYTES,'CSV must be nonempty and no larger than 1 MiB.')
    bom=payload.startswith(b'\xef\xbb\xbf')
    text=payload.decode('utf-8-sig')
    parsed=list(csv.reader(io.StringIO(text,newline=''),delimiter=',',strict=True))
    require(bool(parsed) and parsed[0]==FIELDS,'CSV header must contain exactly the seven SQL90 columns in order.')
    require(len(parsed)==17,'CSV must contain one header and exactly sixteen data rows, without blank or TOTAL rows.')
    rows=[]
    for index,fields in enumerate(parsed[1:],1):
        require(len(fields)==7,f'Data row {index} must contain exactly seven fields.')
        row=[]
        for position,value in enumerate(fields):
            if position in INTEGER_POSITIONS:
                require(re.fullmatch(r'0|[1-9][0-9]*',value) is not None,
                    f'Data row {index}, column {position+1} must be a plain nonnegative integer without separators or decimal notation.')
                row.append(int(value))
            else:row.append(value)
        rows.append(tuple(row))
    require(rows==expected,'CSV values, labels or row order differ from the accepted sixteen-cell table.')
    require(all(row[0]==REFERENCE_MS for row in rows),'Reference timestamp differs.')
    require(len({(row[0],row[1],row[3]) for row in rows})==16,'RF keys are not unique.')
    require(sum(row[5] for row in rows)==11719 and sum(row[6] for row in rows)==17672,'Additive totals differ.')
    return dict(status='PASS',rows=16,columns=7,utf8_bom=bom,size_bytes=len(payload),
        file_sha256=hashlib.sha256(payload).hexdigest(),semantic_sha256=semantic_hash(rows),
        semantic_hash_contract='Compact JSON arrays of typed seven-field rows in file order, each followed by LF; header excluded.',
        reference_timestamp_ms=REFERENCE_MS,visitor_ids=11719,candidate_baskets=17672,
        exact_header_values_labels_and_order=True,plain_integer_fields=True,learner_database_opened=False,csv_modified=False)


def validate_file(path,expected):
    require(path.is_file(),'CSV path must refer to an existing file.')
    before=path.stat()
    with path.open('rb') as stream:payload=stream.read(MAX_BYTES+1)
    result=validate_bytes(payload,expected);after=path.stat()
    require((before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns),'CSV changed while it was being checked.')
    result['csv_basename']=path.name
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv',required=True,help='Path to the CSV actually exported by the learner.')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    try:result=validate_file(Path(args.csv),expected_rows(root))
    except (ValueError,OSError,UnicodeError,csv.Error,KeyError,TypeError) as error:
        print(json.dumps({'status':'FAIL','message':str(error)},ensure_ascii=False));return 2
    print(json.dumps(result,indent=2,ensure_ascii=False));return 0


if __name__=='__main__':sys.exit(main())
