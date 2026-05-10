# Haruspex 在线解析

这是一个前后端不分离的 Django 项目，用于在线上传二进制文件，调用本机 `ar` 和 `haruspex` 处理后下载生成的 `.c` 文件压缩包。

## 功能

- 上传文件后按内容 SHA-256 重命名保存。
- `.a` 和 `.lib` 文件会先执行 `ar -x` 解包，再逐个成员执行 `haruspex filename`。
- 普通文件会直接执行 `haruspex filename`。
- 前端轮询展示解析进度、错误信息和下载入口。
- 所有生成的 `.c` 文件会打包为 zip。
- 下载触发后会自动清理上传文件、解包目录、输出 zip 等临时文件。

## 配置 ar 和 haruspex 路径

打开 [haruspex_web/settings.py](haruspex_web/settings.py)，修改下面两个配置：

```python
AR_PATH = r"C:\path\to\ar.exe"
HARUSPEX_PATH = r"C:\path\to\haruspex.exe"
```

Linux 或 macOS 可以写成：

```python
AR_PATH = "/usr/bin/ar"
HARUSPEX_PATH = "/opt/haruspex/bin/haruspex"
```

如果命令已经在 `PATH` 中，也可以保留默认值：

```python
AR_PATH = "ar"
HARUSPEX_PATH = "haruspex"
```

## 运行

```powershell
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

然后访问 http://127.0.0.1:8000/。

当前环境中的 `.venv` 可能已损坏时，可以删除 `.venv` 后重新执行 `uv sync`。

## 安全设计

- 后端不使用 shell 拼接命令，外部程序通过 `subprocess.run([...], shell=False)` 调用，降低命令注入风险。
- 上传后的实际文件名由 SHA-256 hash 生成，原始文件名只用于展示和下载文件名。
- 所有工作文件限制在 `MEDIA_ROOT/jobs/<job_id>` 等价目录下，并检查路径边界，降低路径穿越风险。
- Django 模板默认开启自动转义，错误信息和文件名不会以 HTML 注入方式渲染。
- 开启 CSRF、防 clickjacking、content type nosniff 和 HttpOnly cookie。
- 默认限制上传大小为 128 MiB，可在 [haruspex_web/settings.py](haruspex_web/settings.py) 中调整 `HARUSPEX_MAX_UPLOAD_SIZE`。

生产环境部署前，请设置真实 `SECRET_KEY`，关闭 `DEBUG`，配置 `ALLOWED_HOSTS`，并使用 HTTPS。
