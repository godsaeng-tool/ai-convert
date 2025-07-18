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

# Groq API 설정 (필수)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "gemma2-9b-it")

# API 키 검증
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")

# 백엔드 서버 URL 설정 (배포 환경 지원)
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8080")
if BACKEND_URL.endswith('/'):
    BACKEND_URL = BACKEND_URL.rstrip('/')

# 파일 업로드 관련 설정
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm', 'mp3', 'wav', 'flac', 'm4a', 'pdf', 'pptx', 'docx', 'doc'}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024 * 1024  # 5GB 제한

# 워커 관련 설정
MAX_WORKERS = 6

# 로컬 모델 설정
WHISPER_MODEL = "base"  # base, small, medium, large 중 선택
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"  # HuggingFace 임베딩 모델

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

# 콜백 URL 설정 (동적으로 백엔드 URL 사용)
DEFAULT_CALLBACK_URL = f"{BACKEND_URL}/api/ai/callback/complete"

# 환경 설정 정보 로깅
logger.info(f"Backend URL: {BACKEND_URL}")
logger.info(f"Default Callback URL: {DEFAULT_CALLBACK_URL}")
logger.info(f"Groq Model: {GROQ_MODEL}")
logger.info(f"Whisper Model: {WHISPER_MODEL}")
logger.info(f"Embedding Model: {EMBEDDING_MODEL}")