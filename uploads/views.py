import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from util.auth_service import require_permission
from util.uploads.uploads import generate_upload_url
from util.uploads.serializer import SignUploadSerializer

ALLOWED = {
    ".pdf": "application/pdf"
}
MAX_SIZE = 30 * 1024 * 1024  # 30 MB


@csrf_exempt
@require_permission(endpoint="article", action="create")
def sign_url(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Método no permitido."}, status=405)

    try:
        body = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        body = {}

    ser = SignUploadSerializer(data=body)
    if not ser.is_valid():
        return JsonResponse(ser.errors, status=400)

    data = ser.validated_data
    result = generate_upload_url(
        folder=data["folder"],
        filename=data["filename"],
        content_type=data["content_type"],
    )
    return JsonResponse(result, status=200)
