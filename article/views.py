import json
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from accounts.models import Profile, User
from util.auth_service import require_permission, require_permission_drf
from util.uploads.uploads import delete_file
from util.utilDB import queryDB

from .models import Article, ArticleAttached, ArticleAuthor, ArticleReviewer, Event, Topic
from .serializers import (
    ArticleReorderSerializer,
    EventDetailSerializer,
    EventSerializer,
    EventWriteSerializer,
)


def _parse_body(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except Exception:
        return {}


MAX_COAUTHORS = 10


def _validate_coauthors(raw, main_email):
    """Valida la lista de coautores (nombre, afiliación y correo obligatorios; apellido opcional).

    Devuelve (lista_limpia, None) o (None, mensaje_de_error).
    """
    if raw in (None, ""):
        return [], None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return None, "El campo 'coauthors' debe ser una lista."
    if not isinstance(raw, list):
        return None, "El campo 'coauthors' debe ser una lista."
    if len(raw) > MAX_COAUTHORS:
        return None, f"Un artículo puede tener máximo {MAX_COAUTHORS} coautores."

    seen = {main_email.lower()} if main_email else set()
    clean = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            return None, f"Coautor {index}: formato inválido."
        name = str(item.get("name") or "").strip()
        lastname = str(item.get("lastname") or "").strip()
        affiliation = str(item.get("affiliation") or "").strip()
        email = str(item.get("email") or "").strip().lower()
        if not name or not affiliation or not email:
            return None, f"Coautor {index}: nombre, afiliación y correo son obligatorios."
        if len(name) > 60 or len(lastname) > 60 or len(affiliation) > 200 or len(email) > 120:
            return None, f"Coautor {index}: algún campo supera el largo permitido."
        try:
            validate_email(email)
        except ValidationError:
            return None, f"Coautor {index}: el correo no es válido."
        if email in seen:
            return None, f"Coautor {index}: el correo {email} está repetido o es el del autor principal."
        seen.add(email)
        clean.append({"name": name, "lastname": lastname, "affiliation": affiliation, "email": email})
    return clean, None


def _save_authors(article, main_user, main_affiliation, coauthors):
    """Reemplaza los autores del artículo: autor de correspondencia (orden 0) + coautores."""
    article.authors.all().delete()
    rows = []
    if main_user:
        rows.append(ArticleAuthor(
            article=article,
            user=main_user,
            author_name=(main_user.user_name or main_user.user_email)[:60],
            author_lastname=(main_user.user_lastname or "")[:60],
            author_affiliation=main_affiliation,
            author_email=(main_user.user_email or "").lower(),
            author_is_corresponding=True,
            author_order=0,
        ))
    for order, coauthor in enumerate(coauthors, start=1):
        rows.append(ArticleAuthor(
            article=article,
            author_name=coauthor["name"],
            author_lastname=coauthor["lastname"],
            author_affiliation=coauthor["affiliation"],
            author_email=coauthor["email"],
            author_is_corresponding=False,
            author_order=order,
        ))
    ArticleAuthor.objects.bulk_create(rows)


def list_topics(request):
    """Listar temas activos."""
    topics = Topic.objects.filter(topic_active=True, topic_delete=False)
    return JsonResponse({
        "success": True,
        "message": "Temas obtenidos con éxito.",
        "data": [t.to_dict() for t in topics]
    }, safe=False, status=200)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def list_events(request):
    if request.method == "POST":
        if not request.user.has_perm_on("event", "create"):
            return Response(
                {"success": False, "message": "No tienes permiso para crear eventos."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = EventWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"success": False, "message": "Los datos del evento no son válidos.", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        event = serializer.save(event_created_by=request.user)
        event = Event.objects.prefetch_related("schedule_items__topic_id").get(pk=event.pk)
        return Response({
            "success": True,
            "message": "Evento creado con éxito.",
            "data": EventDetailSerializer(event).data,
        }, status=status.HTTP_201_CREATED)

    events = Event.objects.order_by("event_date", "event_id")
    return Response({
        "success": True,
        "message": "Eventos obtenidos con éxito.",
        "data": EventSerializer(events, many=True).data,
    }, status=status.HTTP_200_OK)


@api_view(["GET", "PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def event_detail(request, event_id):
    event = get_object_or_404(Event, event_id=event_id)
    if request.method in ("PUT", "PATCH"):
        if not request.user.has_perm_on("event", "update"):
            return Response(
                {"success": False, "message": "No tienes permiso para actualizar eventos."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = EventWriteSerializer(
            event,
            data=request.data,
            partial=request.method == "PATCH",
        )
        if not serializer.is_valid():
            return Response(
                {"success": False, "message": "Los datos del evento no son válidos.", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        event = serializer.save(
            event_updated_by=request.user,
            event_updated_at=timezone.now(),
        )
        event = Event.objects.prefetch_related("schedule_items__topic_id").get(pk=event.pk)
        return Response({
            "success": True,
            "message": "Evento actualizado con éxito.",
            "data": EventDetailSerializer(event).data,
        }, status=status.HTTP_200_OK)

    event = get_object_or_404(
        Event.objects.prefetch_related("schedule_items__topic_id"),
        event_id=event_id,
    )
    return Response({
        "success": True,
        "message": "Evento obtenido con éxito.",
        "data": EventDetailSerializer(event).data,
    }, status=status.HTTP_200_OK)

@require_permission(endpoint="article", action="view")
def list_articles(request):
    try:
        profile_id = int(request.user.get("profile_id"))
    except (TypeError, ValueError):
        profile_id = None
    profile_name = Profile.objects.filter(profile_id=profile_id).values_list(
        "profile_name", flat=True
    ).first()
    user_id = request.user.get("user_id")

    # Se usa el ORM + to_dict() para incluir nombre del autor y última versión del PDF
    base = (
        Article.objects
        .select_related("topic_id", "article_created_by")
        .prefetch_related("attachments", "authors")
    )
    match profile_name:
        case "ADMIN":
            articles = base.all()
        case "MEMBER":
            articles = base.filter(article_active=True)
        case "AUTHOR":
            articles = base.filter(article_created_by_id=user_id)
        case _:
            articles = Article.objects.none()

    return JsonResponse({
        "success": True,
        "message": "Artículos obtenidos con éxito.",
        "data": [a.to_dict() for a in articles]
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
    main_user = User.objects.filter(pk=created_by_id).first()

    # Autores: quien postula es el autor principal; los coautores llegan en 'coauthors'
    main_affiliation = str(data.get("main_author_affiliation") or "").strip()
    if not main_affiliation:
        return JsonResponse(
            {"detail": "La afiliación del autor principal ('main_author_affiliation') es obligatoria."},
            status=400,
        )
    coauthors, error = _validate_coauthors(
        data.get("coauthors"), main_user.user_email if main_user else None
    )
    if error:
        return JsonResponse({"detail": error}, status=400)

    with transaction.atomic():
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

        _save_authors(article, main_user, main_affiliation, coauthors)

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

    # Autores: el principal siempre es quien postuló (article_created_by), no quien edita
    authors_to_save = None
    if "coauthors" in data or "main_author_affiliation" in data:
        main_user = article.article_created_by
        current_main = article.authors.filter(author_is_corresponding=True).first()
        if "main_author_affiliation" in data:
            main_affiliation = str(data.get("main_author_affiliation") or "").strip()
        else:
            main_affiliation = current_main.author_affiliation if current_main else ""
        if not main_affiliation:
            return JsonResponse(
                {"detail": "La afiliación del autor principal ('main_author_affiliation') es obligatoria."},
                status=400,
            )
        if "coauthors" in data:
            coauthors, error = _validate_coauthors(
                data.get("coauthors"), main_user.user_email if main_user else None
            )
            if error:
                return JsonResponse({"detail": error}, status=400)
        else:
            coauthors = [
                {
                    "name": a.author_name,
                    "lastname": a.author_lastname,
                    "affiliation": a.author_affiliation,
                    "email": a.author_email,
                }
                for a in article.authors.filter(author_is_corresponding=False)
            ]
        authors_to_save = (main_user, main_affiliation, coauthors)

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

    with transaction.atomic():
        article.save()
        if authors_to_save:
            _save_authors(article, *authors_to_save)
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