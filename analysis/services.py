import hashlib
import shutil
import subprocess
import threading
import zipfile
from pathlib import Path

from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone

from .models import AnalysisJob


CHUNK_SIZE = 1024 * 1024


class JobError(Exception):
    pass


def safe_original_name(name):
    return Path(name or "upload.bin").name[:255]


def job_root(job):
    return Path(settings.MEDIA_ROOT).resolve() / str(job.id)


def is_within_directory(base, path):
    base = Path(base).resolve()
    path = Path(path).resolve()
    return path == base or base in path.parents


def save_upload(job, uploaded_file):
    root = job_root(job)
    uploads = root / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256()
    tmp_path = uploads / "upload.tmp"
    size = 0

    with tmp_path.open("wb") as destination:
        for chunk in uploaded_file.chunks():
            size += len(chunk)
            if size > settings.HARUSPEX_MAX_UPLOAD_SIZE:
                raise JobError("上传文件超过大小限制。")
            digest.update(chunk)
            destination.write(chunk)

    suffix = Path(uploaded_file.name).suffix.lower()
    stored_name = f"{digest.hexdigest()}{suffix}"
    stored_path = uploads / stored_name
    tmp_path.replace(stored_path)

    job.stored_name = stored_name
    job.save(update_fields=["stored_name", "updated_at"])
    return stored_path


def update_job(job_id, *, status=None, progress=None, message=None, error=None, archive_path=None):
    fields = ["updated_at"]
    values = {}
    if status is not None:
        values["status"] = status
        fields.append("status")
    if progress is not None:
        values["progress"] = max(0, min(100, int(progress)))
        fields.append("progress")
    if message is not None:
        values["message"] = message[:500]
        fields.append("message")
    if error is not None:
        values["error"] = error
        fields.append("error")
    if archive_path is not None:
        values["archive_path"] = archive_path
        fields.append("archive_path")

    AnalysisJob.objects.filter(id=job_id).update(**values)


def run_command(args, cwd, timeout=3600):
    cwd = Path(cwd).resolve()
    completed = subprocess.run(
        args,
        cwd=cwd,
        shell=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or completed.stdout or "").strip()
        raise JobError(stderr[:2000] or f"命令执行失败，退出码 {completed.returncode}。")


def archive_members(input_file, work_dir):
    extract_dir = work_dir / "extract"
    extract_dir.mkdir(parents=True, exist_ok=True)

    before = {p.resolve() for p in extract_dir.iterdir()}
    run_command([settings.AR_PATH, "-x", str(input_file)], cwd=extract_dir)
    after = [p for p in extract_dir.iterdir() if p.resolve() not in before]
    members = [p.resolve() for p in after if p.is_file() and is_within_directory(extract_dir, p)]

    if not members:
        raise JobError("ar 解包成功但未得到可处理的成员文件。")
    return members


def collect_c_files(search_roots):
    c_files = []
    for root in search_roots:
        root = Path(root).resolve()
        if not root.exists():
            continue
        for path in root.rglob("*.c"):
            if path.is_file() and is_within_directory(root, path):
                c_files.append(path.resolve())
    return c_files


def build_zip(job, c_files, work_dir):
    output_dir = work_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"{job.id}.zip"

    seen = {}
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in c_files:
            name = source.name
            count = seen.get(name, 0)
            seen[name] = count + 1
            archive_name = name if count == 0 else f"{source.stem}_{count}{source.suffix}"
            archive.write(source, arcname=archive_name)

    return zip_path


def process_job(job_id):
    close_old_connections()
    try:
        job = AnalysisJob.objects.get(id=job_id)
        root = job_root(job)
        work_dir = root / "work"
        work_dir.mkdir(parents=True, exist_ok=True)

        upload_path = root / "uploads" / job.stored_name
        if not upload_path.exists() or not is_within_directory(root, upload_path):
            raise JobError("上传文件不存在或路径非法。")

        update_job(job_id, status=AnalysisJob.Status.RUNNING, progress=12, message="已接收文件，准备解析。")

        suffix = upload_path.suffix.lower()
        input_files = [upload_path.resolve()]
        if suffix in {".a", ".lib"}:
            update_job(job_id, progress=24, message="检测到静态库，正在使用 ar 解包。")
            input_files = archive_members(upload_path, work_dir)

        total = len(input_files)
        produced_roots = [work_dir, upload_path.parent]
        for index, input_file in enumerate(input_files, start=1):
            if not is_within_directory(root, input_file):
                raise JobError("解包结果路径非法。")
            percent = 30 + int((index - 1) / max(total, 1) * 50)
            update_job(job_id, progress=percent, message=f"正在解析第 {index}/{total} 个文件。")
            run_command([settings.HARUSPEX_PATH, str(input_file)], cwd=input_file.parent)

        update_job(job_id, progress=84, message="正在收集 C 源文件。")
        c_files = collect_c_files(produced_roots)
        if not c_files:
            raise JobError("haruspex 未生成任何 .c 文件。")

        zip_path = build_zip(job, c_files, work_dir)
        update_job(
            job_id,
            status=AnalysisJob.Status.SUCCESS,
            progress=100,
            message="解析完成，可以下载结果。",
            archive_path=str(zip_path),
        )
    except Exception as exc:
        update_job(
            job_id,
            status=AnalysisJob.Status.FAILED,
            progress=100,
            message="解析失败。",
            error=str(exc),
        )
    finally:
        close_old_connections()


def start_job(job_id):
    worker = threading.Thread(target=process_job, args=(job_id,), daemon=True)
    worker.start()


def schedule_cleanup(job_id, delay_seconds=10):
    timer = threading.Timer(delay_seconds, cleanup_job, args=(job_id,))
    timer.daemon = True
    timer.start()


def cleanup_job(job_id):
    close_old_connections()
    try:
        with transaction.atomic():
            job = AnalysisJob.objects.select_for_update().get(id=job_id)
            root = job_root(job)
            if root.exists() and is_within_directory(settings.MEDIA_ROOT, root):
                shutil.rmtree(root)
            job.archive_path = ""
            job.status = AnalysisJob.Status.CLEANED
            job.message = "结果已下载，临时文件已清理。"
            job.downloaded_at = timezone.now()
            job.save(update_fields=["archive_path", "status", "message", "downloaded_at", "updated_at"])
    finally:
        close_old_connections()


def cleanup_old_jobs():
    cutoff = timezone.now() - timezone.timedelta(seconds=settings.HARUSPEX_JOB_RETENTION_SECONDS)
    old_jobs = AnalysisJob.objects.filter(updated_at__lt=cutoff).exclude(status=AnalysisJob.Status.RUNNING)
    for job in old_jobs:
        root = job_root(job)
        if root.exists() and is_within_directory(settings.MEDIA_ROOT, root):
            shutil.rmtree(root)
        job.archive_path = ""
        job.status = AnalysisJob.Status.CLEANED
        job.message = "临时文件已按保留周期清理。"
        job.save(update_fields=["archive_path", "status", "message", "updated_at"])
