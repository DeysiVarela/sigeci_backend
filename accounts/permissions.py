from rest_framework.permissions import BasePermission

# Método/acción del viewset -> permiso de la matriz
ACTION_TO_PERMISSION = {
    "list": "view",
    "retrieve": "view",
    "create": "create",
    "update": "update",
    "partial_update": "update",
    "destroy": "delete",
}


class HasProfilePermission(BasePermission):
    """
    Autorización en el servidor según la matriz profile_action.
    La vista declara `permission_resource = "user"`.
    """

    message = "No tienes permiso para realizar esta acción."

    def has_permission(self, request, view):
        user = request.user
        if not user or not getattr(user, "is_authenticated", False):
            return False
        permission = ACTION_TO_PERMISSION.get(getattr(view, "action", None))
        if permission is None:
            return False
        return user.has_perm_on(view.permission_resource, permission)
