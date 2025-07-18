import os
import faiss
from groq import Groq
from collections import deque
from config import (
    logger, GROQ_API_KEY, GROQ_MODEL, EMBEDDING_MODEL, DATA_FOLDER
)
from llama_index.core import StorageContext, VectorStoreIndex, SimpleDirectoryReader, Document
from llama_index.vector_stores.faiss import FaissVectorStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core import Settings
import re

# Groq 클라이언트 설정
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    logger.info("Groq client initialized for vector DB Q&A")
except Exception as e:
    logger.error(f"Groq client 초기화 실패: {str(e)}")
    groq_client = None

# HuggingFace 임베딩 모델 설정
try:
    embedding_model = HuggingFaceEmbedding(model_name=EMBEDDING_MODEL)
    Settings.embed_model = embedding_model
    logger.info(f"HuggingFace 임베딩 모델 로드 완료: {EMBEDDING_MODEL}")
except Exception as e:
    logger.error(f"HuggingFace 임베딩 모델 로드 실패: {str(e)}")
    embedding_model = None

# 강의 인덱스 저장소
lecture_indices = {}  # task_id를 키로 사용하여 각 강의별 인덱스 저장

# 벡터 스토어 초기화
vector_stores = {}  # task_id를 키로 사용하여 각 강의별 벡터 스토어 저장

# 대화 기록 (최근 6개 대화 저장)
conversation_history = {}  # task_id를 키로 사용하여 각 강의별 대화 기록 저장

# 어조 선택 딕셔너리 추가
tones = {
    "a": "까칠하고 깔보는듯한",
    "b": "기본",
    "c": "따뜻하고 다정하고 정중한"
}

def get_qa_response(messages, temperature=0.7):
    """질의응답을 위한 Groq API 응답 생성"""
    if not groq_client:
        raise ValueError("Groq 클라이언트가 초기화되지 않았습니다.")
    
    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=2000
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Groq 질의응답 생성 실패: {str(e)}")
        raise

def index_lecture_text(task_id):
    """강의 텍스트를 벡터 DB에 인덱싱 - HuggingFace 임베딩 사용"""
    if not embedding_model:
        logger.error("임베딩 모델이 로드되지 않았습니다.")
        return False
    
    try:
        # 해당 task_id의 텍스트 파일 로드
        text_path = os.path.join(DATA_FOLDER, f"{task_id}.txt")
        if not os.path.exists(text_path):
            logger.error(f"텍스트 파일을 찾을 수 없음: {text_path}")
            return False
        
        # 텍스트 파일 직접 읽기
        with open(text_path, 'r', encoding='utf-8') as f:
            text_content = f.read()
        
        # 문서를 의미 있는 청크로 분할
        documents = []
        
        # 페이지 구분자 패턴
        page_pattern = r'---\s*(페이지|슬라이드)\s*\d+\s*---'
        
        # 페이지/슬라이드 단위로 분할
        parts = re.split(page_pattern, text_content)
        current_page_info = ""
        
        for i, part in enumerate(parts):
            # 페이지/슬라이드 정보 처리
            if i % 2 == 1:  # 홀수 인덱스는 '페이지' 또는 '슬라이드' 텍스트
                current_page_info = part
                continue
                
            if not part.strip():
                continue
            
            # 페이지 내용을 단락으로 분할
            paragraphs = re.split(r'\n{2,}', part)
            
            for para in paragraphs:
                para = para.strip()
                if len(para) < 50:  # 너무 짧은 단락은 건너뛰기
                    continue
                
                # 단락을 문서로 변환
                doc = Document(
                    text=para,
                    metadata={
                        "page_info": f"{current_page_info} {(i//2)+1}" if current_page_info else f"페이지 {(i//2)+1}",
                        "task_id": task_id
                    }
                )
                documents.append(doc)
        
        # 청크가 너무 적으면 단순 분할 적용
        if len(documents) < 3:
            documents = []
            
            # 단순 분할 (500자 단위)
            chunks = [text_content[i:i+500] for i in range(0, len(text_content), 500)]
            
            for i, chunk in enumerate(chunks):
                if len(chunk.strip()) < 100:  # 너무 짧은 청크는 건너뛰기
                    continue
                
                doc = Document(
                    text=chunk.strip(),
                    metadata={"chunk_id": i, "task_id": task_id}
                )
                documents.append(doc)
        
        logger.info(f"텍스트를 {len(documents)}개 청크로 분할")
        
        # FAISS 벡터 스토어 생성 (HuggingFace 임베딩 사용)
        # HuggingFace 모델의 임베딩 차원 확인 (보통 384차원)
        embed_dim = 384  # all-MiniLM-L6-v2의 차원
        faiss_index = faiss.IndexFlatL2(embed_dim)
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
        
        logger.info(f"강의 텍스트 인덱싱 완료 (HuggingFace 임베딩): {task_id}")
        return True
    except Exception as e:
        logger.error(f"강의 텍스트 인덱싱 실패: {str(e)}")
        return False

def generate_answer(task_id, question, tone="b"):
    """벡터 DB에서 질문에 대한 답변 생성 (Groq 사용)"""
    try:
        # 벡터 DB 초기화 확인
        if not os.path.exists(os.path.join(DATA_FOLDER, f"{task_id}.txt")):
            return "해당 강의 데이터를 찾을 수 없습니다."
            
        # 대화 기록이 없으면 초기화
        if task_id not in conversation_history:
            conversation_history[task_id] = deque(maxlen=6)
        
        # 어조 정보 가져오기
        tone_description = tones.get(tone, tones["b"])  # 기본값은 정중한 어조
        
        # 대화 기록 포함한 프롬프트 생성
        context = "\n".join([f"{role}: {content}" for role, content in conversation_history[task_id]])
        
        # 대화 기록에 사용자 질문 추가
        add_to_conversation_history(task_id, "사용자", question)
            
        # 인덱스 확인 및 로드
        if task_id not in lecture_indices:
            # 문서 로드
            documents = SimpleDirectoryReader(
                input_files=[os.path.join(DATA_FOLDER, f"{task_id}.txt")]
            ).load_data()
            
            # 벡터 인덱스 생성
            index = VectorStoreIndex.from_documents(documents)
            lecture_indices[task_id] = index
        else:
            index = lecture_indices[task_id]
        
        # 개선된 검색: 레트리버 직접 사용
        retriever = index.as_retriever(
            similarity_top_k=5  # 상위 5개 결과 검색
        )
        
        # 질문에 대한 관련 문서 검색
        nodes = retriever.retrieve(question)
        
        # 검색 결과 포맷팅
        retrieved_info = []
        for i, node in enumerate(nodes):
            # 메타데이터 활용
            page_info = node.metadata.get("page_info", "")
            chunk_id = node.metadata.get("chunk_id", "")
            
            context_header = f"[정보 {i+1}]"
            if page_info:
                context_header += f" ({page_info})"
            elif chunk_id:
                context_header += f" (청크 {chunk_id})"
                
            retrieved_info.append(f"{context_header}\n{node.text}")
        
        retrieved_context = "\n\n".join(retrieved_info)
        
        # 개선된 프롬프트
        full_prompt = f"""
이전 대화:
{context}

다음은 질문에 관련된 강의 자료입니다:
{retrieved_context}

사용자 질문: {question}

위 정보를 바탕으로 상세하게 답변해주세요. 
검색된 여러 부분의 정보를 종합하여 완전한 답변을 제공하세요.
정보에 없는 내용은 '강의 내용에 해당 정보가 없습니다'라고 명시하세요.
{tone_description} 어조로 한국어로 답변하세요.
"""
        
        # 응답 생성 - Groq 사용
        messages = [
                {"role": "system", "content": f"당신은 강의 내용에 대해 답변하는 도우미입니다. {tone_description} 어조로 한국어로 답변해주세요."},
                {"role": "user", "content": full_prompt}
            ]
        
        answer = get_qa_response(messages, temperature=0.7)
        
        # 대화 기록에 AI 응답 추가
        add_to_conversation_history(task_id, "AI", answer)
        
        return answer
        
    except Exception as e:
        logger.error(f"질의 처리 실패: {str(e)}")
        return f"오류가 발생했습니다: {str(e)}"

def generate_streaming_answer(task_id, question, tone="b"):
    """벡터 DB 기반으로 스트리밍 답변 생성"""
    # 대화 기록이 없으면 초기화
    if task_id not in conversation_history:
        conversation_history[task_id] = deque(maxlen=6)
    
    # 어조 정보 가져오기
    tone_description = tones.get(tone, tones["b"])  # 기본값은 정중한 어조
    
    # 대화 기록 포함한 프롬프트 생성
    context = "\n".join([f"{role}: {content}" for role, content in conversation_history[task_id]])
    full_prompt = f"이전 대화:\n{context}\n\n사용자 질문: {question}\n\n{tone_description} 어조로 한국어로 답변해주세요."
    
    # 대화 기록에 사용자 질문 추가
    add_to_conversation_history(task_id, "사용자", question)
    
    # 벡터 DB에서 관련 정보 검색 (어조 포함)
    answer = generate_answer(task_id, full_prompt, tone)
    
    # 응답을 청크로 분할하여 스트리밍
    chunk_size = 30
    for i in range(0, len(answer), chunk_size):
        chunk = answer[i:i + chunk_size]
        yield chunk
    
    # 대화 기록에 AI 응답 추가
    add_to_conversation_history(task_id, "AI", answer)

def add_to_conversation_history(task_id, role, content):
    """대화 기록에 메시지 추가"""
    if task_id not in conversation_history:
        conversation_history[task_id] = deque(maxlen=6)
    conversation_history[task_id].append((role, content))