import os
import json
import shutil
import uuid
from config import logger, RESULTS_FOLDER, UPLOAD_FOLDER, DATA_FOLDER  # DATA_FOLDER 추가
from utils.queue_worker import update_progress
from utils.file_utils import cleanup_files
from utils.api_utils import send_callback
from processors.video import download_from_url, enhance_video_transcript
from processors.audio import extract_audio, prepare_audio_for_transcription
from processors.document import process_document  # 문서 처리 모듈 import 추가
from ai_services.transcription import transcribe_audio
from ai_services.generation import generate_summary, generate_quiz, generate_study_plan
from ai_services.vector_db import index_lecture_text

def process_lecture(task_id, file_path=None, url=None, callback_url=None, lecture_id=None, remaining_days=5):
    """강의 처리 메인 함수"""
    try:
        # 결과 디렉토리 생성 (한 번만 생성)
        result_dir = os.path.join(RESULTS_FOLDER, task_id)
        os.makedirs(result_dir, exist_ok=True)
        
        # 1. 다운로드 또는 파일 확인
        if url:
            file_path = download_from_url(task_id, url)
            update_progress(task_id, "processing", 30, "URL에서 파일 다운로드 완료")
        else:
            update_progress(task_id, "processing", 30, "파일 업로드 완료, 처리 시작")

        # 파일 확장자 확인 (파일 유형에 따른 처리 분기 추가)
        file_ext = file_path.split('.')[-1].lower() if file_path else None
        
        # PDF 또는 PPT 파일인 경우 (문서 처리 경로)
        if file_ext in ['pdf', 'ppt', 'pptx']:
            logger.info(f"문서 파일 감지됨: {file_path}")
            update_progress(task_id, "processing", 40, "문서에서 텍스트 추출 중...")
            
            # 문서 처리 모듈을 사용하여 텍스트 추출
            # 이미 생성된 result_dir 전달
            doc_result = process_document(file_path, task_id, result_dir, DATA_FOLDER)
            
            if not doc_result["success"]:
                update_progress(task_id, "failed", 0, doc_result["message"])
                raise Exception(doc_result["message"])
            
            # 추출된 텍스트를 사용하여 다음 단계 진행
            transcribed_text = doc_result["text_content"]
            update_progress(task_id, "processing", 60, "텍스트 추출 완료, AI 분석 시작")
            
        else:
            # 오디오/비디오 파일 처리 (기존 코드)
            update_progress(task_id, "processing", 40, "오디오 추출 중...")
            # 2. 오디오 추출
            audio_path = extract_audio(task_id, file_path)
            
            # 3. 오디오 준비 (대용량 파일 분할 등)
            update_progress(task_id, "processing", 50, "오디오 준비 중...")
            audio_info = prepare_audio_for_transcription(task_id, audio_path)
            
            # 4. whisper STT 변환
            update_progress(task_id, "processing", 60, "텍스트 변환 중...")
            raw_transcribed_text = transcribe_audio(task_id, audio_info)

            # 스크립트 품질 개선 (새로운 단계)
            update_progress(task_id, "processing", 65, "스크립트 품질 개선 중...")
            transcribed_text = enhance_video_transcript(raw_transcribed_text)
            #logger.info(f"스크립트 품질 개선 완료: {len(raw_transcribed_text)} → {len(transcribed_text)} 문자")

        # 텍스트 변환 이후의 공통 AI 처리 부분
        
        # 5. 요약 생성
        update_progress(task_id, "processing", 70, "요약 생성 중...")
        summary_text = generate_summary(task_id, transcribed_text)
        
        # 텍스트 저장 (검색용)
        # 문서 처리 경로에서는 이미 저장되었을 수 있으므로 확인
        text_path = os.path.join(DATA_FOLDER, f"{task_id}.txt")
        if not os.path.exists(text_path):
            with open(text_path, 'w', encoding='utf-8') as f:
                f.write(transcribed_text)
            
        # 요약 저장
        summary_path = os.path.join(result_dir, f"{task_id}_summary.json")
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump({"summary_text": summary_text}, f, ensure_ascii=False, indent=4)
        
        # 6. 퀴즈 생성
        update_progress(task_id, "processing", 80, "퀴즈 생성 중...")
        quiz_text = generate_quiz(task_id, summary_text)
        
        # 7. 학습 계획 생성
        update_progress(task_id, "processing", 90, "학습 계획 생성 중...")
        study_plan = generate_study_plan(task_id, summary_text, remaining_days)
        
        # 8. 벡터 DB 인덱싱
        update_progress(task_id, "processing", 95, "벡터 DB 인덱싱 중...")
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
        result_path = os.path.join(result_dir, f"{task_id}_complete.json")
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(final_result, f, ensure_ascii=False, indent=4)
        
        # 콜백 URL이 제공된 경우 결과 전송
        if callback_url:
            send_callback(callback_url, final_result)
        
        # 10. 임시 파일 정리 (필요한 경우)
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