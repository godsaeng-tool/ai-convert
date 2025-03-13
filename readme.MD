


## 2025 03 13 

클론 후... 
1. 가상환경 설정 

- 프로젝트 폴더 이동 후 (cd)
- python -m venv venv
- .\venv\Scripts\activate  # 가상환경 활성화. 

- 비활성화 : deactivate

2. 패키지 설치

- pip install flask 
- pip install ffmpeg-python     #ffmpeg 
- pip install yt-dlp            #yt-dlp 
- pip install openai-whisper    #whisper  안되면 python 3.11.9 설치 

cpu 대신 gpu 사용 
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
FAISS ,  SentenceTransformer 
pip install faiss-cpu sentence-transformers numpy



3. 실행 
- python app.py


4.gitignore 파일 생성 

# 가상환경 제외

# venv/

# __pycache__/

# *.pyc

# .DS_Store

내용 작성 후 업뎃 바람. 

- 작성자: 송원범 -
