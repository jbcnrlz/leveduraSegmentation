from rest_framework import serializers
from .models import AnaliseLevedura, ImagemMicroscopica, ImagemColonia, LeveduraSegmentada

class ImagemMicroscopicaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImagemMicroscopica
        fields = ['id', 'imagem', 'criado_em', 'metadata']
        read_only_fields = ['id', 'criado_em']

class ImagemColoniaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImagemColonia
        fields = ['id', 'imagem', 'criado_em', 'metadata']
        read_only_fields = ['id', 'criado_em']

class AnaliseLeveduraSerializer(serializers.ModelSerializer):
    imagens_microscopicas = ImagemMicroscopicaSerializer(many=True, read_only=True)
    imagens_colonias = ImagemColoniaSerializer(many=True, read_only=True)
    
    class Meta:
        model = AnaliseLevedura
        fields = [
            'id', 'nome_amostra', 'descricao', 'usuario',
            'status', 'resultado', 'criado_em', 'atualizado_em',
            'imagens_microscopicas', 'imagens_colonias'
        ]
        read_only_fields = ['id', 'criado_em', 'atualizado_em', 'status', 'resultado']


class LeveduraSegmentadaSerializer(serializers.ModelSerializer):
    caracteristicas_formatadas = serializers.SerializerMethodField()
    
    class Meta:
        model = LeveduraSegmentada
        fields = [
            'id', 
            'levedura_id', 
            'imagem', 
            'nome_arquivo',
            'bounding_box', 
            'caracteristicas',
            'caracteristicas_formatadas',
            'diametro_equivalente',
            'circularidade',
            'solidez',
            'relacao_aspecto',
            'area_microns',
            'metadata',
            'criado_em'
        ]
    
    def get_caracteristicas_formatadas(self, obj):
        """Retorna as características em formato legível"""
        if not obj.caracteristicas:
            return {}
        
        return {
            'Área': f"{obj.caracteristicas.get('area_microns', 0):.2f} µm²",
            'Perímetro': f"{obj.caracteristicas.get('perimetro_microns', 0):.2f} µm",
            'Circularidade': f"{obj.caracteristicas.get('circularidade', 0):.3f}",
            'Solidez': f"{obj.caracteristicas.get('solidez', 0):.3f}",
            'Diâmetro Equivalente': f"{obj.caracteristicas.get('diametro_equivalente_microns', 0):.2f} µm",
            'Relação de Aspecto': f"{obj.caracteristicas.get('relacao_aspecto', 0):.2f}",
            'Ângulo': f"{obj.caracteristicas.get('angulacao_graus', 0):.1f}°"
        }
    
    