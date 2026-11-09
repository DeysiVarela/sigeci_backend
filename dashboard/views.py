from django.db import connection
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def get_metrics(request):
    """
    Retorna métricas para el Dashboard ejecutando una consulta SQL directa.
    """
    if request.method != "GET":
        return JsonResponse({"detail": "Método no permitido."}, status=405)

    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            sql_query = """
                SELECT 
                    FLOOR(RANDOM() * 401 + 100)::INT AS new_orders,
                    ROUND((RANDOM() * 100)::NUMERIC, 2) AS bounce_rate,
                    FLOOR(RANDOM() * 801 + 200)::INT AS user_registrations,
                    FLOOR(RANDOM() * 4001 + 1000)::INT AS unique_visitors,
                    FLOOR(RANDOM() * 46 + 5)::INT AS total_articles
            """
        else:
            sql_query = """
                SELECT 
                    ABS(RANDOM() % 401) + 100 AS new_orders,
                    ROUND(ABS(RANDOM() % 10000) / 100.0, 2) AS bounce_rate,
                    ABS(RANDOM() % 801) + 200 AS user_registrations,
                    ABS(RANDOM() % 4001) + 1000 AS unique_visitors,
                    ABS(RANDOM() % 46) + 5 AS total_articles
            """
        cursor.execute(sql_query)
        row = cursor.fetchone()
        columns = [col[0] for col in cursor.description]
        metrics = dict(zip(columns, row))

    return JsonResponse({
        "status": "success",
        "data": metrics,
    }, status=200)
