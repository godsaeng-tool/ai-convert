import os
import yt_dlp
from groq import Groq
from config import logger, UPLOAD_FOLDER, GROQ_API_KEY, GROQ_MODEL
from utils.queue_worker import update_progress
import re

# Groq 클라이언트 설정 (무료)
groq_client = Groq(api_key=GROQ_API_KEY)

def download_progress_hook(d, task_id):
    """yt-dlp 다운로드 진행상황 훅"""
    if d['status'] == 'downloading':
        try:
            percent = d['_percent_str']
            percent = float(percent.strip('%'))
            # 다운로드는 0-40% 진행 상황에 매핑
            progress = min(40, max(10, 10 + (percent * 0.3)))
            update_progress(task_id, "downloading", progress, f"다운로드 중: {percent}%")
        except:
            pass
    elif d['status'] == 'finished':
        update_progress(task_id, "processing", 40, "다운로드 완료, 변환 시작")

def download_from_url(task_id, url):
    """URL에서 동영상 다운로드 (yt-dlp 사용)"""
    try:
        update_progress(task_id, "downloading", 10, "동영상 다운로드 시작")

        output_path = os.path.join(UPLOAD_FOLDER, f"{task_id}")
        os.makedirs(output_path, exist_ok=True)

        # 파일명 관련 옵션 추가
        ydl_opts = {
            'format': 'best',
            'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
            'noplaylist': True,
            'restrictfilenames': True,  # 안전한 파일명 사용
            'progress_hooks': [lambda d: download_progress_hook(d, task_id)],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded_file = ydl.prepare_filename(info)

        update_progress(task_id, "downloaded", 40, "동영상 다운로드 완료")
        return downloaded_file

    except Exception as e:
        logger.error(f"다운로드 실패: {str(e)}")
        update_progress(task_id, "failed", 0, f"다운로드 실패: {str(e)}")
        raise

def enhance_video_transcript(task_id, transcript):
    """비디오 트랜스크립트 개선 (Groq 무료)"""
    try:
        update_progress(task_id, "enhancing", 85, "Groq AI로 트랜스크립트 개선 중...")
        
        # 텍스트가 너무 짧으면 개선하지 않음
        if len(transcript) < 100:
            return transcript
            
        # 텍스트가 너무 길면 첫 부분만 개선
        if len(transcript) > 5000:
            transcript = transcript[:5000] + "..."
        
        messages = [
            {
                "role": "system",
                "content": "당신은 비디오 트랜스크립트를 개선하는 전문가입니다. 문법 오류를 수정하고, 적절한 문장 부호를 추가하며, 자연스러운 한국어로 다듬어주세요."
            },
            {
                "role": "user", 
                "content": f"다음 비디오 트랜스크립트를 자연스러운 한국어로 개선해주세요:\n\n{transcript}"
            }
        ]
        
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=2000
        )
        
        enhanced_text = response.choices[0].message.content
        
        update_progress(task_id, "enhanced", 90, "Groq AI 트랜스크립트 개선 완료")
        logger.info(f"Groq AI 트랜스크립트 개선 완료: {task_id}")
        
        return enhanced_text
        
    except Exception as e:
        logger.error(f"트랜스크립트 개선 실패: {str(e)}")
        # 개선 실패시 원본 반환
        return transcript