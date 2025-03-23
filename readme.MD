# Godsaeng-ai: AI 기반 학습 보조 시스템

## 프로젝트 소개
Godsaeng-AI는 다양한 형식의 강의 자료(비디오, 오디오, PDF, PPT)를 처리하여 텍스트로 변환하고, 생성형 AI를 활용하여 강의 내용을 분석, 요약, 퀴즈 생성, 학습 계획 수립 등을 도와주는 시스템입니다. 또한 RAG(Retrieval-Augmented Generation) 기술을 적용하여 강의 내용에 대한 질의응답 기능을 제공합니다.

## 주요 기능
1. **다양한 형식의 강의 자료 처리**
   - 비디오 파일 (mp4, avi, mov, mkv, webm)
   - 오디오 파일 (mp3, wav, flac, m4a)
   - 문서 파일 (pdf, pptx, docx, doc)
   - YouTube URL을 통한 동영상 자동 다운로드 및 처리

2. **AI 분석 기능**
   - 강의 내용 요약 생성
   - 학습 내용 기반 퀴즈 생성
   - 맞춤형 학습 계획 수립 (남은 학습 일수 기반)
   - RAG 기반 질의응답 시스템

3. **메타데이터 활용**
   - 강의 자료의 출처 정보 추출 및 활용
   - 페이지 정보 보존을 통한 맥락 유지

## 시스템 구조

```
ai_convert/
├── ai_services/           # AI 서비스 모듈
│   ├── generation.py      # 요약, 퀴즈, 학습계획 생성 기능
│   ├── transcription.py   # 음성-텍스트 변환 기능
│   └── vector_db.py       # RAG 검색 및 질의응답 기능
├── processors/            # 파일 처리 모듈
│   ├── audio.py           # 오디오 파일 처리
│   ├── document.py        # PDF/PPT 문서 처리
│   └── video.py           # 비디오 파일 처리
├── utils/                 # 유틸리티 모듈
│   ├── api_utils.py       # API 응답 포맷팅 및 콜백 기능
│   ├── file_utils.py      # 파일 처리 유틸리티
│   └── queue_worker.py    # 비동기 작업 처리
├── app.py                 # Flask 웹 서버 및 API 엔드포인트
├── config.py              # 시스템 설정
└── main_processor.py      # 메인 처리 로직
```

## 시스템 요구사항
- Python 3.8 이상
- FFmpeg (오디오/비디오 처리용)
- OpenAI API 키
- 최소 8GB RAM (권장 16GB 이상)
- 20GB 이상의 디스크 공간

## 설치 방법

1. **저장소 클론**
```bash
git clone https://github.com/username/godsaeng-ai.git
cd godsaeng-ai
```

2. **가상환경 생성 및 활성화**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. **필수 패키지 설치**
```bash
# 웹 프레임워크 및 기본 유틸리티
pip install flask flask-cors python-dotenv

# AI 및 벡터 DB
pip install openai llama-index faiss-cpu
pip install llama-index-vector-stores-faiss

# 문서/오디오/비디오 처리
pip install yt-dlp whisper ffmpeg-python
pip install PyMuPDF python-pptx pdfplumber PyPDF2

# 기타 유틸리티
pip install requests numpy tqdm
pip install sentence-transformers
```

4. **.env 파일 설정**
```
OPENAI_API_KEY=your_openai_api_key_here
```

5. **FFmpeg 설치**
   - Windows: [FFmpeg 다운로드](https://ffmpeg.org/download.html)에서 다운로드 후 PATH에 추가
   - macOS: `brew install ffmpeg`
   - Linux: `sudo apt-get install ffmpeg`

## 백엔드 연동 구조

이 시스템은 Spring Boot 백엔드 서버와 통신하도록 설계되어 있습니다. 주요 통신 흐름은 다음과 같습니다:

1. **작업 요청 수신**
   - Spring Boot 서버에서 `/process` 엔드포인트로 파일 업로드 또는 URL 처리 요청
   - 요청 시 콜백 URL, lecture_id, remaining_days 등 파라미터 전달

2. **비동기 처리**
   - 작업 ID(task_id) 생성 및 작업 큐에 추가
   - 작업 진행 상황 추적 (`/progress/<task_id>` 엔드포인트로 모니터링 가능)

3. **콜백 처리**
   - 작업 완료 시 결과 데이터를 Spring Boot 서버의 콜백 URL로 전송
   - 기본 콜백 URL: `http://localhost:8080/api/ai/callback/complete`

4. **오류 처리**
   - 작업 실패 시에도 콜백 메커니즘을 통해 오류 정보 전달

## API 엔드포인트

### 1. 주요 백엔드 통신 엔드포인트

1. **`/process`**: 강의 자료 처리 요청 수신 (백엔드 → AI 서버)
   - 파일 업로드: multipart/form-data
   - URL 처리: JSON 형식 요청
   - 파라미터: 
     - lecture_id: 강의 ID
     - remaining_days: 학습 완료까지 남은 일수
     - callback_url: 처리 완료 후 결과를 전송할 백엔드 URL

2. **`/progress/<task_id>`**: 작업 진행 상황 조회
   - 요청 방식: GET
   - 응답: 현재 진행 상태, 진행률, 메시지

3. **`/progress/all`**: 모든 작업 진행 상황 조회
   - 요청 방식: GET
   - 응답: 모든 작업의 진행 상태 목록

4. **`/health`**: 서버 상태 확인
   - 요청 방식: GET
   - 응답: 서버 상태, 큐 크기, 활성 작업 수

### 2. 테스트 및 개발용 엔드포인트

다음 엔드포인트는 주로 테스트 및 개발 목적으로 사용되며, 실제 운영 환경에서는 백엔드 서버를 통해 접근합니다:

1. **`/summary`**: 요약 생성
   - 요청 방식: POST
   - 파라미터: lecture_id, streaming(선택)

2. **`/quizzes`**: 퀴즈 생성
   - 요청 방식: POST
   - 파라미터: lecture_id, streaming(선택)

3. **`/study-plan`**: 학습 계획 생성
   - 요청 방식: POST
   - 파라미터: lecture_id, remaining_days, streaming(선택)

4. **`/query`**: RAG 기반 질의응답
   - 요청 방식: POST
   - 파라미터: lecture_id, question, streaming(선택)

## 요청 예시 (백엔드 서버에서 호출)

```python
import requests

# 파일 처리 요청
files = {'file': open('lecture.mp4', 'rb')}
data = {
    'lecture_id': '123', 
    'remaining_days': 5,
    'callback_url': 'http://localhost:8080/api/ai/callback/complete'
}
response = requests.post('http://localhost:5000/process', files=files, data=data)
task_id = response.json()['task_id']

# URL 처리 요청
data = {
    'youtube_url': 'https://www.youtube.com/watch?v=example',
    'lecture_id': '124',
    'source_type': 'YOUTUBE',
    'remaining_days': 7,
    'callback_url': 'http://localhost:8080/api/ai/callback/complete'
}
response = requests.post('http://localhost:5000/process', json=data)
```

## RAG 구현 및 Top-K 검색
시스템은 FAISS 벡터 데이터베이스를 사용하여 텍스트 청크를 저장하고 유사도 기반 검색을 수행합니다:

1. **텍스트 인덱싱**
   - 강의 자료는 의미있는 청크로 분할되어 벡터화
   - 출처 메타데이터와 페이지 정보가 함께 저장

2. **Top-K 검색**
   - 질문 벡터와 가장 유사한 상위 K개 청크 검색 (기본값: K=5)
   - 검색된 청크는 질문 응답 생성을 위한 컨텍스트로 사용

3. **응답 생성**
   - 검색된 정보를 기반으로 GPT 모델이 답변 생성
   - 출처 정보를 포함하여 신뢰성 있는 응답 제공


## 작성자
엄준현
