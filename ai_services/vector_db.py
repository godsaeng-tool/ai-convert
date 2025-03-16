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

def generate_answer(task_id, question):
    """벡터 DB 기반으로 답변 생성"""
    if task_id not in lecture_indices:
        # 인덱스가 없으면 생성 시도
        if not index_lecture_text(task_id):
            return "해당 강의 데이터를 찾을 수 없습니다."
    
    # 쿼리 엔진 생성
    query_engine = lecture_indices[task_id].as_query_engine()
    
    # 벡터 DB 기반으로 답변 생성
    response = query_engine.query(question)
    
    if hasattr(response, 'text'):
        return response.text  # Response 객체에서 텍스트 추출
    return str(response)  # 응답을 문자열로 변환

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