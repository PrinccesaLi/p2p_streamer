import av
import fractions
import aiortc.codecs.h264
from config import EncoderConfig

original_h264_init = aiortc.codecs.h264.H264Encoder.__init__

def setup_universal_encoder(preset, width, height):
    def universal_encoder_init(self):
        original_h264_init(self)
        
        hardware_encoders = ["h264_nvenc", "h264_amf", "h264_qsv", "libx264"]
        selected_codec = None
        
        for codec_name in hardware_encoders:
            try:
                self.codec = av.CodecContext.create(codec_name, "w")
                selected_codec = codec_name
                break 
            except Exception:
                continue 
                
        if not selected_codec:
            raise Exception("Критическая ошибка: В системе нет доступных H.264 кодеков!")
        target_bitrate = EncoderConfig.get_bitrate(preset, width, height)

        self.codec.pix_fmt = "yuv420p" 
        self.codec.time_base = fractions.Fraction(1, 90000)
        self.codec.framerate = fractions.Fraction(60, 1)
        self.codec.bit_rate = target_bitrate 
        self.codec.options = EncoderConfig.get_options(selected_codec, preset)
        
        print(f"\n[ВИДЕО] ИНИЦИАЛИЗАЦИЯ УСПЕШНА!")
        print(f" Движок: {selected_codec.upper()} | Режим: {preset.upper()} | Битрейт: {target_bitrate // 1000} kbps\n")

    aiortc.codecs.h264.H264Encoder.__init__ = universal_encoder_init