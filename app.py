from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import uuid
import subprocess
import threading
import yt_dlp
import time
import logging
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import atexit
import re
import queue

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("lecture_processor.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("lecture_processor")

app = Flask(__name__)
CORS(app)

# 설정 변수
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
PROCESSED_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'processed')
RESULTS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm', 'mp3', 'wav', 'flac', 'm4a'}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024 * 1024  # 5GB 제한

# 폴더 생성
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROCESSED_FOLDER'] = PROCESSED_FOLDER
app.config['RESULTS_FOLDER'] = RESULTS_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# 진행 상황 추적용 딕셔너리
progress_tracker = {}
lock = threading.Lock()

# 작업 큐 생성
task_queue = queue.Queue()

# ThreadPoolExecutor 생성 (전역 변수로 설정)
executor = ThreadPoolExecutor(max_workers=4)

def sanitize_filename(filename):
    """파일명에서 시스템에 문제가 될 수 있는 특수문자 제거"""
    # 특수문자 및 공백 제거, 영숫자와 일부 안전한 문자만 허용
    sanitized = re.sub(r'[^\w\-_.]', '_', filename)
    return sanitized

def allowed_file(filename):
    """허용된 파일 확장자인지 확인"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def update_progress(task_id, status, progress=0, message="", result=None):
    """진행 상황 업데이트"""
    with lock:
        if task_id not in progress_tracker:
            progress_tracker[task_id] = {}
        
        progress_tracker[task_id].update({
            "status": status,
            "progress": progress,
            "message": message,
            "timestamp": time.time()
        })
        
        if result:
            progress_tracker[task_id]["result"] = result
            
        # 완료된 작업은 일정 시간 후 제거 (클린업)
        if status == "completed" or status == "failed":
            def cleanup():
                time.sleep(3600)  # 1시간 후 제거
                with lock:
                    if task_id in progress_tracker:
                        del progress_tracker[task_id]
            
            cleanup_thread = threading.Thread(target=cleanup)
            cleanup_thread.daemon = True
            cleanup_thread.start()

def download_from_url(task_id, url):
    """URL에서 동영상 다운로드 (yt-dlp 사용)"""
    try:
        update_progress(task_id, "downloading", 10, "동영상 다운로드 시작")
        
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{task_id}")
        os.makedirs(output_path, exist_ok=True)
        
        # 파일명 관련 옵션 추가
        ydl_opts = {
            'format': 'best',
            'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
            'noplaylist': True,
            'restrictfilenames': True,  # 안전한 파일명 사용
            'progress_hooks': [lambda d: download_progress_hook(d, task_id)],
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded_file = ydl.prepare_filename(info)
            
        update_progress(task_id, "downloaded", 40, "동영상 다운로드 완료")
        return downloaded_file
    
    except Exception as e:
        logger.error(f"다운로드 실패: {str(e)}")
        update_progress(task_id, "failed", 0, f"다운로드 실패: {str(e)}")
        raise

def download_progress_hook(d, task_id):
    """yt-dlp 다운로드 진행상황 훅"""
    if d['status'] == 'downloading':
        try:
            percent = d['_percent_str']
            percent = float(percent.strip('%'))
            # 다운로드는 0-40% 진행 상황에 매핑
            progress = min(40, max(10, 10 + (percent * 0.3)))
            update_progress(task_id, "downloading", progress, f"다운로드 중: {percent}%")
        except:
            pass
    elif d['status'] == 'finished':
        update_progress(task_id, "processing", 40, "다운로드 완료, 변환 시작")

def extract_audio(task_id, video_path):
    """비디오에서 오디오 추출 (ffmpeg 사용)"""
    try:
        update_progress(task_id, "processing", 45, "오디오 추출 시작")
        
        output_dir = os.path.join(app.config['PROCESSED_FOLDER'], task_id)
        os.makedirs(output_dir, exist_ok=True)
        
        # 인코딩 문제를 피하기 위해 간단한 파일명 사용
        audio_path = os.path.join(output_dir, f"{task_id}.mp3")
        
        # 경로에 한글이 포함되어도 작동하도록 UTF-8 설정
        if os.name == 'nt':  # Windows
            # Windows에서 한글 경로 처리를 위한 설정
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            # ffmpeg 명령 구성 (간소화된 버전)
            cmd = [
                'ffmpeg',
                '-y',  # 기존 파일 덮어쓰기
                '-i', video_path,
                '-vn',  # 비디오 스트림 제외
                '-ar', '16000',  # 샘플링 레이트 16kHz
                '-ac', '1',  # 모노 채널
                '-b:a', '64k',  # 비트레이트
                '-f', 'mp3',
                audio_path
            ]
            
            # 프로세스 실행
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                startupinfo=si
            )
        else:  # Linux/Mac
            # ffmpeg 명령 구성
            cmd = [
                'ffmpeg',
                '-y',  # 기존 파일 덮어쓰기
                '-i', video_path,
                '-vn',  # 비디오 스트림 제외
                '-ar', '16000',  # 샘플링 레이트 16kHz
                '-ac', '1',  # 모노 채널
                '-b:a', '64k',  # 비트레이트
                '-f', 'mp3',
                audio_path
            ]
            
            # 프로세스 실행 및 실시간 출력 캡처
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                universal_newlines=True
            )
        
        # ffmpeg 출력에서 진행 상황 파싱
        stdout, stderr = process.communicate()
        
        # 프로세스 완료 확인
        if process.returncode != 0:
            logger.error(f"FFmpeg 오류: {stderr}")
            raise Exception(f"오디오 추출 실패: 반환 코드 {process.returncode}")
        
        update_progress(task_id, "processing", 70, "오디오 추출 완료")
        return audio_path
    
    except Exception as e:
        logger.error(f"오디오 추출 실패: {str(e)}")
        update_progress(task_id, "failed", 0, f"오디오 추출 실패: {str(e)}")
        raise

def send_to_ai_processor(task_id, audio_path):
    """오디오 파일을 AI 처리 모듈로 전달 (같은 서버 내 다른 함수로 전달)"""
    try:
        update_progress(task_id, "ai_processing", 75, "AI 처리 시작")
        
        # 이 부분에서는 파일 경로를 AI 처리 함수에 전달
        # 실제 구현에서는 다른 팀원이 담당하는 AI 처리 모듈에 파일 경로를 전달하는 식으로 생각했습니다다
        
        # 예시: 다른 모듈의 함수 호출 (미구현)-> 이런식으로 구현해서 붙여주시면 될 것 같습니다!!
        # from ai_module import process_audio
        # result = process_audio(audio_path)

        # 임시 결과 객체 (실제로는 AI 처리 결과가 여기에 들어감)
        result = {
            "audio_path": audio_path,
            "status": "processed",
            "message": "오디오 처리 완료, AI 분석 준비 완료",
            # 여기에 AI 처리 결과가 추가될 것
        }
        
        # 결과 파일 저장 디렉토리 생성
        result_dir = os.path.join(app.config['RESULTS_FOLDER'], task_id)
        os.makedirs(result_dir, exist_ok=True)
        
        # 결과 JSON 저장 (실제로는 AI 처리 결과)
        result_path = os.path.join(result_dir, f"{task_id}_result.json")
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=4)
        
        # 완료 상태 업데이트
        update_progress(task_id, "completed", 100, "AI 처리 완료", result)
        
        return result
    
    except Exception as e:
        logger.error(f"AI 처리 실패: {str(e)}")
        update_progress(task_id, "failed", 0, f"AI 처리 실패: {str(e)}")
        raise

def process_lecture(task_id, file_path=None, url=None):
    """강의 처리 메인 함수"""
    try:
        # 1. 다운로드 또는 파일 확인
        if url:
            file_path = download_from_url(task_id, url)
        else:
            update_progress(task_id, "processing", 40, "파일 업로드 완료, 변환 시작")
        
        # 2. 오디오 추출
        audio_path = extract_audio(task_id, file_path)
        
        # 3. AI 처리 모듈로 전달
        result = send_to_ai_processor(task_id, audio_path)
        
        # 4. 임시 파일 정리 (파일 저장 안 하고, 처리 완료하면 삭제하는 방식으로)
        cleanup_uploads(task_id)
        
        return result
    
    except Exception as e:
        logger.error(f"강의 처리 실패: {str(e)}")
        update_progress(task_id, "failed", 0, f"처리 실패: {str(e)}")
        raise

def cleanup_uploads(task_id):
    """원본 영상 파일만 정리"""
    try:
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], task_id)
        if os.path.exists(upload_path):
            shutil.rmtree(upload_path)
    except Exception as e:
        logger.warning(f"업로드 파일 정리 중 오류: {str(e)}")

# 작업 처리 스레드
def worker():
    """작업 큐에서 작업을 가져와서 처리하는 워커 스레드"""
    while True:
        try:
            # 큐에서 작업 가져오기
            task = task_queue.get()
            if task is None:  # 종료 신호
                break
                
            task_id, file_path, url = task
            # 작업 처리
            process_lecture(task_id, file_path, url)
            
        except Exception as e:
            logger.error(f"작업 처리 중 오류: {str(e)}")
        finally:
            # 작업 완료 표시
            task_queue.task_done()

# 워커 스레드 시작
def start_workers(num_workers=4):
    """워커 스레드들을 시작"""
    for _ in range(num_workers):
        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()

# 서버 시작 시 워커 스레드 시작
start_workers()

@app.route('/')
def home():
    return "강의 처리 서버가 실행 중입니다!"

@app.route('/process/file', methods=['POST'])
def upload_file():
    """파일 업로드 처리 엔드포인트"""
    if 'file' not in request.files:
        return jsonify({"error": "파일이 없습니다"}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({"error": "선택된 파일이 없습니다"}), 400
    
    if not allowed_file(file.filename):
        return jsonify({"error": f"지원되지 않는 파일 형식입니다. 허용된 형식: {', '.join(ALLOWED_EXTENSIONS)}"}), 400
    
    try:
        task_id = str(uuid.uuid4())
        # 안전한 파일명 사용
        filename = sanitize_filename(secure_filename(file.filename))
        upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], task_id)
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, filename)
        file.save(file_path)
        
        update_progress(task_id, "uploaded", 10, "파일 업로드 완료")
        
        # 작업 큐에 추가
        task_queue.put((task_id, file_path, None))
        
        return jsonify({
            "task_id": task_id,
            "message": "파일 업로드 완료, 처리 대기열에 추가됨",
            "status": "queued"
        }), 202
    
    except Exception as e:
        logger.error(f"파일 업로드 실패: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/process/url', methods=['POST'])
def upload_url():
    """URL 처리 엔드포인트"""
    data = request.get_json()
    
    if not data or 'url' not in data:
        return jsonify({"error": "URL이 제공되지 않았습니다"}), 400
    
    url = data['url']
    
    try:
        task_id = str(uuid.uuid4())
        update_progress(task_id, "queued", 0, "URL 처리 대기 중")
        
        # 작업 큐에 추가
        task_queue.put((task_id, None, url))
        
        return jsonify({
            "task_id": task_id,
            "message": "URL 처리 대기열에 추가됨",
            "status": "queued"
        }), 202
    
    except Exception as e:
        logger.error(f"URL 처리 실패: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/process/batch', methods=['POST'])
def upload_batch():
    """다중 파일 업로드 엔드포인트"""
    if 'files[]' not in request.files:
        return jsonify({"error": "파일이 없습니다"}), 400
    
    files = request.files.getlist('files[]')
    results = []
    
    for file in files:
        if file.filename == '':
            continue
            
        if not allowed_file(file.filename):
            results.append({
                "filename": file.filename,
                "status": "error",
                "message": f"지원되지 않는 파일 형식입니다. 허용된 형식: {', '.join(ALLOWED_EXTENSIONS)}"
            })
            continue
            
        try:
            task_id = str(uuid.uuid4())
            # 안전한 파일명 사용
            filename = sanitize_filename(secure_filename(file.filename))
            upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], task_id)
            os.makedirs(upload_dir, exist_ok=True)
            file_path = os.path.join(upload_dir, filename)
            file.save(file_path)
            
            update_progress(task_id, "uploaded", 10, "파일 업로드 완료")
            
            # 작업 큐에 추가
            task_queue.put((task_id, file_path, None))
            
            results.append({
                "filename": file.filename,
                "task_id": task_id,
                "status": "queued",
                "message": "파일 업로드 완료, 처리 대기열에 추가됨"
            })
            
        except Exception as e:
            logger.error(f"파일 업로드 실패: {str(e)}")
            results.append({
                "filename": file.filename,
                "status": "error",
                "message": str(e)
            })
    
    return jsonify({
        "message": f"{len(results)}개 파일 업로드 처리 완료",
        "results": results
    }), 202

@app.route('/progress/<task_id>', methods=['GET'])
def get_progress(task_id):
    """작업 진행 상황 조회 엔드포인트"""
    with lock:
        if task_id not in progress_tracker:
            return jsonify({"error": "작업을 찾을 수 없습니다"}), 404
        
        return jsonify(progress_tracker[task_id]), 200

@app.route('/progress/all', methods=['GET'])
def get_all_progress():
    """모든 작업 진행 상황 조회 엔드포인트"""
    with lock:
        return jsonify(progress_tracker), 200

@app.route('/download/audio/<task_id>', methods=['GET'])
def download_processed_audio(task_id):
    """처리된 오디오 파일 다운로드 엔드포인트"""
    try:
        processed_dir = os.path.join(app.config['PROCESSED_FOLDER'], task_id)
        
        if not os.path.exists(processed_dir):
            return jsonify({"error": "처리된 파일을 찾을 수 없습니다"}), 404
        
        # 디렉토리 내 mp3 파일 찾기
        audio_files = [f for f in os.listdir(processed_dir) if f.endswith('.mp3')]
        
        if not audio_files:
            return jsonify({"error": "처리된 오디오 파일을 찾을 수 없습니다"}), 404
        
        return send_file(
            os.path.join(processed_dir, audio_files[0]),
            mimetype='audio/mpeg',
            as_attachment=True,
            download_name=f"processed_{task_id}.mp3"
        )
    
    except Exception as e:
        logger.error(f"파일 다운로드 실패: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/download/result/<task_id>', methods=['GET'])
def download_result(task_id):
    """AI 처리 결과 다운로드 엔드포인트"""
    try:
        result_dir = os.path.join(app.config['RESULTS_FOLDER'], task_id)
        
        if not os.path.exists(result_dir):
            return jsonify({"error": "결과 파일을 찾을 수 없습니다"}), 404
        
        # 결과 JSON 파일 찾기
        result_files = [f for f in os.listdir(result_dir) if f.endswith('_result.json')]
        
        if not result_files:
            return jsonify({"error": "결과 파일을 찾을 수 없습니다"}), 404
        
        return send_file(
            os.path.join(result_dir, result_files[0]),
            mimetype='application/json',
            as_attachment=True,
            download_name=f"result_{task_id}.json"
        )
    
    except Exception as e:
        logger.error(f"결과 다운로드 실패: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/cancel/<task_id>', methods=['POST'])
def cancel_task(task_id):
    """작업 취소 엔드포인트"""
    with lock:
        if task_id not in progress_tracker:
            return jsonify({"error": "작업을 찾을 수 없습니다"}), 404
        
        update_progress(task_id, "cancelled", 0, "사용자에 의해 취소됨")
        return jsonify({"message": "작업 취소 요청됨"}), 200

@app.route('/health', methods=['GET'])
def health_check():
    """서버 상태 확인 엔드포인트"""
    # 큐 상태도 추가
    queue_size = task_queue.qsize()
    
    return jsonify({
        "status": "healthy",
        "time": time.time(),
        "queue_size": queue_size,
        "active_tasks": len(progress_tracker)
    }), 200

# AI 처리 모듈 통합 인터페이스
# 실제로는 다른 팀원이 개발한 AI 모듈을 import하여 사용할 것
# 예씨: from ai_module import transcribe, summarize, generate_questions

@app.route('/ai/process', methods=['POST'])
def ai_process_endpoint():
    """AI 처리 엔드포인트 (다른 팀원이 개발할 부분과 통합할 포인트)"""
    if 'file' not in request.files:
        return jsonify({"error": "파일이 없습니다"}), 400
    
    file = request.files['file']
    task_id = request.form.get('task_id', str(uuid.uuid4()))
    
    try:
        # 임시 저장
        audio_dir = os.path.join(app.config['PROCESSED_FOLDER'], task_id)
        os.makedirs(audio_dir, exist_ok=True)
        audio_path = os.path.join(audio_dir, f"{task_id}_received.mp3")
        file.save(audio_path)
        
        # AI 처리 모듈 호출 (여기서는 예시로만 구현)
        result = send_to_ai_processor(task_id, audio_path)
        
        return jsonify({
            "task_id": task_id,
            "status": "processing",
            "message": "AI 처리 시작됨"
        }), 202
        
    except Exception as e:
        logger.error(f"AI 처리 요청 실패: {str(e)}")
        return jsonify({"error": str(e)}), 500

# 애플리케이션 종료 시 정리
@atexit.register
def cleanup():
    # 모든 워커에게 종료 신호 보내기
    for _ in range(4):  # 워커 수만큼
        task_queue.put(None)
    
    # ThreadPoolExecutor 종료
    executor.shutdown(wait=False)

if __name__ == '__main__':
    app.run(port=5000, debug=True)