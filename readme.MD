


## 2025 03 13 

클론 후... 
1. 가상환경 설정(필요x)

2. 패키지 설치

- pip install flask 
- pip install ffmpeg-python     #ffmpeg 
- pip install yt-dlp            #yt-dlp 
- pip install openai-whisper    #whisper  안되면 python 3.11.9 설치 

 현재 ffmpeg를 따로 설치해서 환경변수 설정하지 않으면 안 될 가능성이 높습니다.   -0313 20:54
  추가적으로 cp949 decoding 문제로 오류가 발생할 수 있는데 이는 확인중입니다.    -0313 20:54

3. 실행 
- python app.py
- 실행하고 test.html 브라우저로 여시면 됩니다! - 2025/03/13 17:24 추가


4.gitignore 파일 생성 

# 가상환경 제외

# venv/

# __pycache__/

# *.pyc

# .DS_Store

내용 작성 후 업뎃 바람. 

- 작성자: 송원범 -
+엄준현
