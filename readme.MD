## 2025 03 16... 

클론 후... 
## 시스템 요구사항
- Python 3.8 이상
- FFmpeg
- OpenAI API 키

## 설치 방법

1. 저장소 클론
```bash
git clone [repository-url]
cd [repository-name]
```

2. 가상환경 생성 및 활성화
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. 필수 패키지 설치
```bash
# 웹 프레임워크 및 기본 유틸리티
pip install flask flask-cors python-dotenv

# AI 및 벡터 DB
pip install openai llama-index faiss-cpu

# 오디오/비디오 처리
pip install yt-dlp whisper ffmpeg-python

# 기타 유틸리티
pip install requests numpy tqdm
```

내용 작성 후 업뎃 바람. 

- 작성자:엄준현
