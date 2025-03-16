import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# .env에서 환경변수 로드
load_dotenv()

# 기본 경로 설정
BASE_DIR = Path(__file__).resolve().parent

# 폴더 경로 설정
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
PROCESSED_FOLDER = os.path.join(BASE_DIR, 'processed')
RESULTS_FOLDER = os.path.join(BASE_DIR, 'results')
DATA_FOLDER = os.path.join(BASE_DIR, 'data')

# 폴더 생성
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)
os.makedirs(DATA_FOLDER, exist_ok=True)

# OpenAI API 키 설정
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OpenAI API 키가 설정되지 않았습니다. .env 파일을 확인하세요.")

# 파일 업로드 관련 설정
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm', 'mp3', 'wav', 'flac', 'm4a'}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024 * 1024  # 5GB 제한

# 워커 관련 설정
MAX_WORKERS = 6

# 로깅 설정
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(os.path.join(BASE_DIR, "lecture_processor.log"), encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("lecture_processor")

# 로거 생성
logger = setup_logging()

# 콜백 URL 설정
DEFAULT_CALLBACK_URL = "http://localhost:8080/api/ai/callback/complete"