# 재미있는 비만도 진단 대시보드

한국인 BMI·허리둘레 참조표준을 바탕으로 상대적 분위수 위치를 보여 주는 Streamlit 프로젝트입니다. 이 문서는 Python과 Streamlit이 익숙하지 않은 사용자를 위한 **처음부터 실행하고, 실패한 단계부터 다시 시작하는 실행 안내서**입니다.

> **의료 안전 고지:** 이 프로젝트의 결과는 참조집단 내 상대적 위치를 이해하기 위한 참고용 안내입니다. `의료진단이 아니며 의료적 판단을 대체하지 않는다`. 질병명 판정, 치료 권고, 응급 판단 또는 의료진 상담의 대체로 사용하지 마세요.

## 1. 현재 구현 범위

현재 저장소에서 바로 확인할 수 있는 구성은 다음과 같습니다.

- `app.py`: 공통 Streamlit 초기화, 캐시 fingerprint, 페이지 namespace, 공통 고지와 오류 경계
- `src/`: 입력 검증, BMI, Excel 로더/표준 스키마, 분위수·지역 fallback, 등급, 안전한 멘트, 진단 조립, 학습 frame 변환, Plotly 시각화
- `data/`: BMI 및 허리둘레 원본 Excel 파일
- `tests/`: pytest 단위 테스트와 Hypothesis 속성 테스트
- `pages/`: 현재 `__init__.py`만 있으며 세 개의 실제 Streamlit 페이지는 아직 없습니다.

따라서 아래 문서에는 최종 대시보드 흐름을 모두 적되, 아직 없는 세부 페이지와 모델 평가 함수는 **구현 완료 후 실행할 단계**로 표시합니다. `app.py` 공통 셸 테스트는 실행할 수 있지만, 페이지가 없으면 앱에서 세 페이지 콘텐츠를 확인할 수 없습니다.

## 2. 준비물과 프로젝트 루트

Windows PowerShell 기준입니다. 모든 명령은 `README.md`, `requirements.txt`, `src/`, `tests/`, `data/`가 있는 프로젝트 루트에서 실행합니다.

```powershell
Get-Location
Get-ChildItem
```

성공 기준: 현재 위치에 `requirements.txt`, `src`, `tests`, `data`가 보입니다.

실패 시 재시작: 명령을 실행한 폴더가 다르면 프로젝트 폴더로 이동한 뒤 이 단계부터 다시 확인합니다. OneDrive 동기화 중이면 동기화가 끝난 뒤 재시도하세요.

## 3. 가상환경과 의존성 설치

가상환경을 만들고 활성화합니다.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version
python -m pip --version
```

PowerShell 실행 정책으로 활성화가 막히면, 가상환경을 활성화하지 않고도 아래처럼 `.venv`의 Python을 직접 사용할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe --version
```

의존성을 설치합니다.

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip check
```

성공 기준:

- `pip check`가 `No broken requirements found.`를 출력합니다.
- `pandas`, `numpy`, `scikit-learn`, `plotly`, `streamlit`, `openpyxl`, `pytest`, `hypothesis`를 import할 수 있습니다.

```powershell
python -c "import pandas,numpy,sklearn,plotly,streamlit,openpyxl,pytest,hypothesis; print('dependencies: OK')"
```

실패 시 재시작: 이 단계에서 멈추고 Python 버전·가상환경 활성화 여부·인터넷 또는 사내 패키지 미러를 확인합니다. 설치가 해결될 때까지 Excel 로드나 앱 실행 단계로 넘어가지 말고, 설치 명령부터 다시 실행합니다.

## 4. 참조 Excel 파일 배치 확인

다음 두 파일이 정확히 `data/`에 있어야 합니다.

- `data/한국인_비만지수(체질량지수)_참조표준.xlsx`
- `data/한국인_비만지수(허리둘레)_참조표준.xlsx`

```powershell
Get-ChildItem .\data\*.xlsx
Test-Path ".\data\한국인_비만지수(체질량지수)_참조표준.xlsx"
Test-Path ".\data\한국인_비만지수(허리둘레)_참조표준.xlsx"
```

성공 기준: 두 `Test-Path` 결과가 모두 `True`이고 파일명이 변경되지 않았습니다.

실패 시 재시작: 원본 파일을 다시 `data/`에 복사하고 파일명·확장자를 확인한 뒤 이 단계부터 재시작합니다. 다른 폴더나 임의의 파일명을 사용하지 마세요.

## 5. Excel 시트·열 매핑과 로더 확인

현재 로더는 각 workbook의 첫 번째 시트를 읽고 다음 원본 열을 표준 스키마로 변환합니다.

| Excel 열 | 표준 의미 |
|---|---|
| `지역` | `region` |
| `성별` | `sex` |
| `나이` (`20~24 세` 형식) | `age_min`, `age_max` |
| `1분위수`, `5분위수`, `10분위수`, `25분위수`, `50분위수`, `75분위수`, `90분위수`, `95분위수`, `99분위수` | `quantiles` |
| 파일 종류 | `measure_type` (`bmi` 또는 `waist`) |
| 파일명·행 번호 | `source`, `source_row` |

실제 시트명과 열을 확인합니다.

```powershell
@'
from pathlib import Path
from src.data_loader import inspect_workbook

for path in sorted(Path("data").glob("*.xlsx")):
    print(f"\n[{path.name}]")
    info = inspect_workbook(path)
    print("sheets:", info["sheets"])
    print("columns:", info["columns"])
    print("labels:", info["column_labels"])
'@ | python -
```

표준 로더를 실제 파일로 확인합니다.

```powershell
@'
from pathlib import Path
from src.data_loader import load_reference_data

bmi = Path("data/한국인_비만지수(체질량지수)_참조표준.xlsx")
waist = Path("data/한국인_비만지수(허리둘레)_참조표준.xlsx")
records, issues = load_reference_data(bmi, waist)
print("records:", len(records), "issues:", len(issues))
print("measure types:", sorted({record.measure_type for record in records}))
print("first record:", records[0])
if issues:
    print("first issue:", issues[0])
'@ | python -
```

성공 기준: 두 파일 모두 읽히고, record가 1개 이상이며 `measure types`에 `bmi`와 `waist`가 포함됩니다. 개별 행 문제가 있으면 `issues`에 행·필드·사유가 표시되지만 유효 행은 계속 사용할 수 있습니다.

실패 시 재시작: 파일 없음/Excel 읽기 실패이면 [4단계](#4-참조-excel-파일-배치-확인)부터, 필수 열 누락·연령 형식·분위수 오름차순 오류이면 원본 열/값을 수정한 뒤 [5단계](#5-excel-시트열-매핑과-로더-확인)부터 다시 실행합니다.

## 6. 단계별 테스트 실행

### 6.1 입력 검증·BMI·분위수·지역 fallback

```powershell
python -m pytest tests/test_validation.py tests/test_bmi.py tests/test_quantile.py tests/test_diagnosis.py -q
```

성공 기준: 입력 범위(나이 0~120, 키 30~250cm, 몸무게 1~300kg, 허리둘레 20~200cm), BMI 공식, 경계·선형 보간·중복 경계, 지역 일치 우선과 전국/미지정 fallback, 부분 실패 격리가 모두 통과합니다.

실패 시 재시작: 입력 또는 BMI 실패는 `src/validation.py`·`src/bmi.py`와 관련 테스트를 확인하고 이 명령부터 재실행합니다. 분위수/fallback 실패는 `src/quantile.py`와 loader 매핑을 확인한 뒤 이 단계부터 재시작합니다.

### 6.2 등급·멘트 안전성·표준 스키마

```powershell
python -m pytest tests/test_grading.py tests/test_messages.py tests/test_schema_loader.py -q
```

성공 기준: 0/20/40/60/80/100 경계가 올바르게 등급화되고, BMI·허리둘레 10개 조합에 각각 서로 다른 멘트 5개 이상이 있으며, 금지 표현이 차단되고 seed 선택이 재현됩니다. loader는 원본 열을 표준 스키마로 변환하고 잘못된 행·필수 열 누락·재로드 결정성을 검증합니다.

실패 시 재시작: 멘트 부족·중복·안전성 실패이면 `src/messages.py`의 catalog를 수정하고 이 단계부터 재실행합니다. schema/매핑 실패이면 [4단계](#4-참조-excel-파일-배치-확인)부터 파일을 확인하고 [5단계](#5-excel-시트열-매핑과-로더-확인)부터 재시작합니다.

### 6.3 모델 학습 데이터와 평가

현재 저장소에서 실행 가능한 모델 관련 테스트는 표준 record를 long-format 학습 frame으로 바꾸는 단계입니다.

```powershell
python -m pytest tests/test_modeling.py -q
```

성공 기준: `percentile`이 target으로 분리되고 feature에 들어가지 않으며, 동일 참조행의 percentile들이 하나의 `group_key`를 공유합니다.

최종 모델 평가 서비스가 구현된 뒤에는 다음 명령으로 Linear Regression과 Decision Tree Regressor의 동일 split, train-only 전처리, MAE/R², 평가 불가 조건, 재현성을 확인합니다.

```powershell
python -m pytest tests/test_modeling.py -q
```

실패 시 재시작: feature/target 분리 또는 group key 실패는 `src/modeling.py`와 해당 테스트부터, 모델 평가 데이터·seed·전처리 실패는 모델 설정과 평가 frame을 확인한 뒤 이 단계부터 재시작합니다. 평가 행이 2개 미만이거나 target 분산이 0이면 점수를 표시하지 않고 평가 불가 사유를 표시해야 합니다.

### 6.4 EDA와 진단 확인

최종 Streamlit 통합 단계에서는 EDA에서 행 수·열 수·결측 열 수·성별/연령/지역 범주와 분포 차트를 확인하고, 진단에서 정상 입력·누락 입력·범위 초과·지역 미매칭을 각각 확인합니다.

현재 `app.py`의 공통 셸은 있으나 EDA/진단/모델 성능 페이지 파일과 `evaluate_models()` 평가 함수는 아직 없습니다. 따라서 아래 명령 중 `test_visualization.py`는 현재 구현 범위를 확인하고, `streamlit run app.py`는 공통 셸만 실행합니다. 세 페이지 확인은 해당 페이지 구현 후 실행합니다.

```powershell
python -m pytest tests/test_visualization.py -q
streamlit run app.py
```

앱에서 확인할 항목:

1. `진단`: 정상 입력, 필수값 누락, 범위 초과, 지역 미매칭 fallback
2. `데이터 탐색 EDA`: 행·열·결측 요약, 집단 범주, 분포 차트
3. `모델 성능`: Linear Regression과 Decision Tree Regressor의 MAE/R², 평가 불가 안내
4. 세 페이지 결과와 같은 화면의 `의료진단이 아니며 의료적 판단을 대체하지 않는다`

성공 기준: 데이터 오류는 원시 traceback 대신 원인과 조치를 보여 주고, 한 지표 실패가 다른 지표 결과를 숨기지 않으며, 분위수 시각화 값은 0~100입니다.

실패 시 재시작: `app.py` 없음/페이지 로드 실패는 Streamlit 통합 단계에서 멈추고 앱 진입점·페이지를 먼저 구현합니다. EDA 오류는 loader/데이터 배치 단계로, 진단 입력 오류는 validation 단계로, 지역 fallback 오류는 분위수 테스트 단계로 돌아갑니다.

## 7. 전체 테스트와 완료 기준

개별 단계가 통과한 뒤 프로젝트 루트에서 전체 테스트를 실행합니다.

```powershell
python -m pytest -q
```

선택적 컴파일 smoke도 실행합니다.

```powershell
python -m compileall src tests pages
```

최종 성공 기준은 다음을 모두 만족하는 것입니다.

- 의존성 설치와 `pip check` 성공
- 두 Excel 파일이 `data/`에 있고 loader가 BMI/waist 표준 record를 생성
- 입력 검증, BMI, 분위수·fallback, 등급·멘트 안전성, schema 테스트 통과
- 모델 frame/평가 테스트 통과; 평가 불가 조건은 점수 없이 설명됨
- EDA·진단·모델 페이지와 공통 의료 고지 확인
- 프로젝트 루트의 전체 `python -m pytest -q`가 실패 없이 종료
- 정책·경계·fallback을 바꾼 경우 관련 테스트도 갱신 후 전체 pytest 재통과

전체 테스트 실패 시 실패한 첫 번째 테스트 모듈을 기준으로 해당 단계의 재시작 지점으로 돌아갑니다. 전체 테스트를 건너뛰거나 일부 테스트만 통과한 상태를 완료로 판정하지 않습니다.

## 8. 프로젝트 구조

```text
.
├─ app.py                         # 최종 Streamlit 진입점
├─ pages/                         # 진단·EDA·모델 성능 페이지
├─ src/                           # 로더·계산·모델링·시각화 모듈
├─ data/                          # 두 개의 한국인 참조표준 Excel
├─ tests/                         # pytest/Hypothesis 테스트
├─ requirements.txt               # 고정 버전 의존성
└─ README.md                      # 이 실행 문서
```

이 프로젝트는 건강 정보를 단정하거나 의료 결정을 내리기 위한 제품이 아닙니다. 숫자와 문구는 교육·탐색 목적의 상대적 참고값이며, 건강에 관한 판단은 자격 있는 의료 전문가와 상담하세요.

## 9. Task 8.2 검증 기록 (실행 환경: Windows, Python 3.11.9)

기존 소스 코드와 스펙 문서는 수정하지 않고, 아래 명령을 프로젝트 루트에서 실행했다. 단계별 명령은 설계 문서의 순서를 따랐다.

| 단계 | 명령 | 결과 |
|---|---|---|
| 입력 검증·BMI·분위수·진단 | `python -m pytest tests/test_validation.py tests/test_bmi.py tests/test_quantile.py tests/test_diagnosis.py -q` | **통과: 54 passed** (2.07초) |
| 등급·멘트·표준 스키마 | `python -m pytest tests/test_grading.py tests/test_messages.py tests/test_schema_loader.py -q` | **통과: 45 passed** (9.59초) |
| 모델링·시각화 | `python -m pytest tests/test_modeling.py tests/test_visualization.py -q` | **실패: 16 passed, 3 failed** (124.92초) |
| Streamlit 통합 테스트 | `python -m pytest tests/test_streamlit_app.py -q` | **실행 불가: 파일 없음** (`tests/test_streamlit_app.py`가 현재 저장소에 없음) |
| 전체 테스트 | `python -m pytest -q` | **통과: 130 passed** (25.55초) |
| 컴파일 smoke | `python -m compileall src tests pages` | **통과** |
| 실제 데이터 통합 smoke | loader → diagnosis → training frame → modeling | **부분 통과**: 1,716 records, 66 row issues, 학습 frame `(15444, 13)`, 두 모델 평가 가능. 대표 입력은 두 지표 모두 `REFERENCE_GROUP_NOT_FOUND`를 반환했으며 disclaimer는 정상 표시됨. |
| 앱 smoke | `streamlit run app.py --server.headless true --server.port 8511` 및 `http://localhost:8511/` 요청 | **통과**: HTTP 200 및 Streamlit 응답 확인 후 프로세스 종료 |

### 실패 원인과 재시작 지점

- 모델링 Property 9: 생성 데이터에서 Linear Regression과 Decision Tree의 예측값을 서로 exact 비교하는 과정에서 부동소수점 미세 차이가 발생했다 (`0.9999999999999432` 대 `1.0`). **재시작 지점:** `tests/test_modeling.py` Property 9와 `src/modeling.py`의 모델 결과 비교 정책을 확인한 뒤 모델링·시각화 테스트 묶음부터 다시 실행한다.
- 모델링 Property 10: 두 참조행과 3개 분위수로 생성된 사례가 평가 가능으로 판정되어, 테스트가 기대한 “평가 불가” 조건과 충돌했다. **재시작 지점:** `tests/test_modeling.py`의 평가 불가 데이터 생성 조건과 `src/modeling.py`의 evaluation 행/분산 판정부터 확인한 뒤 모델링 테스트 묶음부터 다시 실행한다.
- 시각화 Property 13: Plotly가 계산한 residual과 Python 기대값 사이에 1 ulp 수준의 부동소수점 차이가 발생했다 (`6.661338147750939e-16` 대 `6.661338147750938e-16`). **재시작 지점:** `tests/test_visualization.py` Property 13의 비교 허용오차와 `src/visualization.py`의 residual 전달을 확인한 뒤 모델링·시각화 묶음부터 다시 실행한다.
- `tests/test_streamlit_app.py` 누락: AppTest 통합 테스트 파일이 없어 해당 단계의 자동 검증을 수행하지 못했다. **재시작 지점:** Streamlit AppTest 파일을 준비한 뒤 Streamlit 통합 테스트 단계부터 다시 실행한다.
- 실제 loader smoke의 66개 row issue: 파일 로드는 중단되지 않았고 유효 record는 계속 처리되었다. **재시작 지점:** 원본 Excel의 문제 행과 `src/data_loader.py` 매핑/행 검증을 확인한 뒤 실제 데이터 로더 smoke부터 다시 실행한다.

전체 `pytest`는 동일 작업 내에서 130개가 통과했지만, 별도 단계의 Hypothesis 실행에서 위 3개 반례가 관찰되었으므로 모델링·시각화 단계가 완전히 해소되었다고 단정하지 않는다. 정책·소스·스펙 변경은 이번 검증에서 수행하지 않았다.
