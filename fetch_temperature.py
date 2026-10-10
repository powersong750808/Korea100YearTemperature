"""Backfill actual KMA ASOS daily mean temperatures into annual means.

One run processes a bounded batch, preserving completed years and retrying
transient errors. GitHub Actions schedules subsequent batches automatically.
"""
import json
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

API = 'https://apihub.kma.go.kr/api/typ01/url/kma_sfcdd3.php'
STATIONS = {'서울': 108, '부산': 159, '제주': 184, '인천': 112,
            '목포': 165, '대구': 143, '강릉': 105, '전주': 146}
OUT = Path(__file__).with_name('temperature.json')
KST = timezone(timedelta(hours=9))
START_YEAR = 1925
END_YEAR = 2025  # fixed requested historical window
YEARS_PER_RUN = 10
MAX_RETRIES = 3
MIN_DAYS = 300

COLUMNS = ('TM STN WS_AVG WR_DAY WD_MAX WS_MAX WS_MAX_TM WD_INS WS_INS WS_INS_TM '
           'TA_AVG TA_MAX TA_MAX_TM TA_MIN TA_MIN_TM TD_AVG TS_AVG TG_MIN HM_AVG '
           'HM_MIN HM_MIN_TM PV_AVG EV_S EV_L FG_DUR PA_AVG PS_AVG PS_MAX '
           'PS_MAX_TM PS_MIN PS_MIN_TM CA_TOT SS_DAY SS_DUR SS_CMB SI_DAY '
           'SI_60M_MAX SI_60M_MAX_TM RN_DAY RN_D99 RN_DUR RN_60M_MAX '
           'RN_60M_MAX_TM RN_10M_MAX RN_10M_MAX_TM RN_POW_MAX RN_POW_MAX_TM '
           'SD_NEW SD_NEW_TM SD_MAX SD_MAX_TM TE_05 TE_10 TE_15 TE_30 TE_50').split()


def get_text(year, key):
    params = {'tm1': f'{year}0101', 'tm2': f'{year}1231', 'obs': 'TA',
              'stn': ':'.join(map(str, STATIONS.values())),
              'help': 0, 'authKey': key}
    url = API + '?' + urllib.parse.urlencode(params)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(request, timeout=90) as response:
                text = response.read().decode('utf-8-sig', 'replace')
            if text.lstrip().startswith('<') or any(x in text.lower() for x in
                    ('forbidden', 'unauthorized', 'invalid auth', 'error:')):
                raise ValueError('Unexpected API response: ' + text[:160])
            return text
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise RuntimeError(f'API authorization error HTTP {exc.code}') from exc
            if exc.code not in (429, 500, 502, 503, 504):
                raise RuntimeError(f'API HTTP {exc.code}') from exc
            print(f'{year}: HTTP {exc.code}, attempt {attempt}/{MAX_RETRIES}', flush=True)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            print(f'{year}: network error {exc}, attempt {attempt}/{MAX_RETRIES}', flush=True)
        if attempt < MAX_RETRIES:
            time.sleep(5 * attempt)
    raise RuntimeError(f'{year}: failed after {MAX_RETRIES} attempts')


def fetch_year(year, key):
    text = get_text(year, key)
    sums, counts = defaultdict(float), defaultdict(int)
    headers = COLUMNS
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('#'):
            candidate = line.lstrip('#').strip().split()
            if {'TM', 'STN', 'TA_AVG'}.issubset(candidate):
                headers = candidate
            continue
        parts = line.split()
        if len(parts) < len(headers):
            continue
        row = dict(zip(headers, parts))
        try:
            stn = int(row['STN'])
            day = row['TM'][:8]
            temp = float(row['TA_AVG'])
            if stn not in STATIONS.values() or len(day) != 8 or int(day[:4]) != year:
                continue
            date.fromisoformat(f'{day[:4]}-{day[4:6]}-{day[6:8]}')
            if not -60 < temp < 60:
                continue
        except (ValueError, KeyError):
            continue
        sums[stn] += temp
        counts[stn] += 1
    if not counts:
        raise RuntimeError(f'{year}: no valid daily temperatures; response: {text[:100]!r}')
    values = {name: round(sums[stn] / counts[stn], 2) if counts[stn] >= MIN_DAYS else None
              for name, stn in STATIONS.items()}
    print(f'{year}: ' + ', '.join(f'{name}={counts[stn]} days' for name, stn in STATIONS.items()), flush=True)
    return values


def save(records):
    payload = {'source': '기상청 API허브 종관기상관측(ASOS) 일자료 TA_AVG 연도별 산술평균 (300일 이상)',
               'updated_at': datetime.now(KST).isoformat(timespec='seconds'),
               'stations': STATIONS, 'records': dict(sorted(records.items()))}
    tmp = OUT.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(OUT)


def main():
    key = os.environ.get('KMA_API_KEY', '').strip()
    if not key:
        raise RuntimeError('GitHub Secret KMA_API_KEY is missing')
    existing = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {}
    records = {str(y): v for y, v in existing.get('records', {}).items()
               if str(y).isdigit() and START_YEAR <= int(y) <= END_YEAR}
    missing = [year for year in range(END_YEAR, START_YEAR - 1, -1)
               if str(year) not in records]
    if not missing:
        print(f'Complete: {len(records)} years stored (not all stations necessarily available).')
        return
    # Process the next missing years; one run is short enough for hosted runners.
    batch = missing[:YEARS_PER_RUN]
    print(f'Backfill batch: {batch}; existing years: {len(records)}', flush=True)
    failed = []
    for year in batch:
        try:
            result = fetch_year(year, key)
            if not any(value is not None for value in result.values()):
                raise RuntimeError('Fewer than 300 valid days at every station')
            records[str(year)] = result
            save(records)
            print(f'SAVED {year}; total years={len(records)}', flush=True)
        except Exception as exc:
            failed.append(year)
            print(f'SKIPPED {year}: {exc}', flush=True)
        time.sleep(2)
    print(f'FINISHED: stored={len(records)} years, failed this batch={failed}', flush=True)
    if failed:
        print('Missing years will be retried in subsequent runs.', flush=True)


if __name__ == '__main__':
    main()

