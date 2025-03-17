import os
import re
import shutil
from werkzeug.utils import secure_filename
import subprocess
from config import logger, ALLOWED_EXTENSIONS
from flask import current_app as app

def sanitize_filename(filename):
    """파일명에서 시스템에 문제가 될 수 있는 특수문자 제거"""
    # 특수문자 및 공백 제거, 영숫자와 일부 안전한 문자만 허용
    sanitized = re.sub(r'[^\w\-_.]', '_', filename)
    return sanitized

def allowed_file(filename):
    """허용된 파일 확장자인지 확인"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_uploaded_file(file, upload_dir, filename):
    """업로드된 파일을 안전하게 저장"""
    try:
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, filename)
        
        # 파일 크기 확인
        file.seek(0, os.SEEK_END)
        size = file.tell()
        if size > app.config['MAX_CONTENT_LENGTH']:
            raise ValueError(f"파일 크기가 너무 큽니다. 최대 {app.config['MAX_CONTENT_LENGTH'] / (1024*1024*1024)}GB까지 허용됩니다.")
        
        file.seek(0)  # 파일 포인터 리셋
        file.save(file_path)
        
        return file_path
    except Exception as e:
        logger.error(f"파일 저장 실패: {str(e)}")
        raise

def cleanup_files(directory):
    """지정된 디렉토리의 파일들을 삭제"""
    try:
        if os.path.exists(directory):
            shutil.rmtree(directory)
        logger.info(f"디렉토리 정리 완료: {directory}")
    except Exception as e:
        logger.warning(f"파일 정리 중 오류: {str(e)}")

def compress_audio(input_path, output_path, bitrate="32k"):
    """오디오 파일 압축 (16kHz 모노, 지정된 비트레이트)"""
    cmd = [
        'ffmpeg', '-i', input_path,
        '-ar', '16000', '-ac', '1', '-b:a', bitrate,
        '-y', output_path  # 기존 파일 덮어쓰기
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    if result.returncode != 0:
        error_message = result.stderr.decode('utf-8', errors='replace')
        logger.error(f"오디오 압축 실패: {error_message}")
        raise Exception(f"오디오 압축 실패: 반환 코드 {result.returncode}")
    
    return output_path

def get_audio_duration(audio_path):
    """오디오 파일의 길이(초)를 반환"""
    probe_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of',
                 'default=noprint_wrappers=1:nokey=1', audio_path]
    result = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    if result.returncode != 0:
        error_message = result.stderr.decode('utf-8', errors='replace')
        logger.error(f"오디오 길이 확인 실패: {error_message}")
        raise Exception(f"오디오 길이 확인 실패: 반환 코드 {result.returncode}")
    
    return float(result.stdout.decode('utf-8').strip())

def get_file_size_mb(file_path):
    """파일 크기를 MB 단위로 반환"""
    size_bytes = os.path.getsize(file_path)
    return size_bytes / (1024 * 1024)

def split_audio(audio_path, chunk_dir, chunk_length, task_id):
    """오디오 파일을 지정된 길이의 청크로 분할"""
    os.makedirs(chunk_dir, exist_ok=True)
    
    duration = get_audio_duration(audio_path)
    num_chunks = int(duration / chunk_length) + 1
    chunk_paths = []
    
    for i in range(num_chunks):
        start_time = i * chunk_length
        # 마지막 청크는 끝까지
        end_time = min((i + 1) * chunk_length, duration)
        
        # 청크 파일 생성
        chunk_file = os.path.join(chunk_dir, f"chunk_{i}.mp3")
        
        # ffmpeg로 청크 추출
        cmd = [
            'ffmpeg', '-y', '-i', audio_path,
            '-ss', str(start_time), '-to', str(end_time),
            '-c:a', 'libmp3lame', '-b:a', '32k',
            chunk_file
        ]
        
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        if result.returncode != 0:
            error_message = result.stderr.decode('utf-8', errors='replace')
            logger.error(f"오디오 청크 분할 실패: {error_message}")
            raise Exception(f"오디오 청크 분할 실패: 반환 코드 {result.returncode}")
        
        chunk_paths.append(chunk_file)
    
    return chunk_paths, num_chunks