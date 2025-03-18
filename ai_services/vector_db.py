import os
import faiss
import openai
from collections import deque
from config import logger, OPENAI_API_KEY, DATA_FOLDER
from llama_index.core import StorageContext, VectorStoreIndex, SimpleDirectoryReader
from llama_index.vector_stores.faiss import FaissVectorStore

# OpenAI 클라이언트 설정
openai.api_key = OPENAI_API_KEY
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# 강의 인덱스 저장소
lecture_indices = {}  # task_id를 키로 사용하여 각 강의별 인덱스 저장

# 벡터 스토어 초기화
vector_stores = {}  # task_id를 키로 사용하여 각 강의별 벡터 스토어 저장

# 대화 기록 (최근 6개 대화 저장)
conversation_history = {}  # task_id를 키로 사용하여 각 강의별 대화 기록 저장

def index_lecture_text(task_id):
    """강의 텍스트를 벡터 DB에 인덱싱"""
    try:
        # 해당 task_id의 텍스트 파일 로드
        text_path = os.path.join(DATA_FOLDER, f"{task_id}.txt")
        if not os.path.exists(text_path):
            logger.error(f"텍스트 파일을 찾을 수 없음: {text_path}")
            return False
            
        # llama_index를 사용하여 문서 로드 및 인덱싱
        documents = SimpleDirectoryReader(input_files=[text_path]).load_data()
        
        # 해당 task_id에 대한 FAISS 인덱스 생성
        faiss_index = faiss.IndexFlatL2(1536)
        vector_store = FaissVectorStore(faiss_index=faiss_index)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        
        # 인덱스 생성
        index = VectorStoreIndex.from_documents(
            documents,
            storage_context=storage_context
        )
        
        # 전역 변수에 저장
        lecture_indices[task_id] = index
        vector_stores[task_id] = vector_store
        
        # 대화 기록 초기화
        conversation_history[task_id] = deque(maxlen=6)
        
        logger.info(f"강의 텍스트 인덱싱 완료: {task_id}")
        return True
    except Exception as e:
        logger.error(f"강의 텍스트 인덱싱 실패: {str(e)}")
        return False

# 검증 함수 추가
def verify_answer(question, answer):
    """답변의 정확성을 검증"""
    try:
        verification_prompt = f"이 질문에 이 답변이 맞아? 예/아니오로만 대답해: 질문: {question} 답변: {answer}"

        verification_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 답변의 정확성을 평가하는 역할을 합니다."},
                {"role": "user", "content": verification_prompt}
            ]
        )

        # 검증 결과 추출
        content = verification_response.choices[0].message.content.strip().rstrip('.')
        logger.info(f"[검증 결과] 질문: {question} | 검증 결과: {content}")
        return content
    except Exception as e:
        logger.error(f"답변 검증 실패: {str(e)}")
        return "예"  # 검증 실패 시 기본적으로 답변이 맞다고 가정

def generate_answer(task_id, question):
    """벡터 DB에서 질문에 대한 답변 생성 (스트리밍 없음)"""
    try:
        # 벡터 DB 초기화 확인
        if not os.path.exists(os.path.join(DATA_FOLDER, f"{task_id}.txt")):
            return "해당 강의 데이터를 찾을 수 없습니다."
            
        # 대화 기록이 없으면 초기화
        if task_id not in conversation_history:
            conversation_history[task_id] = deque(maxlen=6)
        
        # 대화 기록 포함한 프롬프트 생성
        context = "\n".join([f"{role}: {content}" for role, content in conversation_history[task_id]])
        full_prompt = f"이전 대화:\n{context}\n\n사용자 질문: {question}\n\n한국어로 답변해주세요."
        
        # 대화 기록에 사용자 질문 추가
        add_to_conversation_history(task_id, "사용자", question)
            
        # 문서 로드
        documents = SimpleDirectoryReader(
            input_files=[os.path.join(DATA_FOLDER, f"{task_id}.txt")]
        ).load_data()
        
        # 벡터 인덱스 생성
        index = VectorStoreIndex.from_documents(documents)
        
        # 쿼리 엔진 생성 - 한국어 응답 설정
        query_engine = index.as_query_engine(
            system_prompt="당신은 강의 내용에 대해 답변하는 도우미입니다. 반드시 한국어로 답변해주세요."
        )
        
        # 질문에 대한 응답 생성
        response = query_engine.query(full_prompt)
        answer = response.response
        
        logger.info(f"[초기 답변] {answer[:100]}...")
        
        # 답변 검증
        verification_result = verify_answer(question, answer)
        
        # 검증 결과가 "아니오"이면 새로운 답변 생성
        if verification_result in ["아니오", "아니요"]:
            logger.info("[답변 검증] 부적절한 답변으로 간주하여 새 답변을 생성합니다.")
            
            new_response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "당신은 강의 내용에 대해 정확한 답변을 제공하는 도우미입니다. 반드시 한국어로 답변해주세요."},
                    {"role": "user", "content": question}
                ]
            )
            answer = new_response.choices[0].message.content
            logger.info(f"[수정된 답변] {answer[:100]}...")
        
        # 대화 기록에 AI 응답 추가
        add_to_conversation_history(task_id, "AI", answer)
        
        return answer
        
    except Exception as e:
        logger.error(f"질의 처리 실패: {str(e)}")
        return f"오류가 발생했습니다: {str(e)}"

def get_conversation_history(task_id):
    """대화 기록 가져오기"""
    if task_id not in conversation_history:
        conversation_history[task_id] = deque(maxlen=6)
    return conversation_history[task_id]

def add_to_conversation_history(task_id, role, content):
    """대화 기록에 추가"""
    if task_id not in conversation_history:
        conversation_history[task_id] = deque(maxlen=6)
    conversation_history[task_id].append((role, content))

def generate_streaming_answer(task_id, question):
    """벡터 DB 기반으로 스트리밍 답변 생성"""
    # 대화 기록이 없으면 초기화
    if task_id not in conversation_history:
        conversation_history[task_id] = deque(maxlen=6)
    
    # 대화 기록 포함한 프롬프트 생성
    context = "\n".join([f"{role}: {content}" for role, content in conversation_history[task_id]])
    full_prompt = f"이전 대화:\n{context}\n\n사용자 질문: {question}"
    
    # 대화 기록에 사용자 질문 추가
    add_to_conversation_history(task_id, "사용자", question)
    
    # 벡터 DB에서 관련 정보 검색
    answer = generate_answer(task_id, full_prompt)
    
    # 응답을 청크로 분할하여 스트리밍
    chunk_size = 30
    for i in range(0, len(answer), chunk_size):
        chunk = answer[i:i + chunk_size]
        yield chunk
    
    # 대화 기록에 AI 응답 추가
    add_to_conversation_history(task_id, "AI", answer)