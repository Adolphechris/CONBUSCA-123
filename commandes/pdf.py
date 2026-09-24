"""
Générateur PDF médico-légal pour les Bons de Commande Ets La Lumière.
"""
import io
from decimal import Decimal
from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    HRFlowable, Image as RLImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
)
import os


def generer_bon_commande_pdf(commande, details, request=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
    )
    elements = []
    styles = getSampleStyleSheet()

    # Couleurs de charte
    primary = colors.HexColor('#2A3F54')
    accent = colors.HexColor('#1ABB9C')
    dark_gray = colors.HexColor('#333333')
    light_bg = colors.HexColor('#F7F7F7')

    style_company = ParagraphStyle(
        'CompanyHeader',
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=16,
        textColor=primary,
    )
    style_sub = ParagraphStyle(
        'CompanySub',
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=dark_gray,
    )
    style_title = ParagraphStyle(
        'DocTitle',
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=18,
        textColor=primary,
        alignment=1,
    )
    style_normal = ParagraphStyle(
        'NormalText',
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=dark_gray,
    )
    style_bold = ParagraphStyle(
        'BoldText',
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=dark_gray,
    )

    # 1. En-tête entreprise
    logo_path = os.path.join(settings.MEDIA_ROOT, 'logo', 'logo_ets_la_lumiere.jpg')
    has_logo = os.path.exists(logo_path)

    company_info = [
        Paragraph("<b>ETS LA LUMIÈRE</b>", style_company),
        Paragraph("RCCM : CD/LSH/RCCM/17-A-6183 | Numéro Impôt : A2033591K", style_sub),
        Paragraph("788A, Boulevard M'siri, Q. Industriel, C. Kampemba, Lubumbashi, RDC", style_sub),
        Paragraph("E-mail : info@etslalumiere.cd / adolphechristopher@gmail.com", style_sub),
    ]

    if has_logo:
        try:
            img = RLImage(logo_path, width=2.8 * cm, height=2.2 * cm)
            header_table = Table([[img, company_info]], colWidths=[3.2 * cm, 14.8 * cm])
        except Exception:
            header_table = Table([[company_info]], colWidths=[18.0 * cm])
    else:
        header_table = Table([[company_info]], colWidths=[18.0 * cm])

    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.4 * cm))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=primary, spaceAfter=10))

    # 2. Titre et métadonnées de la commande
    statut_label = commande.get_statut_display().upper()
    elements.append(Paragraph(f"BON DE COMMANDE DE RÉAPPROVISIONNEMENT N° {commande.numero}", style_title))
    elements.append(Spacer(1, 0.3 * cm))

    valide_par_nom = commande.valide_par.username if commande.valide_par else "En attente Direction"
    date_val = commande.date_validation.strftime('%d/%m/%Y à %H:%M:%S') if commande.date_validation else "En attente"

    info_data = [
        [
            Paragraph(f"<b>Date commande :</b> {commande.date_commande.strftime('%d/%m/%Y')}", style_normal),
            Paragraph(f"<b>Statut légal :</b> <font color='{'#1ABB9C' if commande.statut == Commande.VALIDEE else '#d9534f'}'><b>{statut_label}</b></font>", style_normal),
        ],
        [
            Paragraph(f"<b>Émetteur :</b> {commande.cree_par.username}", style_normal),
            Paragraph(f"<b>Visa Direction :</b> {valide_par_nom} ({date_val})", style_normal),
        ],
    ]
    if commande.commentaire_decision:
        info_data.append([
            Paragraph(f"<b>Observation Direction :</b> {commande.commentaire_decision}", style_normal),
            Paragraph("", style_normal),
        ])

    info_table = Table(info_data, colWidths=[9.0 * cm, 9.0 * cm])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), light_bg),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#DDDDDD')),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.5 * cm))

    # 3. Tableau des articles
    table_data = [[
        Paragraph("<b>N°</b>", style_bold),
        Paragraph("<b>Désignation de l'article</b>", style_bold),
        Paragraph("<b>Fournisseur assigné</b>", style_bold),
        Paragraph("<b>Quantité</b>", style_bold),
        Paragraph("<b>Prix unitaire estimé</b>", style_bold),
        Paragraph("<b>Total estimé</b>", style_bold),
    ]]

    total_commande = Decimal('0')
    idx = 1
    for d in details:
        article_nom = d.article.designation if d.article else "Article inconnu"
        fourn_nom = str(d.article.fournisseur) if (d.article and d.article.fournisseur) else "—"
        total_ligne = Decimal(str(d.prix_total))
        total_commande += total_ligne

        table_data.append([
            Paragraph(str(idx), style_normal),
            Paragraph(article_nom, style_normal),
            Paragraph(fourn_nom, style_sub),
            Paragraph(f"{d.qte} {d.article.unite if (d.article and d.article.unite) else ''}", style_normal),
            Paragraph(f"{d.prix:,.2f} FC", style_normal),
            Paragraph(f"{total_ligne:,.2f} FC", style_normal),
        ])
        idx += 1

    table_data.append([
        Paragraph("<b>TOTAL GÉNÉRAL ESTIMÉ</b>", style_bold),
        "", "", "", "",
        Paragraph(f"<b>{total_commande:,.2f} FC</b>", style_bold),
    ])

    col_widths = [1.2 * cm, 6.2 * cm, 4.0 * cm, 2.2 * cm, 2.4 * cm, 2.0 * cm]
    art_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    art_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), primary),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#CCCCCC')),
        ('PADDING', (0, 0), (-1, -1), 5),
        ('SPAN', (0, -1), (4, -1)),
        ('BACKGROUND', (0, -1), (-1, -1), light_bg),
        ('LINEABOVE', (0, -1), (-1, -1), 1.5, primary),
    ]))
    elements.append(art_table)
    elements.append(Spacer(1, 0.8 * cm))

    # 4. Bloc médico-légal des signatures
    sign_data = [
        [
            Paragraph("<b>Signature et Visa de l'Émetteur</b><br/><br/><br/>____________________________<br/>" + commande.cree_par.username, style_normal),
            Paragraph("<b>Visa et Approbation Direction Générale</b><br/><br/><br/>____________________________<br/>" + valide_par_nom, style_normal),
        ]
    ]
    sign_table = Table(sign_data, colWidths=[9.0 * cm, 9.0 * cm])
    sign_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#E0E0E0')),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(sign_table)
    elements.append(Spacer(1, 0.4 * cm))

    # 5. Mention de bas de page médico-légale
    elements.append(Paragraph(
        f"<font size='7' color='#777777'>Document certifié généré par l'ERP ESM — Ets La Lumière le {timezone.now().strftime('%d/%m/%Y à %H:%M:%S')}. "
        "L'intégrité de cette commande de gestion interne est enregistrée dans le journal médico-légal du système.</font>",
        style_sub
    ))

    doc.build(elements)
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="bon_commande_{commande.numero}.pdf"'
    return response
