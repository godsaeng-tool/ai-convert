import os
import json
import openai
from config import logger, OPENAI_API_KEY, RESULTS_FOLDER, DATA_FOLDER
from utils.queue_worker import update_progress
from processors.audio import cleanup_audio_chunks

# OpenAI 클라이언트 설정
openai.api_key = OPENAI_API_KEY
client = openai.OpenAI(api_key=OPENAI_API_KEY)

def transcribe_audio(task_id, audio_info):
    """
    오디오를 OpenAI Whisper API로 변환하여 텍스트 반환
    audio_info는 prepare_audio_for_transcription에서 반환된 결과
    """
    try:
        if audio_info['is_chunked']:
            return _transcribe_chunked_audio(task_id, audio_info)
        else:
            return _transcribe_single_audio(task_id, audio_info['audio_path'])
    except Exception as e:
        logger.error(f"Whisper API 처리 실패: {str(e)}")
        update_progress(task_id, "failed", 0, f"Whisper API 처리 실패: {str(e)}")
        raise

def _transcribe_single_audio(task_id, audio_path):
    """단일 오디오 파일 변환"""
    update_progress(task_id, "ai_processing", 80, "Whisper API 처리 중...")
    
    try:
        with open(audio_path, "rb") as audio_file:
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="ko"
            )
        
        transcribed_text = response.text
        
        # 결과 저장 및 반환
        _save_transcription_result(task_id, transcribed_text)
        
        return transcribed_text
    except Exception as e:
        logger.error(f"단일 오디오 변환 실패: {str(e)}")
        raise

def _transcribe_chunked_audio(task_id, audio_info):
    """분할된 오디오 파일 변환"""
    try:
        chunk_paths = audio_info['chunk_paths']
        num_chunks = audio_info['num_chunks']
        chunk_dir = audio_info['chunk_dir']
        
        # 전체 텍스트 결과 저장용
        full_text = []
        
        # 각 청크 처리
        for i, chunk_file in enumerate(chunk_paths):
            # 진행률 업데이트
            progress = 77 + (i / num_chunks) * 20
            update_progress(task_id, "ai_processing", progress,
                           f"청크 {i + 1}/{num_chunks} 처리 중...")
            
            # API로 청크 처리
            with open(chunk_file, "rb") as audio_file:
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="ko"
                )
            
            # 결과 추가
            full_text.append(response.text)
            
            # 처리된 청크 삭제 (선택적)
            os.remove(chunk_file)
        
        # 임시 디렉토리 정리
        cleanup_audio_chunks(chunk_dir)
        
        # 전체 텍스트 합치기
        transcribed_text = " ".join(full_text)
        
        # 결과 저장 및 반환
        _save_transcription_result(task_id, transcribed_text)
        
        return transcribed_text
    
    except Exception as e:
        # 오류 발생 시에도 임시 파일 정리 시도
        try:
            cleanup_audio_chunks(audio_info['chunk_dir'])
        except:
            pass
        
        logger.error(f"청크 오디오 변환 실패: {str(e)}")
        raise

def _save_transcription_result(task_id, transcribed_text):
    """변환 결과를 파일로 저장"""
    try:
        # 결과 데이터 생성
        result_data = {
            "status": "transcribed",
            "message": "스크립트 변환 완료!",
            "transcribed_text": transcribed_text
        }
        
        # 결과 폴더 생성
        result_dir = os.path.join(RESULTS_FOLDER, task_id)
        os.makedirs(result_dir, exist_ok=True)
        
        # JSON 결과 저장
        result_path = os.path.join(result_dir, f"{task_id}_result.json")
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=4)
        
        # 텍스트 파일로 저장 (두 번째 코드와의 통합용)
        text_path = os.path.join(DATA_FOLDER, f"{task_id}.txt")
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write(transcribed_text)
        
        update_progress(task_id, "transcribed", 90, "텍스트 변환 완료", result_data)
        return result_data
    
    except Exception as e:
        logger.error(f"변환 결과 저장 실패: {str(e)}")
        raise