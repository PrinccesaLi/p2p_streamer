class EncoderConfig:
    
    @staticmethod
    def get_bitrate(preset, width, height):
        base_pixels = 1920 * 1080
        current_pixels = width * height
        ratio = current_pixels / base_pixels

        if preset == "speed":
            base_bitrate = 3_000_000
        elif preset == "quality":
            base_bitrate = 10_000_000 
        elif preset == "super_quality":
            base_bitrate = 18_000_000 
        elif preset == "super_duper":
            base_bitrate = 30_000_000  
        else: 
            base_bitrate = 6_000_000

        return int(base_bitrate * ratio)

    @staticmethod
    def get_options(codec_name, preset="balance"):
        # 1.  AMD (AMF)
        amf_presets = {
            "speed": {"usage": "lowlatency", "rc": "cbr", "quality": "speed", "gop": "60", "bf": "0"},
            "balance": {"usage": "lowlatency", "rc": "vbr", "quality": "balanced", "gop": "60", "bf": "0"},
            "quality": {"usage": "lowlatency", "rc": "vbr", "quality": "quality", "gop": "60", "bf": "0", "vbaq": "1"},
            "super_quality": {"usage": "transcoding", "rc": "vbr", "quality": "quality", "gop": "120", "bf": "2", "profile": "high", "vbaq": "1", "pe": "1"},
            "super_duper": {"usage": "transcoding", "rc": "vbr", "quality": "quality", "gop": "240", "bf": "3", "profile": "high", "vbaq": "1", "pe": "1", "coder": "cabac"}
        }
        
        # 2. NVIDIA (NVENC)
        nvenc_presets = {
            "speed": {"preset": "p1", "tune": "zerolatency", "rc": "cbr", "zerolatency": "1", "gop": "60", "bf": "0"},
            "balance": {"preset": "p4", "tune": "zerolatency", "rc": "vbr", "zerolatency": "1", "gop": "60", "bf": "0"},
            "quality": {
                "preset": "p7", "tune": "hq", "rc": "vbr", "gop": "60", "bf": "2",
                "spatial-aq": "1", "temporal-aq": "1"
            },
            "super_quality": {
                "preset": "p7", "tune": "hq", "rc": "vbr", "gop": "120", "bf": "4", "profile": "high",
                "spatial-aq": "1", "temporal-aq": "1", "rc-lookahead": "32", "b_ref_mode": "middle"
            },
            "super_duper": {
                "preset": "p7", "tune": "hq", "rc": "vbr", "gop": "240", "bf": "4", "profile": "high",
                "spatial-aq": "1", "temporal-aq": "1", "rc-lookahead": "32", "b_ref_mode": "middle",
                "multipass": "fullres" 
            }
        }

        # 3. Intel (QSV)
        qsv_presets = {
            "speed": {"preset": "veryfast"},
            "balance": {"preset": "faster"},
            "quality": {"preset": "medium", "look_ahead": "1"},
            "super_quality": {"preset": "veryslow", "look_ahead": "1", "profile": "high", "extbrc": "1"},
            "super_duper": {"preset": "veryslow", "look_ahead": "1", "profile": "high", "extbrc": "1"}
        }

        # 4. (libx264)
        x264_presets = {
            "speed": {"preset": "ultrafast", "tune": "zerolatency"},
            "balance": {"preset": "superfast", "tune": "zerolatency"},
            "quality": {"preset": "fast", "tune": "zerolatency"},
            "super_quality": {"preset": "medium", "tune": "film", "profile": "high"},
            "super_duper": {"preset": "slower", "tune": "film", "profile": "high"}
        }

        if codec_name == "h264_nvenc": return nvenc_presets.get(preset, nvenc_presets["balance"])
        elif codec_name == "h264_amf": return amf_presets.get(preset, amf_presets["balance"])
        elif codec_name == "h264_qsv": return qsv_presets.get(preset, qsv_presets["balance"])
        else: return x264_presets.get(preset, x264_presets["balance"])