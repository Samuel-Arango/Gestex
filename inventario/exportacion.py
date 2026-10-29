"""
Exportación de reportes a CSV y PDF (RF10).

Seguridad:
- CSV: los nombres de productos los escribe el usuario. Si una celda empieza
  con =, +, - o @, Excel la ejecutaría como fórmula ("inyección CSV").
  Esas celdas se escriben con una comilla simple delante para neutralizarlas.
- PDF: el texto se escapa antes de pasarlo a Paragraph, porque ReportLab
  interpreta etiquetas tipo <b>. Así un nombre con "<" no rompe el documento.
"""
import csv
from decimal import Decimal, InvalidOperation
from io import BytesIO
from xml.sax.saxutils import escape

from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

AZUL_OSCURO = colors.HexColor('#0f1b2d')
AZUL_CLARO = colors.HexColor('#f6f8fb')
ROJO_SUAVE = colors.HexColor('#fdecec')
GRIS_LINEA = colors.HexColor('#dfe6f0')

# Separador de columnas: punto y coma, que Excel en configuración española lee bien.
SEPARADOR_CSV = ';'


def _es_numero(texto):
    try:
        Decimal(texto)
        return True
    except (InvalidOperation, ValueError):
        return False


def celda_segura(valor):
    """Neutraliza valores que Excel podría interpretar como fórmulas."""
    texto = str(valor)
    if not texto:
        return texto
    if texto[0] in ('=', '+', '@', '\t', '\r'):
        return "'" + texto
    # Un guion inicial es válido en números negativos (balance -3.00), pero no en texto.
    if texto[0] == '-' and not _es_numero(texto):
        return "'" + texto
    return texto


def respuesta_csv(reporte, nombre_archivo):
    respuesta = HttpResponse(content_type='text/csv; charset=utf-8')
    respuesta['Content-Disposition'] = f'attachment; filename="{nombre_archivo}.csv"'

    # BOM UTF-8: Excel reconoce las tildes y las eñes sin configuración extra.
    respuesta.write('\ufeff')
    escritor = csv.writer(respuesta, delimiter=SEPARADOR_CSV)
    escritor.writerow(reporte['encabezados'])
    for fila in reporte['filas']:
        escritor.writerow([celda_segura(valor) for valor in fila['valores']])
    return respuesta


def generar_pdf(reporte, descripcion_filtros, generado_en):
    """Devuelve el PDF del reporte como bytes."""
    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.8 * cm,
        title=reporte['titulo'],
        author='Gestex',
    )

    estilos = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle(
        'titulo', parent=estilos['Title'], fontSize=16, leading=20,
        textColor=AZUL_OSCURO, alignment=0,
    )
    estilo_texto = ParagraphStyle('texto', parent=estilos['Normal'], fontSize=9, leading=12)
    estilo_celda = ParagraphStyle('celda', parent=estilo_texto, fontSize=8.5, leading=11)
    estilo_encabezado = ParagraphStyle(
        'encabezado', parent=estilo_celda, textColor=colors.white, fontName='Helvetica-Bold',
    )

    elementos = [
        Paragraph(escape(reporte['titulo']), estilo_titulo),
        Paragraph(escape(descripcion_filtros), estilo_texto),
        Paragraph(
            escape(' · '.join(f'{etiqueta}: {valor}' for etiqueta, valor in reporte['resumen'])),
            estilo_texto,
        ),
        Spacer(1, 10),
    ]

    if not reporte['filas']:
        elementos.append(Paragraph('No hay datos con estos filtros.', estilo_texto))
    else:
        encabezados = reporte['encabezados']
        datos = [[Paragraph(escape(str(titulo)), estilo_encabezado) for titulo in encabezados]]
        for fila in reporte['filas']:
            datos.append([Paragraph(escape(str(valor)), estilo_celda) for valor in fila['valores']])

        ancho_columna = documento.width / len(encabezados)
        tabla = Table(datos, colWidths=[ancho_columna] * len(encabezados), repeatRows=1)

        estilo = [
            ('BACKGROUND', (0, 0), (-1, 0), AZUL_OSCURO),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0.25, GRIS_LINEA),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, AZUL_CLARO]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]
        for indice, fila in enumerate(reporte['filas'], start=1):
            if fila['alerta']:
                estilo.append(('BACKGROUND', (0, indice), (-1, indice), ROJO_SUAVE))
        tabla.setStyle(TableStyle(estilo))
        elementos.append(tabla)

    elementos.extend([Spacer(1, 10), Paragraph(escape(reporte['nota']), estilo_texto)])

    def pie_de_pagina(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#64748b'))
        canvas.drawString(doc.leftMargin, 0.9 * cm, f'Gestex · Generado el {generado_en:%d/%m/%Y %H:%M}')
        canvas.drawRightString(
            doc.pagesize[0] - doc.rightMargin, 0.9 * cm, f'Página {canvas.getPageNumber()}',
        )
        canvas.restoreState()

    documento.build(elementos, onFirstPage=pie_de_pagina, onLaterPages=pie_de_pagina)
    return buffer.getvalue()


def respuesta_pdf(reporte, descripcion_filtros, generado_en, nombre_archivo):
    respuesta = HttpResponse(generar_pdf(reporte, descripcion_filtros, generado_en), content_type='application/pdf')
    respuesta['Content-Disposition'] = f'attachment; filename="{nombre_archivo}.pdf"'
    return respuesta
