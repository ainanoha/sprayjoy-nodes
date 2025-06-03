import torch
import numpy as np
from PIL import Image
import io
import os
import oss2
from datetime import datetime


class UploadAliyunOSS:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "access_key_id": ("STRING", {"default": "", "multiline": False}),
                "access_key_secret": ("STRING", {"default": "", "multiline": False}),
                "endpoint": (
                    "STRING",
                    {
                        "default": "https://oss-cn-hangzhou.aliyuncs.com",
                        "multiline": False,
                    },
                ),
                "bucket_name": ("STRING", {"default": "", "multiline": False}),
                "dest_path": (
                    "STRING",
                    {"default": "comfyui/{timestamp}.png", "multiline": False},
                ),
            },
            "optional": {
                "image_format": (["PNG", "JPEG", "WEBP"], {"default": "PNG"}),
                "jpeg_quality": (
                    "INT",
                    {"default": 95, "min": 1, "max": 100, "step": 1},
                ),
                "output_image": ("BOOLEAN", {"default": True}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "file_url")
    FUNCTION = "upload_image"
    CATEGORY = "image/upload"
    DESCRIPTION = "Upload image to Aliyun OSS and return the original image"
    OUTPUT_NODE = True  # 标记为输出节点，避免 "no outputs" 错误

    def upload_image(
        self,
        image,
        access_key_id,
        access_key_secret,
        endpoint,
        bucket_name,
        dest_path,
        image_format="PNG",
        jpeg_quality=95,
        output_image=True,
    ):
        file_url = ""

        # 参数验证
        if not access_key_id.strip():
            print("❌ AccessKey ID 不能为空")
            if output_image:
                return (image, file_url)
            else:
                return {"ui": {"text": ["AccessKey ID 不能为空"]}}

        if not access_key_secret.strip():
            print("❌ AccessKey Secret 不能为空")
            if output_image:
                return (image, file_url)
            else:
                return {"ui": {"text": ["AccessKey Secret 不能为空"]}}

        if not bucket_name.strip():
            print("❌ Bucket 名称不能为空")
            if output_image:
                return (image, file_url)
            else:
                return {"ui": {"text": ["Bucket 名称不能为空"]}}

        if not dest_path.strip():
            print("❌ 目标路径不能为空")
            if output_image:
                return (image, file_url)
            else:
                return {"ui": {"text": ["目标路径不能为空"]}}

        try:
            # 转换图像格式
            if len(image.shape) == 4:
                # 批处理，只处理第一张图片
                image_tensor = image[0]
            else:
                image_tensor = image

            # 将tensor转换为PIL Image
            image_np = (image_tensor.cpu().numpy() * 255).astype(np.uint8)
            pil_image = Image.fromarray(image_np)

            # 处理目标路径
            processed_dest_path = self._process_dest_path(dest_path, image_format)

            # 将图像转换为字节流
            image_bytes = io.BytesIO()
            if image_format.upper() == "JPEG":
                # 如果是JPEG，需要转换为RGB模式（去除alpha通道）
                if pil_image.mode in ("RGBA", "LA"):
                    # 创建白色背景
                    background = Image.new("RGB", pil_image.size, (255, 255, 255))
                    if pil_image.mode == "RGBA":
                        background.paste(
                            pil_image, mask=pil_image.split()[-1]
                        )  # 使用alpha通道作为遮罩
                    else:
                        background.paste(pil_image)
                    pil_image = background
                pil_image.save(
                    image_bytes, format="JPEG", quality=jpeg_quality, optimize=True
                )
            elif image_format.upper() == "WEBP":
                pil_image.save(
                    image_bytes, format="WEBP", quality=jpeg_quality, optimize=True
                )
            else:  # PNG
                pil_image.save(image_bytes, format="PNG", optimize=True)

            image_bytes.seek(0)

            # 初始化OSS客户端
            auth = oss2.Auth(access_key_id, access_key_secret)
            bucket = oss2.Bucket(auth, endpoint, bucket_name)

            # 设置Content-Type
            content_type = {
                "PNG": "image/png",
                "JPEG": "image/jpeg",
                "WEBP": "image/webp",
            }.get(image_format.upper(), "image/png")

            # 上传图像
            result = bucket.put_object(
                processed_dest_path,
                image_bytes.getvalue(),
                headers={"Content-Type": content_type},
            )

            if result.status == 200:
                print(f"✅ 图像成功上传到OSS: {processed_dest_path}")
                # 生成文件访问URL
                file_url = self._generate_file_url(
                    endpoint, bucket_name, processed_dest_path
                )
                # print(f"🔗 文件访问链接: {file_url}")
                print(f"📊 文件大小: {len(image_bytes.getvalue())} bytes")

                # 返回结果
                if output_image:
                    return (image, file_url)
                else:
                    return {
                        "ui": {
                            "text": [
                                f"上传成功: {processed_dest_path}",
                                f"文件链接: {file_url}",
                            ]
                        }
                    }
            else:
                print(f"❌ 上传失败，状态码: {result.status}")
                if output_image:
                    return (image, file_url)
                else:
                    return {"ui": {"text": [f"上传失败，状态码: {result.status}"]}}

        except oss2.exceptions.AccessDenied:
            error_msg = "❌ 访问被拒绝，请检查 AccessKey 权限"
            print(error_msg)
            if output_image:
                return (image, file_url)
            else:
                return {"ui": {"text": [error_msg]}}
        except oss2.exceptions.NoSuchBucket:
            error_msg = "❌ 存储桶不存在，请检查 bucket_name"
            print(error_msg)
            if output_image:
                return (image, file_url)
            else:
                return {"ui": {"text": [error_msg]}}
        except oss2.exceptions.InvalidAccessKeyId:
            error_msg = "❌ 无效的 AccessKey ID"
            print(error_msg)
            if output_image:
                return (image, file_url)
            else:
                return {"ui": {"text": [error_msg]}}
        except oss2.exceptions.SignatureDoesNotMatch:
            error_msg = "❌ 签名不匹配，请检查 AccessKey Secret"
            print(error_msg)
            if output_image:
                return (image, file_url)
            else:
                return {"ui": {"text": [error_msg]}}
        except oss2.exceptions.OssError as e:
            error_msg = f"❌ OSS错误: {e}"
            print(error_msg)
            if output_image:
                return (image, file_url)
            else:
                return {"ui": {"text": [error_msg]}}
        except Exception as e:
            error_msg = f"❌ 上传OSS时发生未知错误: {str(e)}"
            print(error_msg)
            import traceback

            traceback.print_exc()
            if output_image:
                return (image, file_url)
            else:
                return {"ui": {"text": [error_msg]}}

    def _process_dest_path(self, dest_path, image_format):
        """处理目标路径，替换占位符和确保正确的文件扩展名"""
        # 处理时间戳占位符
        if "{timestamp}" in dest_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            dest_path = dest_path.replace("{timestamp}", timestamp)

        # 确保文件扩展名正确
        file_ext = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}.get(
            image_format.upper(), ".png"
        )

        # 如果路径没有扩展名或扩展名不匹配，添加正确的扩展名
        if not any(
            dest_path.lower().endswith(ext)
            for ext in [".png", ".jpg", ".jpeg", ".webp"]
        ):
            dest_path += file_ext
        elif not dest_path.lower().endswith(file_ext.lower()):
            # 替换现有扩展名
            dest_path = os.path.splitext(dest_path)[0] + file_ext

        # 移除开头的斜杠（OSS不需要）
        dest_path = dest_path.lstrip("/")

        return dest_path

    def _generate_file_url(self, endpoint, bucket_name, dest_path):
        """生成文件访问URL"""
        # 规范化endpoint
        if not endpoint.startswith("http"):
            endpoint = f"https://{endpoint}"

        # 去除endpoint末尾的斜杠
        endpoint = endpoint.rstrip("/")

        # 构建URL
        if "oss-" in endpoint:
            # 阿里云OSS格式: https://bucket-name.oss-region.aliyuncs.com/path
            base_url = endpoint.replace("://", f"://{bucket_name}.")
        else:
            # 自定义域名格式
            base_url = f"{endpoint}/{bucket_name}"

        return f"{base_url}/{dest_path}"
