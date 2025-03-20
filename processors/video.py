import os
import yt_dlp
from config import logger, UPLOAD_FOLDER
from utils.queue_worker import update_progress
import re
from openai import OpenAI

# OpenAI 클라이언트 설정
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

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

def enhance_video_transcript(transcript):
    """영상 스크립트 품질 개선"""
    try:
        # 텍스트가 너무 길면 분할
        chunks = []
        current_chunk = ""
        words = transcript.split()
        
        for word in words:
            if len(current_chunk) + len(word) < 3500:
                current_chunk += word + " "
            else:
                chunks.append(current_chunk.strip())
                current_chunk = word + " "
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        enhanced_chunks = []
        
        for chunk in chunks:
            prompt = f"""
다음은 강의 영상의 음성 인식 스크립트입니다:

{chunk}

이 스크립트를 교육 자료로 개선해주세요:
1. "음", "그" 같은 간투사 제거
2. 불완전한 문장 완성
3. 반복되는 표현 정리
4. 구어체를 정돈된 문어체로 변환
5. 문단으로 적절히 구분

원본 내용의 의미를 유지하되, 읽기 쉽고 명확한 형태로 만들어주세요.
"""
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "당신은 강의 스크립트를 교육 자료로 변환하는 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )
            
            enhanced_chunks.append(response.choices[0].message.content)
        
        enhanced_transcript = "\n\n".join(enhanced_chunks)
        logger.info(f"스크립트 품질 개선 완료: {len(transcript)} → {len(enhanced_transcript)} 문자")
        return enhanced_transcript
    except Exception as e:
        logger.error(f"스크립트 품질 개선 중 오류: {str(e)}")
        return transcript  # 오류 시 원본 반환