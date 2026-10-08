import asyncio, json, subprocess, sys, os

os.chdir('/root/xiaozhi-server/main/xiaozhi-server')
sys.path.insert(0, '/root/xiaozhi-server/main/xiaozhi-server')

from core.providers.asr.fun_local import ASRProvider
from core.providers.asr.base import ASRProviderBase

# 将官方示例 zh.mp3 转为 16kHz 单声道 16bit PCM（与 WS 链路解码后格式一致）
subprocess.run(
    ['ffmpeg', '-y', '-i', 'models/SenseVoiceSmall/example/zh.mp3',
     '-ar', '16000', '-ac', '1', '-f', 's16le', '/tmp/zh_test.pcm'],
    check=True, capture_output=True
)
pcm = open('/tmp/zh_test.pcm', 'rb').read()
print(f"PCM_BYTES={len(pcm)}", flush=True)

config = {"model_dir": "models/SenseVoiceSmall", "output_dir": "tmp/", "language": "auto"}
provider = ASRProvider(config, True)
print("MODEL_LOADED=OK", flush=True)

artifacts = ASRProviderBase.AudioArtifacts(
    pcm_frames=[pcm], pcm_bytes=pcm, file_path=None, temp_path=None
)
text, fp = asyncio.run(provider.speech_to_text([pcm], "asr-verify-test", artifacts))
print("RESULT_JSON=" + json.dumps(text, ensure_ascii=False), flush=True)
print("VERIFY_DONE", flush=True)
