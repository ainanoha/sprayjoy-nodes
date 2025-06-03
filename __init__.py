from .upload_aliyun_oss import UploadAliyunOSS

NODE_CLASS_MAPPINGS = {
    "UploadAliyunOSS": UploadAliyunOSS
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "UploadAliyunOSS": "Upload to Aliyun OSS"
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS'] 