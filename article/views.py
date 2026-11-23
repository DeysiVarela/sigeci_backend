import json
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from util.auth_service import require_permission, require_permission_drf
from util.uploads.uploads import delete_file
from util.utilDB import queryDB

from .models import Article, ArticleAttached, ArticleReviewer, Topic
from .serializers import ArticleReorderSerializer


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
    profile = str(request.user.get("profile_id"))
    user = request.user.get("user_id")
    articles = []
    match profile:
        case "1":
            articles = queryDB("""
                select 
                    ar.*,
                    tp.topic_subject
                from article ar
                inner join topic tp
                    on tp.topic_id = ar.topic_id
            """, None)

        case "2":
            articles = (
                Article.objects
                .select_related("topic_id", "article_created_by")
                .prefetch_related("attachments")
                .filter(article_active=True)
            )
        case "3":
            articles = queryDB("""
                select 
                    ar.*,
                    tp.topic_subject
                from article ar
                inner join topic tp
                    on tp.topic_id = ar.topic_id
                where ar.article_created_by = %s
            """, [user])

    return JsonResponse({
        "success": True,
        "message": "Artículos obtenidos con éxito.",
        "data": articles
    }, safe=False, status=200)


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

    attached_url = data.get("article_attached_url")
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


def _can_evaluate(request, permission):
    user = getattr(request, "user", None)
    return bool(
        getattr(user, "is_authenticated", False)
        and user.has_perm_on("evaluation", permission)
    )


def _evaluation_payload(review):
    article = review.article
    attachment = review.article_attached
    if attachment is None:
        attachment = article.attachments.filter(
            article_attached_active=True,
            article_attached_delete=False,
        ).order_by("-article_attached_id").first()

    status_map = {
        "PENDING": "PENDIENTE",
        "IN_REVIEW": "EN_REVISION",
        "APPROVED": "APROBADO",
        "REJECTED": "RECHAZADO",
    }
    pdf_url = attachment.article_attached_url if attachment else None
    pdf_name = pdf_url.rstrip("/").split("/")[-1].split("?")[0] if pdf_url else None

    return {
        "id": review.article_reviewer_id,
        "articleId": article.article_id,
        "title": article.article_subject,
        "author": (
            f"{article.article_created_by.user_name} {article.article_created_by.user_lastname}"
            if article.article_created_by else ""
        ).strip(),
        "category": article.topic_id.topic_subject if article.topic_id else "",
        "summary": article.article_description,
        "deadline": str(review.evaluation_deadline) if review.evaluation_deadline else None,
        "status": status_map.get(review.status, review.status),
        "comments": review.comment or "",
        "verdict": status_map.get(review.status, review.status),
        "pdfSignedUrl": pdf_url,
        "pdfFileName": pdf_name,
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def assigned_evaluations(request):
    if not _can_evaluate(request, "view"):
        return Response({"detail": "No tienes permiso para consultar evaluaciones."}, status=403)

    reviews = (
        ArticleReviewer.objects.select_related(
            "article", "article__topic_id", "article__article_created_by",
            "article_attached", "user",
        )
        .filter(
            user=request.user,
            article_reviewer_active=True,
            article_reviewer_delete=False,
            article__article_active=True,
            article__article_delete=False,
        )
    )
    return Response([_evaluation_payload(review) for review in reviews], status=200)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def assigned_evaluation_detail(request, review_id):
    if not _can_evaluate(request, "view"):
        return Response({"detail": "No tienes permiso para consultar evaluaciones."}, status=403)

    review = (
        ArticleReviewer.objects.select_related(
            "article", "article__topic_id", "article__article_created_by", "article_attached",
        )
        .filter(
            article_reviewer_id=review_id,
            user=request.user,
            article_reviewer_active=True,
            article_reviewer_delete=False,
            article__article_active=True,
            article__article_delete=False,
        )
        .first()
    )
    if review is None:
        return Response({"detail": "La evaluación no está asignada a tu cuenta."}, status=404)

    if review.status == "PENDING":
        review.status = "IN_REVIEW"
        review.article_reviewer_updated_by = request.user
        review.article_reviewer_updated_at = timezone.now()
        review.save(update_fields=[
            "status", "article_reviewer_updated_by", "article_reviewer_updated_at"
        ])

    return Response(_evaluation_payload(review), status=200)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def submit_evaluation_verdict(request, review_id):
    if not _can_evaluate(request, "update"):
        return Response({"detail": "No tienes permiso para emitir veredictos."}, status=403)

    review = ArticleReviewer.objects.select_related("article").filter(
        article_reviewer_id=review_id,
        user=request.user,
        article_reviewer_active=True,
        article_reviewer_delete=False,
        article__article_active=True,
        article__article_delete=False,
    ).first()
    if review is None:
        return Response({"detail": "La evaluación no está asignada a tu cuenta."}, status=404)

    if review.status in ("APPROVED", "REJECTED"):
        return Response({"detail": "El veredicto ya fue registrado y no puede modificarse."}, status=409)

    verdict = str(request.data.get("verdict") or "").strip().upper()
    comments = str(request.data.get("comments") or "").strip()

    if verdict not in ("APPROVED", "REJECTED", "APROBADO", "RECHAZADO"):
        return Response({"detail": "El veredicto debe ser APROBADO o RECHAZADO."}, status=400)
    if not comments:
        return Response({"detail": "Los comentarios cualitativos son obligatorios."}, status=400)

    review.status = "APPROVED" if verdict in ("APPROVED", "APROBADO") else "REJECTED"
    review.comment = comments
    review.article_reviewer_updated_by = request.user
    review.article_reviewer_updated_at = timezone.now()
    review.save(update_fields=[
        "status", "comment", "article_reviewer_updated_by", "article_reviewer_updated_at"
    ])
    return Response(_evaluation_payload(review), status=200)

# ==============================================================================
# VISTAS DE LA SCRUM-176 (ARTÍCULOS POR TÓPICO Y REORDENAMIENTO)
# ==============================================================================
class ArticleReorderView(APIView):
    """
    POST /api/v1/article/reorder/
    Recibe una lista de IDs en el nuevo orden y actualiza la base de datos.
    """
    authentication_classes = []
    permission_classes = []

    @require_permission_drf(endpoint="article", action="update")
    def post(self, request):
        serializer = ArticleReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ordered_ids = serializer.validated_data['ordered_ids']

        for index, article_id in enumerate(ordered_ids):
            Article.objects.filter(article_id=article_id).update(article_order=index)

        return Response({"detail": "Orden actualizado correctamente."}, status=status.HTTP_200_OK)


class ArticleByTopicListView(APIView):
    """
    GET /api/v1/article/topics/{topic_id}/articles/
    Lista los artículos de un tópico específico.
    """
    authentication_classes = []
    permission_classes = []

    @require_permission_drf(endpoint="article", action="view")
    def get(self, request, topic_id):
        topic = get_object_or_404(Topic, topic_id=topic_id, topic_active=True, topic_delete=False)
        articles = Article.objects.filter(
            topic_id=topic,
            article_active=True,
            article_delete=False
        ).order_by('article_order')

        return Response({
            "success": True,
            "message": f"Artículos del tópico {topic.topic_subject} obtenidos.",
            "data": [a.to_dict() for a in articles]
        }, status=200)
