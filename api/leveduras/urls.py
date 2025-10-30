from django.urls import path
from . import views

app_name = 'leveduras'

urlpatterns = [
    path('analises/', views.criar_analise, name='criar_analise'),
    path('analises/<uuid:analise_id>/', views.status_analise, name='status_analise'),
    path('analises/<uuid:analise_id>/microscopica/', views.upload_imagem_microscopica, name='upload_microscopica'),
    path('analises/<uuid:analise_id>/colonia/', views.upload_imagem_colonia, name='upload_colonia'),
    path('analises/<int:imagem_id>/status/', views.status_processamento, name='status-processamento'),
    path('analises/<int:imagem_id>/levedura_segmentada/', views.estatisticas_caracteristicas, name='leveduras-processamento'),
]