import io
import uuid
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Article, ArticleReviewer, ArticleAttached, Topic
from .serializers import (
    ArticleCorrectedVersionSerializer, 
    ArticleAttachedSerializer,
    ArticleReorderSerializer,
    AvalInputSerializer,
    CorrectedVersionUploadSerializer,
    FinalSubmissionSerializer  # <-- Nuevo para SCRUM-31
)
from .services import upload_file # <-- Importamos nuestro servicio

COMMITTEE_PROFILES = ("ADMIN", "MEMBER")
BLOCKED_STATES = ("REJECTED", "FOR_PUBLICATION")


def is_committee(user):
    """CA-03: el comité son los perfiles ADMIN y MEMBER (activos y no eliminados)."""
    return user.profiles.filter(
        profile_name__in=COMMITTEE_PROFILES,
        profile_active=True,
        profile_delete=False,
    ).exists()


def _is_active_reviewer(user, article):
    return ArticleReviewer.objects.filter(
        article=article,
        user=user,
        article_reviewer_active=True,
        article_reviewer_delete=False,
    ).exists()


# ==============================================================================
# VISTAS DE LA SCRUM-30 (CORREGIDAS)
# ==============================================================================
class ArticleCorrectedVersionView(APIView):
    """
    GET  /api/articles/{id}/corrected-version/  (CA-01) → versión adjunta más reciente
    POST /api/articles/{id}/corrected-version/          → el autor sube su PDF corregido
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        article = get_object_or_404(Article, article_id=pk, article_delete=False)
        is_author = article.article_created_by_id == request.user.pk
        if not (is_committee(request.user) or is_author or _is_active_reviewer(request.user, article)):
            raise PermissionDenied("No tienes permiso para ver esta versión.")
        return Response(ArticleCorrectedVersionSerializer(article).data, status=status.HTTP_200_OK)

    @transaction.atomic
    def post(self, request, pk):
        article = get_object_or_404(Article, article_id=pk, article_delete=False)

        if article.article_created_by_id != request.user.pk:
            raise PermissionDenied("Solo el autor puede subir la versión corregida.")

        serializer = CorrectedVersionUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Usa Plan A (Supabase) o Plan B (local) automáticamente
        corrected_url = upload_file(serializer.validated_data['corrected_pdf'], "corrected_versions")

        attachment = ArticleAttached.objects.create(
            article=article,
            article_attached_url=corrected_url,
            article_attached_version="Corregida",
            article_attached_created_by=request.user,
        )

        article.article_updated_by = request.user
        article.article_updated_at = timezone.now()
        article.save()

        return Response(
            {
                "detail": "Versión corregida subida correctamente.",
                "corrected_version": ArticleAttachedSerializer(attachment).data,
            },
            status=status.HTTP_201_CREATED,
        )


class ArticleAvalPresentationView(APIView):
    """POST /api/articles/{id}/aval-presentation/  (CA-02 a CA-05)"""
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        article = get_object_or_404(Article, article_id=pk, article_delete=False)
        inp = AvalInputSerializer(data=request.data)
        inp.is_valid(raise_exception=True)

        user = request.user
        committee = is_committee(user)

        if article.article_created_by_id == user.pk:
            raise PermissionDenied("No puedes avalar tu propio artículo.")

        row = ArticleReviewer.objects.select_for_update().filter(article=article, user=user).first()

        if row is None:
            if not committee:
                raise PermissionDenied("Solo los miembros del comité o evaluadores asignados pueden emitir el aval.")
            row = ArticleReviewer(article=article, user=user, article_reviewer_created_by=user)
        elif not (row.article_reviewer_active and not row.article_reviewer_delete):
            if not committee:
                raise PermissionDenied("Solo los miembros del comité o evaluadores asignados pueden emitir el aval.")
            row.article_reviewer_active = True
            row.article_reviewer_delete = False
            row.status = "IN_REVIEW"

        if row.status in BLOCKED_STATES:
            return Response({"detail": f"No se puede emitir aval desde el estado actual: {row.status}"}, status=status.HTTP_409_CONFLICT)

        row.status = "FOR_PRESENTATION"
        row.comment = inp.validated_data.get("comment", row.comment)
        row.article_reviewer_updated_by = user
        row.article_reviewer_updated_at = timezone.now()

        try:
            with transaction.atomic():
                row.save()
        except IntegrityError:
            return Response({"detail": "El aval ya fue registrado por otra solicitud. Intenta de nuevo."}, status=status.HTTP_409_CONFLICT)

        pdf_bytes = _build_aval_pdf(article, user)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="Aval_Articulo_{article.article_id}.pdf"'
        response["Cache-Control"] = "no-store"
        return response


# ==============================================================================
# VISTAS DE LA SCRUM-31 (NUEVAS)
# ==============================================================================
class ArticleFinalSubmissionView(APIView):
    """POST /api/articles/{id}/final-submission/ (CA-01, CA-02)"""
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        article = get_object_or_404(Article, article_id=pk, article_delete=False)

        if article.article_created_by_id != request.user.pk:
            raise PermissionDenied("Solo el autor puede subir la versión final.")

        serializer = FinalSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        final_pdf = serializer.validated_data['final_pdf']
        copyright_pdf = serializer.validated_data['copyright_pdf']

        # 1. Subir PDF Final (Usa Plan A o Plan B automáticamente)
        final_pdf_url = upload_file(final_pdf, "final_versions")
        
        ArticleAttached.objects.create(
            article=article,
            article_attached_url=final_pdf_url,
            article_attached_version="Final",
            article_attached_created_by=request.user
        )

        # 2. Subir Copyright
        copyright_url = upload_file(copyright_pdf, "copyrights")
        
        # 3. Guardar en el artículo
        article.article_copyright_url = copyright_url
        article.article_updated_by = request.user
        article.article_updated_at = timezone.now()
        article.save()

        return Response(
            {"detail": "Versión final y copyright subidos correctamente.", "copyright_url": copyright_url},
            status=status.HTTP_201_CREATED
        )


class ArticleAvalPublicationView(APIView):
    """POST /api/articles/{id}/aval-publication/ (CA-03 a CA-06)"""
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        article = get_object_or_404(Article, article_id=pk, article_delete=False)
        user = request.user
        
        if article.article_created_by_id == user.pk:
            raise PermissionDenied("No puedes avalar tu propio artículo.")

        committee = is_committee(user)
        row = ArticleReviewer.objects.select_for_update().filter(article=article, user=user).first()

        if not committee and not row:
            raise PermissionDenied("Solo el comité o revisores asignados pueden dar el aval de publicación.")

        if not article.article_copyright_url:
            return Response({"detail": "El autor aún no ha subido el documento de copyright."}, status=status.HTTP_400_BAD_REQUEST)

        if row:
            row.status = "FOR_PUBLICATION"
            row.article_reviewer_updated_by = user
            row.article_reviewer_updated_at = timezone.now()
            row.save()

        if not article.verification_code:
            article.verification_code = uuid.uuid4()
        #article.is_eligible_for_proceedings = True
        article.article_updated_by = user
        article.article_updated_at = timezone.now()
        article.save()

        pdf_bytes = _build_publication_pdf(article, user)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="Certificado_Publicacion_{article.article_id}.pdf"'
        return response


# ==============================================================================
# FUNCIONES GENERADORAS DE PDF
# ==============================================================================
def _build_aval_pdf(article, issuer):
    """Genera la constancia de presentación en memoria (SCRUM-30)."""
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)

    p.setFont("Helvetica-Bold", 18)
    p.drawCentredString(300, 750, "SIGECI - Constancia de Aval")

    p.setFont("Helvetica", 12)
    author = article.article_created_by
    author_name = f"{author.user_name} {author.user_lastname}".strip() if author else "Desconocido"
    subject = article.article_subject
    if len(subject) > 60:
        subject = subject[:60] + "..."

    p.drawString(100, 680, f"Artículo ID: {article.article_id}")
    p.drawString(100, 660, f"Título: {subject}")
    p.drawString(100, 640, f"Autor: {author_name}")
    p.line(100, 620, 500, 620)

    p.drawString(100, 590, "Por medio de la presente, se certifica que el artículo ha sido")
    p.drawString(100, 575, "evaluado y cuenta con el AVAL PARA PRESENTACIÓN en el evento.")

    p.setFont("Helvetica-Bold", 12)
    p.drawString(100, 520, f"Evaluador: {issuer.user_name} {issuer.user_lastname}")
    issued = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M")
    p.drawString(100, 500, f"Fecha de emisión: {issued}")

    p.showPage()
    p.save()
    return buffer.getvalue()


def _build_publication_pdf(article, issuer):
    """Genera el certificado formal de publicación (CA-05 SCRUM-31)."""
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)

    p.setFont("Helvetica-Bold", 18)
    p.drawCentredString(300, 750, "SIGECI - Certificado de Publicación")

    p.setFont("Helvetica", 12)
    author = article.article_created_by
    author_name = f"{author.user_name} {author.user_lastname}".strip() if author else "Desconocido"
    subject = article.article_subject
    if len(subject) > 60:
        subject = subject[:60] + "..."

    p.drawString(100, 680, f"Artículo ID: {article.article_id}")
    p.drawString(100, 660, f"Título: {subject}")
    p.drawString(100, 640, f"Autor: {author_name}")
    p.drawString(100, 620, f"Código de Verificación: {article.verification_code}")
    
    p.line(100, 600, 500, 600)

    p.drawString(100, 570, "Por medio de la presente, se certifica que el artículo ha sido")
    p.drawString(100, 555, "formalmente AVALADO PARA PUBLICACIÓN en las memorias del evento.")

    p.setFont("Helvetica-Bold", 12)
    p.drawString(100, 500, f"Emitido por: {issuer.user_name} {issuer.user_lastname}")
    issued = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M")
    p.drawString(100, 480, f"Fecha de emisión: {issued}")

    p.showPage()
    p.save()
    return buffer.getvalue()

class ArticleReorderView(APIView):
    """
    POST /api/articles/reorder/
    Recibe una lista de IDs en el nuevo orden y actualiza la base de datos.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Validamos que el usuario sea del comité (ADMIN o MEMBER)
        if not is_committee(request.user):
            raise PermissionDenied("Solo el comité puede organizar el orden de los artículos.")

        serializer = ArticleReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        ordered_ids = serializer.validated_data['ordered_ids']

        # Actualizamos el orden de cada artículo
        for index, article_id in enumerate(ordered_ids):
            try:
                article = Article.objects.get(article_id=article_id)
                article.article_order = index # Guardamos la posición (0, 1, 2...)
                article.save()
            except Article.DoesNotExist:
                pass 

        return Response({"detail": "Orden actualizado correctamente."}, status=status.HTTP_200_OK)

class ArticleByTopicListView(APIView):
    """
    GET /api/articles/topics/{topic_id}/articles/
    Lista los artículos de un tópico específico.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, topic_id):
        # Validar que el tópico exista
        topic = get_object_or_404(Topic, topic_id=topic_id, topic_active=True, topic_delete=False)
        
        # ORM: Traer los artículos del tópico, ordenados por 'article_order'
        articles = Article.objects.filter(
            topic_id=topic, 
            article_active=True, 
            article_delete=False
        ).order_by('article_order')

        # Retornar los datos usando el método to_dict() que ya tienes
        return Response({
            "success": True,
            "message": f"Artículos del tópico {topic.topic_subject} obtenidos.",
            "data": [a.to_dict() for a in articles]
        }, status=200)