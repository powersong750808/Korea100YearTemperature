import json, os, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

API = 'https://apihub.kma.go.kr/api/typ02/openApi/SfcYearlyInfoService/getYearSumry'
STATIONS = {'서울':108,'부산':159,'제주':184,'인천':112,'목포':165,'대구':143,'강릉':105,'전주':146}
OUT = Path(__file__).with_name('temperature.json')

def get_year(year, key):
    found = {}
    page = 1
    while True:
        params = {'pageNo':page,'numOfRows':300,'dataType':'XML','year':year,'authKey':key}
        req = urllib.request.Request(API+'?'+urllib.parse.urlencode(params),headers={'User-Agent':'CentennialTemperatureDashboard/1.0'})
        with urllib.request.urlopen(req,timeout=35) as response:
            raw = response.read()
        root = ET.fromstring(raw)
        code = root.findtext('.//resultCode')
        if code and code not in ('00','0'):
            raise RuntimeError(f'KMA API 오류: {year}년, code={code}, message={root.findtext(".//resultMsg")}')
        items = root.findall('.//item')
        for item in items:
            fields = {el.tag.lower(): (el.text or '').strip() for el in item}
            try:
                station = int(fields.get('stn_id',''))
                raw_temp = fields.get('va_lst_03','')
                if station in STATIONS.values() and raw_temp not in ('','-','-999','-9999'):
                    # KMA annual yearbook API specifies 0.1°C units.
                    temp = float(raw_temp) / 10
                    if -40 < temp < 50:
                        found[station] = round(temp,2)
            except (ValueError,TypeError):
                continue
        total = int(root.findtext('.//totalCount') or len(items))
        if page * 300 >= total or not items:
            break
        page += 1
    return found

def main():
    key = os.environ.get('KMA_API_KEY','').strip()
    if not key:
        raise RuntimeError('KMA_API_KEY가 설정되지 않았습니다. 기상청 API허브 인증키가 필요합니다.')
    previous = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {}
    records = {int(y):data for y,data in previous.get('records',{}).items() if int(y) < datetime.now(timezone(timedelta(hours=9))).year}
    this_year = datetime.now(timezone(timedelta(hours=9))).year
    years = list(range(1912,this_year)) if not records else list(range(max(1912,this_year-3),this_year))
    success = 0
    for year in years:
        try:
            observations = get_year(year,key)
            if observations:
                records[year] = {name: observations.get(stn) for name,stn in STATIONS.items()}
                success += 1
            print(f'{year}: {len(observations)}개 관측소')
        except Exception as exc:
            print(f'{year}: 조회 실패 ({type(exc).__name__}: {exc})')
            if not records and success == 0:
                raise
    if not records:
        raise RuntimeError('실제 연평균기온 자료를 수집하지 못했습니다. 가상 데이터를 생성하지 않습니다.')
    payload = {'source':'기상청 API허브 지상기상연보 연요약자료조회','updated_at':datetime.now(timezone(timedelta(hours=9))).isoformat(timespec='seconds'),'stations':STATIONS,'records':{str(y):records[y] for y in sorted(records)}}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'저장 완료: {len(records)}개 연도, 이번 실행 조회 성공 {success}개 연도')

if __name__=='__main__': main()
