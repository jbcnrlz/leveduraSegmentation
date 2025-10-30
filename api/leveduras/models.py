import uuid
from django.db import models
from django.utils import timezone

class AnaliseLevedura(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nome_amostra = models.CharField(max_length=200, blank=True)
    descricao = models.TextField(blank=True)
    usuario = models.CharField(max_length=100, blank=True)
    
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('processando', 'Processando'),
        ('concluido', 'Concluído'),
        ('erro', 'Erro'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pendente')
    
    resultado = models.JSONField(null=True, blank=True)
    criado_em = models.DateTimeField(default=timezone.now)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.nome_amostra} - {self.status}"

class ImagemMicroscopica(models.Model):
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('processando', 'Processando'),
        ('concluido', 'Concluído'),
        ('erro', 'Erro'),
    ]
    analise = models.ForeignKey(AnaliseLevedura, on_delete=models.CASCADE, related_name='imagens_microscopicas')
    imagem = models.ImageField(upload_to='leveduras/microscopicas/%Y/%m/%d/')
    metadata = models.JSONField(null=True, blank=True)
    criado_em = models.DateTimeField(default=timezone.now)
    status_processamento = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pendente'
    )
    progresso = models.IntegerField(default=0)  # 0-100%
    erro_processamento = models.TextField(blank=True, null=True)
    task_id = models.CharField(max_length=255, blank=True, null=True)
    iniciado_em = models.DateTimeField(null=True, blank=True)
    concluido_em = models.DateTimeField(null=True, blank=True)
    def __str__(self):
        return f"Microscópica - {self.analise.nome_amostra}"

class ImagemColonia(models.Model):
    analise = models.ForeignKey(AnaliseLevedura, on_delete=models.CASCADE, related_name='imagens_colonias')
    imagem = models.ImageField(upload_to='leveduras/colonias/%Y/%m/%d/')
    metadata = models.JSONField(null=True, blank=True)
    criado_em = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Colônia - {self.analise.nome_amostra}"
    

class LeveduraSegmentada(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    analise = models.ForeignKey('AnaliseLevedura', on_delete=models.CASCADE, related_name='leveduras_segmentadas')
    imagem_original = models.ForeignKey('ImagemMicroscopica', on_delete=models.CASCADE, related_name='leveduras_segmentadas')
    levedura_id = models.IntegerField(help_text="ID da levedura na segmentação")
    imagem = models.ImageField(
        upload_to='leveduras_segmentadas/%Y/%m/%d/',
        max_length=500
    )
    nome_arquivo = models.CharField(max_length=255)
    bounding_box = models.JSONField(help_text="Coordenadas da bounding box {x, y, width, height}")
    metadata = models.JSONField(default=dict)
    criado_em = models.DateTimeField(auto_now_add=True)
    caracteristicas = models.JSONField(default=dict, blank=True)
    diametro_equivalente = models.FloatField(null=True, blank=True)  # em micrômetros
    circularidade = models.FloatField(null=True, blank=True)
    solidez = models.FloatField(null=True, blank=True)
    relacao_aspecto = models.FloatField(null=True, blank=True)
    area_pixels = models.FloatField(null=True, blank=True)
    area_microns = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = 'leveduras_segmentadas'
        ordering = ['levedura_id']
    
    def __str__(self):
        return f"Levedura {self.levedura_id} - {self.analise}"