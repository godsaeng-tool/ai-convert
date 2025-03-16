import os
import json
import shutil
import uuid
from config import logger, RESULTS_FOLDER, UPLOAD_FOLDER
from utils.queue_worker import update_progress
from utils.file_utils import cleanup_files
from utils.api_utils import send_callback
from processors.video import download_from_url
from processors.audio import extract_audio, prepare_audio_for_transcription
from ai_services.transcription import transcribe_audio
from ai_services.generation import generate_summary, generate_quiz, generate_study_plan
from ai_services.vector_db import index_lecture_text

def process_lecture(task_id, file_path=None, url=None, callback_url=None, lecture_id=None):
    """강의 처리 메인 함수"""
    try:
        # 1. 다운로드 또는 파일 확인
        if url:
            file_path = download_from_url(task_id, url)
        else:
            update_progress(task_id, "processing", 40, "파일 업로드 완료, 변환 시작")

        # 2. 오디오 추출
        audio_path = extract_audio(task_id, file_path)

        # 3. 오디오 준비 (대용량 파일 분할 등)
        audio_info = prepare_audio_for_transcription(task_id, audio_path)

        # 4. whisper STT 변환
        transcribed_text = transcribe_audio(task_id, audio_info)

        # 5. 요약 생성
        summary_text = generate_summary(task_id, transcribed_text)

        # 6. 퀴즈 생성
        quiz_text = generate_quiz(task_id, summary_text)

        # 7. 학습 계획 생성
        study_plan = generate_study_plan(task_id, summary_text)

        # 8. 벡터 DB 인덱싱
        index_lecture_text(task_id)

        # 100% 업데이트
        update_progress(task_id, "completed", 100, "모든 처리 완료")

        # 9. 최종 결과 데이터 생성
        final_result = {
            "task_id": task_id,
            "lecture_id": lecture_id,
            "status": "completed",
            "message": "처리 완료",
            "transcribed_text": transcribed_text,
            "summary_text": summary_text,
            "quiz_text": quiz_text,
            "study_plan": study_plan
        }

        # 최종 결과 저장
        result_dir = os.path.join(RESULTS_FOLDER, task_id)
        os.makedirs(result_dir, exist_ok=True)
        result_path = os.path.join(result_dir, f"{task_id}_complete.json")
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(final_result, f, ensure_ascii=False, indent=4)

        # 콜백 URL이 제공된 경우 결과 전송
        if callback_url:
            send_callback(callback_url, final_result)

        # 10. 임시 파일 정리 (파일 저장 안 하고, 처리 완료하면 삭제하는 방식으로)
        cleanup_files(os.path.join(UPLOAD_FOLDER, task_id))

        return final_result

    except Exception as e:
        logger.error(f"강의 처리 실패: {str(e)}")
        update_progress(task_id, "failed", 0, f"처리 실패: {str(e)}")
        # 에러 발생 시에도 콜백 전송
        if callback_url:
            error_data = {
                "task_id": task_id,
                "lecture_id": lecture_id,
                "status": "error",
                "message": str(e)
            }
            send_callback(callback_url, error_data)
        
        # 임시 파일 정리 시도
        try:
            cleanup_files(os.path.join(UPLOAD_FOLDER, task_id))
        except:
            pass
            
        raise