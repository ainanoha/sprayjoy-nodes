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
                    {"default": "comfyui/{timestamp}.png", "multiline": True},
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
    RETURN_NAMES = ("image", "file_urls")
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
        file_urls_str = ""

        # 参数验证
        if not access_key_id.strip():
            print("❌ AccessKey ID 不能为空")
            if output_image:
                return (image, file_urls_str)
            else:
                return {"ui": {"text": ["AccessKey ID 不能为空"]}}

        if not access_key_secret.strip():
            print("❌ AccessKey Secret 不能为空")
            if output_image:
                return (image, file_urls_str)
            else:
                return {"ui": {"text": ["AccessKey Secret 不能为空"]}}

        if not bucket_name.strip():
            print("❌ Bucket 名称不能为空")
            if output_image:
                return (image, file_urls_str)
            else:
                return {"ui": {"text": ["Bucket 名称不能为空"]}}

        if not dest_path.strip():
            print("❌ 目标路径不能为空")
            if output_image:
                return (image, file_urls_str)
            else:
                return {"ui": {"text": ["目标路径不能为空"]}}

        try:
            # 处理图像批次
            if len(image.shape) == 4:
                # 批处理多张图片
                images_to_process = image
                num_images = images_to_process.shape[0]
            else:
                # 单张图片，转换为批次格式
                images_to_process = image.unsqueeze(0)
                num_images = 1

            # 准备目标路径列表
            dest_paths = self._prepare_dest_paths(dest_path, num_images, image_format)

            # 初始化OSS客户端
            auth = oss2.Auth(access_key_id, access_key_secret)
            bucket = oss2.Bucket(auth, endpoint, bucket_name)

            # 设置Content-Type
            content_type = {
                "PNG": "image/png",
                "JPEG": "image/jpeg",
                "WEBP": "image/webp",
            }.get(image_format.upper(), "image/png")

            file_urls = []
            upload_results = []

            # 循环处理每张图片
            for idx in range(num_images):
                image_tensor = images_to_process[idx]
                processed_dest_path = dest_paths[idx]

                # 检查目标路径是否为图片格式
                image_extensions = [".png", ".jpg", ".jpeg", ".webp"]
                current_ext = os.path.splitext(processed_dest_path)[1].lower()
                is_image_format = current_ext in image_extensions

                if is_image_format:
                    # 图片格式：进行正常的图片处理
                    # 将tensor转换为PIL Image
                    image_np = (image_tensor.cpu().numpy() * 255).astype(np.uint8)
                    pil_image = Image.fromarray(image_np)

                    # 将图像转换为字节流
                    image_bytes = io.BytesIO()
                    if image_format.upper() == "JPEG":
                        # 如果是JPEG，需要转换为RGB模式（去除alpha通道）
                        if pil_image.mode in ("RGBA", "LA"):
                            # 创建白色背景
                            background = Image.new(
                                "RGB", pil_image.size, (255, 255, 255)
                            )
                            if pil_image.mode == "RGBA":
                                background.paste(
                                    pil_image, mask=pil_image.split()[-1]
                                )  # 使用alpha通道作为遮罩
                            else:
                                background.paste(pil_image)
                            pil_image = background
                        pil_image.save(
                            image_bytes,
                            format="JPEG",
                            quality=jpeg_quality,
                            optimize=True,
                        )
                    elif image_format.upper() == "WEBP":
                        pil_image.save(
                            image_bytes,
                            format="WEBP",
                            quality=jpeg_quality,
                            optimize=True,
                        )
                    else:  # PNG
                        pil_image.save(image_bytes, format="PNG", optimize=True)

                    image_bytes.seek(0)
                    upload_data = image_bytes.getvalue()
                    upload_content_type = content_type
                else:
                    # 非图片格式：直接使用原始tensor数据
                    # 将tensor转换为numpy数组并转换为字节
                    image_np = (image_tensor.cpu().numpy() * 255).astype(np.uint8)
                    upload_data = image_np.tobytes()
                    # 根据文件扩展名设置Content-Type
                    content_type_map = {
                        ".mp4": "video/mp4",
                        ".avi": "video/x-msvideo",
                        ".mov": "video/quicktime",
                        ".mkv": "video/x-matroska",
                        ".wmv": "video/x-ms-wmv",
                        ".flv": "video/x-flv",
                        ".webm": "video/webm",
                        ".gif": "image/gif",
                        ".bmp": "image/bmp",
                        ".tiff": "image/tiff",
                        ".tga": "image/x-tga",
                    }
                    upload_content_type = content_type_map.get(
                        current_ext, "application/octet-stream"
                    )

                # 上传文件
                result = bucket.put_object(
                    processed_dest_path,
                    upload_data,
                    headers={"Content-Type": upload_content_type},
                )

                if result.status == 200:
                    file_type = "图像" if is_image_format else "文件"
                    print(
                        f"✅ {file_type} {idx+1}/{num_images} 成功上传到OSS: {processed_dest_path}"
                    )
                    # 生成文件访问URL
                    file_url = self._generate_file_url(
                        endpoint, bucket_name, processed_dest_path
                    )
                    file_urls.append(file_url)
                    print(f"📊 文件大小: {len(upload_data)} bytes")
                    upload_results.append(f"上传成功: {processed_dest_path}")
                else:
                    file_type = "图像" if is_image_format else "文件"
                    print(
                        f"❌ {file_type} {idx+1}/{num_images} 上传失败，状态码: {result.status}"
                    )
                    file_urls.append("")
                    upload_results.append(
                        f"上传失败: {processed_dest_path}, 状态码: {result.status}"
                    )

            # 将URL列表连接为字符串
            file_urls_str = "\n".join(file_urls)

            # 返回结果
            if output_image:
                return (image, file_urls_str)
            else:
                return {
                    "ui": {"text": upload_results + [f"文件链接:\n{file_urls_str}"]}
                }

        except oss2.exceptions.AccessDenied:
            error_msg = "❌ 访问被拒绝，请检查 AccessKey 权限"
            print(error_msg)
            if output_image:
                return (image, file_urls_str)
            else:
                return {"ui": {"text": [error_msg]}}
        except oss2.exceptions.NoSuchBucket:
            error_msg = "❌ 存储桶不存在，请检查 bucket_name"
            print(error_msg)
            if output_image:
                return (image, file_urls_str)
            else:
                return {"ui": {"text": [error_msg]}}
        except oss2.exceptions.InvalidAccessKeyId:
            error_msg = "❌ 无效的 AccessKey ID"
            print(error_msg)
            if output_image:
                return (image, file_urls_str)
            else:
                return {"ui": {"text": [error_msg]}}
        except oss2.exceptions.SignatureDoesNotMatch:
            error_msg = "❌ 签名不匹配，请检查 AccessKey Secret"
            print(error_msg)
            if output_image:
                return (image, file_urls_str)
            else:
                return {"ui": {"text": [error_msg]}}
        except oss2.exceptions.OssError as e:
            error_msg = f"❌ OSS错误: {e}"
            print(error_msg)
            if output_image:
                return (image, file_urls_str)
            else:
                return {"ui": {"text": [error_msg]}}
        except Exception as e:
            error_msg = f"❌ 上传OSS时发生未知错误: {str(e)}"
            print(error_msg)
            import traceback

            traceback.print_exc()
            if output_image:
                return (image, file_urls_str)
            else:
                return {"ui": {"text": [error_msg]}}

    def _prepare_dest_paths(self, dest_path_input, num_images, image_format):
        """准备目标路径列表，支持多路径按换行符分割"""
        # 按换行符分割路径
        dest_paths = [
            path.strip() for path in dest_path_input.strip().split("\n") if path.strip()
        ]

        if not dest_paths:
            dest_paths = ["comfyui/{timestamp}.png"]

        # 如果路径数量 >= 图片数量，直接使用对应的路径
        if len(dest_paths) >= num_images:
            result_paths = dest_paths[:num_images]
        else:
            # 如果路径数量 < 图片数量，使用最后一个路径并添加后缀
            result_paths = dest_paths.copy()
            last_path = dest_paths[-1]

            # 为剩余的图片生成路径
            for i in range(len(dest_paths), num_images):
                suffix_index = i - len(dest_paths)
                # 在文件名（扩展名前）添加后缀
                path_without_ext = os.path.splitext(last_path)[0]
                ext = os.path.splitext(last_path)[1]
                if not ext:
                    # 如果没有扩展名，后面会自动添加
                    new_path = f"{path_without_ext}-{suffix_index}"
                else:
                    new_path = f"{path_without_ext}-{suffix_index}{ext}"
                result_paths.append(new_path)

        # 处理每个路径
        processed_paths = []
        for path in result_paths:
            processed_path = self._process_dest_path(path, image_format)
            processed_paths.append(processed_path)

        return processed_paths

    def _process_dest_path(self, dest_path, image_format):
        """处理目标路径，替换占位符和确保正确的文件扩展名"""
        # 处理时间戳占位符
        if "{timestamp}" in dest_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            dest_path = dest_path.replace("{timestamp}", timestamp)

        # 检查是否为图片格式的扩展名
        image_extensions = [".png", ".jpg", ".jpeg", ".webp"]
        current_ext = os.path.splitext(dest_path)[1].lower()

        # 如果不是图片格式的扩展名，直接使用原始路径
        if current_ext and current_ext not in image_extensions:
            # 移除开头的斜杠（OSS不需要）
            dest_path = dest_path.lstrip("/")
            return dest_path

        # 确保文件扩展名正确（仅对图片格式）
        file_ext = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}.get(
            image_format.upper(), ".png"
        )

        # 如果路径没有扩展名或扩展名不匹配，添加正确的扩展名
        if not any(dest_path.lower().endswith(ext) for ext in image_extensions):
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
