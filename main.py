import os
import re
import uuid
import subprocess
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse

app = FastAPI()

def remove_file(path: str):
    if os.path.exists(path):
        os.remove(path)

@app.get("/")
def home():
    return {"status": "HQ Audio Transposer Server is Running!"}

@app.post("/transpose")
async def transpose_audio(
    file: UploadFile = File(...),
    semitones: int = Form(0),
    format: str = Form("MP3"),
    sr: int = Form(44100),
    bit_depth: int = Form(24),
    bitrate: int = Form(320),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    task_id = str(uuid.uuid4())
    tmp_upload = f"tmp_upload_{task_id}"
    tmp_in = f"tmp_in_{task_id}.wav"
    tmp_rb = f"tmp_rb_{task_id}.wav"
    
    # 원본 파일명 안전하게 정제
    orig_filename = file.filename or "audio"
    clean_title = os.path.splitext(orig_filename)[0]
    clean_title = re.sub(r'[\\/*?:"<>|]', "", clean_title)
    
    pitch_sign = f"+{semitones}" if semitones > 0 else str(semitones)
    if semitones == 0: pitch_sign = "0"
    final_filename = f"{clean_title} {pitch_sign}.{format.lower()}"

    try:
        # 1. 맥북에서 업로드한 음원 스트림 데이터를 서버 디스크에 임시 저장
        with open(tmp_upload, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # 2. FFmpeg를 활용해 포맷 상관없이 깨끗한 고음질 고정 샘플레이트 WAV로 변환
        conv_cmd = f"ffmpeg -y -i {tmp_upload} -ar {sr} {tmp_in}"
        subprocess.run(conv_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(tmp_upload): os.remove(tmp_upload)

        if not os.path.exists(tmp_in):
            raise HTTPException(status_code=400, detail="업로드된 오디오 파일 디코딩에 실패했습니다.")

        # 3. Rubberband 초고음질 음정 변환 연산 수행 (--formant 옵션으로 음색 보존)
        rb_cmd = f"rubberband --formant --pitch {semitones} {tmp_in} {tmp_rb}"
        subprocess.run(rb_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 4. 최종 결과물 포맷 인코딩 (WAV 혹은 최고음질 MP3 320kbps)
        if format.upper() == 'WAV':
            bit_depth_fmt = f"pcm_s{bit_depth}le"
            cmd = f"ffmpeg -y -i {tmp_rb} -ar {sr} -c:a {bit_depth_fmt} \"{final_filename}\""
        else:
            cmd = f"ffmpeg -y -i {tmp_rb} -ar {sr} -b:a {bitrate}k \"{final_filename}\""

        subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 연산에 쓰인 대용량 임시 파일 청소
        if os.path.exists(tmp_in): os.remove(tmp_in)
        if os.path.exists(tmp_rb): os.remove(tmp_rb)

        # 파일 전송 완료 후 최종 파일 삭제 작업 백그라운드 등록
        background_tasks.add_task(remove_file, final_filename)

        return FileResponse(
            path=final_filename, 
            filename=final_filename, 
            media_type="application/octet-stream"
         )

    except Exception as e:
        if os.path.exists(tmp_in): os.remove(tmp_in)
        if os.path.exists(tmp_rb): os.remove(tmp_rb)
        if os.path.exists(final_filename): os.remove(final_filename)
        raise HTTPException(status_code=500, detail=str(e))
