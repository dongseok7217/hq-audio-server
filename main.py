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

# 🛠️ 수정한 부분 1: @app.get을 @app.post로 변경하여 플러터의 POST 요청을 허용합니다!
@app.post("/transpose")
def transpose_audio(
    url: str,
    semitones: int = 0,  # 🛠️ 수정한 부분 2: 플러터 앱과 똑같이 pitch 대신 semitones로 이름을 맞췄습니다.
    format: str = "MP3",
    sr: int = 44100,
    bit_depth: int = 24,
    bitrate: int = 320,
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            video_title = info.get('title', 'audio')
        clean_title = re.sub(r'[\\/*?:"<>|]', "", video_title)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"유튜브 링크 분석 실패: {e}")

    task_id = str(uuid.uuid4())
    tmp_in = f"tmp_in_{task_id}"
    tmp_rb = f"tmp_rb_{task_id}.wav"

    # 🛠️ 수정한 부분 3: 내부에서 사용되던 pitch 변수들을 모두 semitones로 안전하게 변경했습니다.
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
            'quiet': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        downloaded_wav = f"{tmp_in}.wav"

        # 🛠️ 수정한 부분 4: Rubberband 명령어에 들어가는 변수도 semitones로 변경 완료!
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
