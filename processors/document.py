import os
import fitz  # PyMuPDF
import pptx
from config import logger

def extract_text_from_pdf(file_path):
    """PDF 파일에서 텍스트 추출 - 여러 라이브러리 시도"""
    text = ""
    errors = []
    
    # 1. PyMuPDF 시도 (최우선)
    try:
        doc = fitz.open(file_path)
        for page_num in range(len(doc)):
            page = doc[page_num]
            text += page.get_text() + "\n\n"
        doc.close()
        logger.info(f"PyMuPDF로 PDF 텍스트 추출 성공: {file_path}")
        return text
    except Exception as e:
        error_msg = f"PyMuPDF 추출 실패: {str(e)}"
        logger.warning(error_msg)
        errors.append(error_msg)
    
    # 2. pdfplumber 시도 (2순위)
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n\n"
        
        if text.strip():  # 텍스트가 추출되었는지 확인
            logger.info(f"pdfplumber로 PDF 텍스트 추출 성공: {file_path}")
            return text
        else:
            error_msg = "pdfplumber가 텍스트를 추출했지만 내용이 비어 있습니다"
            logger.warning(error_msg)
            errors.append(error_msg)
    except Exception as e:
        error_msg = f"pdfplumber 추출 실패: {str(e)}"
        logger.warning(error_msg)
        errors.append(error_msg)
    
    # 3. PyPDF2 시도 (3순위)
    try:
        import PyPDF2
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n\n"
        
        if text.strip():  # 텍스트가 추출되었는지 확인
            logger.info(f"PyPDF2로 PDF 텍스트 추출 성공: {file_path}")
            return text
        else:
            error_msg = "PyPDF2가 텍스트를 추출했지만 내용이 비어 있습니다"
            logger.warning(error_msg)
            errors.append(error_msg)
    except Exception as e:
        error_msg = f"PyPDF2 추출 실패: {str(e)}"
        logger.warning(error_msg)
        errors.append(error_msg)
    
    # 모든 방법이 실패한 경우
    error_message = "모든 PDF 텍스트 추출 방법이 실패했습니다:\n" + "\n".join(errors)
    logger.error(error_message)
    raise Exception(error_message)

def extract_text_from_ppt(file_path):
    """PPT 파일에서 텍스트 추출"""
    try:
        presentation = pptx.Presentation(file_path)
        text = ""
        
        for slide in presentation.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    text += shape.text + "\n"
            text += "\n"
        
        logger.info(f"PPT 텍스트 추출 완료: {file_path}")
        return text
    except Exception as e:
        logger.error(f"PPT 텍스트 추출 실패: {str(e)}")
        raise

def process_document(file_path, task_id, result_dir, data_dir):
    """문서 파일(PDF/PPT) 처리 및 텍스트 추출"""
    try:
        # 확장자 확인
        file_ext = file_path.split('.')[-1].lower()
        
        # 파일 타입에 따라 적절한 처리 함수 호출
        if file_ext == 'pdf':
            extracted_text = extract_text_from_pdf(file_path)
        elif file_ext in ['ppt', 'pptx']:
            extracted_text = extract_text_from_ppt(file_path)
        else:
            raise ValueError(f"지원되지 않는 문서 형식: {file_ext}")
        
        # 추출된 텍스트 저장
        text_path = os.path.join(data_dir, f"{task_id}.txt")
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write(extracted_text)
        
        return {
            "success": True,
            "message": "문서 텍스트 추출 완료",
            "text_path": text_path,
            "text_content": extracted_text
        }
    
    except Exception as e:
        logger.error(f"문서 처리 실패: {str(e)}")
        return {
            "success": False,
            "message": f"문서 처리 실패: {str(e)}"
        }