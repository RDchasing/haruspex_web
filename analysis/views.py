from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from .models import AnalysisJob
from .services import cleanup_old_jobs, safe_original_name, save_upload, schedule_cleanup, start_job


def index(request):
    cleanup_old_jobs()
    recent_jobs = AnalysisJob.objects.exclude(status=AnalysisJob.Status.CLEANED)[:8]
    return render(request, "analysis/index.html", {"recent_jobs": recent_jobs})


@require_POST
def create_job(request):
    uploaded_file = request.FILES.get("binary")
    if not uploaded_file:
        return render(
            request,
            "analysis/index.html",
            {"error": "请选择要上传的二进制文件。", "recent_jobs": AnalysisJob.objects.all()[:8]},
            status=400,
        )

    job = AnalysisJob.objects.create(
        original_name=safe_original_name(uploaded_file.name),
        status=AnalysisJob.Status.QUEUED,
        progress=3,
        message="正在保存上传文件。",
    )

    try:
        save_upload(job, uploaded_file)
    except Exception as exc:
        job.status = AnalysisJob.Status.FAILED
        job.progress = 100
        job.message = "上传失败。"
        job.error = str(exc)
        job.save(update_fields=["status", "progress", "message", "error", "updated_at"])
        return redirect("analysis:job_detail", job_id=job.id)

    start_job(job.id)
    return redirect("analysis:job_detail", job_id=job.id)


def job_detail(request, job_id):
    job = get_object_or_404(AnalysisJob, id=job_id)
    return render(request, "analysis/job_detail.html", {"job": job})


@require_GET
def job_status(request, job_id):
    job = get_object_or_404(AnalysisJob, id=job_id)
    return JsonResponse(
        {
            "id": str(job.id),
            "status": job.status,
            "status_label": job.get_status_display(),
            "progress": job.progress,
            "message": job.message,
            "error": job.error,
            "download_url": reverse("analysis:download_result", kwargs={"job_id": job.id})
            if job.status == AnalysisJob.Status.SUCCESS
            else "",
        }
    )


@require_GET
def download_result(request, job_id):
    job = get_object_or_404(AnalysisJob, id=job_id)
    if job.status != AnalysisJob.Status.SUCCESS or not job.archive_path:
        raise Http404("结果文件尚未生成。")

    archive_path = Path(job.archive_path).resolve()
    media_root = Path(settings.MEDIA_ROOT).resolve()
    if not archive_path.exists() or media_root not in archive_path.parents:
        raise Http404("结果文件不存在。")

    download_name = f"{Path(job.original_name).stem or 'haruspex-result'}.zip"
    response = FileResponse(archive_path.open("rb"), as_attachment=True, filename=download_name)
    schedule_cleanup(job.id)
    return response
