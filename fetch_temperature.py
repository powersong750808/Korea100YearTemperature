"""KMA ASOS daily observations -> annual mean temperature for eight stations.
No fabricated observations. Gradually backfills history, latest years first.
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

API = 'https://apihub.kma.go.kr/api/typ01/url/kma_sfcdd3.php'
STATIONS = {'서울':108,'부산':159,'제주':184,'인천':112,'목포':165,'대구':143,'강릉':105,'전주':146}
OUT = Path(__file__).with_name('temperature.json')
KST = timezone(timedelta(hours=9))
# API column order documented for daily-period endpoint. Prefer actual header if returned.
COLUMNS = 'TM STN WS_AVG WR_DAY WD_MAX WS_MAX WS_MAX_TM WD_INS WS_INS WS_INS_TM TA_AVG TA_MAX TA_MAX_TM TA_MIN TA_MIN_TM TD_AVG TS_AVG TG_MIN HM_AVG HM_MIN HM_MIN_TM PV_AVG EV_S EV_L FG_DUR PA_AVG PS_AVG PS_MAX PS_MAX_TM PS_MIN PS_MIN_TM CA_TOT SS_DAY SS_DUR SS_CMB SI_DAY SI_60M_MAX SI_60M_MAX_TM RN_DAY RN_D99 RN_DUR RN_60M_MAX RN_60M_MAX_TM RN_10M_MAX RN_10M_MAX_TM RN_POW_MAX RN_POW_MAX_TM SD_NEW SD_NEW_TM SD_MAX SD_MAX_TM TE_05 TE_10 TE_15 TE_30 TE_50'.split()

def fetch_year(year, key):
    params = {'tm1':f'{year}0101','tm2':f'{year}1231','obs':'TA','stn':':'.join(map(str,STATIONS.values())),'help':0,'authKey':key}
    req = urllib.request.Request(API+'?'+urllib.parse.urlencode(params), headers={'User-Agent':'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            raw=response.read()
    except urllib.error.HTTPError as e:
        body=e.read(250).decode('utf-8','replace')
        raise RuntimeError(f'기상청 HTTP {e.code}: {body}') from None
    text=raw.decode('utf-8-sig','replace')
    if text.lstrip().startswith('<') or any(x in text.lower() for x in ['forbidden','unauthorized','invalid auth','error:']):
        raise RuntimeError('기상청 응답 오류: '+text[:250].replace('\n',' '))
    sums=defaultdict(float); counts=defaultdict(int); headers=COLUMNS
    for line in text.splitlines():
        s=line.strip()
        if not s: continue
        if s.startswith('#'):
            candidate=s.lstrip('#').strip().split()
            if 'TM' in candidate and 'STN' in candidate and 'TA_AVG' in candidate:
                headers=candidate
            continue
        parts=s.split()
        if len(parts)<len(headers):
            continue
        row=dict(zip(headers,parts))
        try:
            stn=int(row['STN']); day=row['TM'][:8]; temp=float(row['TA_AVG'])
            if stn not in STATIONS.values() or len(day)!=8 or int(day[:4])!=year or not (-60<temp<60):continue
            date.fromisoformat(day[:4]+'-'+day[4:6]+'-'+day[6:8])
        except (KeyError,ValueError):continue
        sums[stn]+=temp; counts[stn]+=1
    if not counts:
        raise RuntimeError(f'{year}년 유효한 TA_AVG 자료 없음. 응답 앞부분: {text[:180]!r}')
    result={}
    for name,stn in STATIONS.items():
        if counts[stn]>=300:
            result[name]=round(sums[stn]/counts[stn],2)
        else:
            result[name]=None
    print(f'{year}: '+', '.join(f'{name} {counts[stn]}일' for name,stn in STATIONS.items()))
    return result

def main():
    key=os.environ.get('KMA_API_KEY','').strip()
    if not key:raise RuntimeError('GitHub Secret KMA_API_KEY가 비어 있습니다.')
    current=datetime.now(KST).year
    previous=json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {}
    records={str(y):v for y,v in previous.get('records',{}).items() if int(y)<current}
    # First run: 3 recent years. Each later run adds 3 older years; monthly schedule backfills gradually.
    missing=[y for y in range(current-1,1924,-1) if str(y) not in records]
    years=missing[:]
    if not years:
        years=[current-1]  # refresh latest year
    success=0
    for year in years:
        result=fetch_year(year,key)
        if any(v is not None for v in result.values()):
            records[str(year)]=result;success+=1
    if not success:raise RuntimeError('연평균기온을 계산할 만큼 충분한 실제 관측자료가 없습니다.')
    payload={'source':'기상청 API허브 종관기상관측(ASOS) 일자료(기간 조회) TA_AVG의 연도별 산술평균 (300일 이상)','updated_at':datetime.now(KST).isoformat(timespec='seconds'),'stations':STATIONS,'records':dict(sorted(records.items()))}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'저장 완료: {len(records)}개 연도, 이번 실행 {success}개 연도')

if __name__=='__main__':main()
