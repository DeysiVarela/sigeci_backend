from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.utils import timezone

# Importaciones para generar el PDF
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io

from .models import Article, ArticleReviewer
from .serializers import ArticleCorrectedVersionSerializer, AvalPresentationSerializer


class ArticleCorrectedVersionView(APIView):
    """
    GET /api/articles/{id}/corrected-version/
    Consulta la versión corregida enviada por el autor.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        article = get_object_or_404(Article, article_id=pk, article_delete=False)
        serializer = ArticleCorrectedVersionSerializer(article)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ArticleAvalPresentationView(APIView):
    """
    POST /api/articles/{id}/aval-presentation/
    Registra la decisión favorable y genera el PDF del AVAL formal (CA-02, CA-03, CA-04, CA-05).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        article = get_object_or_404(Article, article_id=pk, article_delete=False)
        
        # CA-03: Validar que el usuario sea ADMIN o MEMBER
        is_committee = request.user.profiles.filter(profile_name__in=["ADMIN", "MEMBER"]).exists()
        
        reviewer_assignment = ArticleReviewer.objects.filter(
            article=article, 
            user=request.user,
            article_reviewer_active=True,
            article_reviewer_delete=False
        ).first()

        if not is_committee and not reviewer_assignment:
            raise PermissionDenied("Solo los miembros del comité o evaluadores asignados pueden emitir el aval.")

        if reviewer_assignment:
            target_reviewer = reviewer_assignment
        else:
            target_reviewer = ArticleReviewer.objects.filter(article=article).first()
            if not target_reviewer:
                target_reviewer = ArticleReviewer(
                    article=article,
                    user=request.user,
                    status="FOR_PRESENTATION"
                )

        # CA-04: Actualizar estado y trazabilidad
        target_reviewer.status = "FOR_PRESENTATION" 
        target_reviewer.comment = request.data.get("comment", target_reviewer.comment)
        target_reviewer.article_reviewer_updated_by = request.user
        target_reviewer.save()

        # CA-05: Generar el PDF de la constancia
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        
        # Diseño del PDF
        p.setFont("Helvetica-Bold", 20)
        p.drawCentredString(300, 750, "SIGECI - Constancia de Aval")
        
        p.setFont("Helvetica", 12)
        p.drawString(100, 680, f"Artículo ID: {article.article_id}")
        p.drawString(100, 660, f"Título: {article.article_subject}")
        p.drawString(100, 640, f"Autor principal ID: {article.article_created_by_id}")
        
        p.line(100, 620, 500, 620)
        
        p.drawString(100, 590, "Por medio de la presente, se certifica que el artículo ha sido")
        p.drawString(100, 575, "evaluado y cuenta con el AVAL PARA PRESENTACIÓN en el evento.")
        
        p.setFont("Helvetica-Bold", 12)
        p.drawString(100, 520, f"Evaluador/Comité: {request.user.user_name} {request.user.user_lastname}")
        p.drawString(100, 500, f"Fecha de emisión: {timezone.now().strftime('%Y-%m-%d %H:%M')}")
        
        p.showPage()
        p.save()
        
        buffer.seek(0)
        
        # Retornar el PDF como descarga
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Aval_Articulo_{article.article_id}.pdf"'
        return response