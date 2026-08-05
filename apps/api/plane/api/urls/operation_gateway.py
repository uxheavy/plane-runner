from django.urls import path

from plane.operation_gateway.views import OperationGatewayAPIEndpoint

urlpatterns = [
    path(
        "operations/",
        OperationGatewayAPIEndpoint.as_view(http_method_names=["post"]),
        name="operation-gateway",
    ),
]
