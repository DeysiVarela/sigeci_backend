"""
SCRUM-30 / SCRUM-31: versión corregida, versión final + copyright y avales (presentación / publicación).

Rutas: /api/articles/{id}/...   (ver article/urls_versions.py)

Seguridad (dos capas, ambas en el servidor; el frontend solo oculta botones):
  1. Matriz de permisos (profile_action), vía `profile_permission`:
       - GET  corrected-version      -> article:view
       - POST corrected-version      -> article:update   (+ ser el AUTOR del artículo)
       - POST final-submission       -> article:update   (+ ser el AUTOR del artículo)
       - POST aval-presentation      -> evaluation:update (+ comité o evaluador asignado, y no ser el autor)
       - POST aval-publication       -> evaluation:update (+ comité o evaluador asignado, y no ser el autor)
  2. Reglas por objeto (propiedad / comité / evaluador asignado). Cumplir una capa NO sustituye a la otra.
Sin fila en la matriz => 403 (falla cerrado). Sin sesión => 401 (SigeciJWTAuthentication).
"""
import io
import os
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

from accounts.permissions import profile_permission

from .models import Article, ArticleAttached, ArticleReviewer
from .versions_serializers import (
    ArticleAttachedSerializer,
    ArticleVersionsSerializer,
    AvalInputSerializer,
    CorrectedVersionUploadSerializer,
    FinalSubmissionSerializer,
)
from .versions_storage import upload_version_file

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


def _reviewer_row(article, user):
    return (
        ArticleReviewer.objects.select_for_update()
        .filter(article=article, user=user)
        .order_by("article_reviewer_id")
        .first()
    )


def _get_article(pk):
    return get_object_or_404(Article, article_id=pk, article_delete=False)


def _require_author(article, user, message):
    if article.article_created_by_id != user.pk:
        raise PermissionDenied(message)


# ==============================================================================
# SCRUM-30
# ==============================================================================
class ArticleCorrectedVersionView(APIView):
    """
    GET  /api/articles/{id}/corrected-version/  (CA-01) -> versión adjunta más reciente + historial
    POST /api/articles/{id}/corrected-version/          -> el autor sube su PDF corregido
    """

    def get_permissions(self):
        resource_permission = "view" if self.request.method == "GET" else "update"
        return [IsAuthenticated(), profile_permission("article", resource_permission)()]

    def get(self, request, pk):
        article = _get_article(pk)
        is_author = article.article_created_by_id == request.user.pk
        if not (is_committee(request.user) or is_author or _is_active_reviewer(request.user, article)):
            raise PermissionDenied("No tienes permiso para ver esta versión.")
        return Response(ArticleVersionsSerializer(article).data, status=status.HTTP_200_OK)

    @transaction.atomic
    def post(self, request, pk):
        article = _get_article(pk)
        _require_author(article, request.user, "Solo el autor puede subir la versión corregida.")

        serializer = CorrectedVersionUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["corrected_pdf"]

        key = upload_version_file(upload, "corrected_versions", ".pdf")
        attachment = ArticleAttached.objects.create(
            article=article,
            article_attached_url=key,
            article_attached_version="Corregida",
            article_attached_created_by=request.user,
        )
        article.article_updated_by = request.user
        article.article_updated_at = timezone.now()
        article.save(update_fields=["article_updated_by", "article_updated_at"])

        return Response(
            {
                "detail": "Versión corregida subida correctamente.",
                "corrected_version": ArticleAttachedSerializer(attachment).data,
            },
            status=status.HTTP_201_CREATED,
        )


class ArticleAvalPresentationView(APIView):
    """POST /api/articles/{id}/aval-presentation/  (CA-02 a CA-05) -> constancia PDF"""

    permission_classes = [IsAuthenticated, profile_permission("evaluation", "update")]

    @transaction.atomic
    def post(self, request, pk):
        article = _get_article(pk)
        inp = AvalInputSerializer(data=request.data)
        inp.is_valid(raise_exception=True)

        user = request.user
        committee = is_committee(user)

        if article.article_created_by_id == user.pk:
            raise PermissionDenied("No puedes avalar tu propio artículo.")

        row = _reviewer_row(article, user)

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
            return Response(
                {"detail": f"No se puede emitir aval desde el estado actual: {row.status}"},
                status=status.HTTP_409_CONFLICT,
            )

        row.status = "FOR_PRESENTATION"
        row.comment = inp.validated_data.get("comment", row.comment)
        row.article_reviewer_updated_by = user
        row.article_reviewer_updated_at = timezone.now()

        try:
            with transaction.atomic():
                row.save()
        except IntegrityError:
            return Response(
                {"detail": "El aval ya fue registrado por otra solicitud. Intenta de nuevo."},
                status=status.HTTP_409_CONFLICT,
            )

        response = HttpResponse(_build_aval_pdf(article, user), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="Aval_Articulo_{article.article_id}.pdf"'
        response["Cache-Control"] = "no-store"
        return response


# ==============================================================================
# SCRUM-31
# ==============================================================================
class ArticleFinalSubmissionView(APIView):
    """POST /api/articles/{id}/final-submission/ (CA-01, CA-02) -> versión final + copyright"""

    permission_classes = [IsAuthenticated, profile_permission("article", "update")]

    @transaction.atomic
    def post(self, request, pk):
        article = _get_article(pk)
        _require_author(article, request.user, "Solo el autor puede subir la versión final.")

        serializer = FinalSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        final_pdf = serializer.validated_data["final_pdf"]
        copyright_file = serializer.validated_data["copyright_pdf"]

        final_key = upload_version_file(final_pdf, "final_versions", ".pdf")
        ArticleAttached.objects.create(
            article=article,
            article_attached_url=final_key,
            article_attached_version="Final",
            article_attached_created_by=request.user,
        )

        copyright_ext = os.path.splitext(copyright_file.name)[1].lower()
        copyright_key = upload_version_file(copyright_file, "copyrights", copyright_ext)

        article.article_copyright_url = copyright_key
        article.article_updated_by = request.user
        article.article_updated_at = timezone.now()
        article.save(update_fields=["article_copyright_url", "article_updated_by", "article_updated_at"])

        return Response(
            {"detail": "Versión final y copyright subidos correctamente.", "copyright_url": copyright_key},
            status=status.HTTP_201_CREATED,
        )


class ArticleAvalPublicationView(APIView):
    """POST /api/articles/{id}/aval-publication/ (CA-03 a CA-06) -> certificado PDF"""

    permission_classes = [IsAuthenticated, profile_permission("evaluation", "update")]

    @transaction.atomic
    def post(self, request, pk):
        article = _get_article(pk)
        user = request.user

        if article.article_created_by_id == user.pk:
            raise PermissionDenied("No puedes avalar tu propio artículo.")

        committee = is_committee(user)
        row = _reviewer_row(article, user)

        if not committee and not row:
            raise PermissionDenied("Solo el comité o revisores asignados pueden dar el aval de publicación.")
        if row is not None and not committee and not (row.article_reviewer_active and not row.article_reviewer_delete):
            raise PermissionDenied("Tu asignación como evaluador ya no está activa.")

        if row is not None and row.status == "REJECTED":
            return Response(
                {"detail": "No se puede avalar la publicación de un artículo rechazado."},
                status=status.HTTP_409_CONFLICT,
            )

        if not article.article_copyright_url:
            return Response(
                {"detail": "El autor aún no ha subido el documento de copyright."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if row is not None:
            row.status = "FOR_PUBLICATION"
            row.article_reviewer_updated_by = user
            row.article_reviewer_updated_at = timezone.now()
            row.save()

        if not article.verification_code:
            article.verification_code = uuid.uuid4()
        article.article_updated_by = user
        article.article_updated_at = timezone.now()
        article.save(update_fields=["verification_code", "article_updated_by", "article_updated_at"])

        response = HttpResponse(_build_publication_pdf(article, user), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="Certificado_Publicacion_{article.article_id}.pdf"'
        response["Cache-Control"] = "no-store"
        return response


# ==============================================================================
# Generadores de PDF
# ==============================================================================
def _author_and_subject(article):
    author = article.article_created_by
    author_name = f"{author.user_name} {author.user_lastname}".strip() if author else "Desconocido"
    subject = article.article_subject
    if len(subject) > 60:
        subject = subject[:60] + "..."
    return author_name, subject


def _build_aval_pdf(article, issuer):
    """Constancia de aval para presentación, en memoria (SCRUM-30)."""
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.setFont("Helvetica-Bold", 18)
    p.drawCentredString(300, 750, "SIGECI - Constancia de Aval")

    p.setFont("Helvetica", 12)
    author_name, subject = _author_and_subject(article)
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
    """Certificado formal de publicación (CA-05 SCRUM-31)."""
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.setFont("Helvetica-Bold", 18)
    p.drawCentredString(300, 750, "SIGECI - Certificado de Publicación")

    p.setFont("Helvetica", 12)
    author_name, subject = _author_and_subject(article)
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
