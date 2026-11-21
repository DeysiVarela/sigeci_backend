from django.db import connection

def queryDB(query_string, params = None):
    with connection.cursor() as cursor:
        if not params:
            cursor.execute(query_string)
        else:
            cursor.execute(query_string, params)
        columns = [col[0] for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        print("rows", rows)
        return rows