import os
import re
import uuid
import subprocess
from fastapi import FastAPI, Query, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
import yt_dlp

app = FastAPI()

def remove_file(path: str):
    if os.path.exists(path):
        os.remove(path)

@app.get("/")
def home():
    return {"status": "HQ Audio Transposer Server is Running!"}

@app.post("/transpose")
def transpose_audio(
    url: str,
    semitones: int = 0,
    format: str = "MP3",
    sr: int = 44100,
    bit_depth: int = 24,
    bitrate: int = 320,
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    # 🛠️ [차단 우회 포인트 1] 유튜브가 로봇으로 의심하지 못하게 진짜 맥북 브라우저인 척 속이는 헤더 정보입니다.
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    }

    try:
        # 🛠️ [차단 우회 포인트 2] 링크 분석할 때 우회 헤더를 주입합니다.
        ydl_info_opts = {
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'http_headers': headers
        }
        with yt_dlp.YoutubeDL(ydl_info_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_title = info.get('title', 'audio')
        clean_title = re.sub(r'[\\/*?:"<>|]', "", video_title)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"유튜브 링크 분석 실패: {e}")

    task_id = str(uuid.uuid4())
    tmp_in = f"tmp_in_{task_id}"
    tmp_rb = f"tmp_rb_{task_id}.wav"

    pitch_sign = f"+{semitones}" if semitones > 0 else str(semitones)
    if semitones == 0: pitch_sign = "0"
    final_filename = f"{clean_title} {pitch_sign}.{format.lower()}"

    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': tmp_in,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'http_headers': headers  # 🛠️ [차단 우회 포인트 3] 실제 파일 다운로드할 때도 헤더 주입!
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        downloaded_wav = f"{tmp_in}.wav"

        rb_cmd = f"rubberband --formant --pitch {semitones} {downloaded_wav} {tmp_rb}"
        subprocess.run(rb_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if format.upper() == 'WAV':
            bit_depth_fmt = f"pcm_s{bit_depth}le"
            cmd = f"ffmpeg -y -i {tmp_rb} -ar {sr} -c:a {bit_depth_fmt} \"{final_filename}\""
        else:
            cmd = f"ffmpeg -y -i {tmp_rb} -ar {sr} -b:a {bitrate}k \"{final_filename}\""

        subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if os.path.exists(downloaded_wav): os.remove(downloaded_wav)
        if os.path.exists(tmp_rb): os.remove(tmp_rb)

        background_tasks.add_task(remove_file, final_filename)

        return FileResponse(
            path=final_filename, 
            filename=final_filename, 
            media_type="application/octet-stream"
         )

    except Exception as e:
        if os.path.exists(f"{tmp_in}.wav"): os.remove(f"{tmp_in}.wav")
        if os.path.exists(tmp_rb): os.remove(tmp_rb)
        if os.path.exists(final_filename): os.remove(final_filename)
        raise HTTPException(status_code=500, detail=str(e))
