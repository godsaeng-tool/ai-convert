import os
import json
from groq import Groq
from config import logger, GROQ_API_KEY, GROQ_MODEL, RESULTS_FOLDER
from utils.queue_worker import update_progress

# Groq 클라이언트 설정
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    logger.info("Groq client initialized for text generation")
except Exception as e:
    logger.error(f"Groq client 초기화 실패: {str(e)}")
    groq_client = None

# 전역 요약 저장소
global_summary = {}

def get_ai_response(messages, temperature=0.5):
    """Groq API로 AI 응답 생성"""
    if not groq_client:
        raise ValueError("Groq 클라이언트가 초기화되지 않았습니다.")
    
    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=4000
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Groq AI 응답 생성 실패: {str(e)}")
        raise

def get_streaming_ai_response(messages, temperature=0.5):
    """Groq API로 스트리밍 AI 응답 생성"""
    if not groq_client:
        raise ValueError("Groq 클라이언트가 초기화되지 않았습니다.")
    
    try:
        stream = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=4000,
            stream=True
        )
        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content
    except Exception as e:
        logger.error(f"Groq 스트리밍 응답 생성 실패: {str(e)}")
        raise

def generate_summary(task_id, transcribed_text):
    """강의 내용 요약 생성"""
    try:
        update_progress(task_id, "summarizing", 91, "강의 내용 요약 중...")

        # 요약 생성
        messages = [
                {'role': 'system', 'content': 'you are a helpful assistant'},
                {"role": "user", "content": f'''아래의 강의 내용을 자세하게 핵심요약해서 정리해줘
                1. 강의주제를 먼저 정리해줘.
                2. 요약을 그다음에 형식에 맞춰서 정리해줘.
                3. 주제별로 번호를 메겨서 학생들이 공부할 수 있도록 자세하게 정리해줘.
                4. 학생들이 강의 요약만 보고도 강의 핵심 개념에 대해 알고 공부할 수 있도록 내용을 완전히 이해하고 적용할 수 있는 요약이어야 해.
            {transcribed_text}
                강의주제:
                요약:
                '''}
        ]

        summary_text = get_ai_response(messages, temperature=0.5)

        # 글로벌 요약에 저장
        global_summary[task_id] = summary_text

        # 결과 업데이트
        result_dir = os.path.join(RESULTS_FOLDER, task_id)
        os.makedirs(result_dir, exist_ok=True)
        result_path = os.path.join(result_dir, f"{task_id}_summary.json")
        
        summary_data = {
            "status": "summarized",
            "message": "요약 완료",
            "summary_text": summary_text
        }

        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2)

        update_progress(task_id, "summary_completed", 92, "요약 생성 완료")
        logger.info(f"요약 생성 완료: {task_id}")
        return summary_text

    except Exception as e:
        logger.error(f"요약 생성 실패: {str(e)}")
        update_progress(task_id, "failed", 0, f"요약 생성 실패: {str(e)}")
        raise

def generate_quiz(task_id, summary_text):
    """강의 요약에 기반한 퀴즈 생성"""
    try:
        update_progress(task_id, "quiz_generating", 96, "퀴즈 생성 중...")

        # 퀴즈 생성
        messages = [
                {'role': 'system', 'content': 'you are a helpful assistant'},
                {"role": "user", "content": f'''아래의 강의 내용의 핵심을 토대로 퀴즈 문제와 답 5개만 주관식으로 만들어줘!
            {summary_text}
                "문제":
                "정답":
                '''}
        ]

        quiz_text = get_ai_response(messages, temperature=0.5)

        # 결과 업데이트
        result_dir = os.path.join(RESULTS_FOLDER, task_id)
        os.makedirs(result_dir, exist_ok=True)
        result_path = os.path.join(result_dir, f"{task_id}_quiz.json")
        
        quiz_data = {
            "status": "quiz_generated",
            "message": "퀴즈 생성 완료",
            "quiz_text": quiz_text
        }

        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(quiz_data, f, ensure_ascii=False, indent=4)

        update_progress(task_id, "quiz_completed", 97, "퀴즈 생성 완료", {"quiz": quiz_text})
        return quiz_text

    except Exception as e:
        logger.error(f"퀴즈 생성 실패: {str(e)}")
        update_progress(task_id, "failed", 96, f"퀴즈 생성 실패: {str(e)}")
        raise

def generate_study_plan(task_id, summary_text, remaining_days=5):
    """강의 요약에 기반한 학습 계획 생성"""
    try:
        update_progress(task_id, "plan_generating", 98, f"{remaining_days}일치 학습 계획 생성 중...")

        # 학습 계획 생성
        messages = [
                {'role': 'system', 'content': 'you are a helpful assistant'},
                {"role": "user", "content": f'''아래의 강의 핵심요약을 토대로 해당 내용을 효과적으로 학습하기 위해 남은 {remaining_days}일 동안의 단계별 학습 계획을 만들어줘. 
                1. {remaining_days}일 커리큘럼 형태로 구성하고 
                2. 각 일차별 학습 목표, 학습 활동, 복습 방법을 포함해줘.
                3. 학습 난이도를 점진적으로 높여가면서 내용을 완전히 이해하고 적용할 수 있는 계획이어야 해.
                
            {summary_text}
                '''}
        ]

        plan_text = get_ai_response(messages, temperature=0.5)

        # 결과 업데이트
        result_dir = os.path.join(RESULTS_FOLDER, task_id)
        os.makedirs(result_dir, exist_ok=True)
        result_path = os.path.join(result_dir, f"{task_id}_study_plan.json")
        
        plan_data = {
            "status": "plan_generated",
            "message": f"{remaining_days}일치 학습 계획 생성 완료",
            "plan_text": plan_text,
            "days": remaining_days
        }

        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(plan_data, f, ensure_ascii=False, indent=4)

        update_progress(task_id, "plan_completed", 99, f"{remaining_days}일치 학습 계획 완료", {"plan": plan_text, "days": remaining_days})
        return plan_text

    except Exception as e:
        logger.error(f"학습 계획 생성 실패: {str(e)}")
        update_progress(task_id, "failed", 98, f"학습 계획 생성 실패: {str(e)}")
        raise

def stream_summary(task_id, text):
    """요약 결과를 스트리밍 방식으로 반환"""
    update_progress(task_id, "streaming_summary", 92, "요약 스트리밍 중...")

    messages = [
            {'role': 'system', 'content': 'you are a helpful assistant'},
            {"role": "user", "content": f'''아래의 강의 내용을 자세하게 핵심요약해서 정리해줘!
        {text}
            '''}
    ]

    # 전체 요약 텍스트 누적용 변수
    full_summary = ""

    # 스트리밍 생성
    for content in get_streaming_ai_response(messages, temperature=0.5):
            full_summary += content
            yield content

    # 전역 변수에 저장
    global_summary[task_id] = full_summary

def stream_quiz(task_id):
    """퀴즈 결과를 스트리밍 방식으로 반환"""
    update_progress(task_id, "streaming_quiz", 97, "퀴즈 스트리밍 중...")

    # 요약 확인
    if task_id not in global_summary:
        yield "요약 결과를 찾을 수 없습니다. 먼저 요약을 생성해주세요."
        return

    summary_text = global_summary[task_id]

    messages = [
            {'role': 'system', 'content': 'you are a helpful assistant'},
            {"role": "user", "content": f'''아래의 강의 핵심요약을 토대로 퀴즈 문제와 답 5개만 주관식으로 만들어줘!
        {summary_text}
            "문제":
            "정답":
            '''}
    ]

    # 스트리밍 생성
    for content in get_streaming_ai_response(messages, temperature=0.5):
        yield content

def stream_study_plan(task_id, remaining_days=5):
    """학습 계획 결과를 스트리밍 방식으로 반환"""
    update_progress(task_id, "plan_generating", 98, f"{remaining_days}일치 학습 계획 생성 중...")

    # 요약 확인
    if task_id not in global_summary:
        yield "요약 결과를 찾을 수 없습니다. 먼저 요약을 생성해주세요."
        return

    summary_text = global_summary[task_id]

    messages = [
            {'role': 'system', 'content': 'you are a helpful assistant'},
            {"role": "user", "content": f'''아래의 강의 핵심요약을 토대로 해당 내용을 효과적으로 학습하기 위해 남은 {remaining_days}일 동안의 단계별 학습 계획을 만들어줘. 
            1. {remaining_days}일 커리큘럼 형태로 구성하고 
            2. 각 일차별 학습 목표, 학습 활동, 복습 방법을 포함해줘.
            3. 학습 난이도를 점진적으로 높여가면서 내용을 완전히 이해하고 적용할 수 있는 계획이어야 해.
            
        {summary_text}
            '''}
    ]

    # 스트리밍 생성
    for content in get_streaming_ai_response(messages, temperature=0.5):
        yield content