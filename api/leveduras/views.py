import cv2, numpy as np, os
from cellpose import models, core, io, plot
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import AnaliseLevedura, ImagemMicroscopica, ImagemColonia, LeveduraSegmentada
from .serializers import AnaliseLeveduraSerializer
from django.core.files.base import ContentFile
from django.utils import timezone
import tempfile
from django.core.files import File
import math
# Cria um nome de arquivo único
from django.utils import timezone
import uuid
from django.db.models import Avg, StdDev, Min, Max
import threading

MICRONS_PER_PIXEL = 0.035

@api_view(['POST'])
def criar_analise(request):
    serializer = AnaliseLeveduraSerializer(data=request.data)
    
    if serializer.is_valid():
        analise = serializer.save()
        return Response({
            'id': str(analise.id),
            'mensagem': 'Análise criada com sucesso',
            'endpoints_upload': {
                'microscopica': f'/api/analises/{analise.id}/microscopica/',
                'colonia': f'/api/analises/{analise.id}/colonia/'
            }
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
def status_analise(request, analise_id):
    analise = get_object_or_404(AnaliseLevedura, id=analise_id)
    serializer = AnaliseLeveduraSerializer(analise)
    return Response(serializer.data)

@api_view(['POST'])
def upload_imagem_microscopica(request, analise_id):
    analise = get_object_or_404(AnaliseLevedura, id=analise_id)
    
    if 'imagem' not in request.FILES:
        return Response(
            {'erro': 'Nenhuma imagem fornecida'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    imagem = request.FILES['imagem']
    
    if not imagem.content_type.startswith('image/'):
        return Response(
            {'erro': 'Arquivo não é uma imagem válida'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Salva a imagem primeiro
        imagem_micro = ImagemMicroscopica.objects.create(
            analise=analise,
            imagem=imagem,
            status_processamento='pendente',
            metadata={
                'nome_arquivo': imagem.name,
                'tamanho': imagem.size,
                'tipo_conteudo': imagem.content_type,
            }
        )
        
        # Força o save para garantir que o arquivo seja escrito
        imagem_micro.save()
        
        # Inicia o processamento em thread separada
        import threading
        thread = threading.Thread(
            target=processar_em_background,
            args=(str(imagem_micro.id),)
        )
        thread.daemon = True
        thread.start()
        
        return Response({
            'id': str(imagem_micro.id),
            'mensagem': 'Imagem recebida e em processamento',
            'analise_id': str(analise_id),
            'status': 'pendente',
            'url_imagem': imagem_micro.imagem.url,
            'endpoint_status': f'/api/analises/{imagem_micro.id}/status/'
        }, status=status.HTTP_202_ACCEPTED)
        
    except Exception as e:
        return Response(
            {'erro': f'Erro ao salvar imagem: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

def processar_em_background(imagem_micro_id):
    """Processa a segmentação em background"""
    try:
        from django.utils import timezone
        
        imagem_micro = ImagemMicroscopica.objects.get(id=imagem_micro_id)
        imagem_micro.status_processamento = 'processando'
        imagem_micro.iniciado_em = timezone.now()
        imagem_micro.progresso = 10
        imagem_micro.save()
        
        # Aguarda um pouco para garantir que o arquivo foi salvo
        import time
        time.sleep(2)
        
        # Verifica novamente se o arquivo existe
        if not imagem_micro.imagem or not hasattr(imagem_micro.imagem, 'path'):
            raise ValueError("Arquivo de imagem não disponível para processamento")
        
        # Processa a segmentação
        leveduras_segmentadas = processar_segmentacao(
            imagem_micro, 
            imagem_micro.analise
        )
        
        # Atualiza status para concluído
        imagem_micro.status_processamento = 'concluido'
        imagem_micro.progresso = 100
        imagem_micro.concluido_em = timezone.now()
        imagem_micro.save()
        
        print(f"Processamento concluído para {imagem_micro_id}")
        return leveduras_segmentadas
        
    except Exception as e:
        imagem_micro = ImagemMicroscopica.objects.get(id=imagem_micro_id)
        imagem_micro.status_processamento = 'erro'
        imagem_micro.erro_processamento = str(e)
        imagem_micro.save()
        print(f"Erro no processamento: {str(e)}")
        raise e

@api_view(['GET'])
def status_processamento(request, imagem_id):
    """Endpoint para verificar status do processamento"""
    imagem_micro = get_object_or_404(ImagemMicroscopica, id=imagem_id)
    
    response_data = {
        'id': str(imagem_micro.id),
        'status': imagem_micro.status_processamento,
        'progresso': imagem_micro.progresso,
        'criado_em': imagem_micro.criado_em,
        'iniciado_em': imagem_micro.iniciado_em,
        'concluido_em': imagem_micro.concluido_em,
    }
    
    if imagem_micro.status_processamento == 'concluido':
        leveduras = imagem_micro.leveduras_segmentadas.all()
        response_data['total_leveduras'] = leveduras.count()
        response_data['leveduras_segmentadas'] = [
            {
                'id': str(lev.id),
                'levedura_id': lev.levedura_id,
                'url_imagem': lev.imagem.url,
                'bounding_box': lev.bounding_box,
                'area_pixels': lev.bounding_box['width'] * lev.bounding_box['height'],
                # Características extraídas
                'caracteristicas': lev.caracteristicas if lev.caracteristicas else {},
                'caracteristicas_formatadas': {
                    'Área': f"{lev.caracteristicas.get('area_microns', 0):.2f} µm²" if lev.caracteristicas else "N/A",
                    'Perímetro': f"{lev.caracteristicas.get('perimetro_microns', 0):.2f} µm" if lev.caracteristicas else "N/A",
                    'Circularidade': f"{lev.caracteristicas.get('circularidade', 0):.3f}" if lev.caracteristicas else "N/A",
                    'Solidez': f"{lev.caracteristicas.get('solidez', 0):.3f}" if lev.caracteristicas else "N/A",
                    'Diâmetro Equivalente': f"{lev.caracteristicas.get('diametro_equivalente_microns', 0):.2f} µm" if lev.caracteristicas else "N/A",
                    'Eixo Maior': f"{lev.caracteristicas.get('eixo_maior_microns', 0):.2f} µm" if lev.caracteristicas else "N/A",
                    'Eixo Menor': f"{lev.caracteristicas.get('eixo_menor_microns', 0):.2f} µm" if lev.caracteristicas else "N/A",
                    'Relação de Aspecto': f"{lev.caracteristicas.get('relacao_aspecto', 0):.2f}" if lev.caracteristicas else "N/A",
                    'Ângulo do Eixo Principal': f"{lev.caracteristicas.get('angulacao_graus', 0):.1f}°" if lev.caracteristicas else "N/A",
                    'Centroide': f"({lev.caracteristicas.get('centroide_x', 0)}, {lev.caracteristicas.get('centroide_y', 0)})" if lev.caracteristicas else "N/A"
                },
                # Campos individuais para facilitar filtros
                'diametro_equivalente': lev.diametro_equivalente,
                'circularidade': lev.circularidade,
                'solidez': lev.solidez,
                'relacao_aspecto': lev.relacao_aspecto,
                'area_microns': lev.area_microns,
                'metadata': lev.metadata
            }
            for lev in leveduras
        ]
        
        # Adiciona estatísticas gerais se houver leveduras
        if leveduras.exists():
            leveduras_com_caract = leveduras.exclude(caracteristicas={})
            response_data['estatisticas_gerais'] = {
                'leveduras_com_caracteristicas': leveduras_com_caract.count(),
                'taxa_sucesso_caracteristicas': f"{(leveduras_com_caract.count() / leveduras.count()) * 100:.1f}%",
                'media_area_microns': leveduras_com_caract.aggregate(Avg('area_microns'))['area_microns__avg'],
                'media_circularidade': leveduras_com_caract.aggregate(Avg('circularidade'))['circularidade__avg'],
                'media_relacao_aspecto': leveduras_com_caract.aggregate(Avg('relacao_aspecto'))['relacao_aspecto__avg']
            }
        
    elif imagem_micro.status_processamento == 'erro':
        response_data['erro'] = imagem_micro.erro_processamento
    
    return Response(response_data)

def processar_segmentacao(imagem_micro, analise):
    """
    Processa a segmentação da imagem e retorna as leveduras encontradas
    """
    try:
        # Verifica se o arquivo de imagem está associado
        if not imagem_micro.imagem:
            raise ValueError("Nenhuma imagem associada ao objeto ImagemMicroscopica")
        
        if not hasattr(imagem_micro.imagem, 'path') or not imagem_micro.imagem.path:
            raise ValueError("Arquivo de imagem não encontrado no sistema de arquivos")
        
        # 1. Carrega e prepara a imagem
        img_path = imagem_micro.imagem.path
        img = io.imread(img_path)
        print(f"Shape da imagem original: {img.shape}")
        
        # Converte para escala de cinza se necessário
        if len(img.shape) == 3:
            img_gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        else:
            img_gray = img

        # 2. Configuração do modelo
        model = models.CellposeModel(gpu=True, model_type='cyto')
        channels = [0, 0]  # (canal_de_segmentacao, canal_do_nucleo)

        # 3. Parâmetros de segmentação
        flow_threshold = 0.2 
        cellprob_threshold = 0.2 
        tile_norm_blocksize = 0

        print("Executando segmentação com Cellpose...")
        masks, flows, styles = model.eval(
            img_gray, 
            channels=channels,
            batch_size=32, 
            flow_threshold=flow_threshold, 
            cellprob_threshold=cellprob_threshold, 
            normalize={"tile_norm_blocksize": tile_norm_blocksize}
        )
        print("Segmentação concluída.")

        # 4. Processa cada levedura segmentada
        unique_levedura_ids = np.unique(masks)
        total_leveduras = len(unique_levedura_ids) - 1 
        print(f"\nContagem total de leveduras segmentadas: {total_leveduras}")

        leveduras_segmentadas = []
        levedura_count = 0

        for levedura_id in unique_levedura_ids:
            if levedura_id == 0:  # Ignora o fundo
                continue

            levedura_count += 1

            # Cria máscara binária para a levedura atual
            individual_mask = (masks == levedura_id).astype(np.uint8) * 255

            # Encontra contornos para obter bounding box
            contours, _ = cv2.findContours(individual_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            if contours:
                cnt = max(contours, key=cv2.contourArea)
                x, y, w, h = cv2.boundingRect(cnt)
                
                # Adiciona padding
                padding = 5 
                x_start = max(0, x - padding)
                y_start = max(0, y - padding)
                x_end = min(img.shape[1], x + w + padding)
                y_end = min(img.shape[0], y + h + padding)

                # Recorta a levedura
                if len(img.shape) == 3:
                    cropped_levedura = img[y_start:y_end, x_start:x_end]
                else:
                    cropped_levedura = img_gray[y_start:y_end, x_start:x_end]

                # Salva a levedura segmentada no banco de dados
                levedura_obj = salvar_levedura_segmentada(
                    cropped_levedura, 
                    levedura_id, 
                    analise, 
                    imagem_micro,
                    (x, y, w, h)
                )
                
                # Adiciona à lista de resposta
                leveduras_segmentadas.append({
                    'id': str(levedura_obj.id),
                    'levedura_id': int(levedura_id),
                    'url_imagem': levedura_obj.imagem.url,
                    'bounding_box': {
                        'x': x,
                        'y': y,
                        'width': w,
                        'height': h
                    },
                    'area': w * h
                })
                
                print(f"Levedura {levedura_id} processada e salva")

        print(f"\nTodas as {levedura_count} leveduras foram processadas.")
        return leveduras_segmentadas

    except Exception as e:
        print(f"Erro durante a segmentação: {str(e)}")
        raise e

def salvar_levedura_segmentada(imagem_array, levedura_id, analise, imagem_micro, bounding_box):
    """
    Salva uma levedura segmentada no banco de dados - Versão alternativa
    """
    try:
        caracteristicas = extrair_caracteristicas_levedura(imagem_array)
        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        filename = f"levedura_{levedura_id:04d}_{timestamp}_{unique_id}.png"
        
        # Salva temporariamente no disco
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
            if len(imagem_array.shape) == 2:  # Imagem em escala de cinza
                success = cv2.imwrite(temp_file.name, imagem_array)
            else:  # Imagem colorida
                success = cv2.imwrite(temp_file.name, cv2.cvtColor(imagem_array, cv2.COLOR_RGB2BGR))
            
            if not success:
                raise ValueError("Erro ao salvar imagem temporária")
            
            # Cria o objeto no banco de dados
            with open(temp_file.name, 'rb') as file:
                levedura = LeveduraSegmentada(
                    analise=analise,
                    imagem_original=imagem_micro,
                    levedura_id=levedura_id,
                    nome_arquivo=filename,
                    bounding_box={
                        'x': bounding_box[0],
                        'y': bounding_box[1],
                        'width': bounding_box[2],
                        'height': bounding_box[3]
                    },
                    caracteristicas=caracteristicas or {},
                    # Campos individuais para facilitar consultas
                    diametro_equivalente=caracteristicas.get('diametro_equivalente_microns') if caracteristicas else None,
                    circularidade=caracteristicas.get('circularidade') if caracteristicas else None,
                    solidez=caracteristicas.get('solidez') if caracteristicas else None,
                    relacao_aspecto=caracteristicas.get('relacao_aspecto') if caracteristicas else None,
                    area_pixels=caracteristicas.get('area_pixels') if caracteristicas else None,
                    area_microns=caracteristicas.get('area_microns') if caracteristicas else None,
                    metadata={
                        'area': bounding_box[2] * bounding_box[3],
                        'formato': 'PNG',
                        'dimensoes': {
                            'altura': imagem_array.shape[0],
                            'largura': imagem_array.shape[1]
                        },
                        'caracteristicas_extrahidas': bool(caracteristicas)
                    }
                )
                levedura.imagem.save(filename, File(file))
                levedura.save()
        
        # Limpa o arquivo temporário
        os.unlink(temp_file.name)
        
        print(f"Levedura {levedura_id} salva com sucesso: {filename}")
        return levedura
        
    except Exception as e:
        # Garante que o arquivo temporário seja removido em caso de erro
        if 'temp_file' in locals() and os.path.exists(temp_file.name):
            os.unlink(temp_file.name)
        print(f"Erro ao salvar levedura {levedura_id}: {str(e)}")
        raise e
    
@api_view(['POST'])
def upload_imagem_colonia(request, analise_id):
    analise = get_object_or_404(AnaliseLevedura, id=analise_id)
    
    if 'imagem' not in request.FILES:
        return Response(
            {'erro': 'Nenhuma imagem fornecida'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    imagem = request.FILES['imagem']
    
    if not imagem.content_type.startswith('image/'):
        return Response(
            {'erro': 'Arquivo não é uma imagem válida'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    imagem_colonia = ImagemColonia.objects.create(
        analise=analise,
        imagem=imagem,
        metadata={
            'nome_arquivo': imagem.name,
            'tamanho': imagem.size,
            'tipo_conteudo': imagem.content_type,
        }
    )
    
    return Response({
        'id': str(imagem_colonia.id),
        'mensagem': 'Imagem de colônia salva com sucesso',
        'analise_id': str(analise_id),
        'url_imagem': imagem_colonia.imagem.url
    }, status=status.HTTP_201_CREATED)


def extrair_caracteristicas_levedura(imagem_array, microns_por_pixel=MICRONS_PER_PIXEL):
    """
    Extrai características morfológicas de uma levedura a partir de um array numpy
    """
    try:
        # Se a imagem for colorida, converte para escala de cinza
        if len(imagem_array.shape) == 3:
            img_gray = cv2.cvtColor(imagem_array, cv2.COLOR_RGB2GRAY)
        else:
            img_gray = imagem_array
        
        # 1. Tratamento de Contraste (CLAHE)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        contrasted_img = clahe.apply(img_gray)
        
        # 2. Limiarização
        _, binary_mask = cv2.threshold(contrasted_img, 80, 255, cv2.THRESH_BINARY_INV)
        
        # 3. Encontrar Contornos
        contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            # Fallback para Otsu
            _, binary_mask_otsu = cv2.threshold(contrasted_img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            contours, _ = cv2.findContours(binary_mask_otsu, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                return None
        
        # Pega o maior contorno
        contour = max(contours, key=cv2.contourArea)
        
        # Filtra contornos muito pequenos
        if cv2.contourArea(contour) < 50:
            return None
        
        caracteristicas = {}
        
        # --- CÁLCULO DAS CARACTERÍSTICAS ---
        area_pixels = cv2.contourArea(contour)
        area_microns2 = area_pixels * (microns_por_pixel ** 2)
        
        perimetro_pixels = cv2.arcLength(contour, closed=True)
        perimetro_microns = perimetro_pixels * microns_por_pixel
        
        # Circularidade
        circularidade = (4 * np.pi * area_pixels) / (perimetro_pixels ** 2) if perimetro_pixels > 0 else 0.0
        
        # Solidez
        hull = cv2.convexHull(contour)
        area_hull = cv2.contourArea(hull)
        solidez = area_pixels / area_hull if area_hull > 0 else 0.0
        
        # Diâmetro equivalente (diâmetro de um círculo com a mesma área)
        diametro_equivalente_pixels = 2 * math.sqrt(area_pixels / math.pi)
        diametro_equivalente_microns = diametro_equivalente_pixels * microns_por_pixel
        
        # Eixos e relação de aspecto
        eixo_maior_microns = 0
        eixo_menor_microns = 0
        relacao_aspecto = 0
        angulacao_graus = 0
        
        if len(contour) >= 5:
            (center_ellipse, axes_ellipse, angle_ellipse) = cv2.fitEllipse(contour)
            eixo_menor_pixels = min(axes_ellipse)
            eixo_maior_pixels = max(axes_ellipse)
            
            eixo_maior_microns = eixo_maior_pixels * microns_por_pixel
            eixo_menor_microns = eixo_menor_pixels * microns_por_pixel
            relacao_aspecto = eixo_maior_pixels / eixo_menor_pixels
            angulacao_graus = angle_ellipse
        
        # Centroide
        M = cv2.moments(contour)
        cx, cy = 0, 0
        if M["m00"] != 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
        
        # Compilar todas as características
        caracteristicas_completas = {
            'area_pixels': float(area_pixels),
            'area_microns': float(area_microns2),
            'perimetro_pixels': float(perimetro_pixels),
            'perimetro_microns': float(perimetro_microns),
            'circularidade': float(circularidade),
            'solidez': float(solidez),
            'diametro_equivalente_microns': float(diametro_equivalente_microns),
            'eixo_maior_microns': float(eixo_maior_microns),
            'eixo_menor_microns': float(eixo_menor_microns),
            'relacao_aspecto': float(relacao_aspecto),
            'angulacao_graus': float(angulacao_graus),
            'centroide_x': cx,
            'centroide_y': cy,
            'microns_por_pixel': microns_por_pixel
        }
        
        return caracteristicas_completas
        
    except Exception as e:
        print(f"Erro ao extrair características: {str(e)}")
        return None
    
@api_view(['GET'])
def estatisticas_caracteristicas(request, imagem_id):
    """
    Retorna estatísticas das características das leveduras de uma imagem
    """
    try:
        leveduras = LeveduraSegmentada.objects.filter(imagem_original_id=imagem_id)
        
        estatisticas = {
            'total_leveduras': leveduras.count(),
            'area_microns': {
                'media': leveduras.aggregate(Avg('area_microns'))['area_microns__avg'],
                'desvio_padrao': leveduras.aggregate(StdDev('area_microns'))['area_microns__stddev'],
                'min': leveduras.aggregate(Min('area_microns'))['area_microns__min'],
                'max': leveduras.aggregate(Max('area_microns'))['area_microns__max']
            },
            'circularidade': {
                'media': leveduras.aggregate(Avg('circularidade'))['circularidade__avg'],
            },
            'relacao_aspecto': {
                'media': leveduras.aggregate(Avg('relacao_aspecto'))['relacao_aspecto__avg'],
            }
        }
        
        return Response(estatisticas)
        
    except Exception as e:
        return Response({'erro': str(e)}, status=400)