from flask import Flask, request, jsonify, send_file, render_template, Response, stream_with_context
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import uuid
import time
import json
import atexit

# 설정 및 유틸리티 모듈 가져오기
from config import (
    logger, UPLOAD_FOLDER, PROCESSED_FOLDER, RESULTS_FOLDER, DATA_FOLDER,
    MAX_CONTENT_LENGTH, MAX_WORKERS, ALLOWED_EXTENSIONS
)
from utils.queue_worker import (
    task_queue, update_progress, get_progress, get_all_progress,
    worker_function, start_workers, stop_workers
)
from utils.file_utils import allowed_file, save_uploaded_file, sanitize_filename
from utils.api_utils import format_response, create_error_response, create_success_response

# 처리 함수 가져오기
from main_processor import process_lecture

# AI 서비스 모듈 가져오기
from ai_services.generation import (
    stream_summary, stream_quiz, stream_study_plan, 
    generate_summary, generate_quiz, generate_study_plan, global_summary
)
from ai_services.vector_db import (
    index_lecture_text, generate_streaming_answer, generate_answer
)

# Flask 앱 초기화
app = Flask(__name__)
CORS(app)

# 설정 적용
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROCESSED_FOLDER'] = PROCESSED_FOLDER
app.config['RESULTS_FOLDER'] = RESULTS_FOLDER
app.config['DATA_FOLDER'] = DATA_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['ALLOWED_EXTENSIONS'] = ALLOWED_EXTENSIONS

# 작업 처리 워커 시작 - 메인 프로세서 설정
worker = worker_function(process_lecture)
worker_threads = start_workers(worker, MAX_WORKERS)

# 종료 시 정리 함수
@atexit.register
def cleanup():
    """애플리케이션 종료 시 정리"""
    stop_workers(MAX_WORKERS)

# 메인 페이지
@app.route('/')
def index():
    return render_template('test.html')

# 파일 업로드 처리 엔드포인트
@app.route('/process/file', methods=['POST'])
def upload_file():
    """파일 업로드 처리 엔드포인트"""
    if 'file' not in request.files:
        return jsonify(create_error_response("파일이 없습니다")), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify(create_error_response("선택된 파일이 없습니다")), 400

    if not allowed_file(file.filename):
        return jsonify(create_error_response(f"지원되지 않는 파일 형식입니다. 허용된 형식: {', '.join(ALLOWED_EXTENSIONS)}")), 400

    try:
        task_id = str(uuid.uuid4())
        # 안전한 파일명 사용
        filename = sanitize_filename(secure_filename(file.filename))
        upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], task_id)
        file_path = save_uploaded_file(file, upload_dir, filename)

        update_progress(task_id, "uploaded", 10, "파일 업로드 완료")

        # 작업 큐에 추가
        task_queue.put((task_id, file_path, None))

        return jsonify(create_success_response(
            message="파일 업로드 완료, 처리 대기열에 추가됨",
            data={"task_id": task_id, "status": "queued"}
        )), 202

    except Exception as e:
        logger.error(f"파일 업로드 실패: {str(e)}")
        return jsonify(create_error_response(str(e))), 500

# URL 처리 엔드포인트
@app.route('/process/url', methods=['POST'])
def upload_url():
    """URL 처리 엔드포인트"""
    data = request.get_json()

    if not data or 'url' not in data:
        return jsonify(create_error_response("URL이 제공되지 않았습니다")), 400

    url = data['url']

    try:
        task_id = str(uuid.uuid4())
        update_progress(task_id, "queued", 0, "URL 처리 대기 중")

        # 작업 큐에 추가
        task_queue.put((task_id, None, url))

        return jsonify(create_success_response(
            message="URL 처리 대기열에 추가됨",
            data={"task_id": task_id, "status": "queued"}
        )), 202

    except Exception as e:
        logger.error(f"URL 처리 실패: {str(e)}")
        return jsonify(create_error_response(str(e))), 500

# 다중 파일 업로드 엔드포인트
@app.route('/process/batch', methods=['POST'])
def upload_batch():
    """다중 파일 업로드 엔드포인트"""
    if 'files[]' not in request.files:
        return jsonify(create_error_response("파일이 없습니다")), 400

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
            file_path = save_uploaded_file(file, upload_dir, filename)

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

    return jsonify(create_success_response(
        message=f"{len(results)}개 파일 업로드 처리 완료",
        data={"results": results}
    )), 202

# 작업 진행 상황 조회 엔드포인트
@app.route('/progress/<task_id>', methods=['GET'])
def get_task_progress(task_id):
    """작업 진행 상황 조회 엔드포인트"""
    progress = get_progress(task_id)
    
    if not progress:
        return jsonify(create_error_response("작업을 찾을 수 없습니다")), 404

    return jsonify(progress), 200

# 모든 작업 진행 상황 조회 엔드포인트
@app.route('/progress/all', methods=['GET'])
def get_all_task_progress():
    """모든 작업 진행 상황 조회 엔드포인트"""
    return jsonify(get_all_progress()), 200

# AI 변환 결과 조회 엔드포인트
@app.route('/ai/transcribe', methods=['POST'])
def transcribe_audio():
    """오디오를 Whisper로 변환하여 텍스트 반환"""
    data = request.get_json()
    task_id = data.get("task_id")

    if not task_id:
        return jsonify(create_error_response("task_id가 제공되지 않았습니다")), 400

    result_dir = os.path.join(app.config['RESULTS_FOLDER'], task_id)

    if not os.path.exists(result_dir):
        return jsonify(create_error_response("결과 파일을 찾을 수 없습니다")), 404

    result_files = [f for f in os.listdir(result_dir) if f.endswith('_result.json')]

    if not result_files:
        return jsonify(create_error_response("스크립트 변환 결과를 찾을 수 없습니다")), 404

    result_path = os.path.join(result_dir, result_files[0])
    with open(result_path, 'r', encoding='utf-8') as f:
        result_data = json.load(f)

    return jsonify(result_data)

# 처리된 오디오 파일 다운로드 엔드포인트
@app.route('/download/audio/<task_id>', methods=['GET'])
def download_processed_audio(task_id):
    """처리된 오디오 파일 다운로드 엔드포인트"""
    try:
        processed_dir = os.path.join(app.config['PROCESSED_FOLDER'], task_id)

        if not os.path.exists(processed_dir):
            return jsonify(create_error_response("처리된 파일을 찾을 수 없습니다")), 404

        # 디렉토리 내 mp3 파일 찾기
        audio_files = [f for f in os.listdir(processed_dir) if f.endswith('.mp3')]

        if not audio_files:
            return jsonify(create_error_response("처리된 오디오 파일을 찾을 수 없습니다")), 404

        return send_file(
            os.path.join(processed_dir, audio_files[0]),
            mimetype='audio/mpeg',
            as_attachment=True,
            download_name=f"processed_{task_id}.mp3"
        )

    except Exception as e:
        logger.error(f"파일 다운로드 실패: {str(e)}")
        return jsonify(create_error_response(str(e))), 500

# AI 처리 결과 다운로드 엔드포인트
@app.route('/download/result/<task_id>', methods=['GET'])
def download_result(task_id):
    """AI 처리 결과 다운로드 엔드포인트"""
    try:
        result_dir = os.path.join(app.config['RESULTS_FOLDER'], task_id)

        if not os.path.exists(result_dir):
            return jsonify(create_error_response("결과 파일을 찾을 수 없습니다")), 404

        # 결과 JSON 파일 찾기
        result_files = [f for f in os.listdir(result_dir) if f.endswith('_result.json')]

        if not result_files:
            return jsonify(create_error_response("결과 파일을 찾을 수 없습니다")), 404

        return send_file(
            os.path.join(result_dir, result_files[0]),
            mimetype='application/json',
            as_attachment=True,
            download_name=f"result_{task_id}.json"
        )

    except Exception as e:
        logger.error(f"결과 다운로드 실패: {str(e)}")
        return jsonify(create_error_response(str(e))), 500

# 작업 취소 엔드포인트
@app.route('/cancel/<task_id>', methods=['POST'])
def cancel_task(task_id):
    """작업 취소 엔드포인트"""
    progress = get_progress(task_id)
    
    if not progress:
        return jsonify(create_error_response("작업을 찾을 수 없습니다")), 404

    update_progress(task_id, "cancelled", 0, "사용자에 의해 취소됨")
    return jsonify(create_success_response("작업 취소 요청됨")), 200

# 서버 상태 확인 엔드포인트
@app.route('/health', methods=['GET'])
def health_check():
    """서버 상태 확인 엔드포인트"""
    # 큐 상태도 추가
    queue_size = task_queue.qsize()

    return jsonify({
        "status": "healthy",
        "time": time.time(),
        "queue_size": queue_size,
        "active_tasks": len(get_all_progress())
    }), 200

# 요약 생성 엔드포인트
@app.route('/summary', methods=['POST', 'GET'])
def summary_api():
    """강의 요약 생성 또는 스트리밍 엔드포인트"""
    if request.method == 'POST':
        if 'lecture_id' not in request.json:
            return jsonify(create_error_response("lecture_id가 필요합니다")), 400

        lecture_id = request.json['lecture_id']

        # 스트리밍 옵션 확인
        streaming = request.json.get('streaming', True)

        # 파일 경로 확인
        if not os.path.exists(os.path.join(app.config['DATA_FOLDER'], f"{lecture_id}.txt")):
            return jsonify(create_error_response(f"lecture_id {lecture_id}에 해당하는 데이터를 찾을 수 없습니다.")), 404

        if streaming:
            # 스트리밍 방식 응답
            try:
                # 파일 로드
                with open(os.path.join(app.config['DATA_FOLDER'], f"{lecture_id}.txt"), 'r', encoding='utf-8') as f:
                    text = f.read()
                
                return Response(
                    stream_with_context(stream_summary(lecture_id, text)),
                    content_type='text/plain; charset=utf-8'
                )
            except Exception as e:
                logger.error(f"요약 스트리밍 실패: {str(e)}")
                return jsonify(create_error_response(str(e))), 500
        else:
            # 비동기 요약 생성 요청
            try:
                # 파일 로드
                with open(os.path.join(app.config['DATA_FOLDER'], f"{lecture_id}.txt"), 'r', encoding='utf-8') as f:
                    text = f.read()

                # 요약 생성
                summary_text = generate_summary(lecture_id, text)
                return jsonify(create_success_response(data={"summary": summary_text}))
            except Exception as e:
                logger.error(f"요약 생성 실패: {str(e)}")
                return jsonify(create_error_response(str(e))), 500
    else:
        # GET 요청 - 요약 HTML 페이지 반환
        return render_template('summary.html')

# 퀴즈 생성 엔드포인트
@app.route('/quizzes', methods=['POST', 'GET'])
def quizzes_api():
    """강의 퀴즈 생성 엔드포인트"""
    if request.method == 'POST':
        if 'lecture_id' not in request.json:
            return jsonify(create_error_response("lecture_id가 필요합니다")), 400

        lecture_id = request.json['lecture_id']
        streaming = request.json.get('streaming', True)

        # 요약 데이터 확인
        if lecture_id not in global_summary or not global_summary[lecture_id]:
            # 요약이 없을 경우, 파일에서 요약 찾기 시도
            summary_path = os.path.join(app.config['RESULTS_FOLDER'], lecture_id, f"{lecture_id}_summary.json")
            if os.path.exists(summary_path):
                with open(summary_path, 'r', encoding='utf-8') as f:
                    summary_data = json.load(f)
                    global_summary[lecture_id] = summary_data.get('summary_text', '')

            # 그래도 없으면 에러 반환
            if lecture_id not in global_summary or not global_summary[lecture_id]:
                return jsonify(create_error_response('요약 결과가 없습니다. 먼저 /summary 엔드포인트를 호출하세요.')), 400

        if streaming:
            # 스트리밍 방식 응답
            return Response(
                stream_with_context(stream_quiz(lecture_id)),
                content_type='text/plain; charset=utf-8'
            )
        else:
            # 비동기 퀴즈 생성 요청
            try:
                quiz_text = generate_quiz(lecture_id, global_summary[lecture_id])
                return jsonify(create_success_response(data={"quiz": quiz_text}))
            except Exception as e:
                logger.error(f"퀴즈 생성 실패: {str(e)}")
                return jsonify(create_error_response(str(e))), 500
    else:
        # GET 요청 - 퀴즈 HTML 페이지 반환
        return render_template('quiz.html')

# 학습 계획 생성 엔드포인트
@app.route('/study-plan', methods=['POST', 'GET'])
def study_plan_api():
    """강의 학습 계획 생성 엔드포인트"""
    if request.method == 'POST':
        if 'lecture_id' not in request.json:
            return jsonify(create_error_response("lecture_id가 필요합니다")), 400

        lecture_id = request.json['lecture_id']
        streaming = request.json.get('streaming', True)

        # 요약 데이터 확인
        if lecture_id not in global_summary or not global_summary[lecture_id]:
            # 요약이 없을 경우, 파일에서 요약 찾기 시도
            summary_path = os.path.join(app.config['RESULTS_FOLDER'], lecture_id, f"{lecture_id}_summary.json")
            if os.path.exists(summary_path):
                with open(summary_path, 'r', encoding='utf-8') as f:
                    summary_data = json.load(f)
                    global_summary[lecture_id] = summary_data.get('summary_text', '')

            # 그래도 없으면 에러 반환
            if lecture_id not in global_summary or not global_summary[lecture_id]:
                return jsonify(create_error_response('요약 결과가 없습니다. 먼저 /summary 엔드포인트를 호출하세요.')), 400

        if streaming:
            # 스트리밍 방식 응답
            return Response(
                stream_with_context(stream_study_plan(lecture_id)),
                content_type='text/plain; charset=utf-8'
            )
        else:
            # 비동기 학습 계획 생성 요청
            try:
                plan_text = generate_study_plan(lecture_id, global_summary[lecture_id])
                return jsonify(create_success_response(data={"plan": plan_text}))
            except Exception as e:
                logger.error(f"학습 계획 생성 실패: {str(e)}")
                return jsonify(create_error_response(str(e))), 500
    else:
        # GET 요청 - 학습 계획 HTML 페이지 반환
        return render_template('study_plan.html')

# 처리 결과 조회
@app.route('/result/<task_id>', methods=['GET'])
def get_result(task_id):
    """처리 결과 조회"""
    try:
        result_path = os.path.join(app.config['RESULTS_FOLDER'], task_id, f"{task_id}_complete.json")
        if os.path.exists(result_path):
            with open(result_path, 'r', encoding='utf-8') as f:
                result = json.load(f)
            return jsonify(result)
        else:
            return jsonify(create_error_response("결과를 찾을 수 없습니다.")), 404
    except Exception as e:
        logger.error(f"결과 조회 실패: {str(e)}")
        return jsonify(create_error_response(str(e))), 500

# 강의 인덱싱 엔드포인트
@app.route('/index/<task_id>', methods=['POST'])
def index_lecture(task_id):
    """강의 텍스트를 벡터 DB에 인덱싱"""
    try:
        if index_lecture_text(task_id):
            return jsonify(create_success_response("강의 인덱싱 완료"))
        else:
            return jsonify(create_error_response("강의 데이터를 찾을 수 없습니다.")), 404
    except Exception as e:
        logger.error(f"강의 인덱싱 실패: {str(e)}")
        return jsonify(create_error_response(str(e))), 500

# 질문-답변 API
@app.route('/query', methods=['POST'])
def query():
    """질문-답변 API"""
    try:
        data = request.json
        question = data.get('question')
        task_id = data.get('task_id')
        
        if not task_id:
            return jsonify(create_error_response("task_id가 필요합니다")), 400
        
        if not question:
            return jsonify(create_error_response("question이 필요합니다")), 400
        
        # 스트리밍 대신 전체 응답 한 번에 반환
        answer = generate_answer(task_id, question)  # 스트리밍 없는 함수 사용
        return jsonify(create_success_response(data={"answer": answer}))
        
    except Exception as e:
        logger.error(f"질문 처리 실패: {str(e)}")
        return jsonify(create_error_response(str(e))), 500

# 강의 목록 조회
@app.route('/lectures', methods=['GET'])
def get_lectures():
    """처리된 강의 목록 조회"""
    try:
        lectures = []
        for filename in os.listdir(app.config['DATA_FOLDER']):
            if filename.endswith('.txt'):
                lecture_id = filename.split('.')[0]
                # 첫 줄만 읽어서 제목으로 사용
                with open(os.path.join(app.config['DATA_FOLDER'], filename), 'r', encoding='utf-8') as f:
                    first_line = f.readline().strip()
                    title = first_line[:50] + '...' if len(first_line) > 50 else first_line
                
                lectures.append({
                    "id": lecture_id,
                    "title": title,
                    "date": os.path.getmtime(os.path.join(app.config['DATA_FOLDER'], filename))
                })
        
        # 날짜 기준 내림차순 정렬
        lectures.sort(key=lambda x: x["date"], reverse=True)
        
        return jsonify(lectures)
    except Exception as e:
        logger.error(f"강의 목록 조회 실패: {str(e)}")
        return jsonify(create_error_response(str(e))), 500

# 백엔드 통합용 처리 API
@app.route('/process', methods=['POST'])
def process_api():
    """백엔드 통합용 처리 API"""
    try:
        data = request.get_json()
        
        # 필수 파라미터 확인
        if 'lecture_id' not in data:
            return jsonify(create_error_response("lecture_id가 필요합니다")), 400
            
        lecture_id = data['lecture_id']
        source_type = data.get('source_type', 'FILE')
        callback_url = data.get('callback_url')
        
        task_id = str(uuid.uuid4())
        
        if source_type.upper() == 'YOUTUBE':
            if 'youtube_url' not in data:
                return jsonify(create_error_response("youtube_url이 필요합니다")), 400
                
            youtube_url = data['youtube_url']
            update_progress(task_id, "queued", 0, "YouTube URL 처리 대기 중")
            
            # 작업 큐에 추가 (콜백 URL과 lecture_id 포함)
            task_queue.put((task_id, None, youtube_url, callback_url, lecture_id))
            
        elif source_type.upper() == 'FILE':
            if 'file_url' not in data:
                return jsonify(create_error_response("file_url이 필요합니다")), 400
                
            file_url = data['file_url']
            update_progress(task_id, "queued", 0, "파일 처리 대기 중")
            
            # 작업 큐에 추가 (콜백 URL과 lecture_id 포함)
            task_queue.put((task_id, file_url, None, callback_url, lecture_id))
            
        else:
            return jsonify(create_error_response("지원되지 않는 source_type입니다")), 400
            
        return jsonify(create_success_response(
            message="처리 대기열에 추가됨",
            data={"task_id": task_id, "lecture_id": lecture_id, "status": "queued"}
        )), 202
            
    except Exception as e:
        logger.error(f"처리 요청 실패: {str(e)}")
        return jsonify(create_error_response(str(e))), 500

if __name__ == '__main__':
    app.run(port=5000, debug=True)