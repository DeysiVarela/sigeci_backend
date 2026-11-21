import json
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from util.auth_service import require_permission
from util.uploads.uploads import delete_file

from .models import Article, ArticleAttached, Topic


def _parse_body(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except Exception:
        return {}


def list_topics(request):
    """Listar temas activos."""
    topics = Topic.objects.filter(topic_active=True, topic_delete=False)
    return JsonResponse({
        "success": True,
        "message": "Temas obtenidos con éxito.",
        "data": [t.to_dict() for t in topics]
    }, safe=False, status=200)


@require_permission(endpoint="article", action="view")
def list_articles(request):
    """Listar artículos activos."""
    articles = (
        Article.objects
        .select_related("topic_id", "article_created_by")
        .prefetch_related("attachments")
        .filter(article_active=True)
    )
    return JsonResponse({
        "success": True,
        "message": "Artículos obtenidos con éxito.",
        "data": [a.to_dict() for a in articles]
    }, safe=False, status=200)


@csrf_exempt
@require_permission(endpoint="article", action="view")
def detail_article(request, article_id):
    """Consultar detalle, actualizar o eliminar según el método HTTP."""
    if request.method in ("PUT", "PATCH"):
        return update_article(request, article_id)
    if request.method == "DELETE":
        return delete_article(request, article_id)
    if request.method != "GET":
        return JsonResponse({"detail": "Método no permitido.", "success": False}, status=405)

    try:
        article = (
            Article.objects
            .select_related("topic_id", "article_created_by")
            .prefetch_related("attachments")
            .get(pk=article_id)
        )
        return JsonResponse({
            "success": True,
            "message": "Artículo obtenido con éxito.",
            "data": article.to_dict()
        }, status=200)
    except Article.DoesNotExist:
        return JsonResponse({"detail": "Artículo no encontrado.", "success": False}, status=404)


@csrf_exempt
@require_permission(endpoint="article", action="create")
def create_article(request):
    """Crear un nuevo artículo."""
    if request.method != "POST":
        return JsonResponse({"detail": "Método no permitido."}, status=405)

    data = _parse_body(request)
    if not data and request.POST:
        data = request.POST.dict()

    subject = data.get("article_subject") or data.get("title")
    content = data.get("article") or data.get("content")

    if not subject or not content:
        return JsonResponse(
            {"detail": "Los campos 'article_subject' y 'article' son obligatorios."},
            status=400,
        )

    created_by_id = request.user.get("user_id")

    article = Article.objects.create(
        article_subject=subject,
        article_description=data.get("article_description", data.get("summary", "")),
        topic_id_id=data.get("topic_id"),
        article=content,
        article_date=data.get("article_date") or data.get("published_at"),
        article_created_by_id=created_by_id,
    )

    attached_url = data.get("article_attached_url") or data.get("pdf_url") or data.get("file_url")
    if attached_url:
        ArticleAttached.objects.create(
            article=article,
            article_attached_url=attached_url,
            article_attached_created_by_id=created_by_id,
        )

    return JsonResponse({
        "success": True,
        "message": "Artículo creado con éxito.",
        "data": article.to_dict(),
    }, status=201)


@csrf_exempt
@require_permission(endpoint="article", action="update")
def update_article(request, article_id):
    """Actualizar un artículo existente."""
    if request.method not in ("PUT", "PATCH", "POST"):
        return JsonResponse({"detail": "Método no permitido."}, status=405)

    try:
        article = Article.objects.get(pk=article_id)
    except Article.DoesNotExist:
        return JsonResponse({"detail": "Artículo no encontrado."}, status=404)

    data = _parse_body(request)
    if not data and request.POST:
        data = request.POST.dict()

    if "article_subject" in data:
        article.article_subject = data["article_subject"]
    elif "title" in data:
        article.article_subject = data["title"]

    if "article_description" in data:
        article.article_description = data["article_description"]
    elif "summary" in data:
        article.article_description = data["summary"]

    if "article" in data:
        article.article = data["article"]
    elif "content" in data:
        article.article = data["content"]

    if "topic_id" in data:
        article.topic_id_id = data["topic_id"]

    if "article_date" in data:
        article.article_date = data["article_date"]

    updated_by_id = data.get("article_updated_by") or (
        request.user.get("user_id") if isinstance(request.user, dict) else None
    )
    if updated_by_id:
        article.article_updated_by_id = updated_by_id
    article.article_updated_at = timezone.now()

    attached_url = data.get("article_attached_url") or data.get("pdf_url") or data.get("file_url")
    if attached_url:
        existing_attachments = article.attachments.filter(
            article_attached_active=True,
            article_attached_delete=False,
        )
        for att in existing_attachments:
            if att.article_attached_url and att.article_attached_url != attached_url:
                delete_file(att.article_attached_url)

        latest_att = existing_attachments.first()
        if latest_att:
            latest_att.article_attached_url = attached_url
            if updated_by_id:
                latest_att.article_attached_updated_by_id = updated_by_id
            latest_att.article_attached_updated_at = timezone.now()
            latest_att.save()
        else:
            ArticleAttached.objects.create(
                article=article,
                article_attached_url=attached_url,
                article_attached_created_by_id=updated_by_id,
            )

    article.save()
    return JsonResponse({
        "success": True,
        "message": "Artículo actualizado con éxito.",
        "data": article.to_dict(),
    }, status=200)


@csrf_exempt
@require_permission(endpoint="article", action="delete")
def delete_article(request, article_id):
    """Eliminar un artículo."""
    if request.method not in ("DELETE", "POST"):
        return JsonResponse({"detail": "Método no permitido."}, status=405)

    try:
        article = Article.objects.get(pk=article_id)
        article.delete()
        return JsonResponse({"detail": "Artículo eliminado exitosamente."}, status=200)
    except Article.DoesNotExist:
        return JsonResponse({"detail": "Artículo no encontrado."}, status=404)

