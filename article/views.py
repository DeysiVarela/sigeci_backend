import io

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

from .models import Article, ArticleReviewer
from .serializers import ArticleCorrectedVersionSerializer, AvalInputSerializer

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


def _build_aval_pdf(article, issuer):
    """Genera la constancia en memoria (BytesIO); no escribe nada en disco."""
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


class ArticleCorrectedVersionView(APIView):
    """GET /api/articles/{id}/corrected-version/  (CA-01)"""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        article = get_object_or_404(Article, article_id=pk, article_delete=False)

        is_author = article.article_created_by_id == request.user.pk
        if not (is_committee(request.user) or is_author or _is_active_reviewer(request.user, article)):
            raise PermissionDenied("No tienes permiso para ver esta versión.")

        return Response(ArticleCorrectedVersionSerializer(article).data, status=status.HTTP_200_OK)


class ArticleAvalPresentationView(APIView):
    """POST /api/articles/{id}/aval-presentation/  (CA-02, CA-03, CA-04, CA-05)"""

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        article = get_object_or_404(Article, article_id=pk, article_delete=False)

        inp = AvalInputSerializer(data=request.data)
        inp.is_valid(raise_exception=True)

        user = request.user
        committee = is_committee(user)

        # Nadie avala su propio artículo
        if article.article_created_by_id == user.pk:
            raise PermissionDenied("No puedes avalar tu propio artículo.")

        # Solo la fila de ESTE usuario (nunca la de otro revisor). La UniqueConstraint
        # (article, user) garantiza como máximo una, incluso si está inactiva/eliminada.
        row = ArticleReviewer.objects.select_for_update().filter(article=article, user=user).first()

        if row is None:
            if not committee:
                raise PermissionDenied(
                    "Solo los miembros del comité o evaluadores asignados pueden emitir el aval."
                )
            row = ArticleReviewer(
                article=article, user=user, article_reviewer_created_by=user
            )
        elif not (row.article_reviewer_active and not row.article_reviewer_delete):
            # Asignación dada de baja: solo el comité puede reactivarla
            if not committee:
                raise PermissionDenied(
                    "Solo los miembros del comité o evaluadores asignados pueden emitir el aval."
                )
            row.article_reviewer_active = True
            row.article_reviewer_delete = False
            row.status = "IN_REVIEW"

        # CA-04: transiciones válidas
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
            with transaction.atomic():  # savepoint: un choque de unicidad no rompe la petición
                row.save()
        except IntegrityError:
            return Response(
                {"detail": "El aval ya fue registrado por otra solicitud. Intenta de nuevo."},
                status=status.HTTP_409_CONFLICT,
            )

        # CA-05: PDF en memoria
        pdf_bytes = _build_aval_pdf(article, user)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="Aval_Articulo_{article.article_id}.pdf"'
        response["Cache-Control"] = "no-store"
        return response