# 100년 관측소 연평균기온 자동 그래프

2026년 6월 기준 WMO 승인 국내 8개 100년 관측소의 연평균기온을 기상청 API허브에서 조회하여 그래프로 표시합니다.

## 설정
1. [기상청 API허브](https://apihub.kma.go.kr/apiList.do)에서 **지상기상연보 조회 → 연요약자료조회** API를 신청하고 `authKey`를 발급받으세요. 기존 공공데이터포털 `DATA_GO_KR_KEY`와 별개입니다.
2. GitHub 저장소의 Settings → Secrets and variables → Actions → New repository secret에 이름 `KMA_API_KEY`로 등록하세요.
3. 파일 및 `.github/workflows/update.yml`을 GitHub에 업로드합니다.
4. Actions → Update annual temperature → Run workflow 실행 후 `temperature.json` 생성 여부를 확인합니다.
5. Settings → Pages → Deploy from a branch → main / (root) 설정합니다.

매월 1일 11:20(KST)에 갱신하며, 연평균기온은 완료된 연도만 표시합니다. 최초 실행은 1912년부터 완료된 연도까지 요청하므로 API의 연도별 자료 제공 범위, 트래픽 제한, 오래된 연보 수록 여부에 따라 일부 연도가 누락될 수 있습니다. **인증키를 사용한 실제 API 호출은 아직 검증되지 않았습니다.**

기상청 API허브 명세에 따라 `getYearSumry` 응답의 `Va_lst_03`(단위 0.1℃)를 10으로 나눠 ℃로 저장합니다. 과거 관측자료의 결측 및 균질성 검토는 별도입니다.
