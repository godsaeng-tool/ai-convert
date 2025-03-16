import json
import requests
from config import logger, DEFAULT_CALLBACK_URL

def send_callback(callback_url, data):
    """결과를 콜백 URL로 전송"""
    try:
        # 대체 URL 사용
        if not callback_url:
            callback_url = DEFAULT_CALLBACK_URL
        
        # 요청 데이터 로깅
        logger.info(f"콜백 URL: {callback_url}")
        logger.info(f"콜백 데이터: {data}")
        
        # 헤더 추가
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'AI-Server/1.0'
        }
        
        response = requests.post(callback_url, json=data, headers=headers)
        
        # 응답 로깅
        logger.info(f"콜백 응답 상태 코드: {response.status_code}")
        logger.info(f"콜백 응답 내용: {response.text}")
        
        if response.status_code == 200:
            logger.info(f"콜백 전송 성공: {callback_url}")
            return True
        else:
            logger.error(f"콜백 전송 실패: {response.status_code}, {response.text}")
            return False
    except Exception as e:
        logger.error(f"콜백 전송 중 오류: {str(e)}")
        return False

def format_response(status=True, message="", data=None, status_code=200):
    """API 응답을 일관된 형식으로 포맷팅"""
    response = {
        "success": status,
        "message": message
    }
    
    if data:
        response["data"] = data
    
    return response, status_code

def create_error_response(message, status_code=400):
    """에러 응답 생성"""
    return format_response(status=False, message=message, status_code=status_code)

def create_success_response(message="Success", data=None):
    """성공 응답 생성"""
    return format_response(status=True, message=message, data=data)