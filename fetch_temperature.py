"""기존 연평균 자료를 보존하며 연최고기온을 점진적으로 수집합니다."""
import json, os, urllib.parse, urllib.request, urllib.error
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://apihub.kma.go.kr/api/typ01/url/kma_sfcdd3.php"
STATIONS = {"서울":108,"부산":159,"제주":184,"인천":112,"목포":165,"대구":143,"강릉":105,"전주":146}
OUT = Path(__file__).with_name("temperature.json")
KST = timezone(timedelta(hours=9))
COLUMNS = """TM STN WS_AVG WR_DAY WD_MAX WS_MAX WS_MAX_TM WD_INS WS_INS WS_INS_TM
TA_AVG TA_MAX TA_MAX_TM TA_MIN TA_MIN_TM TD_AVG TS_AVG TG_MIN HM_AVG HM_MIN HM_MIN_TM
PV_AVG EV_S EV_L FG_DUR PA_AVG PS_AVG PS_MAX PS_MAX_TM PS_MIN PS_MIN_TM CA_TOT
SS_DAY SS_DUR SS_CMB SI_DAY SI_60M_MAX SI_60M_MAX_TM RN_DAY RN_D99 RN_DUR
RN_60M_MAX RN_60M_MAX_TM RN_10M_MAX RN_10M_MAX_TM RN_POW_MAX RN_POW_MAX_TM
SD_NEW SD_NEW_TM SD_MAX SD_MAX_TM TE_05 TE_10 TE_15 TE_30 TE_50""".split()

def fetch_year(year, key):
    params = {"tm1":f"{year}0101","tm2":f"{year}1231","obs":"TA",
              "stn":":".join(map(str,STATIONS.values())),"help":0,"authKey":key}
    url = API + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=90) as r:
        content = r.read().decode("utf-8-sig","replace")
    if content.lstrip().startswith("<") or "unauthorized" in content.lower():
        raise RuntimeError("기상청 응답 오류: "+content[:160])
    sums=defaultdict(float); avg_count=defaultdict(int)
    maxima={}; max_count=defaultdict(int)
    headers=COLUMNS
    for line in content.splitlines():
        s=line.strip()
        if not s: continue
        if s.startswith("#"):
            candidate=s.lstrip("#").strip().split()
            if all(c in candidate for c in ("TM","STN","TA_AVG","TA_MAX")):
                headers=candidate
            continue
        parts=s.split()
        if len(parts)<len(headers): continue
        row=dict(zip(headers,parts))
        try:
            stn=int(row["STN"])
            if stn not in STATIONS.values() or int(row["TM"][:4])!=year: continue
        except (KeyError,ValueError): continue
        try:
            avg=float(row["TA_AVG"])
            if -60<avg<60:
                sums[stn]+=avg; avg_count[stn]+=1
        except (ValueError,KeyError): pass
        try:
            high=float(row["TA_MAX"])
            if -60<high<60:
                maxima[stn]=max(maxima.get(stn,-100),high)
                max_count[stn]+=1
        except (ValueError,KeyError): pass
    avg_result={}; high_result={}
    for name,stn in STATIONS.items():
        avg_result[name]=round(sums[stn]/avg_count[stn],2) if avg_count[stn]>=300 else None
        high_result[name]=round(maxima[stn],2) if max_count[stn]>=300 else None
    print(f"{year}: 연평균 유효일수 {sum(avg_count.values())}, 최고기온 유효일수 {sum(max_count.values())}")
    return avg_result,high_result

def main():
    key=os.environ.get("KMA_API_KEY","").strip()
    if not key: raise RuntimeError("GitHub Secret KMA_API_KEY가 필요합니다.")
    if not OUT.exists(): raise RuntimeError("기존 temperature.json이 없습니다. 기존 파일을 유지해 주세요.")
    payload=json.loads(OUT.read_text(encoding="utf-8"))
    records=payload.get("records",{})
    max_records=payload.get("max_records",{})
    current=datetime.now(KST).year
    # 이미 저장된 연평균기온을 우선 보존합니다.
    # 최고기온이 없는 기존 연도부터 매 실행 최대 8개 연도씩 추가합니다.
    pending=sorted((int(y) for y in records if int(y)<current and y not in max_records),reverse=True)
    if not pending:
        print("기존 연도 최고기온 수집 완료. 최신 연도를 재검증합니다.")
        pending=[current-1]
    failures=[]
    for year in pending[:8]:
        try:
            avg,high=fetch_year(year,key)
            # 기존 연평균기온은 절대 덮어쓰지 않습니다.
            max_records[str(year)]=high
        except Exception as exc:
            failures.append(f"{year}: {exc}")
            print("수집 실패:",failures[-1])
    if not max_records:
        raise RuntimeError("연최고기온 수집 실패: "+"; ".join(failures))
    payload["max_records"]=dict(sorted(max_records.items(),key=lambda kv:int(kv[0])))
    payload["max_source"]="기상청 ASOS 일자료 TA_MAX의 연도별 최댓값 (유효일수 300일 이상)"
    payload["updated_at"]=datetime.now(KST).isoformat(timespec="seconds")
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"연평균 {len(records)}개 연도 보존, 연최고 {len(max_records)}개 연도 저장")
    if failures: print("일부 연도 실패:", "; ".join(failures))

if __name__=="__main__":
    main()
