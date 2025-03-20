import threading
import queue
import time
from concurrent.futures import ThreadPoolExecutor
from config import logger, MAX_WORKERS

# 작업 큐 및 진행 상황 추적
task_queue = queue.Queue()
progress_tracker = {}
lock = threading.Lock()

# 스레드 풀 생성
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

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

def get_progress(task_id):
    """특정 작업의 진행 상황 조회"""
    with lock:
        if task_id not in progress_tracker:
            return None
        return progress_tracker[task_id]

def get_all_progress():
    """모든 작업의 진행 상황 조회"""
    with lock:
        return progress_tracker.copy()

def worker_function(processor_func):
    def worker():
        while True:
            try:
                # 작업 큐에서 작업 가져오기
                task = task_queue.get()
                if len(task) >= 6:  # 새 형식 (remaining_days 포함)
                    task_id, file_path, youtube_url, callback_url, lecture_id, remaining_days = task
                else:  # 이전 형식 호환성 유지
                    task_id, file_path, youtube_url, callback_url, lecture_id = task
                    remaining_days = 5  # 기본값
                
                # 프로세서 함수 호출 (남은 일수 전달)
                processor_func(task_id, file_path, youtube_url, callback_url, lecture_id, remaining_days)
                
                # 작업 완료 표시
                task_queue.task_done()
            except Exception as e:
                logger.error(f"작업 처리 중 오류 발생: {str(e)}")
    return worker

def start_workers(worker_function, num_workers=MAX_WORKERS):
    """워커 스레드들을 시작"""
    worker_threads = []
    for _ in range(num_workers):
        t = threading.Thread(target=worker_function)
        t.daemon = True
        t.start()
        worker_threads.append(t)
    return worker_threads

def stop_workers(num_workers=MAX_WORKERS):
    """워커 스레드들을 중지"""
    for _ in range(num_workers):
        task_queue.put(None)
    
    # ThreadPoolExecutor 종료
    executor.shutdown(wait=False)