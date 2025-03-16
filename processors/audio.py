import os
import subprocess
import shutil
from config import logger, PROCESSED_FOLDER
from utils.queue_worker import update_progress
from utils.file_utils import get_audio_duration, get_file_size_mb, compress_audio, split_audio

def extract_audio(task_id, video_path):
    """비디오에서 오디오 추출 (ffmpeg 사용)"""
    try:
        update_progress(task_id, "processing", 45, "오디오 추출 시작")

        output_dir = os.path.join(PROCESSED_FOLDER, task_id)
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

def prepare_audio_for_transcription(task_id, audio_path):
    """
    오디오 파일을 transcription API에 맞게 준비 
    (대용량 파일은 분할하고, 그렇지 않은 파일은 압축)
    """
    try:
        update_progress(task_id, "ai_processing", 75, "Whisper API 처리 준비 중...")

        # 오디오 파일 정보 확인
        duration = get_audio_duration(audio_path)
        
        # 파일 크기 확인 (바이트)
        file_size_mb = get_file_size_mb(audio_path)

        # 대용량 파일 처리 로직
        if file_size_mb > 24:  # 24MB 이상이면 분할 처리
            update_progress(task_id, "ai_processing", 76, f"파일 크기: {file_size_mb:.2f}MB, 분할 처리 시작...")

            # 청크 길이 계산 (대략 10분 단위로 나누기, 크기에 따라 조정)
            chunk_length = min(600, duration / (file_size_mb / 24))  # 초 단위

            # 임시 폴더 생성
            chunk_dir = os.path.join(PROCESSED_FOLDER, f"{task_id}_chunks")
            
            # 오디오 분할
            chunk_paths, num_chunks = split_audio(audio_path, chunk_dir, chunk_length, task_id)
            
            update_progress(task_id, "ai_processing", 77, f"총 {num_chunks}개 청크로 분할 처리 중...")
            return {
                "is_chunked": True,
                "chunk_paths": chunk_paths,
                "num_chunks": num_chunks,
                "chunk_dir": chunk_dir
            }
        else:
            # 기존 로직 - 파일이 작은 경우
            update_progress(task_id, "ai_processing", 80, "오디오 압축 중...")

            # 압축 파일 경로
            compressed_audio_path = audio_path.replace(".mp3", "_compressed.mp3")
            compress_audio(audio_path, compressed_audio_path)
            
            return {
                "is_chunked": False,
                "audio_path": compressed_audio_path
            }
    
    except Exception as e:
        logger.error(f"오디오 준비 실패: {str(e)}")
        update_progress(task_id, "failed", 0, f"오디오 준비 실패: {str(e)}")
        raise

def cleanup_audio_chunks(chunk_dir):
    """임시 오디오 청크 파일 정리"""
    try:
        shutil.rmtree(chunk_dir, ignore_errors=True)
        logger.info(f"오디오 청크 정리 완료: {chunk_dir}")
    except Exception as e:
        logger.warning(f"오디오 청크 정리 실패: {str(e)}")