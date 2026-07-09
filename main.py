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
    # 🛠️ [우회력 극대화] 안드로이드 음악 앱과 iOS 앱 클라이언트를 동시에 주입하여 차단을 강제로 뚫어버립니다.
    ydl_opts_base = {
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android_music', 'ios'],
                'skip': ['webpage', 'hls']
            }
        }
    }

    try:
        # 1. 링크 분석 단계
        with yt_dlp.YoutubeDL(ydl_opts_base) as ydl:
            info = ydl.extract_info(url, download=False)
            video_title = info.get('title', 'audio')
        clean_title = re.sub(r'[\\/*?:"<>|]', "", video_title)
    except Exception as e:
        # 로그에도 에러를 찍고, 앱에도 구체적인 에러 내용을 넘겨줍니다.
        print(f"yt-dlp Extraction Error: {e}")
        raise HTTPException(status_code=400, detail=f"유튜브 다운로드 차단됨 ({str(e)[:60]})")

    task_id = str(uuid.uuid4())
    tmp_in = f"tmp_in_{task_id}"
    tmp_rb = f"tmp_rb_{task_id}.wav"

    pitch_sign = f"+{semitones}" if semitones > 0 else str(semitones)
    if semitones == 0: pitch_sign = "0"
    final_filename = f"{clean_title} {pitch_sign}.{format.lower()}"

    try:
        # 2. 실제 다운로드 옵션 세팅
        ydl_download_opts = {
            **ydl_opts_base,
            'format': 'bestaudio/best',
            'outtmpl': tmp_in,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '192',
            }],
        }
        
        with yt_dlp.YoutubeDL(ydl_download_opts) as ydl:
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
